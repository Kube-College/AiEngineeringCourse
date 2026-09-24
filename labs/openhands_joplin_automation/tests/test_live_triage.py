"""Live triage composition without Docker or provider calls."""

import json
import stat
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from openhands_controller.config import Settings
from openhands_controller.domain.models import Dispatch
from openhands_controller.domain.states import Role
from openhands_controller.persistence.store import Store
from openhands_controller.runtime.agents import AGENTS, ModelRoute
from openhands_controller.runtime.live import LiveTriageAgent, load_runtime_tokens
from openhands_controller.runtime.prompts import role_prompt


NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)


class FakeManager:
    def __init__(self):
        self.ensured = []

    def identifier(self, issue):
        return f"stable-{issue[1]}"

    def ensure(self, issue, base_sha, image_digest):
        self.ensured.append((issue, base_sha, image_digest))
        return self.identifier(issue)

    def connect(self, identifier):
        assert identifier == "stable-2"
        return object()

    def stop(self, identifier):
        pass

    def record(self, identifier):
        return {"status": "ready"}


class FakeGateway:
    def __init__(self, gate, *, token, bind_host, port):
        assert token == "gateway-secret"
        assert bind_host == "127.0.0.1"
        self.port = port
        self.gate = gate
        self.active = False

    def __enter__(self):
        self.active = True
        return self

    def __exit__(self, *args):
        self.active = False


class FakeTransport:
    def __init__(self, **kwargs):
        assert kwargs["gateway"].active
        self.budget_gate_verified = True

    def create(self, dispatch):
        return "conversation-id"

    def start(self, dispatch):
        pass

    def status(self, dispatch):
        return {"execution_status": "running"}


def test_live_agent_uses_pinned_workspace_and_active_budget_gateway(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    issue = ("lspinheiro/joplin", 2)
    store.create_workflow(issue, "revision", budget_limit=5_000_000)
    dispatch = Dispatch("dispatch-2", issue, "revision", Role.TRIAGE, 1, "stable-2", None,
                        None, (NOW + timedelta(minutes=20)).isoformat())
    store.create_dispatch(dispatch)
    manager = FakeManager()
    agent = LiveTriageAgent(
        store, Settings(_env_file=None, agent_backend="openhands", llm_api_key="model-key"),
        manager, base_sha="a" * 40, image_digest="sha256:" + "b" * 64,
        gateway_token="gateway-secret", gateway_port=18301,
        gateway_factory=FakeGateway, transport_factory=FakeTransport,
    )
    try:
        assert agent.create(dispatch) == "conversation-id"
        assert manager.ensured == [(issue, "a" * 40, "sha256:" + "b" * 64)]
        assert agent.observe(dispatch).status == "running"
    finally:
        agent.close()


def test_live_agent_passes_review_model_to_budget_gateway(tmp_path, monkeypatch):
    route = ModelRoute("example/reviewer", Decimal("3"), Decimal("7"))
    monkeypatch.setitem(AGENTS, Role.REVIEW, replace(AGENTS[Role.REVIEW], model=route))
    store = Store(tmp_path / "state.sqlite")
    issue = ("lspinheiro/joplin", 2)
    store.create_workflow(issue, "revision", budget_limit=5_000_000)
    dispatch = Dispatch("dispatch-2", issue, "revision", Role.REVIEW, 1, "stable-2", None,
                        "a" * 40, (NOW + timedelta(minutes=20)).isoformat())
    store.create_dispatch(dispatch)
    agent = LiveTriageAgent(
        store, Settings(_env_file=None, agent_backend="openhands", llm_api_key="model-key"),
        FakeManager(), base_sha="a" * 40, image_digest="sha256:" + "b" * 64,
        gateway_token="gateway-secret", gateway_port=18301,
        gateway_factory=FakeGateway, transport_factory=FakeTransport,
    )
    try:
        agent.create(dispatch)
        assert agent._gateway.gate.model_route == route
    finally:
        agent.close()


def test_runtime_tokens_survive_restart_with_private_file(tmp_path):
    first = load_runtime_tokens(tmp_path)
    assert first == load_runtime_tokens(tmp_path)
    assert first[0] != first[1]
    path = tmp_path / "runtime-auth.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["server_token"] == first[0]


def test_triage_task_message_contains_issue_and_result_contract():
    prompt = role_prompt(Role.TRIAGE, issue_title="Broken title", issue_body="Steps")
    assert "Broken title" in prompt
    assert "Steps" in prompt
    assert "validation_profile" in prompt
    assert "Do not implement" not in prompt
