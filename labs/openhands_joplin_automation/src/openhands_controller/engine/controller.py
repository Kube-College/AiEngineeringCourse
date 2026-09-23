import json
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from enum import StrEnum
from functools import partial
from typing import Callable

from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..domain.commands import parse_command
from ..domain.errors import CreateNotSent
from ..domain.models import Dispatch, DispatchRecord, Event, IssueKey, RunObservation, Workflow
from ..domain.ports import AgentAdapter, Delivery
from ..domain.results import ROLE_RESULTS, ReviewResult, TriageResult
from ..domain.states import (ALLOWED, DISPATCH_ROLE, IDLE, PRE_APPROVAL, TERMINAL, DispatchStatus, Role,
                             RunStatus, StopRequest, WorkflowState, check_transition)
from ..persistence.budget import Budget
from ..persistence.store import Store
from .lock import SchedulerLock

S, D = WorkflowState, DispatchStatus
WRITE_PERMISSIONS = {"write", "maintain", "admin"}


class Action(StrEnum):
    CREATE = "create"
    START = "start"
    OBSERVE = "observe"
    RECONCILE = "reconcile"
    STOP = "stop"
    STOP_OBSERVE = "stop_observe"
    RESUME = "resume"


# Adapter call that advances an active dispatch in each status.
NEXT_ACTION = {D.STOPPING: Action.STOP_OBSERVE, D.RESUMING: Action.RECONCILE, D.RETRYABLE: Action.CREATE,
               D.CREATED: Action.RECONCILE, D.RUNNING: Action.OBSERVE}
# Dispatch status recorded once a requested stop is confirmed.
STOPPED_STATUS = {StopRequest.REVISION: D.STALE, StopRequest.CANCEL: D.CANCELLED, StopRequest.PAUSE: D.PAUSED,
                  StopRequest.TIMEOUT: D.FAILED, StopRequest.ITERATIONS: D.FAILED}
STOPPED_STATE = {StopRequest.CANCEL: S.CANCELLED, StopRequest.PAUSE: S.PAUSED}


