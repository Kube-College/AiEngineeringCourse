from dataclasses import dataclass
from typing import Protocol

IssueKey = tuple[str, int]


class EventConflict(ValueError):
    """An event identity was reused with different content."""


class VersionConflict(ValueError):
    """A workflow was changed by another writer."""


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
    role: str
    attempt: int
    workspace_id: str
    conversation_id: str | None
    candidate_sha: str | None
    deadline: str


@dataclass(frozen=True)
class RunObservation:
    status: str
    result: dict[str, object] | None = None
    usage: tuple[dict[str, object], ...] = ()
    error: str | None = None


class AgentAdapter(Protocol):
    def create(self, dispatch: Dispatch) -> str: ...
    def start(self, dispatch: Dispatch) -> None: ...
    def observe(self, dispatch: Dispatch) -> RunObservation: ...
    def stop(self, dispatch: Dispatch, *, cancel: bool) -> None: ...
    def resume(self, dispatch: Dispatch) -> None: ...


@dataclass(frozen=True)
class ValidationResult:
    candidate_sha: str
    profile: str
    passed: bool
    evidence_dir: str


class Delivery(Protocol):
    def capture(self, dispatch: Dispatch) -> str: ...
    def validate(self, candidate_sha: str, profile: str) -> ValidationResult: ...
    def publish(self, issue: IssueKey, candidate_sha: str) -> str: ...
