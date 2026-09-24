from datetime import datetime, timedelta, timezone
from dataclasses import replace
from decimal import Decimal
from http.client import HTTPConnection
import json

import pytest

from openhands_controller.adapters.openhands import (
    CapabilityError, ModelRequestGate, OpenHandsAdapter, SDKTransport,
)
from openhands_controller.config import Settings
from openhands_controller.domain.models import Dispatch
from openhands_controller.domain.states import Role, RunStatus
from openhands_controller.persistence.budget import Budget
from openhands_controller.persistence.store import Store
from openhands_controller.runtime.gateway import ModelGatewayServer
from openhands_controller.runtime.agents import AGENTS


class ScriptedTransport:
    budget_gate_verified = True

    def __init__(self):
        self.created = []
        self.statuses = []
        self.create_error = None
        self.stopped = []
        self.forced = []

    def create(self, dispatch):
        self.created.append(dispatch.id)
        if self.create_error:
            raise self.create_error
        return "conversation-1"

    def start(self, dispatch):
        self.started = dispatch.id

    def status(self, dispatch):
        return self.statuses.pop(0) if self.statuses else {"execution_status": "paused"}

    def pause(self, dispatch):
        self.stopped.append((dispatch.id, "pause"))

    def interrupt(self, dispatch):
        self.stopped.append((dispatch.id, "interrupt"))

    def resume(self, dispatch):
        self.resumed = dispatch.id

    def force_stop(self, dispatch):
        self.forced.append(dispatch.workspace_id)


