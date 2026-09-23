import json
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable

from .contracts import AgentAdapter, CreateNotSent, Delivery, Dispatch, Event, RunObservation
from .scheduler import SchedulerLock
from .store import Store


ROLE_STATES = {"queued": ("triage", "triaging"), "implementing": ("implementation", "implementing"),
               "reviewing": ("review", "reviewing"), "fixing": ("fix", "fixing")}
ALLOWED = {
    "queued": {"triaging", "cancelled", "needs-human"},
    "triaging": {"awaiting-approval", "needs-human", "paused", "cancelled", "queued"},
    "awaiting-approval": {"implementing", "cancelled", "needs-human", "queued"},
    "implementing": {"validating", "needs-human", "paused", "cancelled", "queued"},
    "validating": {"reviewing", "needs-human", "cancelled", "queued"},
    "reviewing": {"fixing", "ready-for-human", "needs-human", "paused", "cancelled", "queued"},
    "fixing": {"validating", "needs-human", "paused", "cancelled", "queued"},
    "paused": {"implementing", "triaging", "reviewing", "fixing", "cancelled", "needs-human", "queued"},
    "needs-human": {"queued", "cancelled"},
    "ready-for-human": {"completed", "needs-human", "cancelled", "queued"},
    "cancelled": set(), "completed": set(),
}


