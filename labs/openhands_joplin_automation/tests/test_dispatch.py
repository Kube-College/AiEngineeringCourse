import pytest
import sqlite3
from time import sleep
from threading import Event as ThreadEvent
from time import monotonic

from openhands_controller.controller import Controller
from openhands_controller.scheduler import SchedulerLock
from openhands_controller.contracts import Event, RunObservation
from support import Harness


def test_ambiguous_create_is_not_replayed(tmp_path):
    h = Harness(tmp_path, fault="after_agent_create")
    h.emit("issue")
    for _ in range(50):
        try:
            h.controller.tick()
        except RuntimeError:
            break
        sleep(0.001)
    else:
        pytest.fail("fault was not reported within 50 ticks")
    created = list(h.agent.created)
    h.restart()
    h.controller.tick()
    assert h.agent.created == created
    assert h.store.workflow(("demo/joplin", 1))["state"] == "needs-human"


def test_two_issues_use_one_active_dispatch(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.controller.handle(h.issue().__class__("issue-2", "issue", ("demo/joplin", 2), "r1", "maintainer", {"title": "second"}))
    h.run_to("triaging")
    for _ in range(20):
        h.controller.tick()
        sleep(0.001)
    assert len(h.agent.created) == 1


def test_malformed_triage_result_needs_human(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.run_to("triaging")
    for _ in range(50):
        h.controller.tick()
        if h.store.active_dispatch()["status"] == "running":
            break
        sleep(0.001)
    h.complete("triage", summary="missing scope")
    h.run_to("needs-human")
    assert h.store.workflow(("demo/joplin", 1))["approval_revision"] is None


def test_old_revision_result_cannot_advance_workflow(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.run_to("triaging")
    for _ in range(50):
        h.controller.tick()
        if h.store.active_dispatch()["status"] == "running":
            break
        sleep(0.001)
    h.emit("issue", revision="r2", title="new scope")
    h.complete("triage", scope="old", summary="old", validation_profile="core")
    for _ in range(50):
        h.controller.tick()
        if h.store.active_dispatch() is None:
            break
        sleep(0.001)
    assert h.store.workflow(("demo/joplin", 1))["revision"] == "r2"
    assert h.store.workflow(("demo/joplin", 1))["state"] == "queued"
    h.run_to("triaging")
    assert h.store.dispatches(("demo/joplin", 1))[-1].revision == "r2"


def test_restart_after_identifier_persisted_does_not_create_again(tmp_path, monkeypatch):
    h = Harness(tmp_path)
    h.emit("issue")
    original = h.store.update_dispatch

    def crash_after_persist(dispatch_id, **changes):
        original(dispatch_id, **changes)
        if changes.get("status") == "created":
            raise RuntimeError("crash after ID persistence")

    monkeypatch.setattr(h.store, "update_dispatch", crash_after_persist)
    for _ in range(50):
        try:
            h.controller.tick()
        except RuntimeError:
            break
        sleep(0.001)
    else:
        pytest.fail("fault was not reached")
    created = list(h.agent.created)
    h.restart()
    for _ in range(50):
        h.controller.tick()
        sleep(0.001)
        if h.store.active_dispatch()["status"] == "running":
            break
    assert h.agent.created == created
    assert h.store.active_dispatch()["status"] == "running"


def test_second_process_lock_is_rejected(tmp_path):
    lock = SchedulerLock(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            SchedulerLock(tmp_path)
    finally:
        lock.close()


def test_second_controller_cannot_run_same_state_dir(tmp_path):
    h = Harness(tmp_path)
    with pytest.raises(RuntimeError, match="another controller"):
        Controller(h.store, h.agent, h.delivery, lambda actor, repo: "write", h.clock)


def test_failure_before_create_retries_same_intent(tmp_path):
    h = Harness(tmp_path, fault="before_agent_create")
    h.emit("issue")
    for _ in range(100):
        try:
            h.controller.tick()
        except RuntimeError:
            pass
        sleep(0.001)
        if h.agent.created:
            break
    assert len(h.agent.created) == 1
    assert len(h.store.dispatches(("demo/joplin", 1))) == 1


def test_failure_after_start_does_not_create_again(tmp_path):
    h = Harness(tmp_path, fault="after_agent_start")
    h.emit("issue")
    for _ in range(100):
        try:
            h.controller.tick()
        except RuntimeError:
            break
        sleep(0.001)
    else:
        pytest.fail("start fault not observed")
    created = list(h.agent.created)
    h.restart()
    h.controller.tick()
    assert h.agent.created == created
    assert h.store.workflow(("demo/joplin", 1))["state"] == "needs-human"


def test_tick_stays_responsive_during_remote_create(tmp_path):
    h = Harness(tmp_path)
    entered, release = ThreadEvent(), ThreadEvent()
    original_create = h.agent.create

    def slow_create(dispatch):
        entered.set()
        assert release.wait(2)
        return original_create(dispatch)

    h.agent.create = slow_create
    h.emit("issue")
    try:
        start = monotonic()
        h.controller.tick()
        elapsed = monotonic() - start
        assert entered.wait(1)
        assert elapsed < 0.2
        assert h.store.active_dispatch()["status"] == "intent"
    finally:
        release.set()
        h.controller.close()


def test_dispatch_result_and_workflow_transition_commit_together(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.complete("implementation", summary="patch", changed_paths=["packages/lib/models/Note.ts"])
    dispatch = next(d for d in h.store.dispatches(("demo/joplin", 1)) if d.role == "implementation")
    with h.store.transaction() as db:
        db.execute("""CREATE TRIGGER fail_validating BEFORE UPDATE OF state ON workflows
                   WHEN NEW.state='validating' BEGIN SELECT RAISE(ABORT, 'simulated crash'); END""")
    for _ in range(100):
        try:
            h.controller.tick()
        except sqlite3.DatabaseError:
            break
        sleep(0.001)
    else:
        pytest.fail("transition fault was not reached")
    assert h.store.dispatch_row(dispatch.id)["status"] == "running"
    with h.store.transaction() as db:
        db.execute("DROP TRIGGER fail_validating")
    h.restart()
    h.run_to("reviewing")
    assert len([d for d in h.store.dispatches(("demo/joplin", 1)) if d.role == "implementation"]) == 1


def test_late_running_observation_stops_agent_before_releasing_slot(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    dispatch = next(d for d in h.store.dispatches(("demo/joplin", 1)) if d.role == "implementation")
    entered, release = ThreadEvent(), ThreadEvent()
    original_observe = h.agent.observe

    def delayed_observe(current):
        if h.agent.status[current.id] == "failed":
            return original_observe(current)
        entered.set()
        assert release.wait(2)
        return RunObservation("running")

    h.agent.observe = delayed_observe
    h.controller.tick()
    assert entered.wait(1)
    h.clock.advance(1201)
    release.set()
    h.run_to("needs-human")
    assert h.agent.status[dispatch.id] == "failed"
    assert h.store.active_dispatch() is None


def test_unknown_remote_status_keeps_global_slot(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.agent.observe = lambda dispatch: RunObservation("unknown")
    h.run_to("needs-human")
    active = h.store.active_dispatch()
    assert active is not None and active["status"] == "uncertain"
    created = list(h.agent.created)
    h.controller.handle(Event("issue-2", "issue", ("demo/joplin", 2), "r1", "maintainer", {"title": "second"}))
    for _ in range(5):
        h.controller.tick()
    assert h.agent.created == created


def test_simulated_validation_and_review_handoff(tmp_path):
    h = Harness(tmp_path)
    h.emit("issue")
    h.run_to("triaging")
    h.complete("triage", scope="note titles", summary="update shared model", validation_profile="core")
    h.run_to("awaiting-approval")
    row = h.store.workflow(("demo/joplin", 1))
    h.store.cas_workflow(("demo/joplin", 1), row["version"], state="implementing", approval_revision="r1")
    h.run_to("implementing")
    for _ in range(50):
        h.controller.tick()
        sleep(0.001)
        if h.store.active_dispatch() and h.store.active_dispatch()["status"] == "running":
            break
    h.complete("implementation", summary="changed title logic", changed_paths=["packages/lib/models/Note.ts"])
    h.run_to("reviewing")
    assert len(h.delivery.published) == 1
    implementation = next(d for d in h.store.dispatches(("demo/joplin", 1)) if d.role == "implementation")
    assert h.store.workflow(("demo/joplin", 1))["candidate_sha"] == f"sha-{implementation.id}"
    for _ in range(50):
        h.controller.tick()
        sleep(0.001)
        if h.store.active_dispatch() and h.store.active_dispatch()["status"] == "running":
            break
    sha = h.store.workflow(("demo/joplin", 1))["candidate_sha"]
    h.complete("review", candidate_sha=sha, verdict="pass", findings=[])
    h.run_to("ready-for-human")
    assert h.store.workflow(("demo/joplin", 1))["published_sha"] == sha
