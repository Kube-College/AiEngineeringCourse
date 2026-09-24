"""Evidence needed to assess an agent run after the controller has moved on."""

from openhands_controller.domain.models import Dispatch
from openhands_controller.domain.states import Role
from openhands_controller.persistence.budget import Budget
from openhands_controller.persistence.store import Store
from openhands_controller.config import Settings
from support import Harness


ISSUE = ("demo/joplin", 17)


def _dispatch() -> Dispatch:
    return Dispatch("run-17", ISSUE, "revision-a", Role.TRIAGE, 1,
                    "workspace-17", "conversation-17", None, "2026-09-24T12:00:00+00:00")


def test_state_and_dispatch_history_survive_restart_without_duplicate_transitions(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    assert store.create_workflow(ISSUE, "revision-a", budget_limit=5_000_000)
    assert not store.create_workflow(ISSUE, "revision-a", budget_limit=5_000_000)
    store.create_dispatch(_dispatch(), model="openai/gpt-5.6-terra", profile_hash="abc123")
    store.update_dispatch("run-17", status="running")
    store.update_dispatch("run-17", status="running", iterations=2)
    row = store.workflow(ISSUE)
    store.cas_workflow(ISSUE, row.version, state="triaging")
    row = store.workflow(ISSUE)
    store.transition_dispatch("run-17", ISSUE, row.version, "awaiting-approval", "finished")

    reopened = Store(tmp_path / "state.sqlite")
    with reopened.connection() as db:
        history = db.execute(
            "SELECT kind, value FROM run_history WHERE repo=? AND issue_number=? ORDER BY id", ISSUE
        ).fetchall()
        dispatch = db.execute("SELECT model, profile_hash FROM dispatches WHERE id='run-17'").fetchone()
    assert [tuple(row) for row in history] == [
        ("workflow", "queued"), ("dispatch", "intent"), ("dispatch", "running"),
        ("workflow", "triaging"), ("dispatch", "finished"),
        ("workflow", "awaiting-approval"),
    ]
    assert tuple(dispatch) == ("openai/gpt-5.6-terra", "abc123")


def test_model_charges_are_attributed_to_the_dispatch_and_unknown_cost_stays_unknown(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    store.create_workflow(ISSUE, "revision-a", budget_limit=5_000_000)
    store.create_dispatch(_dispatch())
    budget = Budget(store)
    assert budget.reserve(ISSUE, "run-17:model:call-1", 100_000)
    budget.settle(ISSUE, "run-17:model:call-1", 61_000)
    assert budget.reserve(ISSUE, "run-17:model:call-2", 100_000)
    budget.settle(ISSUE, "run-17:model:call-2", None)
    with store.connection() as db:
        charges = db.execute(
            "SELECT dispatch_id, actual_microusd, status FROM usage ORDER BY request_id"
        ).fetchall()
    assert [tuple(row) for row in charges] == [
        ("run-17", 61_000, "settled"), ("run-17", None, "unknown")
    ]


def test_human_feedback_is_replaced_for_one_run_without_changing_workflow_state(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    store.create_workflow(ISSUE, "revision-a", budget_limit=5_000_000)
    store.create_dispatch(_dispatch())
    store.rate_dispatch("run-17", "partly-useful", "Missed the desktop path")
    store.rate_dispatch("run-17", "useful", "Rechecked the report")
    with store.connection() as db:
        feedback = db.execute("SELECT rating, note FROM feedback WHERE dispatch_id='run-17'").fetchall()
    assert [tuple(row) for row in feedback] == [("useful", "Rechecked the report")]
    assert store.workflow(ISSUE).state == "queued"


def test_live_dispatch_records_selected_model_and_profile_version(tmp_path):
    h = Harness(tmp_path, settings=Settings(_env_file=None, agent_backend="openhands"))
    h.run_to("triaging")
    with h.store.connection() as db:
        row = db.execute("SELECT model,profile_hash FROM dispatches LIMIT 1").fetchone()
    assert row["model"] == "openai/gpt-5.6-terra"
    assert len(row["profile_hash"]) == 64
    h.controller.close()


def test_reopening_existing_database_attributes_old_model_charges(tmp_path):
    path = tmp_path / "state.sqlite"
    store = Store(path)
    store.create_workflow(ISSUE, "revision-a", budget_limit=5_000_000)
    store.create_dispatch(_dispatch())
    with store.transaction() as db:
        db.execute("INSERT INTO usage(repo,issue_number,request_id,reserved_microusd,status,actual_microusd) "
                   "VALUES(?,?,?,?,?,?)", (*ISSUE, "run-17:model:old", 100_000, "settled", 50_000))
    reopened = Store(path)
    with reopened.connection() as db:
        linked = db.execute("SELECT dispatch_id FROM usage WHERE request_id='run-17:model:old'").fetchone()[0]
    assert linked == "run-17"


def test_reopening_pre_console_database_adds_usage_dispatch_link(tmp_path):
    path = tmp_path / "state.sqlite"
    store = Store(path)
    store.create_workflow(ISSUE, "revision-a", budget_limit=5_000_000)
    store.create_dispatch(_dispatch())
    with store.transaction() as db:
        db.execute("ALTER TABLE usage DROP COLUMN dispatch_id")
        db.execute("INSERT INTO usage(repo,issue_number,request_id,reserved_microusd,status,actual_microusd) "
                   "VALUES(?,?,?,?,?,?)", (*ISSUE, "run-17:model:old", 100_000, "settled", 50_000))
    reopened = Store(path)
    with reopened.connection() as db:
        linked = db.execute("SELECT dispatch_id FROM usage WHERE request_id='run-17:model:old'").fetchone()[0]
    assert linked == "run-17"
