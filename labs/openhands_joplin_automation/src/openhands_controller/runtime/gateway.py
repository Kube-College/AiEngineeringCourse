"""Authenticated HTTP boundary for each OpenRouter model attempt."""

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..adapters.openhands import CapabilityError, ModelRequestGate


def openrouter_provider(api_key: str) -> Callable[[dict[str, object]], tuple[int, dict[str, object]]]:
    """Forward one non-streaming completion; the gate owns retries and accounting."""
    def call(payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        request = Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            # The body may contain provider details; it is never logged here.
            try:
                body = json.load(exc)
            except (ValueError, OSError):
                body = {"error": "provider error"}
            return exc.code, body

    return call


class ModelGatewayServer:
    """Expose a dispatch's budget gate over authenticated HTTP."""

    def __init__(self, gate: ModelRequestGate, *, token: str, bind_host: str, port: int = 0):
        if not token or not bind_host:
            raise ValueError("gateway token and bind host are required")
        self.gate = gate
        self._token = token
        self._server = ThreadingHTTPServer((bind_host, port), self._handler())
        self._thread: Thread | None = None

    @property
    def port(self) -> int:
        return self._server.server_port

    @property
    def active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _handler(self):
        gate, token = self.gate, self._token

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_POST(self):
                supplied = self.headers.get("Authorization", "")
                if not hmac.compare_digest(supplied, f"Bearer {token}"):
                    self._send(401, {"error": "unauthorised"})
                    return
                if self.path != "/api/v1/chat/completions":
                    self._send(404, {"error": "unsupported route"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= gate.MAX_INPUT_BYTES:
                        raise ValueError("request too large or empty")
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError("JSON object required")
                    status, result = gate.forward(body)
                except (ValueError, CapabilityError) as exc:
                    self._send(402, {"error": str(exc)})
                    return
                except Exception:
                    self._send(502, {"error": "provider outcome uncertain; accounting blocked"})
                    return
                self._send(status, result)

            def _send(self, status: int, payload: dict[str, object]):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def __enter__(self):
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
