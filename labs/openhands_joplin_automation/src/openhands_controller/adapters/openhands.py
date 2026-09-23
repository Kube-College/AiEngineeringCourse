"""OpenHands adapter and the durable per-provider-request budget boundary."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import ValidationError

from ..config import Settings
from ..domain.models import Dispatch, IssueKey, RunObservation, Usage
from ..domain.results import ROLE_RESULTS, ReviewResult
from ..domain.states import Role, RunStatus
from ..persistence.budget import Budget
from ..runtime.prompts import build_gateway_llm_config, role_prompt


class CapabilityError(RuntimeError):
    """Live execution is disabled because a required boundary is absent."""


class OpenHandsTransport(Protocol):
    budget_gate_verified: bool

    def create(self, dispatch: Dispatch) -> str: ...
    def start(self, dispatch: Dispatch) -> None: ...
    def status(self, dispatch: Dispatch) -> dict[str, object]: ...
    def pause(self, dispatch: Dispatch) -> None: ...
    def interrupt(self, dispatch: Dispatch) -> None: ...
    def resume(self, dispatch: Dispatch) -> None: ...


class OpenHandsAdapter:
    """Translate private transport state into the controller's stable protocol."""

    per_request_budget = True

    def __init__(self, transport: OpenHandsTransport, *, settings: Settings,
                 clock: Callable[[], datetime]):
        self.transport = transport
        self.settings = settings
        self.clock = clock

    def _require_gate(self) -> None:
        if not self.transport.budget_gate_verified:
            raise CapabilityError("OpenHands request gate is unqualified; live execution disabled")

    def create(self, dispatch: Dispatch) -> str:
        self._require_gate()
        return self.transport.create(dispatch)

    def start(self, dispatch: Dispatch) -> None:
        self._require_gate()
        if self.clock() >= datetime.fromisoformat(dispatch.deadline):
            raise CapabilityError("run deadline passed before start")
        self.transport.start(dispatch)

    def observe(self, dispatch: Dispatch) -> RunObservation:
        try:
            data = self.transport.status(dispatch)
        except Exception as exc:
            return RunObservation(RunStatus.UNKNOWN, error=f"remote status unavailable: {type(exc).__name__}")
        status = data.get("execution_status")
        usage = tuple(Usage.model_validate(entry) for entry in data.get("usage", ()))
        iterations = data.get("iterations")
        if isinstance(iterations, int):
            usage += (Usage(request_id=dispatch.id, iterations=iterations),)
        if status in {"idle", "created"}:
            return RunObservation(RunStatus.CREATED, usage=usage)
        if status == "running":
            return RunObservation(RunStatus.RUNNING, usage=usage)
        if status == "paused":
            return RunObservation(RunStatus.PAUSED, usage=usage)
        if status == "waiting_for_confirmation":
            question = data.get("question") or "Agent requires human input"
            return RunObservation(RunStatus.FAILED, usage=usage, error=f"waiting for input: {question}")
        if status == "finished":
            raw = data.get("result")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except ValueError:
                    raw = None
            try:
                result = ROLE_RESULTS[dispatch.role].model_validate(raw)
            except ValidationError:
                return RunObservation(RunStatus.FAILED, usage=usage, error="invalid role result")
            if isinstance(result, ReviewResult) and result.candidate_sha != dispatch.candidate_sha:
                return RunObservation(RunStatus.FAILED, usage=usage, error="review candidate SHA mismatch")
            return RunObservation(RunStatus.FINISHED, result=result.model_dump(), usage=usage)
        if status in {"error", "stuck"}:
            return RunObservation(RunStatus.FAILED, usage=usage, error=str(data.get("error") or status))
        if status == "missing":
            return RunObservation(RunStatus.MISSING, usage=usage)
        return RunObservation(RunStatus.UNKNOWN, usage=usage, error="unknown remote status")

    def stop(self, dispatch: Dispatch, *, cancel: bool) -> None:
        if cancel:
            self.transport.interrupt(dispatch)
        else:
            self.transport.pause(dispatch)

    def resume(self, dispatch: Dispatch) -> None:
        self._require_gate()
        if self.clock() >= datetime.fromisoformat(dispatch.deadline):
            raise CapabilityError("run deadline passed before resume")
        self.transport.resume(dispatch)


