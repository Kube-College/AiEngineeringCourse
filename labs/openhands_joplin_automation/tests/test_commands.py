import pytest
from threading import Event as ThreadEvent
from time import sleep

from openhands_controller.commands import parse_command
from openhands_controller.revision import revision_hash
from openhands_controller.contracts import Event, EventConflict
from support import Harness


@pytest.mark.parametrize("body, expected", [
    ("/agent implement", ("implement", None)),
    ("/agent pause", ("pause", None)),
    ("/agent resume", ("resume", None)),
    ("/agent cancel", ("cancel", None)),
    ("/agent budget 7.25", ("budget", "7.25")),
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
    assert h.store.workflow(("demo/joplin", 1))["approval_revision"] is None


def test_early_and_read_only_approvals_are_rejected(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.emit("command", body="/agent implement")
    assert h.store.workflow(("demo/joplin", 1))["approval_revision"] is None
    h.run_to("awaiting-approval")
    h.controller.permissions = lambda actor, repo: "read"
    h.emit("command", body="/agent implement")
    assert h.store.workflow(("demo/joplin", 1))["state"] == "awaiting-approval"


def test_edited_and_projection_commands_do_not_execute(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    h.emit("command", body="/agent implement", action="edited")
    h.emit("command", body="/agent implement", projection=True)
    h.emit("comment", body="Ordinary discussion")
    assert h.store.workflow(("demo/joplin", 1))["approval_revision"] is None


def test_label_presence_does_not_authorise_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    h.emit("label", label="agent:implement", action="present")
    assert h.store.workflow(("demo/joplin", 1))["approval_revision"] is None
    h.emit("label", label="agent:implement", action="added")
    assert h.store.workflow(("demo/joplin", 1))["approval_revision"] == "r1"


def test_repeated_event_identity_cannot_change_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("awaiting-approval")
    event = Event("approval-1", "command", ("demo/joplin", 1), "r1", "maintainer", {"body": "/agent implement"})
    h.controller.handle(event)
    h.controller.handle(event)
    with pytest.raises(EventConflict):
        h.controller.handle(Event("approval-1", "command", ("demo/joplin", 1), "r1", "maintainer", {"body": "/agent cancel"}))
    assert h.store.workflow(("demo/joplin", 1))["state"] == "implementing"


def test_cancel_queued_issue_while_other_issue_runs(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.controller.handle(Event("second-issue", "issue", ("demo/joplin", 2), "r1", "maintainer", {"title": "second"}))
    h.run_to("triaging")
    h.controller.handle(Event("cancel-second", "command", ("demo/joplin", 2), "r1", "maintainer", {"body": "/agent cancel"}))
    assert h.store.workflow(("demo/joplin", 2))["state"] == "cancelled"
    assert h.store.workflow(("demo/joplin", 1))["stop_requested"] is None


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
        assert row["state"] == "implementing"
        assert row["stop_requested"] == "cancel"
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
    assert h.store.workflow(("demo/joplin", 1))["approval_revision"] is None
