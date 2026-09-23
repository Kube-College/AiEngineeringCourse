import json
from threading import Event as ThreadEvent, Thread

import pytest

from openhands_controller.cli import main
from openhands_controller.budget import Budget
from openhands_controller.config import Config
from openhands_controller.contracts import RunObservation
from openhands_controller.store import Store
from support import Harness


@pytest.mark.parametrize("scenario, expected", [
    ("happy", "ready-for-human"),
    ("duplicate", "ready-for-human"),
    ("restart", "ready-for-human"),
    ("budget", "needs-human"),
    ("cancel", "cancelled"),
])
def test_cli_scenario_persists_outcome(tmp_path, capsys, scenario, expected):
    main(["simulate", "--state-dir", str(tmp_path), "--scenario", scenario])
    output = json.loads(capsys.readouterr().out)
    reopened = Store(tmp_path / "controller.sqlite")
    row = reopened.workflow(("demo/joplin", 1))
    assert row["state"] == expected
    assert output["state"] == expected
    if expected == "ready-for-human":
        assert row["pr_url"]
        assert row["published_sha"] == row["candidate_sha"]
        assert Budget(reopened).snapshot(("demo/joplin", 1))["actual_microusd"] == 300_000
    if scenario == "cancel":
        assert Budget(reopened).snapshot(("demo/joplin", 1))["unknown"] is True


def test_recorded_but_unapplied_event_is_replayed(tmp_path):
    h = Harness(tmp_path)
    event = h.issue()
    assert h.store.record_event(event)
    h.controller.handle(event)
    assert h.store.workflow(("demo/joplin", 1))["state"] == "queued"


def test_configured_timeout_is_used(tmp_path):
    h = Harness(tmp_path, config=Config(timeout_seconds=2))
    h.run_to("implementing")
    h.clock.advance(3)
    h.run_to("needs-human")
    assert h.store.workflow(("demo/joplin", 1))["reason"] == "timeout"


def test_timeout_stops_run_before_handoff(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.clock.advance(1201)
    h.run_to("needs-human")
    assert h.delivery.published == []
    assert h.store.active_dispatch() is None


def test_iteration_cap_stops_run_before_handoff(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    original_observe = h.agent.observe

    def exhausted(dispatch):
        if h.agent.status[dispatch.id] == "failed":
            return original_observe(dispatch)
        return RunObservation("running", usage=({"request_id": dispatch.id, "iterations": 50,
                                                 "cumulative_microusd": 200_000},))

    h.agent.observe = exhausted
    h.run_to("needs-human")
    assert h.delivery.published == []


def test_unknown_usage_blocks_next_role(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.run_to("triaging")
    h.agent.report_usage = False
    h.complete("triage", scope="core", summary="scope", validation_profile="core")
    h.run_to("awaiting-approval")
    h.emit("command", body="/agent implement")
    h.run_to("needs-human")
    assert h.store.workflow(("demo/joplin", 1))["reason"] == "budget exhausted or unknown"


def test_review_allows_one_fix_then_hands_off(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.complete("implementation", summary="first patch", changed_paths=["packages/lib/models/Note.ts"])
    h.run_to("reviewing")
    first_sha = h.store.workflow(("demo/joplin", 1))["candidate_sha"]
    h.complete("review", candidate_sha=first_sha, verdict="changes_requested",
               findings=[{"path": "packages/lib/models/Note.ts", "line": 1, "explanation": "still wrong"}])
    h.run_to("fixing")
    h.complete("fix", summary="corrected", changed_paths=["packages/lib/models/Note.ts"])
    h.run_to("reviewing")
    second_sha = h.store.workflow(("demo/joplin", 1))["candidate_sha"]
    assert second_sha != first_sha
    h.complete("review", candidate_sha=second_sha, verdict="changes_requested",
               findings=[{"path": "packages/lib/models/Note.ts", "line": 1, "explanation": "still wrong"}])
    h.run_to("needs-human")
    assert h.store.workflow(("demo/joplin", 1))["review_cycles"] == 1


def test_cancel_during_validation_prevents_publication(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.complete("implementation", summary="patch", changed_paths=["packages/lib/models/Note.ts"])
    h.run_to("validating")
    entered, release = ThreadEvent(), ThreadEvent()
    original = h.delivery.validate

    def slow_validation(candidate_sha, profile):
        entered.set()
        assert release.wait(2)
        return original(candidate_sha, profile)

    h.delivery.validate = slow_validation
    worker = Thread(target=h.controller.tick)
    worker.start()
    try:
        assert entered.wait(1)
        h.emit("command", body="/agent cancel")
    finally:
        release.set()
        worker.join(timeout=2)
    assert h.delivery.published == []
    assert h.store.workflow(("demo/joplin", 1))["state"] == "cancelled"