class Controller:
    def __init__(self, store: Store, agent: AgentAdapter, delivery: Delivery,
                 permissions: Callable[[str, str], str], clock: Callable[[], datetime],
                 settings: Settings | None = None):
        self.store, self.agent, self.delivery = store, agent, delivery
        self.permissions, self.clock = permissions, clock
        self.settings = settings or Settings()
        self.budget = Budget(store)
        self._lock = SchedulerLock(store.path.parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-adapter")
        self._pending: tuple[Action, str, Future] | None = None

    def close(self):
        self._pool.shutdown(wait=True, cancel_futures=True)
        self._lock.close()

    def wait(self, timeout: float | None = None) -> None:
        """Block until the pending adapter call, if any, completes."""
        if self._pending:
            wait([self._pending[2]], timeout)

    def _move(self, row: Workflow, state: WorkflowState, **changes: object) -> Workflow:
        check_transition(row.state, state)
        return self.store.cas_workflow(row.issue, row.version, state=state, **changes)

    def _finish(self, row: Workflow, dispatch: Dispatch, state: WorkflowState,
                *, status: DispatchStatus = D.FINISHED, result: dict[str, object] | None = None,
                **changes: object) -> None:
        check_transition(row.state, state)
        self.store.transition_dispatch(dispatch.id, dispatch.issue, row.version, state, status,
                                       json.dumps(result, sort_keys=True) if result is not None else None,
                                       **changes)

    def _is_active(self, issue: IssueKey) -> bool:
        active = self.store.active_dispatch()
        return active is not None and active.issue == issue

    def _expired(self, dispatch: Dispatch) -> bool:
        return self.clock() >= datetime.fromisoformat(dispatch.deadline)

    # Events

    def handle(self, event: Event) -> None:
        self.store.record_event(event)
        if self.store.event_outcome(event.id) == "processed":
            return
        self._apply_event(event)
        self.store.mark_event_processed(event.id)

    def _apply_event(self, event: Event) -> None:
        if event.kind == "issue":
            self._apply_issue(event)
            return
        command = self._authorised_command(event)
        if command is None:
            return
        name, total = command
        row = self.store.workflow(event.issue)
        match name:
            case "budget":
                try:
                    self.budget.increase(event.issue, total, event.id)
                except ValueError:
                    pass
            case "implement":
                if row.state == S.AWAITING_APPROVAL:
                    self._move(row, S.IMPLEMENTING, approval_revision=row.revision, stop_requested=None)
            case "cancel":
                if row.state in TERMINAL:
                    return
                if self._is_active(event.issue):
                    self.store.cas_workflow(event.issue, row.version, stop_requested=StopRequest.CANCEL)
                else:
                    self._move(row, S.CANCELLED, stop_requested=None)
            case "pause":
                if row.state == S.PAUSED or row.stop_requested or S.PAUSED not in ALLOWED[row.state]:
                    return
                if self._is_active(event.issue):
                    self.store.cas_workflow(event.issue, row.version, stop_requested=StopRequest.PAUSE,
                                            resume_state=row.state)
                else:
                    self._move(row, S.PAUSED, resume_state=row.state)
            case "resume":
                self._resume(row)

    def _apply_issue(self, event: Event) -> None:
        title = str(event.payload.get("title", ""))
        body = str(event.payload.get("body", ""))
        if self.store.create_workflow(event.issue, event.revision, title=title, body=body,
                                      budget_limit=self.settings.issue_budget_microusd):
            return
        row = self.store.workflow(event.issue)
        if row.revision != event.revision:
            self._move(row, S.QUEUED, revision=event.revision, title=title, body=body,
                       approval_revision=None,
                       stop_requested=StopRequest.REVISION if self._is_active(event.issue) else None,
                       review_cycles=0, reason="issue changed")

    def _authorised_command(self, event: Event) -> tuple[str, int | None] | None:
        payload = event.payload
        if event.kind not in {"command", "label"} or payload.get("projection"):
            return None
        if payload.get("action") == "edited" or event.revision != self.store.workflow(event.issue).revision:
            return None
        if event.kind == "label":
            approved = payload.get("action") == "added" and payload.get("label") == "agent:implement"
            parsed = ("implement", None) if approved else None
        else:
            parsed = parse_command(str(payload.get("body", "")))
        if parsed is None:
            return None
        try:
            permission = self.permissions(event.actor, event.issue[0])
        except Exception:
            return None
        return parsed if permission in WRITE_PERMISSIONS else None

    def _resume(self, row: Workflow) -> None:
        if row.state != S.PAUSED:
            return
        stage = row.resume_state
        if stage not in PRE_APPROVAL and row.approval_revision != row.revision:
            return
        if self.budget.has_unknown(row.issue) or self.store.active_dispatch():
            return
        paused = [d for d in self.store.dispatches(row.issue) if d.revision == row.revision and d.status == D.PAUSED]
        if not paused:
            if stage in ALLOWED[S.PAUSED]:
                self._move(row, stage, resume_state=None)
            return
        self.store.update_dispatch(paused[-1].id, status=D.RESUMING)
        self._submit(Action.RESUME, paused[-1].dispatch)

    # Scheduling

    def tick(self) -> None:
        if self._pending:
            action, dispatch_id, future = self._pending
            if future.done():
                self._pending = None
                self._complete(action, self.store.dispatch(dispatch_id), future)
            return
        active = self.store.active_dispatch()
        if active:
            self._advance(active)
        else:
            self._schedule_next()

    def _submit(self, action: Action, dispatch: Dispatch, *, cancel: bool = False) -> None:
        match action:
            case Action.CREATE:
                call = self.agent.create
            case Action.START:
                call = self.agent.start
            case Action.RESUME:
                call = self.agent.resume
            case Action.STOP:
                call = partial(self.agent.stop, cancel=cancel)
            case _:
                call = self.agent.observe
        self._pending = (action, dispatch.id, self._pool.submit(call, dispatch))

    def _complete(self, action: Action, record: DispatchRecord, future: Future) -> None:
        try:
            value = future.result()
        except CreateNotSent:
            self.store.update_dispatch(record.id, status=D.RETRYABLE)
            raise
        except Exception as exc:
            self.store.update_dispatch(record.id, status=D.UNCERTAIN)
            self.budget.settle(record.issue, record.id, None)
            self._move(self.store.workflow(record.issue), S.NEEDS_HUMAN, reason=f"uncertain {action}: {exc}")
            raise
        dispatch = record.dispatch
        match action:
            case Action.CREATE:
                self.store.update_dispatch(dispatch.id, status=D.CREATED, conversation_id=value)
            case Action.START:
                self.store.update_dispatch(dispatch.id, status=D.RUNNING)
            case Action.RESUME:
                self.store.update_dispatch(dispatch.id, status=D.RUNNING)
                row = self.store.workflow(dispatch.issue)
                if not row.stop_requested and row.revision == dispatch.revision:
                    self._move(row, row.resume_state, resume_state=None)
            case Action.STOP:
                self._submit(Action.STOP_OBSERVE, dispatch)
            case Action.STOP_OBSERVE:
                row = self.store.workflow(dispatch.issue)
                if value.status in {RunStatus.PAUSED, RunStatus.FAILED, RunStatus.FINISHED, RunStatus.MISSING}:
                    if row.stop_requested != StopRequest.PAUSE:
                        self._settle_observation(dispatch, value)
                    self._confirm_stop(dispatch, row)
            case Action.RECONCILE:
                if value.status == RunStatus.RUNNING:
                    self.store.update_dispatch(dispatch.id, status=D.RUNNING)
                elif value.status == RunStatus.CREATED:
                    self._submit(Action.START, dispatch)
                else:
                    self.store.update_dispatch(dispatch.id, status=D.UNCERTAIN)
                    self._move(self.store.workflow(dispatch.issue), S.NEEDS_HUMAN,
                               reason="remote start cannot be reconciled")
            case Action.OBSERVE:
                self._observed(record, value)

    def _advance(self, active: DispatchRecord) -> None:
        dispatch, status = active.dispatch, active.status
        row = self.store.workflow(dispatch.issue)
        if status == D.RUNNING and self._expired(dispatch) and not row.stop_requested:
            row = self.store.cas_workflow(dispatch.issue, row.version, stop_requested=StopRequest.TIMEOUT)
        if row.stop_requested and status in {D.CREATED, D.RUNNING, D.RESUMING}:
            self.store.update_dispatch(dispatch.id, status=D.STOPPING)
            self._submit(Action.STOP, dispatch, cancel=row.stop_requested.cancels_remote)
        elif status in NEXT_ACTION:
            self._submit(NEXT_ACTION[status], dispatch)
        elif status in {D.INTENT, D.UNCERTAIN}:
            self.store.update_dispatch(dispatch.id, status=D.UNCERTAIN)
            if row.state != S.NEEDS_HUMAN:
                self._move(row, S.NEEDS_HUMAN, reason="remote creation identity is uncertain")

    def _schedule_next(self) -> None:
        for row in self.store.workflows():
            if row.stop_requested or row.state in IDLE:
                continue
            if row.state == S.VALIDATING:
                self._validate(row)
                return
            if role := DISPATCH_ROLE.get(row.state):
                self._dispatch(row, role)
                return

    def _dispatch(self, row: Workflow, role: Role) -> None:
        issue = row.issue
        attempt = 1 + sum(d.revision == row.revision and d.role == role for d in self.store.dispatches(issue))
        dispatch_id = f"{issue[0].replace('/', '-')}-{issue[1]}-{row.revision}-{role}-{attempt}"
        if not self.budget.reserve(issue, dispatch_id, self.settings.dispatch_estimate_microusd):
            self._move(row, S.NEEDS_HUMAN, reason="budget exhausted or unknown")
            return
        dispatch = Dispatch(dispatch_id, issue, row.revision, role, attempt,
                            f"workspace-{issue[1]}", None, row.candidate_sha,
                            (self.clock() + timedelta(seconds=self.settings.run_timeout_seconds)).isoformat())
        self.store.create_dispatch(dispatch)
        if role == Role.TRIAGE:
            self._move(row, S.TRIAGING)
        self._submit(Action.CREATE, dispatch)

    def _confirm_stop(self, dispatch: Dispatch, row: Workflow) -> None:
        request = row.stop_requested
        if request is None:
            return
        self.store.update_dispatch(dispatch.id, status=STOPPED_STATUS[request])
        if request is StopRequest.REVISION:
            self.store.cas_workflow(dispatch.issue, row.version, stop_requested=None)
        elif request.is_limit:
            self._move(row, S.NEEDS_HUMAN, stop_requested=None, reason=request.removeprefix("limit-"))
        else:
            self._move(row, STOPPED_STATE[request], stop_requested=None)

    # Observations

    def _observed(self, record: DispatchRecord, observation: RunObservation) -> None:
        dispatch = record.dispatch
        row = self.store.workflow(dispatch.issue)
        iterations = self._account_observation(record, observation)
        status = observation.status
        if row.revision != dispatch.revision or row.stop_requested:
            if status == RunStatus.FINISHED:
                self._settle_observation(dispatch, observation)
                self._confirm_stop(dispatch, row)
            return
        if self._expired(dispatch):
            if status in {RunStatus.RUNNING, RunStatus.CREATED, RunStatus.PAUSED}:
                self.store.cas_workflow(dispatch.issue, row.version, stop_requested=StopRequest.TIMEOUT)
            elif status == RunStatus.FINISHED:
                self._settle_observation(dispatch, observation)
                self._finish(row, dispatch, S.NEEDS_HUMAN, status=D.FAILED, reason="run timed out")
            else:
                self.budget.settle(dispatch.issue, dispatch.id, None)
                self._finish(row, dispatch, S.NEEDS_HUMAN, status=D.UNCERTAIN,
                             reason="remote status after deadline is uncertain")
            return
        if status in {RunStatus.UNKNOWN, RunStatus.MISSING}:
            self.budget.settle(dispatch.issue, dispatch.id, None)
            self._finish(row, dispatch, S.NEEDS_HUMAN, status=D.UNCERTAIN, reason=observation.error or status)
            return
        if status == RunStatus.FAILED:
            self._settle_observation(dispatch, observation)
            self._finish(row, dispatch, S.NEEDS_HUMAN, status=D.FAILED, reason=observation.error or status)
            return
        if status != RunStatus.FINISHED:
            if iterations >= self.settings.max_iterations:
                self.store.cas_workflow(dispatch.issue, row.version, stop_requested=StopRequest.ITERATIONS)
            return
        self._settle_observation(dispatch, observation)
        result = self._parse_result(dispatch, observation.result)
        raw = observation.result
        if result is None:
            self._finish(row, dispatch, S.NEEDS_HUMAN, status=D.FAILED, reason="invalid role result")
        elif isinstance(result, TriageResult):
            self._finish(row, dispatch, S.AWAITING_APPROVAL, result=raw,
                         validation_profile=result.validation_profile)
        elif not isinstance(result, ReviewResult):
            self._finish(row, dispatch, S.VALIDATING, result=raw)
        elif result.verdict == "pass":
            self._finish(row, dispatch, S.READY_FOR_HUMAN, result=raw)
        elif row.review_cycles < self.settings.max_fix_cycles:
            self._finish(row, dispatch, S.FIXING, result=raw, review_cycles=row.review_cycles + 1)
        else:
            self._finish(row, dispatch, S.NEEDS_HUMAN, result=raw, reason="review correction exhausted")

    def _account_observation(self, record: DispatchRecord, observation: RunObservation) -> int:
        reports = observation.usage_for(record.id)
        for usage in reports:
            if usage.cumulative_microusd is not None:
                self.budget.observe_cumulative(record.issue, record.id, usage.cumulative_microusd)
        iterations = max([record.iterations, *(u.iterations for u in reports if u.iterations is not None)])
        if iterations != record.iterations:
            self.store.update_dispatch(record.id, iterations=iterations)
        return iterations

    def _settle_observation(self, dispatch: Dispatch, observation: RunObservation) -> None:
        amounts = [usage.cumulative_microusd for usage in observation.usage_for(dispatch.id)]
        actual = max(amounts) if amounts and None not in amounts else None
        self.budget.settle(dispatch.issue, dispatch.id, actual)

    @staticmethod
    def _parse_result(dispatch: Dispatch, raw: object) -> BaseModel | None:
        try:
            result = ROLE_RESULTS[dispatch.role].model_validate(raw)
        except ValidationError:
            return None
        if isinstance(result, ReviewResult) and result.candidate_sha != dispatch.candidate_sha:
            return None
        return result

    # Delivery

    def _validate(self, row: Workflow) -> None:
        issue = row.issue
        last = self.store.dispatches(issue)[-1].dispatch
        sha = self.delivery.capture(last)
        result = self.delivery.validate(sha, str(row.validation_profile))
        self.store.record_validation(issue, sha, result)
        if not result.passed or result.candidate_sha != sha:
            self._move(row, S.NEEDS_HUMAN, reason="validation failed")
            return
        current = self.store.workflow(issue)
        if current.version != row.version or current.stop_requested or current.revision != row.revision:
            return
        # Publication is a fake in Plan 01. Production publication arrives in Plan 04.
        pr_url = self.delivery.publish(issue, sha)
        self._move(row, S.REVIEWING, candidate_sha=sha, published_sha=sha, pr_url=pr_url)