class Controller:
    def __init__(self, store: Store, agent: AgentAdapter, delivery: Delivery,
                 permissions: Callable[[str, str], str], clock: Callable[[], datetime]):
        self.store, self.agent, self.delivery = store, agent, delivery
        self.permissions, self.clock = permissions, clock
        self._lock = SchedulerLock(store.path.parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-adapter")
        self._pending: tuple[str, str, Future] | None = None

    def close(self):
        self._pool.shutdown(wait=True, cancel_futures=True)
        self._lock.close()

    def _move(self, row: dict[str, object], state: str, **changes: object):
        if state != row["state"] and state not in ALLOWED[row["state"]]:
            raise ValueError(f"invalid transition {row['state']} -> {state}")
        return self.store.cas_workflow((row["repo"], row["issue_number"]), row["version"], state=state, **changes)

    def handle(self, event: Event) -> None:
        if not self.store.record_event(event):
            return
        if event.kind == "issue":
            title = str(event.payload.get("title", ""))
            body = str(event.payload.get("body", ""))
            if self.store.create_workflow(event.issue, event.revision, title=title, body=body):
                return
            row = self.store.workflow(event.issue)
            if row["revision"] != event.revision:
                self._move(row, "queued", revision=event.revision, title=title, body=body,
                           approval_revision=None, stop_requested="revision", reason="issue changed")
            return

    def _dispatch(self, row: dict[str, object], role: str) -> None:
        issue = (row["repo"], row["issue_number"])
        attempts = [d for d in self.store.dispatches(issue) if d.revision == row["revision"] and d.role == role]
        attempt = len(attempts) + 1
        dispatch_id = f"{issue[0].replace('/', '-')}-{issue[1]}-{row['revision']}-{role}-{attempt}"
        dispatch = Dispatch(dispatch_id, issue, row["revision"], role, attempt,
                            f"workspace-{issue[1]}", None, row["candidate_sha"],
                            (self.clock() + timedelta(minutes=20)).isoformat())
        self.store.create_dispatch(dispatch)
        if role == "triage":
            row = self._move(row, "triaging")
        self._submit("create", dispatch)

    def _submit(self, action: str, dispatch: Dispatch):
        fn = {"create": self.agent.create, "start": self.agent.start, "observe": self.agent.observe,
              "reconcile": self.agent.observe}[action]
        self._pending = (action, dispatch.id, self._pool.submit(fn, dispatch))

    def tick(self) -> None:
        if self._pending:
            action, dispatch_id, future = self._pending
            if not future.done():
                return
            self._pending = None
            row = self.store.dispatch_row(dispatch_id)
            try:
                value = future.result()
            except CreateNotSent:
                self.store.update_dispatch(dispatch_id, status="retryable")
                raise
            except Exception as exc:
                self.store.update_dispatch(dispatch_id, status="uncertain")
                workflow = self.store.workflow((row["repo"], row["issue_number"]))
                self._move(workflow, "needs-human", reason=f"uncertain {action}: {exc}")
                raise
            dispatch = self._as_dispatch(row)
            if action == "create":
                self.store.update_dispatch(dispatch_id, status="created", conversation_id=value)
                return
            if action == "start":
                self.store.update_dispatch(dispatch_id, status="running")
                return
            if action == "reconcile":
                if value.status == "running":
                    self.store.update_dispatch(dispatch_id, status="running")
                elif value.status == "created":
                    self._submit("start", dispatch)
                else:
                    self.store.update_dispatch(dispatch_id, status="uncertain")
                    workflow = self.store.workflow(dispatch.issue)
                    self._move(workflow, "needs-human", reason="remote start cannot be reconciled")
                return
            self._observed(dispatch, value)
            return

        active = self.store.active_dispatch()
        if active:
            dispatch = self._as_dispatch(active)
            status = active["status"]
            if status == "retryable":
                self._submit("create", dispatch)
            elif status in {"intent", "uncertain"}:
                self.store.update_dispatch(dispatch.id, status="uncertain")
                workflow = self.store.workflow(dispatch.issue)
                if workflow["state"] != "needs-human":
                    self._move(workflow, "needs-human", reason="remote creation identity is uncertain")
            elif status == "created":
                self._submit("reconcile", dispatch)
            elif status == "running":
                self._submit("observe", dispatch)
            return

        for row in self.store.workflows():
            if row["stop_requested"] or row["state"] in {"cancelled", "completed", "paused", "needs-human", "ready-for-human", "awaiting-approval"}:
                continue
            if row["state"] == "validating":
                self._validate(row)
                return
            if row["state"] in ROLE_STATES:
                role, _ = ROLE_STATES[row["state"]]
                self._dispatch(row, role)
                return

    @staticmethod
    def _as_dispatch(row: dict[str, object]) -> Dispatch:
        return Dispatch(row["id"], (row["repo"], row["issue_number"]), row["revision"],
                        row["role"], row["attempt"], row["workspace_id"], row["conversation_id"],
                        row["candidate_sha"], row["deadline"])

    def _observed(self, dispatch: Dispatch, observation: RunObservation) -> None:
        row = self.store.workflow(dispatch.issue)
        if row["revision"] != dispatch.revision or row["stop_requested"]:
            if observation.status == "finished":
                self.store.update_dispatch(dispatch.id, status="stale")
                if row["stop_requested"] == "revision":
                    self.store.cas_workflow(dispatch.issue, row["version"], stop_requested=None)
            return
        if self.clock() >= datetime.fromisoformat(dispatch.deadline):
            self.store.update_dispatch(dispatch.id, status="failed")
            self._move(row, "needs-human", reason="run timed out")
            return
        if observation.status in {"failed", "unknown", "missing"}:
            self.store.update_dispatch(dispatch.id, status="failed")
            self._move(row, "needs-human", reason=observation.error or observation.status)
            return
        if observation.status != "finished":
            return
        result = observation.result
        if not self._valid_result(dispatch, result):
            self.store.update_dispatch(dispatch.id, status="failed")
            self._move(row, "needs-human", reason="invalid role result")
            return
        self.store.update_dispatch(dispatch.id, status="finished", result_json=json.dumps(result, sort_keys=True))
        if dispatch.role == "triage":
            self._move(row, "awaiting-approval", validation_profile=result["validation_profile"])
        elif dispatch.role in {"implementation", "fix"}:
            self._move(row, "validating")
        elif result["verdict"] == "pass":
            self._move(row, "ready-for-human")
        elif row["review_cycles"] < 1:
            self._move(row, "fixing", review_cycles=row["review_cycles"] + 1)
        else:
            self._move(row, "needs-human", reason="review correction exhausted")

    @staticmethod
    def _valid_result(dispatch: Dispatch, result: object) -> bool:
        if not isinstance(result, dict):
            return False
        if dispatch.role == "triage":
            return set(result) == {"scope", "summary", "validation_profile"} and all(
                isinstance(value, str) and value for value in result.values())
        if dispatch.role in {"implementation", "fix"}:
            return (set(result) == {"summary", "changed_paths"} and
                    isinstance(result["summary"], str) and bool(result["summary"]) and
                    isinstance(result["changed_paths"], list) and bool(result["changed_paths"]) and
                    all(isinstance(path, str) and path for path in result["changed_paths"]))
        return (set(result) == {"candidate_sha", "verdict", "findings"} and
                result["candidate_sha"] == dispatch.candidate_sha and
                result["verdict"] in {"pass", "changes_requested"} and
                isinstance(result["findings"], list) and all(
                    isinstance(f, dict) and set(f) == {"path", "line", "explanation"} and
                    isinstance(f["path"], str) and type(f["line"]) is int and f["line"] > 0 and
                    isinstance(f["explanation"], str) for f in result["findings"]))

    def _validate(self, row: dict[str, object]):
        issue = (row["repo"], row["issue_number"])
        last = self.store.dispatches(issue)[-1]
        sha = self.delivery.capture(last)
        result = self.delivery.validate(sha, str(row["validation_profile"]))
        with self.store.transaction() as db:
            db.execute("INSERT INTO validations(repo,issue_number,candidate_sha,profile,passed,evidence_dir) VALUES(?,?,?,?,?,?)",
                       (*issue, sha, result.profile, int(result.passed), result.evidence_dir))
        if not result.passed or result.candidate_sha != sha:
            self._move(row, "needs-human", reason="validation failed")
            return
        # Publication is a fake in Plan 01. Production publication arrives in Plan 04.
        pr_url = self.delivery.publish(issue, sha)
        self._move(row, "reviewing", candidate_sha=sha, published_sha=sha, pr_url=pr_url)