class ModelRequestGate:
    """Reserve each attempt before forwarding one OpenRouter request."""

    MODEL = "openai/gpt-5.6-terra"
    MAX_OUTPUT_TOKENS = 4096
    MAX_INPUT_BYTES = 128_000

    def __init__(self, budget: Budget, dispatch: Dispatch,
                 provider: Callable[[dict[str, object]], tuple[int, dict[str, object]]]):
        self.budget = budget
        self.dispatch = dispatch
        self.provider = provider

    def forward(self, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        if payload.get("model") != self.MODEL or payload.get("stream") is not False:
            raise CapabilityError("unsupported model route or streaming mode")
        caps = [payload[key] for key in ("max_tokens", "max_completion_tokens") if key in payload]
        if (not caps or any(not isinstance(cap, int) or isinstance(cap, bool)
                            or not 1 <= cap <= self.MAX_OUTPUT_TOKENS for cap in caps)):
            raise CapabilityError("output token cap missing or exceeded")
        tokens = max(caps)
        payload = {**payload, "usage": {"include": True}}
        input_bytes = len(json.dumps(payload).encode("utf-8"))
        if input_bytes > self.MAX_INPUT_BYTES:
            raise CapabilityError("input byte cap exceeded")
        estimate = input_bytes * 2 + tokens * 12
        request_id = f"{self.dispatch.id}:model:{uuid4()}"
        if not self.budget.reserve(self.dispatch.issue, request_id, estimate):
            raise CapabilityError("issue budget exhausted or unknown")
        try:
            status, response = self.provider(payload)
        except Exception:
            self.budget.settle(self.dispatch.issue, request_id, None)
            raise
        if status == 429:
            self.budget.settle(self.dispatch.issue, request_id, 0)
            return status, response
        if status < 200 or status >= 300:
            self.budget.settle(self.dispatch.issue, request_id, None)
            return status, response
        usage = response.get("usage")
        if not isinstance(usage, dict):
            self.budget.settle(self.dispatch.issue, request_id, None)
            return 502, {"error": "provider usage unavailable; accounting blocked"}
        reported = usage.get("cost")
        if isinstance(reported, (int, float, str)):
            actual = int(Decimal(str(reported)) * 1_000_000)
        else:
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            if not all(isinstance(item, int) and item >= 0 for item in (prompt, completion)):
                self.budget.settle(self.dispatch.issue, request_id, None)
                return 502, {"error": "provider usage unavailable; accounting blocked"}
            actual = prompt * 2 + completion * 12
        self.budget.settle(self.dispatch.issue, request_id, actual)
        return status, response


class SDKTransport:
    """Pinned OpenHands 1.48 conversation calls behind an active budget gateway."""

    def __init__(self, *, settings: Settings, workspace_factory: Callable[[Dispatch], object],
                 issue_details: Callable[[IssueKey], tuple[str, str]], gateway: object | None,
                 gateway_token: str = ""):
        self.settings = settings
        self.workspace_factory = workspace_factory
        self.issue_details = issue_details
        self.gateway = gateway
        self.gateway_token = gateway_token

    @property
    def budget_gate_verified(self) -> bool:
        return bool(self.gateway and getattr(self.gateway, "active", False) and self.gateway_token)

    @staticmethod
    def _id(dispatch: Dispatch) -> UUID:
        return uuid5(NAMESPACE_URL, f"openhands-joplin:{dispatch.id}")

    def _workspace(self, dispatch: Dispatch):
        return self.workspace_factory(dispatch)

    def _attach(self, dispatch: Dispatch):
        from openhands.sdk import RemoteConversation

        return RemoteConversation.attach(self._workspace(dispatch), self._id(dispatch), visualizer=None)

    def create(self, dispatch: Dispatch) -> str:
        if not self.budget_gate_verified:
            raise CapabilityError("request gate is inactive")
        from openhands.sdk import LLM, RemoteConversation
        from openhands.sdk.conversation.request import StartConversationRequest
        from openhands.sdk.workspace import LocalWorkspace
        from openhands.tools.preset.default import get_default_agent

        workspace = self._workspace(dispatch)
        title, body = self.issue_details(dispatch.issue)
        prompt = role_prompt(dispatch.role, issue_title=title, issue_body=body,
                             candidate_sha=dispatch.candidate_sha)
        config = build_gateway_llm_config(
            self.settings, f"http://host.docker.internal:{self.gateway.port}/api/v1", self.gateway_token,
        )
        request = StartConversationRequest(
            agent=get_default_agent(llm=LLM(**config), cli_mode=True),
            workspace=LocalWorkspace(working_dir=workspace.working_dir),
            conversation_id=self._id(dispatch),
            max_iterations=self.settings.max_iterations,
        )
        conversation = RemoteConversation.create(workspace, request, visualizer=None)
        try:
            conversation.send_message(prompt)
            return str(conversation.id)
        finally:
            conversation.close()

    def start(self, dispatch: Dispatch) -> None:
        conversation = self._attach(dispatch)
        try:
            conversation.run(blocking=False)
        finally:
            conversation.close()

    def status(self, dispatch: Dispatch) -> dict[str, object]:
        from openhands.sdk.event.llm_convertible.message import MessageEvent

        try:
            conversation = self._attach(dispatch)
        except Exception as exc:
            if getattr(getattr(exc, "response", None), "status_code", None) == 404:
                return {"execution_status": "missing"}
            raise
        try:
            state = conversation.state
            state.refresh_from_server()
            status = state.execution_status.value
            result = None
            if status == "finished":
                for event in reversed(list(state.events)):
                    if isinstance(event, MessageEvent) and event.source == "agent":
                        result = "".join(part.text for part in event.llm_message.content if hasattr(part, "text"))
                        break
            return {"execution_status": status, "result": result}
        finally:
            conversation.close()

    def pause(self, dispatch: Dispatch) -> None:
        conversation = self._attach(dispatch)
        try:
            conversation.pause()
        finally:
            conversation.close()

    def interrupt(self, dispatch: Dispatch) -> None:
        conversation = self._attach(dispatch)
        try:
            conversation.interrupt()
        finally:
            conversation.close()

    def resume(self, dispatch: Dispatch) -> None:
        self.start(dispatch)


def run_smoke(settings: Settings, image_digest: str) -> int:
    """Edit one marker through authenticated Docker tools and check the file."""
    import re
    import secrets
    import subprocess
    import tempfile
    import time
    from pathlib import Path

    from openhands.sdk.workspace import RemoteWorkspace
    from ..persistence.store import Store
    from ..runtime.gateway import ModelGatewayServer, openrouter_provider

    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest):
        raise CapabilityError("full immutable Agent Server image digest required")
    image = f"ghcr.io/openhands/agent-server@{image_digest}"
    with tempfile.TemporaryDirectory(prefix="openhands-joplin-smoke-") as temp:
        root = Path(temp)
        volume = root / "volume"
        volume.mkdir(mode=0o700)
        env_file = root / "server.env"
        server_token = secrets.token_urlsafe(32)
        env_file.write_text(f"SESSION_API_KEY={server_token}\nOH_PERSISTENCE_DIR=/workspace/.openhands\n")
        env_file.chmod(0o600)
        store = Store(root / "controller.sqlite")
        issue = ("local/smoke", 1)
        store.create_workflow(issue, "smoke", budget_limit=min(settings.issue_budget_microusd, 500_000),
                              title="Local OpenHands tool smoke",
                              body="Write exactly the text MARKER_OK to /workspace/marker.txt using file tools.")
        dispatch = Dispatch("local-smoke", issue, "smoke", Role.IMPLEMENTATION, 1,
                            "local-smoke", None, None,
                            (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat())
        gateway_token = secrets.token_urlsafe(32)
        provider = openrouter_provider(settings.llm_api_key.get_secret_value())
        gate = ModelRequestGate(Budget(store), dispatch, provider)
        container_id = None
        with ModelGatewayServer(gate, token=gateway_token, bind_host="0.0.0.0") as gateway:
            try:
                run = subprocess.run([
                    "docker", "run", "-d", "--rm", "--name", f"openhands-joplin-smoke-{uuid4().hex[:12]}",
                    "--publish", "127.0.0.1::8000", "--mount",
                    f"type=bind,source={volume},target=/workspace", "--env-file", str(env_file),
                    image, "--host", "0.0.0.0", "--port", "8000",
                ], capture_output=True, text=True, timeout=90, check=True)
                container_id = run.stdout.strip()
                port_result = subprocess.run(["docker", "port", container_id, "8000/tcp"],
                                             capture_output=True, text=True, timeout=15, check=True)
                port = int(port_result.stdout.strip().rsplit(":", 1)[1])
                workspace = RemoteWorkspace(host=f"http://127.0.0.1:{port}", api_key=server_token,
                                            working_dir="/workspace")
                for _ in range(60):
                    try:
                        workspace.get_server_info()
                        break
                    except Exception:
                        time.sleep(1)
                else:
                    raise CapabilityError("Agent Server did not become ready")
                transport = SDKTransport(settings=settings.model_copy(update={"max_iterations": 8}),
                                         workspace_factory=lambda _: workspace,
                                         issue_details=lambda _: ("Local OpenHands tool smoke",
                                                                  "Write exactly MARKER_OK to /workspace/marker.txt."),
                                         gateway=gateway, gateway_token=gateway_token)
                adapter = OpenHandsAdapter(transport, settings=settings, clock=lambda: datetime.now(timezone.utc))
                conversation_id = adapter.create(dispatch)
                running = Dispatch(**{**dispatch.__dict__, "conversation_id": conversation_id})
                adapter.start(running)
                for _ in range(150):
                    observed = adapter.observe(running)
                    if observed.status in {RunStatus.FINISHED, RunStatus.FAILED, RunStatus.UNKNOWN}:
                        break
                    time.sleep(2)
                else:
                    adapter.stop(running, cancel=True)
                    raise CapabilityError("smoke run timed out")
                marker = volume / "marker.txt"
                if observed.status is not RunStatus.FINISHED or not marker.is_file() or marker.read_text().strip() != "MARKER_OK":
                    raise CapabilityError("smoke did not produce the required filesystem marker")
                snapshot = Budget(store).snapshot(issue)
                print(f"model={settings.llm_model} provider=OpenRouter image={image_digest} "
                      f"conversation={conversation_id} marker=verified actual_microusd={snapshot.actual_microusd} "
                      f"unknown={snapshot.unknown}")
                return 0
            finally:
                if container_id:
                    subprocess.run(["docker", "rm", "-f", container_id], capture_output=True,
                                   text=True, timeout=30, check=False)
