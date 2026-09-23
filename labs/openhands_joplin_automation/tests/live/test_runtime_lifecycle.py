"""Opt-in Docker checks for saved workspace and conversation continuity."""

import os
from datetime import datetime, timedelta, timezone

import pytest

from openhands_controller.adapters.openhands import ModelRequestGate, OpenHandsAdapter, SDKTransport
from openhands_controller.config import Settings
from openhands_controller.domain.models import Dispatch
from openhands_controller.domain.states import DispatchStatus, Role, RunStatus
from openhands_controller.persistence.budget import Budget
from openhands_controller.persistence.store import Store
from openhands_controller.runtime.gateway import ModelGatewayServer
from openhands_controller.runtime.workspaces import DockerCLI, WorkspaceManager


pytestmark = pytest.mark.live


def test_marker_and_conversation_survive_container_recreation(tmp_path):
    if os.environ.get("RUN_OPENHANDS_LIVE") != "1" or not os.environ.get("OPENHANDS_IMAGE_DIGEST"):
        pytest.skip("set RUN_OPENHANDS_LIVE=1 and OPENHANDS_IMAGE_DIGEST for Docker qualification")
    image_digest = os.environ["OPENHANDS_IMAGE_DIGEST"]
    store = Store(tmp_path / "state.sqlite")
    issue = ("local/qualification", 1)
    store.create_workflow(issue, "r1", budget_limit=500_000, title="Persistence marker",
                          body="Keep the marker in the mounted workspace")
    token = "local-qualification-server-token"
    manager = WorkspaceManager(store, tmp_path / "workspaces", docker=DockerCLI(), server_token=token)
    workspace_id = manager.ensure(issue, "a" * 40, image_digest)
    dispatch = Dispatch("qualification-triage", issue, "r1", Role.TRIAGE, 1, workspace_id, None, None,
                        (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat())
    store.create_dispatch(dispatch)
    called = []

    def unexpected_provider_call(payload):
        called.append(payload)
        raise AssertionError("no model request is needed for persistence qualification")

    gate = ModelRequestGate(Budget(store), dispatch, unexpected_provider_call)
    settings = Settings(_env_file=None, llm_api_key="dummy-model-key")
    with ModelGatewayServer(gate, token="local-gateway-token", bind_host="127.0.0.1") as gateway:
        transport = SDKTransport(settings=settings, workspace_factory=lambda d: manager.connect(d.workspace_id),
                                 issue_details=lambda _: ("Persistence marker", "Inspect the workspace"),
                                 gateway=gateway, gateway_token="local-gateway-token")
        adapter = OpenHandsAdapter(transport, settings=settings, clock=lambda: datetime.now(timezone.utc))
        conversation_id = adapter.create(dispatch)
        store.update_dispatch(dispatch.id, status=DispatchStatus.CREATED, conversation_id=conversation_id)
        active = store.dispatches(issue)[0].dispatch
        assert adapter.observe(active).status is RunStatus.CREATED
        adapter.stop(active, cancel=False)
        assert adapter.observe(active).status is RunStatus.PAUSED
        workspace = manager.connect(workspace_id)
        assert workspace.execute_command("printf MARKER_OK > /workspace/marker.txt").exit_code == 0
        manager.stop(workspace_id)
        restarted = WorkspaceManager(Store(store.path), manager.root, docker=DockerCLI(), server_token=token)
        restarted.reattach(workspace_id)
        manager = restarted
        assert (manager.root / workspace_id / "marker.txt").read_text() == "MARKER_OK"
        assert adapter.observe(active).status is RunStatus.PAUSED
        assert len(store.dispatches(issue)) == 1
        assert called == []
        manager.stop(workspace_id)
