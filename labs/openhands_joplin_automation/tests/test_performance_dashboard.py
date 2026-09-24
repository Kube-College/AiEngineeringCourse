"""A local viewer reports evidence without exposing agent authority."""

from openhands_controller.domain.models import Dispatch
from openhands_controller.persistence.budget import Budget
from openhands_controller.persistence.store import Store


ISSUE = ("demo/joplin", 17)


def _record_run(path):
    store = Store(path)
    store.create_workflow(ISSUE, "r1", budget_limit=5_000_000,
                          title="Focus <script>secret</script>")
    dispatch = Dispatch("run-17", ISSUE, "r1", "triage", 1,
                        "workspace-17", "conversation-17", None, "2026-09-24T12:00:00+00:00")
    store.create_dispatch(dispatch, model="openai/gpt-5.6-terra", profile_hash="abc123")
    store.update_dispatch(dispatch.id, status="running", iterations=3)
    workflow = store.workflow(ISSUE)
    store.transition_dispatch(dispatch.id, ISSUE, workflow.version, "awaiting-approval", "finished",
                              '{"scope":"desktop","summary":"Investigate focus","validation_profile":"desktop"}')
    store.rate_dispatch(dispatch.id, "partly-useful", "Needs a reproduction")
    budget = Budget(store)
    budget.reserve(ISSUE, "run-17:model:one", 100_000)
    budget.settle(ISSUE, "run-17:model:one", 75_000)
    budget.reserve(ISSUE, "run-17:model:two", 100_000)
    budget.settle(ISSUE, "run-17:model:two", None)


def test_reader_keeps_completion_cost_uncertainty_and_human_quality_separate(tmp_path):
    from openhands_controller.performance import PerformanceReader

    path = tmp_path / "state.sqlite"
    _record_run(path)
    reader = PerformanceReader(path)
    run = reader.runs()[0]
    assert (run["role"], run["status"], run["workflow_state"]) == (
        "triage", "finished", "awaiting-approval"
    )
    assert run["actual_microusd"] == 75_000
    assert run["unknown_requests"] == 1
    assert run["rating"] == "partly-useful"
    assert run["model"] == "openai/gpt-5.6-terra"
    assert run["iterations"] == 3
    detail = reader.issue(*ISSUE)
    assert [entry["value"] for entry in detail["history"]] == [
        "queued", "intent", "running", "finished", "awaiting-approval"
    ]


def test_agent_events_keep_only_kind_source_tool_and_timestamp():
    from openhands_controller.performance import normalise_events

    raw = [{"id": "evt-1", "kind": "ActionEvent", "source": "agent",
            "timestamp": "2026-09-24T12:01:00Z",
            "action": {"kind": "terminal", "command": "echo PRIVATE_TOKEN"},
            "llm_message": {"content": "PRIVATE_TOKEN"}},
           {"id": "evt-2", "kind": "MessageEvent", "source": "user",
            "timestamp": "2026-09-24T12:01:01Z", "message": "PRIVATE_TOKEN"}]
    assert normalise_events(raw) == [
        {"kind": "ActionEvent", "source": "agent", "tool": "terminal",
         "timestamp": "2026-09-24T12:01:00Z"},
        {"kind": "MessageEvent", "source": "user", "tool": None,
         "timestamp": "2026-09-24T12:01:01Z"},
    ]


def test_rendered_dashboard_escapes_issue_data_and_shows_the_evidence(tmp_path):
    from openhands_controller.performance import PerformanceReader, render_dashboard

    path = tmp_path / "state.sqlite"
    _record_run(path)
    page = render_dashboard(PerformanceReader(path), selected=ISSUE,
                            agent_events=[{"kind": "ActionEvent", "source": "agent",
                                           "tool": "terminal", "timestamp": "12:01"}])
    assert "Focus &lt;script&gt;secret&lt;/script&gt;" in page
    assert "Focus <script>secret</script>" not in page
    assert "awaiting-approval" in page
    assert "partly-useful" in page
    assert "run-17" in page
    assert "Cost uncertain" in page
    assert "terminal" in page
    assert "PRIVATE_TOKEN" not in page


def test_reader_returns_archived_agent_events_when_runtime_is_gone(tmp_path):
    from openhands_controller.performance import PerformanceReader

    path = tmp_path / "state.sqlite"
    _record_run(path)
    store = Store(path)
    store.record_agent_events("run-17", [{"id": "event-1", "kind": "ActionEvent",
                                          "source": "agent", "tool": "terminal",
                                          "timestamp": "2026-09-24T12:01:00Z"}])
    store.record_agent_events("run-17", [{"id": "event-1", "kind": "ActionEvent",
                                          "source": "agent", "tool": "terminal",
                                          "timestamp": "2026-09-24T12:01:00Z"}])
    assert PerformanceReader(path).issue(*ISSUE)["agent_events"] == [
        {"kind": "ActionEvent", "source": "agent", "tool": "terminal",
         "timestamp": "2026-09-24T12:01:00Z"}
    ]


def test_archived_events_drop_invalid_identifiers_and_untrusted_fields(tmp_path):
    path = tmp_path / "state.sqlite"
    _record_run(path)
    store = Store(path)
    store.record_agent_events("run-17", [
        {"id": "bad id with spaces", "kind": "MessageEvent", "source": "user",
         "message": "PRIVATE_TOKEN"},
        {"id": "safe-event", "kind": "ActionEvent", "source": {"bad": "PRIVATE_TOKEN"},
         "tool": "bad tool", "timestamp": "2026-09-24T12:01:00Z", "command": "PRIVATE_TOKEN"},
    ])
    with store.connection() as db:
        rows = db.execute("SELECT event_id,source,tool FROM agent_events").fetchall()
    assert [tuple(row) for row in rows] == [("safe-event", "other", None)]


def test_run_without_usage_is_not_reported_as_zero_cost(tmp_path):
    from openhands_controller.performance import PerformanceReader, render_dashboard

    path = tmp_path / "state.sqlite"
    store = Store(path)
    store.create_workflow(ISSUE, "r1", budget_limit=5_000_000)
    store.create_dispatch(Dispatch("run-17", ISSUE, "r1", "triage", 1,
                                   "workspace-17", "conversation-17", None,
                                   "2026-09-24T12:00:00+00:00"))
    page = render_dashboard(PerformanceReader(path), selected=ISSUE)
    assert "No charge recorded" in page
    assert "$0.0000" not in page


def test_dashboard_does_not_render_raw_runtime_failure_text(tmp_path):
    from openhands_controller.performance import PerformanceReader, render_dashboard

    path = tmp_path / "state.sqlite"
    _record_run(path)
    store = Store(path)
    workflow = store.workflow(ISSUE)
    store.cas_workflow(ISSUE, workflow.version, reason="Agent Server failed: PRIVATE_TOKEN")
    page = render_dashboard(PerformanceReader(path), selected=ISSUE)
    assert "PRIVATE_TOKEN" not in page
    assert "See controller logs" in page
