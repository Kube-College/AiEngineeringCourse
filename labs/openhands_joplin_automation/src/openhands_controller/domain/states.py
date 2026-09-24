from enum import StrEnum


class WorkflowState(StrEnum):
    QUEUED = "queued"
    TRIAGING = "triaging"
    AWAITING_APPROVAL = "awaiting-approval"
    IMPLEMENTING = "implementing"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    FIXING = "fixing"
    PAUSED = "paused"
    NEEDS_HUMAN = "needs-human"
    READY_FOR_HUMAN = "ready-for-human"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class Role(StrEnum):
    TRIAGE = "triage"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    FIX = "fix"


class DispatchStatus(StrEnum):
    INTENT = "intent"
    RETRYABLE = "retryable"
    CREATED = "created"
    RUNNING = "running"
    RESUMING = "resuming"
    UNCERTAIN = "uncertain"
    STOPPING = "stopping"
    PAUSED = "paused"
    FINISHED = "finished"
    FAILED = "failed"
    STALE = "stale"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    FAILED = "failed"
    UNKNOWN = "unknown"
    MISSING = "missing"


class StopRequest(StrEnum):
    REVISION = "revision"
    CANCEL = "cancel"
    PAUSE = "pause"
    TIMEOUT = "limit-timeout"
    ITERATIONS = "limit-iterations"

    @property
    def is_limit(self) -> bool:
        return self in {StopRequest.TIMEOUT, StopRequest.ITERATIONS}

    @property
    def cancels_remote(self) -> bool:
        return self is StopRequest.CANCEL or self.is_limit


S = WorkflowState

# Statuses covered by the one_active_dispatch index in schema.sql.
ACTIVE_DISPATCH = frozenset({
    DispatchStatus.INTENT, DispatchStatus.RETRYABLE, DispatchStatus.CREATED, DispatchStatus.RUNNING,
    DispatchStatus.RESUMING, DispatchStatus.UNCERTAIN, DispatchStatus.STOPPING,
})

ALLOWED: dict[WorkflowState, frozenset[WorkflowState]] = {state: frozenset(targets) for state, targets in {
    S.QUEUED: {S.TRIAGING, S.PAUSED, S.CANCELLED, S.NEEDS_HUMAN},
    S.TRIAGING: {S.AWAITING_APPROVAL, S.NEEDS_HUMAN, S.PAUSED, S.CANCELLED, S.QUEUED},
    S.AWAITING_APPROVAL: {S.IMPLEMENTING, S.PAUSED, S.CANCELLED, S.NEEDS_HUMAN, S.QUEUED},
    S.IMPLEMENTING: {S.VALIDATING, S.NEEDS_HUMAN, S.PAUSED, S.CANCELLED, S.QUEUED},
    S.VALIDATING: {S.REVIEWING, S.PAUSED, S.NEEDS_HUMAN, S.CANCELLED, S.QUEUED},
    S.REVIEWING: {S.FIXING, S.READY_FOR_HUMAN, S.NEEDS_HUMAN, S.PAUSED, S.CANCELLED, S.QUEUED},
    S.FIXING: {S.VALIDATING, S.NEEDS_HUMAN, S.PAUSED, S.CANCELLED, S.QUEUED},
    S.PAUSED: {S.AWAITING_APPROVAL, S.IMPLEMENTING, S.TRIAGING, S.VALIDATING, S.REVIEWING, S.FIXING,
               S.CANCELLED, S.NEEDS_HUMAN, S.QUEUED},
    S.NEEDS_HUMAN: {S.QUEUED, S.CANCELLED},
    S.READY_FOR_HUMAN: {S.COMPLETED, S.NEEDS_HUMAN, S.CANCELLED, S.QUEUED},
    S.CANCELLED: set(),
    S.COMPLETED: set(),
}.items()}

# Workflow states that wait for the scheduler to dispatch a role.
DISPATCH_ROLE = {S.QUEUED: Role.TRIAGE, S.IMPLEMENTING: Role.IMPLEMENTATION,
                 S.REVIEWING: Role.REVIEW, S.FIXING: Role.FIX}
# Workflow states the scheduler never advances on its own.
IDLE = frozenset({S.CANCELLED, S.COMPLETED, S.PAUSED, S.NEEDS_HUMAN, S.READY_FOR_HUMAN, S.AWAITING_APPROVAL})
TERMINAL = frozenset({S.CANCELLED, S.COMPLETED})
# Stages that may resume without a current approval.
PRE_APPROVAL = frozenset({S.QUEUED, S.TRIAGING, S.AWAITING_APPROVAL})


def check_transition(current: WorkflowState, target: WorkflowState) -> None:
    if target != current and target not in ALLOWED[current]:
        raise ValueError(f"invalid transition {current} -> {target}")
