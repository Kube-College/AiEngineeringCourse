"""Typed role outputs accepted from an agent run."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from .states import Role

NonEmpty = Annotated[str, Field(strict=True, min_length=1)]


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


class TriageResult(_Result):
    scope: NonEmpty
    summary: NonEmpty
    validation_profile: NonEmpty


class ChangeResult(_Result):
    summary: NonEmpty
    changed_paths: Annotated[list[NonEmpty], Field(min_length=1)]


class Finding(_Result):
    path: StrictStr
    line: Annotated[int, Field(gt=0)]
    explanation: StrictStr


class ReviewResult(_Result):
    candidate_sha: StrictStr
    verdict: Literal["pass", "changes_requested"]
    findings: list[Finding]


ROLE_RESULTS: dict[Role, type[_Result]] = {
    Role.TRIAGE: TriageResult,
    Role.IMPLEMENTATION: ChangeResult,
    Role.FIX: ChangeResult,
    Role.REVIEW: ReviewResult,
}
