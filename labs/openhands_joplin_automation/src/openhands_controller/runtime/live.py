"""Compose the qualified OpenHands adapter for one active agent dispatch."""

import json
import os
import secrets
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..adapters.openhands import ModelRequestGate, OpenHandsAdapter, SDKTransport
from ..config import Settings
from ..domain.models import Dispatch, RunObservation
from ..persistence.budget import Budget
from ..persistence.store import Store
from .gateway import ModelGatewayServer, openrouter_provider
from .agents import resolve_model
from .workspaces import WorkspaceManager


def load_runtime_tokens(state_dir: Path) -> tuple[str, str]:
    """Keep Agent Server and gateway auth stable across controller restarts."""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "runtime-auth.json"
    if not path.exists():
        value = {"server_token": secrets.token_urlsafe(32), "gateway_token": secrets.token_urlsafe(32)}
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as output:
                json.dump(value, output)
    if not path.is_file() or path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("runtime auth file must be a private regular file")
    saved = json.loads(path.read_text())
    if not all(isinstance(saved.get(key), str) and saved[key] for key in ("server_token", "gateway_token")):
        raise ValueError("runtime auth file is invalid")
    return saved["server_token"], saved["gateway_token"]


class LiveTriageAgent:
    """One active Docker workspace, conversation and metered model gateway."""

    per_request_budget = True

    def __init__(self, store: Store, settings: Settings, manager: WorkspaceManager,
                 *, base_sha: str, image_digest: str, gateway_token: str, gateway_port: int,
                 gateway_factory: Callable = ModelGatewayServer,
                 transport_factory: Callable = SDKTransport):
        self.store, self.settings, self.manager = store, settings, manager
        self.base_sha, self.image_digest = base_sha, image_digest
        self.gateway_token, self.gateway_port = gateway_token, gateway_port
        self.gateway_factory, self.transport_factory = gateway_factory, transport_factory
        self._current_id: str | None = None
        self._gateway = None
        self._adapter: OpenHandsAdapter | None = None

    def _for(self, dispatch: Dispatch) -> OpenHandsAdapter:
        if self._current_id == dispatch.id and self._adapter is not None:
            return self._adapter
        self.close()
        actual_id = self.manager.ensure(dispatch.issue, self.base_sha, self.image_digest)
        if actual_id != dispatch.workspace_id:
            raise ValueError("dispatch workspace identity differs from persistent workspace")
        gate = ModelRequestGate(
            Budget(self.store), dispatch,
            openrouter_provider(self.settings.llm_api_key.get_secret_value()),
            model_route=resolve_model(dispatch.role, self.settings),
        )
        gateway = self.gateway_factory(gate, token=self.gateway_token,
                                       bind_host="127.0.0.1", port=self.gateway_port)
        gateway.__enter__()
        try:
            transport = self.transport_factory(
                settings=self.settings, workspace_factory=lambda d: self.manager.connect(d.workspace_id),
                issue_details=lambda issue: (self.store.workflow(issue).title, self.store.workflow(issue).body),
                gateway=gateway, gateway_token=self.gateway_token,
                workspace_stop=self.manager.stop,
                workspace_status=lambda identifier: str(self.manager.record(identifier)["status"]),
            )
            self._adapter = OpenHandsAdapter(transport, settings=self.settings,
                                             clock=lambda: datetime.now(timezone.utc))
            self._gateway = gateway
            self._current_id = dispatch.id
            return self._adapter
        except BaseException:
            gateway.__exit__(None, None, None)
            raise

    def create(self, dispatch: Dispatch) -> str:
        return self._for(dispatch).create(dispatch)

    def start(self, dispatch: Dispatch) -> None:
        self._for(dispatch).start(dispatch)

    def observe(self, dispatch: Dispatch) -> RunObservation:
        return self._for(dispatch).observe(dispatch)

    def stop(self, dispatch: Dispatch, *, cancel: bool) -> None:
        self._for(dispatch).stop(dispatch, cancel=cancel)

    def resume(self, dispatch: Dispatch) -> None:
        self._for(dispatch).resume(dispatch)

    def close(self) -> None:
        if self._gateway is not None:
            self._gateway.__exit__(None, None, None)
        self._gateway = None
        self._adapter = None
        self._current_id = None