@pytest.fixture
def fixture(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    issue = ("demo/joplin", 1)
    store.create_workflow(issue, "r1", budget_limit=100_000)
    dispatch = Dispatch("d1", issue, "r1", Role.REVIEW, 1, "w1", "conversation-1", "abc123",
                        (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat())
    store.create_dispatch(dispatch)
    store.update_dispatch(dispatch.id, status="running")
    transport = ScriptedTransport()
    adapter = OpenHandsAdapter(transport, settings=Settings(_env_file=None), clock=lambda: datetime.now(timezone.utc))
    return store, dispatch, transport, adapter


def test_create_response_loss_is_not_retried(fixture):
    _, dispatch, transport, adapter = fixture
    transport.create_error = TimeoutError("response lost")
    with pytest.raises(TimeoutError):
        adapter.create(dispatch)
    assert transport.created == ["d1"]


def test_terminal_text_without_strict_result_fails(fixture):
    _, dispatch, transport, adapter = fixture
    transport.statuses = [{"execution_status": "finished", "result": "Done"}]
    observation = adapter.observe(dispatch)
    assert observation.status is RunStatus.FAILED
    assert "invalid role result" in observation.error


def test_waiting_for_input_becomes_human_handoff(fixture):
    _, dispatch, transport, adapter = fixture
    transport.statuses = [{"execution_status": "waiting_for_confirmation", "question": "May I delete this?"}]
    observation = adapter.observe(dispatch)
    assert observation.status is RunStatus.FAILED
    assert "May I delete this?" in observation.error


def test_review_result_requires_exact_candidate_sha(fixture):
    _, dispatch, transport, adapter = fixture
    transport.statuses = [{"execution_status": "finished", "result": {
        "candidate_sha": "wrong", "verdict": "pass", "findings": []}}]
    assert adapter.observe(dispatch).status is RunStatus.FAILED


def test_timeout_requests_interrupt(fixture):
    _, dispatch, transport, adapter = fixture
    expired = Dispatch(**{**dispatch.__dict__, "deadline": "2020-01-01T00:00:00+00:00"})
    transport.statuses = [{"execution_status": "running"}]
    assert adapter.observe(expired).status is RunStatus.RUNNING
    adapter.stop(expired, cancel=True)
    assert transport.stopped == [("d1", "interrupt")]


def test_live_transport_without_request_gate_fails_closed(fixture):
    _, dispatch, transport, _ = fixture
    transport.budget_gate_verified = False
    adapter = OpenHandsAdapter(transport, settings=Settings(_env_file=None),
                               clock=lambda: datetime.now(timezone.utc))
    with pytest.raises(CapabilityError, match="request gate"):
        adapter.create(dispatch)
    assert transport.created == []


def test_retry_is_budgeted(fixture):
    store, dispatch, _, _ = fixture
    budget = Budget(store)
    responses = [(429, {}), (200, {"usage": {"prompt_tokens": 1000, "completion_tokens": 200}})]
    model_calls = []

    def provider(payload):
        model_calls.append(payload)
        return responses.pop(0)

    gate = ModelRequestGate(budget, dispatch, provider)
    request = {"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "Hello"}],
               "max_tokens": 1000, "stream": False}
    assert gate.forward(request)[0] == 429
    assert gate.forward(request)[0] == 200
    with store.connection() as db:
        records = db.execute("SELECT status FROM usage WHERE repo=? AND issue_number=?", dispatch.issue).fetchall()
    assert len(model_calls) <= len(records)
    assert all(record["status"] == "settled" for record in records)


def test_ambiguous_provider_failure_blocks_next_request(fixture):
    store, dispatch, _, _ = fixture
    calls = []

    def provider(payload):
        calls.append(payload)
        raise TimeoutError("provider response lost")

    gate = ModelRequestGate(Budget(store), dispatch, provider)
    request = {"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "Hi"}],
               "max_tokens": 1000, "stream": False}
    with pytest.raises(TimeoutError):
        gate.forward(request)
    with pytest.raises(CapabilityError, match="budget"):
        gate.forward(request)
    assert len(calls) == 1


def test_gateway_accepts_chat_completion_token_field_and_requests_cost(fixture):
    store, dispatch, _, _ = fixture
    sent = []

    def provider(payload):
        sent.append(payload)
        return 200, {"usage": {"cost": 0.0044, "prompt_tokens": 1000, "completion_tokens": 200}}

    gate = ModelRequestGate(Budget(store), dispatch, provider)
    status, _ = gate.forward({"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "Hi"}],
                              "max_completion_tokens": 1000, "stream": False})
    assert status == 200
    assert sent[0]["usage"] == {"include": True}
    assert Budget(store).snapshot(dispatch.issue).actual_microusd == 4400


def test_custom_model_gate_allows_only_its_route_and_uses_reported_cost(fixture):
    from openhands_controller.runtime.agents import ModelRoute
    store, dispatch, _, _ = fixture
    route = ModelRoute("example/reviewer", Decimal("3"), Decimal("7"))
    calls = []

    def provider(payload):
        calls.append(payload)
        return 200, {"usage": {"cost": "0.000027", "prompt_tokens": 2, "completion_tokens": 3}}

    gate = ModelRequestGate(Budget(store), dispatch, provider, model_route=route)
    request = {"model": route.name, "messages": [{"role": "user", "content": "Hi"}],
               "max_tokens": 1000, "stream": False}
    with pytest.raises(CapabilityError, match="unsupported model route"):
        gate.forward({**request, "model": "openai/gpt-5.6-terra"})
    assert calls == []

    assert gate.forward(request)[0] == 200
    snapshot = Budget(store).snapshot(dispatch.issue)
    assert snapshot.estimated_microusd >= 7000
    assert snapshot.actual_microusd == 27
    assert calls[0]["model"] == "example/reviewer"


def test_custom_model_without_reported_cost_blocks_further_requests(fixture):
    from openhands_controller.runtime.agents import ModelRoute
    store, dispatch, _, _ = fixture
    route = ModelRoute("example/reviewer", Decimal("3"), Decimal("7"))
    gate = ModelRequestGate(Budget(store), dispatch,
                            lambda _: (200, {"usage": {"prompt_tokens": 2, "completion_tokens": 3}}),
                            model_route=route)
    request = {"model": route.name, "messages": [{"role": "user", "content": "Hi"}],
               "max_tokens": 1000, "stream": False}

    assert gate.forward(request)[0] == 502
    assert Budget(store).snapshot(dispatch.issue).unknown is True
    with pytest.raises(CapabilityError, match="budget"):
        gate.forward(request)


def test_gateway_defaults_omitted_stream_to_nonstreaming(fixture):
    store, dispatch, _, _ = fixture
    sent = []

    def provider(payload):
        sent.append(payload)
        return 200, {"usage": {"prompt_tokens": 2, "completion_tokens": 3}}

    gate = ModelRequestGate(Budget(store), dispatch, provider)
    request = {"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "Hi"}],
               "max_tokens": 1000}
    assert gate.forward(request)[0] == 200
    assert sent[0]["stream"] is False
    with pytest.raises(CapabilityError, match="streaming"):
        gate.forward({**request, "stream": True})
    assert len(sent) == 1


def test_http_gateway_requires_token_and_budgets_authorised_request(fixture):
    store, dispatch, _, _ = fixture
    called = []

    def provider(payload):
        called.append(payload)
        return 200, {"usage": {"prompt_tokens": 2, "completion_tokens": 3}}

    gate = ModelRequestGate(Budget(store), dispatch, provider)
    with ModelGatewayServer(gate, token="gateway-secret", bind_host="127.0.0.1") as server:
        connection = HTTPConnection("127.0.0.1", server.port)
        body = json.dumps({"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "Hi"}],
                           "max_tokens": 1000, "stream": False})
        connection.request("POST", "/api/v1/chat/completions", body=body,
                           headers={"Content-Type": "application/json"})
        assert connection.getresponse().status == 401
        assert called == []
        connection.request("POST", "/api/v1/chat/completions", body=body,
                           headers={"Content-Type": "application/json", "Authorization": "Bearer gateway-secret"})
        assert connection.getresponse().status == 200
        assert len(called) == 1
        connection.close()


def test_http_gateway_allows_bounded_large_context_and_rejects_excess(fixture):
    store, dispatch, _, _ = fixture
    Budget(store).increase(dispatch.issue, 1_000_000, "larger-context-budget")
    calls = []

    def provider(payload):
        calls.append(payload)
        return 200, {"usage": {"cost": "0.001"}}

    gate = ModelRequestGate(Budget(store), dispatch, provider)
    with ModelGatewayServer(gate, token="gateway-secret", bind_host="127.0.0.1") as server:
        connection = HTTPConnection("127.0.0.1", server.port)
        headers = {"Content-Type": "application/json", "Authorization": "Bearer gateway-secret"}
        request = {"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "x" * 150_000}],
                   "max_tokens": 1000, "stream": False}
        connection.request("POST", "/api/v1/chat/completions", body=json.dumps(request), headers=headers)
        assert connection.getresponse().status == 200
        assert len(calls) == 1

        request["messages"][0]["content"] = "x" * 270_000
        connection.request("POST", "/api/v1/chat/completions", body=json.dumps(request), headers=headers)
        assert connection.getresponse().status == 402
        assert len(calls) == 1
        connection.close()


def test_sdk_transport_refuses_inactive_gateway(fixture):
    _, dispatch, _, _ = fixture
    transport = SDKTransport(settings=Settings(_env_file=None, llm_api_key="dummy"),
                             workspace_factory=lambda _dispatch: object(),
                             issue_details=lambda _issue: ("title", "body"), gateway=None)
    adapter = OpenHandsAdapter(transport, settings=Settings(_env_file=None),
                               clock=lambda: datetime.now(timezone.utc))
    with pytest.raises(CapabilityError, match="request gate"):
        adapter.create(dispatch)


def test_sdk_transport_requires_owned_stop_hooks():
    gateway = type("Gateway", (), {"active": True, "port": 54321})()
    transport = SDKTransport(settings=Settings(_env_file=None), workspace_factory=lambda _: object(),
                             issue_details=lambda _: ("title", "body"), gateway=gateway,
                             gateway_token="token")
    assert transport.budget_gate_verified is False


def test_sdk_create_queues_prompt_without_starting_model(fixture, monkeypatch):
    from openhands_controller.runtime.agents import ModelRoute
    sdk = pytest.importorskip("openhands.sdk")
    from openhands.sdk.workspace import RemoteWorkspace

    _, dispatch, _, _ = fixture
    route = ModelRoute("example/reviewer", Decimal("3"), Decimal("7"))
    monkeypatch.setitem(AGENTS, Role.REVIEW, replace(AGENTS[Role.REVIEW], model=route))
    received = []

    class Conversation:
        id = "conversation-1"

        def send_message(self, message):
            received.append(("message", message))

        def close(self):
            pass

    def create(_cls, _workspace, request, **_kwargs):
        received.append(("initial", request.initial_message))
        received.append(("agent", request.agent))
        return Conversation()

    monkeypatch.setattr(sdk.RemoteConversation, "create", classmethod(create))
    gateway = type("Gateway", (), {"active": True, "port": 54321})()
    transport = SDKTransport(settings=Settings(_env_file=None, llm_api_key="dummy"),
                             workspace_factory=lambda _: RemoteWorkspace(host="http://127.0.0.1:8010",
                                                                          api_key="local", working_dir="/workspace"),
                             issue_details=lambda _: ("Title", "Body"), gateway=gateway,
                             gateway_token="gateway-dummy", workspace_stop=lambda _: None,
                             workspace_status=lambda _: "ready")
    transport.create(dispatch)
    assert received[0] == ("initial", None)
    assert received[1][0] == "agent"
    assert [tool.name for tool in received[1][1].tools] == ["terminal"]
    assert received[1][1].llm.model == "openrouter/example/reviewer"
    assert "candidate SHA" in received[1][1].agent_context.system_message_suffix
    assert received[2][0] == "message"
    assert "Role: review" in received[2][1]


def test_finish_action_is_terminal_result():
    from openhands.sdk.event.llm_convertible.action import ActionEvent
    from openhands.sdk.tool.builtins.finish import FinishAction

    result = '{"candidate_sha":"abc123","verdict":"pass","findings":[]}'
    event = ActionEvent.model_construct(source="agent", action=FinishAction(message=result))
    assert SDKTransport.final_result([event]) == result


@pytest.mark.parametrize("response", [
    {"usage": {"cost": "not-a-cost"}},
    {"usage": {"cost": "NaN"}},
    {"usage": {"cost": -1}},
    ["unexpected response"],
])
def test_bad_billing_response_blocks_followup(fixture, response):
    store, dispatch, _, _ = fixture
    calls = []

    def provider(payload):
        calls.append(payload)
        return 200, response

    gate = ModelRequestGate(Budget(store), dispatch, provider)
    request = {"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "Hi"}],
               "max_tokens": 1000, "stream": False}
    assert gate.forward(request)[0] == 502
    assert Budget(store).snapshot(dispatch.issue).unknown is True
    with pytest.raises(CapabilityError):
        gate.forward(request)
    assert len(calls) == 1


def test_gate_recovery_marks_abandoned_reservation_unknown(fixture):
    store, dispatch, _, _ = fixture
    budget = Budget(store)
    assert budget.reserve(dispatch.issue, "abandoned", 1000)
    ModelRequestGate(budget, dispatch, lambda _: (200, {}))
    assert budget.snapshot(dispatch.issue).unknown is True


def test_gate_rejects_expired_and_stopped_dispatches(fixture):
    store, dispatch, _, _ = fixture
    calls = []
    request = {"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "Hi"}],
               "max_tokens": 1000, "stream": False}
    expired = Dispatch(**{**dispatch.__dict__, "deadline": "2020-01-01T00:00:00+00:00"})
    gate = ModelRequestGate(Budget(store), expired, lambda payload: calls.append(payload) or (200, {}))
    with pytest.raises(CapabilityError, match="authorised"):
        gate.forward(request)
    row = store.workflow(dispatch.issue)
    store.cas_workflow(dispatch.issue, row.version, stop_requested="cancel")
    gate = ModelRequestGate(Budget(store), dispatch, lambda payload: calls.append(payload) or (200, {}))
    with pytest.raises(CapabilityError, match="authorised"):
        gate.forward(request)
    assert calls == []


def test_gate_rejects_superseded_and_paused_dispatches(fixture):
    store, dispatch, _, _ = fixture
    calls = []
    request = {"model": "openai/gpt-5.6-terra", "messages": [{"role": "user", "content": "Hi"}],
               "max_tokens": 1000, "stream": False}
    gate = ModelRequestGate(Budget(store), dispatch, lambda payload: calls.append(payload) or (200, {}))
    row = store.workflow(dispatch.issue)
    store.cas_workflow(dispatch.issue, row.version, revision="r2")
    with pytest.raises(CapabilityError, match="authorised"):
        gate.forward(request)
    row = store.workflow(dispatch.issue)
    store.cas_workflow(dispatch.issue, row.version, revision="r1")
    store.update_dispatch(dispatch.id, status="paused")
    with pytest.raises(CapabilityError, match="authorised"):
        gate.forward(request)
    assert calls == []


def test_unresponsive_stop_forces_owned_workspace(fixture):
    _, dispatch, transport, adapter = fixture
    transport.statuses = [{"execution_status": "running"}]
    adapter.stop(dispatch, cancel=True)
    assert transport.stopped == [("d1", "interrupt")]
    assert transport.forced == ["w1"]


def test_failed_sdk_stop_forces_owned_workspace(fixture):
    _, dispatch, transport, adapter = fixture
    transport.interrupt = lambda _: (_ for _ in ()).throw(TimeoutError("server unresponsive"))
    adapter.stop(dispatch, cancel=True)
    assert transport.forced == ["w1"]


def test_sdk_status_reports_stopped_workspace_without_recreation(fixture):
    _, dispatch, _, _ = fixture
    transport = SDKTransport(settings=Settings(_env_file=None),
                             workspace_factory=lambda _: pytest.fail("recreated stopped workspace"),
                             issue_details=lambda _: ("title", "body"), gateway=None,
                             workspace_status=lambda _: "stopped")
    assert transport.status(dispatch) == {"execution_status": "missing"}
