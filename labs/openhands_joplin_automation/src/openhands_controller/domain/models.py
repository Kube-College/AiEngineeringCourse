from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.dataclasses import dataclass

from .states import DispatchStatus, Role, RunStatus, StopRequest, WorkflowState

IssueKey = tuple[str, int]
MicroUSD = Annotated[int, Field(strict=True, ge=0)]


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    issue: IssueKey
    revision: str
    actor: str
    payload: dict[str, object]


@dataclass(frozen=True)
class Dispatch:
    id: str
    issue: IssueKey
    revision: str
    role: Role
    attempt: int
    workspace_id: str
    conversation_id: str | None
    candidate_sha: str | None
    deadline: str


class Usage(BaseModel):
    """One cumulative usage report from an agent run."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    cumulative_microusd: MicroUSD | None = None
    iterations: Annotated[int, Field(strict=True, ge=0)] | None = None


@dataclass(frozen=True)
class RunObservation:
    status: RunStatus
    result: dict[str, object] | None = None
    usage: tuple[Usage, ...] = ()
    error: str | None = None

    def usage_for(self, request_id: str) -> list[Usage]:
        return [usage for usage in self.usage if usage.request_id == request_id]


@dataclass(frozen=True)
class ValidationResult:
    candidate_sha: str
    profile: str
    passed: bool
    evidence_dir: str


class _Row(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    repo: str
    issue_number: int

    @property
    def issue(self) -> IssueKey:
        return self.repo, self.issue_number


class Workflow(_Row):
    revision: str
    title: str
    body: str
    state: WorkflowState
    version: int
    approval_revision: str | None
    reason: str | None
    resume_state: WorkflowState | None
    validation_profile: str | None
    candidate_sha: str | None
    published_sha: str | None
    pr_url: str | None
    review_cycles: int
    stop_requested: StopRequest | None
    budget_limit: int


class DispatchRecord(_Row):
    """A persisted dispatch with its execution status."""

    id: str
    revision: str
    role: Role
    attempt: int
    workspace_id: str
    conversation_id: str | None
    candidate_sha: str | None
    deadline: str
    status: DispatchStatus
    result_json: str | None
    iterations: int

    @property
    def dispatch(self) -> Dispatch:
        return Dispatch(self.id, self.issue, self.revision, self.role, self.attempt, self.workspace_id,
                        self.conversation_id, self.candidate_sha, self.deadline)
