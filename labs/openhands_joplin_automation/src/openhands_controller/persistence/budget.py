import sqlite3
from typing import Annotated

from pydantic import BaseModel, Field, validate_call

from ..domain.models import IssueKey, MicroUSD
from .store import Store

PositiveMicroUSD = Annotated[int, Field(strict=True, gt=0)]
RequiredId = Annotated[str, Field(min_length=1)]


class BudgetSnapshot(BaseModel):
    limit_microusd: int
    estimated_microusd: int
    reserved_microusd: int
    actual_microusd: int
    reported_microusd: int
    unknown: bool


def _limit(db: sqlite3.Connection, issue: IssueKey) -> int:
    row = db.execute("SELECT budget_limit FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
    if not row:
        raise KeyError(issue)
    return row["budget_limit"]


def _has_unknown(db: sqlite3.Connection, issue: IssueKey) -> bool:
    return db.execute("SELECT 1 FROM usage WHERE repo=? AND issue_number=? AND status='unknown' LIMIT 1",
                      issue).fetchone() is not None


class Budget:
    """Issue-wide reservations and actual costs; no revision resets."""

    def __init__(self, store: Store):
        self.store = store

    def has_unknown(self, issue: IssueKey) -> bool:
        with self.store.connection() as db:
            return _has_unknown(db, issue)

    def recover_reserved(self, issue: IssueKey) -> None:
        """A new gateway cannot know whether old in-flight calls were billed."""
        with self.store.transaction() as db:
            db.execute("UPDATE usage SET status='unknown' WHERE repo=? AND issue_number=? AND status='reserved'", issue)

    def can_start_request(self, issue: IssueKey) -> bool:
        """Check whether any positive request reservation could be made."""
        with self.store.connection() as db:
            if _has_unknown(db, issue):
                return False
            spent = db.execute(
                "SELECT COALESCE(SUM(CASE WHEN status='settled' THEN actual_microusd ELSE max(reserved_microusd, COALESCE(reported_microusd,0)) END),0) AS total FROM usage WHERE repo=? AND issue_number=?",
                issue,
            ).fetchone()["total"]
            return spent < _limit(db, issue)

    @validate_call
    def reserve(self, issue: IssueKey, request_id: RequiredId, estimate: PositiveMicroUSD) -> bool:
        with self.store.transaction() as db:
            prior = db.execute("SELECT * FROM usage WHERE repo=? AND issue_number=? AND request_id=?", (*issue, request_id)).fetchone()
            if prior:
                if prior["reserved_microusd"] != estimate:
                    raise ValueError("request ID reused with different estimate")
                return prior["status"] != "unknown"
            if _has_unknown(db, issue):
                return False
            limit = _limit(db, issue)
            spent = db.execute(
                "SELECT COALESCE(SUM(CASE WHEN status='settled' THEN actual_microusd ELSE max(reserved_microusd, COALESCE(reported_microusd,0)) END),0) AS total FROM usage WHERE repo=? AND issue_number=?",
                issue,
            ).fetchone()["total"]
            if spent + estimate > limit:
                return False
            db.execute("INSERT INTO usage(repo,issue_number,request_id,reserved_microusd,status) VALUES(?,?,?,?,?)",
                       (*issue, request_id, estimate, "reserved"))
            return True

    @validate_call
    def observe_cumulative(self, issue: IssueKey, request_id: str, amount: MicroUSD) -> None:
        with self.store.transaction() as db:
            row = db.execute("SELECT reported_microusd FROM usage WHERE repo=? AND issue_number=? AND request_id=?",
                             (*issue, request_id)).fetchone()
            if not row:
                raise KeyError(request_id)
            db.execute("UPDATE usage SET reported_microusd=? WHERE repo=? AND issue_number=? AND request_id=?",
                       (max(row["reported_microusd"] or 0, amount), *issue, request_id))

    @validate_call
    def settle(self, issue: IssueKey, request_id: str, actual: MicroUSD | None) -> None:
        with self.store.transaction() as db:
            row = db.execute("SELECT status,actual_microusd,reported_microusd FROM usage WHERE repo=? AND issue_number=? AND request_id=?",
                             (*issue, request_id)).fetchone()
            if not row:
                raise KeyError(request_id)
            if actual is not None:
                actual = max(actual, row["reported_microusd"] or 0)
            if row["status"] == "settled":
                if row["actual_microusd"] != actual:
                    raise ValueError("settlement conflicts with recorded actual cost")
                return
            if row["status"] == "unknown" and actual is None:
                return
            db.execute("UPDATE usage SET status=?, actual_microusd=? WHERE repo=? AND issue_number=? AND request_id=?",
                       ("unknown" if actual is None else "settled", actual, *issue, request_id))

    @validate_call
    def increase(self, issue: IssueKey, total: PositiveMicroUSD, event_id: RequiredId) -> None:
        with self.store.transaction() as db:
            prior = db.execute("SELECT * FROM budget_increases WHERE event_id=?", (event_id,)).fetchone()
            if prior:
                if (prior["repo"], prior["issue_number"], prior["total_microusd"]) != (*issue, total):
                    raise ValueError("budget event ID conflicts with prior increase")
                return
            if total <= _limit(db, issue):
                raise ValueError("new total must exceed the current allowance")
            db.execute("UPDATE workflows SET budget_limit=?, version=version+1 WHERE repo=? AND issue_number=?",
                       (total, *issue))
            db.execute("INSERT INTO budget_increases(event_id,repo,issue_number,total_microusd) VALUES(?,?,?,?)",
                       (event_id, *issue, total))

    def snapshot(self, issue: IssueKey) -> BudgetSnapshot:
        with self.store.connection() as db:
            limit = _limit(db, issue)
            sums = db.execute("""SELECT
                COALESCE(SUM(reserved_microusd),0) AS estimated,
                COALESCE(SUM(CASE WHEN status='reserved' THEN reserved_microusd ELSE 0 END),0) AS reserved,
                COALESCE(SUM(CASE WHEN status='settled' THEN actual_microusd ELSE 0 END),0) AS actual,
                COALESCE(SUM(reported_microusd),0) AS reported,
                COALESCE(SUM(CASE WHEN status='unknown' THEN 1 ELSE 0 END),0) AS unknown
                FROM usage WHERE repo=? AND issue_number=?""", issue).fetchone()
        return BudgetSnapshot(limit_microusd=limit, estimated_microusd=sums["estimated"],
                              reserved_microusd=sums["reserved"], actual_microusd=sums["actual"],
                              reported_microusd=sums["reported"], unknown=bool(sums["unknown"]))
