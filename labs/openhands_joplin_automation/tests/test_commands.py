import pytest
from threading import Event as ThreadEvent
from time import sleep

from openhands_controller.domain.commands import parse_command
from openhands_controller.domain.revision import revision_hash
from openhands_controller.domain.errors import EventConflict
from openhands_controller.domain.models import Event
from openhands_controller.persistence.store import Store
from support import Harness


@pytest.mark.parametrize("body, expected", [
    ("/agent implement", ("implement", None)),
    ("/agent pause", ("pause", None)),
    ("/agent resume", ("resume", None)),
    ("/agent cancel", ("cancel", None)),
    ("/agent budget 7.25", ("budget", 7_250_000)),
    ("> /agent implement", None),
    ("```\n/agent implement\n```", None),
    ("`/agent implement`", None),
    ("/agent implement please", None),
    ("Here is /agent implement", None),
    ("/agent budget -1", None),
])
def test_parse_standalone_commands(body, expected):
    assert parse_command(body) == expected


def test_revision_hash_changes_only_for_title_or_body():
    assert revision_hash("title", "body") == revision_hash("title", "body")
    assert revision_hash("title", "body") != revision_hash("title", "changed")


def test_cancel_wins_over_finished_agent(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.emit("command", body="/agent cancel")
    h.complete("implementation", summary="done", changed_paths=["packages/lib/models/Note.ts"])
    h.controller.tick()
    assert h.delivery.published == []


def test_issue_edit_revokes_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.emit("issue", title="new scope", body="changed", revision="r2")
    h.emit("command", body="/agent resume")
    assert h.store.workflow(("demo/joplin", 1)).approval_revision is None


def test_early_and_read_only_approvals_are_rejected(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.emit("command", body="/agent implement")
    assert h.store.workflow(("demo/joplin", 1)).approval_revision is None
    h.run_to("awaiting-approval")
    h.controller.permissions = lambda actor, repo: "read"
    h.emit("command", body="/agent implement")
    assert h.store.workflow(("demo/joplin", 1)).state == "awaiting-approval"


def test_edited_and_projection_commands_do_not_execute(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    h.emit("command", body="/agent implement", action="edited")
    h.emit("command", body="/agent implement", projection=True)
    h.emit("comment", body="Ordinary discussion")
    assert h.store.workflow(("demo/joplin", 1)).approval_revision is None


def test_label_presence_does_not_authorise_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    h.emit("label", label="agent:implement", action="present")
    assert h.store.workflow(("demo/joplin", 1)).approval_revision is None
    h.emit("label", label="agent:implement", action="added", created_at="2099-01-01T00:00:00Z")
    assert h.store.workflow(("demo/joplin", 1)).approval_revision == "r1"


def test_label_added_before_triage_finished_cannot_authorise_implementation(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    h.emit("label", label="agent:implement", action="added", created_at="2020-01-01T00:00:00Z")
    assert h.store.workflow(("demo/joplin", 1)).state == "awaiting-approval"
    h.emit("label", label="agent:implement", action="added", created_at="2099-01-01T00:00:00Z")
    assert h.store.workflow(("demo/joplin", 1)).state == "implementing"


def test_approval_in_same_second_as_triage_handoff_waits_for_newer_event(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    with h.store.transaction() as db:
        db.execute("UPDATE run_history SET created_at='2026-09-24T12:00:00.500Z' "
                   "WHERE kind='workflow' AND value='awaiting-approval'")
    h.emit("label", label="agent:implement", action="added", created_at="2026-09-24T12:00:00Z")
    assert h.store.workflow(("demo/joplin", 1)).state == "awaiting-approval"
    h.emit("label", label="agent:implement", action="added", created_at="2026-09-24T12:00:01Z")
    assert h.store.workflow(("demo/joplin", 1)).state == "implementing"


def test_existing_awaiting_workflow_accepts_only_post_upgrade_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    with h.store.transaction() as db:
        db.execute("DROP TABLE run_history")
    Store(h.store.path)
    h.emit("label", label="agent:implement", action="added", created_at="2020-01-01T00:00:00Z")
    assert h.store.workflow(("demo/joplin", 1)).state == "awaiting-approval"
    h.emit("label", label="agent:implement", action="added", created_at="2099-01-01T00:00:00Z")
    assert h.store.workflow(("demo/joplin", 1)).state == "implementing"


def test_repeated_event_identity_cannot_change_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    event = Event("approval-1", "command", ("demo/joplin", 1), "r1", "maintainer", {"body": "/agent implement"})
    h.controller.handle(event)
    h.controller.handle(event)
    with pytest.raises(EventConflict):
        h.controller.handle(Event("approval-1", "command", ("demo/joplin", 1), "r1", "maintainer", {"body": "/agent cancel"}))
    assert h.store.workflow(("demo/joplin", 1)).state == "implementing"


def test_cancel_queued_issue_while_other_issue_runs(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.controller.handle(Event("second-issue", "issue", ("demo/joplin", 2), "r1", "maintainer", {"title": "second"}))
    h.run_to("triaging")
    h.controller.handle(Event("cancel-second", "command", ("demo/joplin", 2), "r1", "maintainer", {"body": "/agent cancel"}))
    assert h.store.workflow(("demo/joplin", 2)).state == "cancelled"
    assert h.store.workflow(("demo/joplin", 1)).stop_requested is None


def test_unresponsive_stop_stays_requested(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    entered, release = ThreadEvent(), ThreadEvent()

    def slow_stop(dispatch, *, cancel):
        entered.set()
        assert release.wait(2)

    h.agent.stop = slow_stop
    try:
        h.emit("command", body="/agent cancel")
        h.controller.tick()
        assert entered.wait(1)
        for _ in range(3):
            h.controller.tick()
        row = h.store.workflow(("demo/joplin", 1))
        assert row.state == "implementing"
        assert row.stop_requested == "cancel"
        assert h.delivery.published == []
    finally:
        release.set()
        h.controller.close()


def test_pause_resume_keeps_same_dispatch(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    created = list(h.agent.created)
    h.emit("command", body="/agent pause")
    h.emit("command", body="/agent pause")
    h.run_to("paused")
    h.emit("command", body="/agent resume")
    h.emit("command", body="/agent resume")
    h.run_to("implementing")
    assert h.agent.created == created


def test_permission_lookup_failure_rejects_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    h.controller.permissions = lambda actor, repo: (_ for _ in ()).throw(RuntimeError("unavailable"))
    h.emit("command", body="/agent implement")
    assert h.store.workflow(("demo/joplin", 1)).approval_revision is None


def test_cancel_during_resume_cannot_restore_implementation(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.emit("command", body="/agent pause")
    h.run_to("paused")
    entered, release = ThreadEvent(), ThreadEvent()
    original_resume = h.agent.resume

    def slow_resume(dispatch):
        entered.set()
        assert release.wait(2)
        original_resume(dispatch)

    h.agent.resume = slow_resume
    try:
        h.emit("command", body="/agent resume")
        assert entered.wait(1)
        h.emit("command", body="/agent cancel")
    finally:
        release.set()
    h.run_to("cancelled")
    assert h.delivery.published == []
    assert h.store.workflow(("demo/joplin", 1)).approval_revision == "r1"


def test_pause_resume_awaiting_approval_restores_nonrunning_stage(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    h.emit("command", body="/agent pause")
    assert h.store.workflow(("demo/joplin", 1)).state == "paused"
    h.emit("command", body="/agent resume")
    assert h.store.workflow(("demo/joplin", 1)).state == "awaiting-approval"
    h.emit("command", body="/agent implement")
    h.run_to("implementing")


def test_pause_resume_approved_stage_before_dispatch(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    h.emit("command", body="/agent implement")
    h.emit("command", body="/agent pause")
    assert h.store.workflow(("demo/joplin", 1)).state == "paused"
    h.emit("command", body="/agent resume")
    h.run_to("implementing")


def test_pause_ready_for_human_is_harmless(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    row = h.store.workflow(("demo/joplin", 1))
    h.store.cas_workflow(("demo/joplin", 1), row.version, state="ready-for-human")
    h.emit("command", body="/agent pause")
    assert h.store.workflow(("demo/joplin", 1)).state == "ready-for-human"


def test_paused_triage_can_resume_to_reach_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("triaging")
    for _ in range(100):
        active = h.store.active_dispatch()
        if active and active.status == "running":
            break
        h.controller.tick()
        sleep(0.001)
    else:
        pytest.fail("triage did not start")
    h.emit("command", body="/agent pause")
    h.run_to("paused")
    h.emit("command", body="/agent resume")
    h.complete("triage", scope="note title", summary="scope", validation_profile="core")
    h.run_to("awaiting-approval")
