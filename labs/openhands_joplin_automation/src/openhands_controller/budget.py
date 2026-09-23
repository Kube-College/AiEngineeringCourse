from .contracts import IssueKey
from .store import Store


def _money(value: object, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ValueError("money must be a nonnegative integer number of microdollars")
    return value


class Budget:
    """Issue-wide reservations and actual costs; no revision resets."""

    def __init__(self, store: Store):
        self.store = store

    def reserve(self, issue: IssueKey, request_id: str, estimate_microusd: int) -> bool:
        estimate = _money(estimate_microusd)
        if not request_id:
            raise ValueError("request ID is required")
        with self.store.transaction() as db:
            prior = db.execute("SELECT * FROM usage WHERE repo=? AND issue_number=? AND request_id=?", (*issue, request_id)).fetchone()
            if prior:
                if prior["reserved_microusd"] != estimate:
                    raise ValueError("request ID reused with different estimate")
                return prior["status"] != "unknown"
            if db.execute("SELECT 1 FROM usage WHERE repo=? AND issue_number=? AND status='unknown' LIMIT 1", issue).fetchone():
                return False
            limit = db.execute("SELECT budget_limit FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
            if not limit:
                raise KeyError(issue)
            spent = db.execute(
                "SELECT COALESCE(SUM(CASE WHEN status='settled' THEN actual_microusd ELSE max(reserved_microusd, COALESCE(reported_microusd,0)) END),0) AS total FROM usage WHERE repo=? AND issue_number=?",
                issue,
            ).fetchone()["total"]
            if spent + estimate > limit["budget_limit"]:
                return False
            db.execute("INSERT INTO usage(repo,issue_number,request_id,reserved_microusd,status) VALUES(?,?,?,?,?)",
                       (*issue, request_id, estimate, "reserved"))
            return True

    def observe_cumulative(self, issue: IssueKey, request_id: str, cumulative_microusd: int) -> None:
        amount = _money(cumulative_microusd, allow_zero=True)
        with self.store.transaction() as db:
            row = db.execute("SELECT reported_microusd FROM usage WHERE repo=? AND issue_number=? AND request_id=?",
                             (*issue, request_id)).fetchone()
            if not row:
                raise KeyError(request_id)
            db.execute("UPDATE usage SET reported_microusd=? WHERE repo=? AND issue_number=? AND request_id=?",
                       (max(row["reported_microusd"] or 0, amount), *issue, request_id))

    def settle(self, issue: IssueKey, request_id: str, actual_microusd: int | None) -> None:
        actual = None if actual_microusd is None else _money(actual_microusd, allow_zero=True)
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

    def increase(self, issue: IssueKey, total_microusd: int, event_id: str) -> None:
        total = _money(total_microusd)
        if not event_id:
            raise ValueError("event ID is required")
        with self.store.transaction() as db:
            prior = db.execute("SELECT * FROM budget_increases WHERE event_id=?", (event_id,)).fetchone()
            if prior:
                if (prior["repo"], prior["issue_number"], prior["total_microusd"]) != (*issue, total):
                    raise ValueError("budget event ID conflicts with prior increase")
                return
            row = db.execute("SELECT budget_limit FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
            if not row:
                raise KeyError(issue)
            if total <= row["budget_limit"]:
                raise ValueError("new total must exceed the current allowance")
            db.execute("UPDATE workflows SET budget_limit=?, version=version+1 WHERE repo=? AND issue_number=?",
                       (total, *issue))
            db.execute("INSERT INTO budget_increases(event_id,repo,issue_number,total_microusd) VALUES(?,?,?,?)",
                       (event_id, *issue, total))

    def snapshot(self, issue: IssueKey) -> dict[str, int | bool]:
        with self.store.connection() as db:
            row = db.execute("SELECT budget_limit FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
            if not row:
                raise KeyError(issue)
            sums = db.execute("""SELECT
                COALESCE(SUM(reserved_microusd),0) AS estimated,
                COALESCE(SUM(CASE WHEN status='reserved' THEN reserved_microusd ELSE 0 END),0) AS reserved,
                COALESCE(SUM(CASE WHEN status='settled' THEN actual_microusd ELSE 0 END),0) AS actual,
                COALESCE(SUM(reported_microusd),0) AS reported,
                COALESCE(SUM(CASE WHEN status='unknown' THEN 1 ELSE 0 END),0) AS unknown
                FROM usage WHERE repo=? AND issue_number=?""", issue).fetchone()
            return {"limit_microusd": row["budget_limit"], "estimated_microusd": sums["estimated"],
                    "reserved_microusd": sums["reserved"],
                    "actual_microusd": sums["actual"], "reported_microusd": sums["reported"],
                    "unknown": bool(sums["unknown"])}
