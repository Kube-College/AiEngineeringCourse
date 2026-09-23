import json
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable

from .contracts import AgentAdapter, CreateNotSent, Delivery, Dispatch, Event, RunObservation
from .commands import parse_command
from .budget import Budget
from .config import Config
from .scheduler import SchedulerLock
from .store import Store


ROLE_STATES = {"queued": ("triage", "triaging"), "implementing": ("implementation", "implementing"),
               "reviewing": ("review", "reviewing"), "fixing": ("fix", "fixing")}
ALLOWED = {
    "queued": {"triaging", "cancelled", "needs-human"},
    "triaging": {"awaiting-approval", "needs-human", "paused", "cancelled", "queued"},
    "awaiting-approval": {"implementing", "paused", "cancelled", "needs-human", "queued"},
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
                 permissions: Callable[[str, str], str], clock: Callable[[], datetime],
                 config: Config | None = None):
        self.store, self.agent, self.delivery = store, agent, delivery
        self.permissions, self.clock = permissions, clock
        self.config = config or Config()
        self.budget = Budget(store)
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
        self.store.record_event(event)
        if self.store.event_outcome(event.id) == "processed":
            return
        self._apply_event(event)
        self.store.mark_event_processed(event.id)

    def _apply_event(self, event: Event) -> None:
        if event.kind == "issue":
            title = str(event.payload.get("title", ""))
            body = str(event.payload.get("body", ""))
            if self.store.create_workflow(event.issue, event.revision, title=title, body=body,
                                          budget_limit=self.config.issue_budget_microusd):
                return
            row = self.store.workflow(event.issue)
            if row["revision"] != event.revision:
                active = self.store.active_dispatch()
                active_here = active and (active["repo"], active["issue_number"]) == event.issue
                self._move(row, "queued", revision=event.revision, title=title, body=body,
                           approval_revision=None, stop_requested="revision" if active_here else None,
                           review_cycles=0, reason="issue changed")
            return
        if event.kind not in {"command", "label"} or event.payload.get("projection"):
            return
        if event.payload.get("action") == "edited" or event.revision != self.store.workflow(event.issue)["revision"]:
            return
        if event.kind == "label":
            if event.payload.get("action") != "added" or event.payload.get("label") != "agent:implement":
                return
            parsed = ("implement", None)
        else:
            parsed = parse_command(str(event.payload.get("body", "")))
        if parsed is None:
            return
        try:
            permission = self.permissions(event.actor, event.issue[0])
        except Exception:
            return
        if permission not in {"write", "maintain", "admin"}:
            return
        command, argument = parsed
        row = self.store.workflow(event.issue)
        active = self.store.active_dispatch()
        active_here = active and (active["repo"], active["issue_number"]) == event.issue
        if command == "budget":
            try:
                amount = Decimal(argument)
                if not amount.is_finite() or amount <= 0:
                    return
                micro = amount * 1_000_000
                if micro != micro.to_integral_value():
                    return
                self.budget.increase(event.issue, int(micro), event.id)
            except (InvalidOperation, ValueError, TypeError):
                return
            return
        if command == "implement":
            if row["state"] == "awaiting-approval":
                self._move(row, "implementing", approval_revision=row["revision"], stop_requested=None)
            return
        if command == "cancel":
            if row["state"] in {"cancelled", "completed"}:
                return
            if active_here:
                self.store.cas_workflow(event.issue, row["version"], stop_requested="cancel")
            else:
                self._move(row, "cancelled", stop_requested=None)
            return
        if command == "pause":
            if row["state"] == "paused" or row["stop_requested"]:
                return
            if active_here:
                self.store.cas_workflow(event.issue, row["version"], stop_requested="pause", resume_state=row["state"])
            elif row["state"] not in {"cancelled", "completed", "needs-human"}:
                self._move(row, "paused", resume_state=row["state"])
            return
        if command == "resume" and row["state"] == "paused" and row["approval_revision"] == row["revision"]:
            with self.store.connection() as db:
                unknown = db.execute("SELECT 1 FROM usage WHERE repo=? AND issue_number=? AND status='unknown' LIMIT 1", event.issue).fetchone()
            if unknown or self.store.active_dispatch():
                return
            paused = [d for d in self.store.dispatches(event.issue) if self.store.dispatch_row(d.id)["status"] == "paused"]
            if not paused:
                return
            dispatch = paused[-1]
            self.store.update_dispatch(dispatch.id, status="resuming")
            self._submit("resume", dispatch)
            return

    def _dispatch(self, row: dict[str, object], role: str) -> None:
        issue = (row["repo"], row["issue_number"])
        attempts = [d for d in self.store.dispatches(issue) if d.revision == row["revision"] and d.role == role]
        attempt = len(attempts) + 1
        dispatch_id = f"{issue[0].replace('/', '-')}-{issue[1]}-{row['revision']}-{role}-{attempt}"
        if not self.budget.reserve(issue, dispatch_id, self.config.dispatch_estimate_microusd):
            self._move(row, "needs-human", reason="budget exhausted or unknown")
            return
        dispatch = Dispatch(dispatch_id, issue, row["revision"], role, attempt,
                            f"workspace-{issue[1]}", None, row["candidate_sha"],
                            (self.clock() + timedelta(seconds=self.config.timeout_seconds)).isoformat())
        self.store.create_dispatch(dispatch)
        if role == "triage":
            row = self._move(row, "triaging")
        self._submit("create", dispatch)

    def _submit(self, action: str, dispatch: Dispatch):
        if action == "stop_cancel":
            fn = lambda d: self.agent.stop(d, cancel=True)
        elif action == "stop_pause" or action == "stop_revision":
            fn = lambda d: self.agent.stop(d, cancel=False)
        else:
            fn = {"create": self.agent.create, "start": self.agent.start,
                  "observe": self.agent.observe, "reconcile": self.agent.observe,
                  "stop_observe": self.agent.observe, "resume": self.agent.resume}[action]
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
                self.budget.settle((row["repo"], row["issue_number"]), dispatch_id, None)
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
            if action == "resume":
                self.store.update_dispatch(dispatch_id, status="running")
                workflow = self.store.workflow(dispatch.issue)
                self._move(workflow, str(workflow["resume_state"]), resume_state=None, stop_requested=None)
                return
            if action.startswith("stop_") and action != "stop_observe":
                self._submit("stop_observe", dispatch)
                return
            if action == "stop_observe":
                workflow = self.store.workflow(dispatch.issue)
                if value.status in {"paused", "failed", "finished", "missing"}:
                    if workflow["stop_requested"] != "pause":
                        self._settle_observation(dispatch, value)
                    self._confirm_stop(dispatch, workflow)
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
            workflow = self.store.workflow(dispatch.issue)
            if status == "running" and self.clock() >= datetime.fromisoformat(dispatch.deadline) and not workflow["stop_requested"]:
                workflow = self.store.cas_workflow(dispatch.issue, workflow["version"], stop_requested="limit-timeout")
            if workflow["stop_requested"] and status in {"created", "running", "resuming"}:
                self.store.update_dispatch(dispatch.id, status="stopping")
                self._submit("stop_cancel" if str(workflow["stop_requested"]).startswith("limit-") else f"stop_{workflow['stop_requested']}", dispatch)
            elif status == "stopping":
                self._submit("stop_observe", dispatch)
            elif status == "resuming":
                self._submit("reconcile", dispatch)
            elif status == "retryable":
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

    def _confirm_stop(self, dispatch: Dispatch, row: dict[str, object]) -> None:
        request = row["stop_requested"]
        if request == "revision":
            self.store.update_dispatch(dispatch.id, status="stale")
            self.store.cas_workflow(dispatch.issue, row["version"], stop_requested=None)
        elif request == "cancel":
            self.store.update_dispatch(dispatch.id, status="cancelled")
            self._move(row, "cancelled", stop_requested=None)
        elif request == "pause":
            self.store.update_dispatch(dispatch.id, status="paused")
            self._move(row, "paused", stop_requested=None)
        elif request in {"limit-timeout", "limit-iterations"}:
            self.store.update_dispatch(dispatch.id, status="failed")
            self._move(row, "needs-human", stop_requested=None, reason=request.removeprefix("limit-"))

    @staticmethod
    def _as_dispatch(row: dict[str, object]) -> Dispatch:
        return Dispatch(row["id"], (row["repo"], row["issue_number"]), row["revision"],
                        row["role"], row["attempt"], row["workspace_id"], row["conversation_id"],
                        row["candidate_sha"], row["deadline"])

    def _observed(self, dispatch: Dispatch, observation: RunObservation) -> None:
        row = self.store.workflow(dispatch.issue)
        iterations = self._account_observation(dispatch, observation)
        if row["revision"] != dispatch.revision or row["stop_requested"]:
            if observation.status == "finished":
                self._settle_observation(dispatch, observation)
                self._confirm_stop(dispatch, row)
            return
        if self.clock() >= datetime.fromisoformat(dispatch.deadline):
            self.store.update_dispatch(dispatch.id, status="failed")
            self._settle_observation(dispatch, observation)
            self._move(row, "needs-human", reason="run timed out")
            return
        if observation.status in {"failed", "unknown", "missing"}:
            self.store.update_dispatch(dispatch.id, status="failed")
            self._settle_observation(dispatch, observation)
            self._move(row, "needs-human", reason=observation.error or observation.status)
            return
        if observation.status != "finished" and iterations >= self.config.max_iterations:
            self.store.cas_workflow(dispatch.issue, row["version"], stop_requested="limit-iterations")
            return
        if observation.status != "finished":
            return
        self._settle_observation(dispatch, observation)
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
        elif row["review_cycles"] < self.config.max_fix_cycles:
            self._move(row, "fixing", review_cycles=row["review_cycles"] + 1)
        else:
            self._move(row, "needs-human", reason="review correction exhausted")

    def _account_observation(self, dispatch: Dispatch, observation: RunObservation) -> int:
        row = self.store.dispatch_row(dispatch.id)
        iterations = int(row["iterations"])
        for usage in observation.usage:
            if usage.get("request_id") != dispatch.id:
                continue
            amount = usage.get("cumulative_microusd")
            if type(amount) is int and amount >= 0:
                self.budget.observe_cumulative(dispatch.issue, dispatch.id, amount)
            count = usage.get("iterations")
            if type(count) is int and count >= 0:
                iterations = max(iterations, count)
        if iterations != row["iterations"]:
            self.store.update_dispatch(dispatch.id, iterations=iterations)
        return iterations

    def _settle_observation(self, dispatch: Dispatch, observation: RunObservation) -> None:
        amounts = [usage.get("cumulative_microusd") for usage in observation.usage if usage.get("request_id") == dispatch.id]
        actual = max(amounts) if amounts and all(type(value) is int and value >= 0 for value in amounts) else None
        self.budget.settle(dispatch.issue, dispatch.id, actual)

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
        current = self.store.workflow(issue)
        if current["version"] != row["version"] or current["stop_requested"] or current["revision"] != row["revision"]:
            return
        # Publication is a fake in Plan 01. Production publication arrives in Plan 04.
        pr_url = self.delivery.publish(issue, sha)
        self._move(row, "reviewing", candidate_sha=sha, published_sha=sha, pr_url=pr_url)
