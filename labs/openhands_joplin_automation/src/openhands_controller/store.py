import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from .contracts import Dispatch, Event, EventConflict, IssueKey, VersionConflict


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(files("openhands_controller").joinpath("schema.sql").read_text())

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.rollback()
                raise
            else:
                db.commit()

    def record_event(self, event: Event) -> bool:
        canonical = json.dumps(asdict(event), sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self.transaction() as db:
            row = db.execute("SELECT canonical_json FROM events WHERE event_id=?", (event.id,)).fetchone()
            if row:
                if row["canonical_json"] != canonical:
                    raise EventConflict(event.id)
                return False
            db.execute(
                "INSERT INTO events(event_id,repo,issue_number,kind,revision,actor,payload_json,canonical_json) VALUES(?,?,?,?,?,?,?,?)",
                (event.id, *event.issue, event.kind, event.revision, event.actor,
                 json.dumps(event.payload, sort_keys=True, allow_nan=False), canonical),
            )
            return True

    def create_workflow(self, issue: IssueKey, revision: str, *, title: str = "", body: str = "", budget_limit: int = 5_000_000) -> bool:
        with self.transaction() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO workflows(repo,issue_number,revision,title,body,state,budget_limit) VALUES(?,?,?,?,?,'queued',?)",
                (*issue, revision, title, body, budget_limit),
            )
            return cursor.rowcount == 1

    def workflow(self, issue: IssueKey) -> dict[str, object]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
            if row is None:
                raise KeyError(issue)
            return dict(row)

    def cas_workflow(self, issue: IssueKey, version: int, **changes: object) -> dict[str, object]:
        allowed = {"revision", "title", "body", "state", "approval_revision", "reason", "resume_state",
                   "validation_profile", "candidate_sha", "published_sha", "pr_url", "review_cycles",
                   "stop_requested", "budget_limit"}
        if not changes or set(changes) - allowed:
            raise ValueError("invalid workflow update")
        assignments = ", ".join(f"{name}=?" for name in changes)
        with self.transaction() as db:
            cursor = db.execute(
                f"UPDATE workflows SET {assignments}, version=version+1 WHERE repo=? AND issue_number=? AND version=?",
                (*changes.values(), *issue, version),
            )
            if cursor.rowcount != 1:
                raise VersionConflict(issue)
        return self.workflow(issue)

    def create_dispatch(self, dispatch: Dispatch, *, status: str = "intent") -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO dispatches(id,repo,issue_number,revision,role,attempt,workspace_id,conversation_id,candidate_sha,deadline,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (dispatch.id, *dispatch.issue, dispatch.revision, dispatch.role, dispatch.attempt,
                 dispatch.workspace_id, dispatch.conversation_id, dispatch.candidate_sha, dispatch.deadline, status),
            )

    def dispatches(self, issue: IssueKey) -> list[Dispatch]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM dispatches WHERE repo=? AND issue_number=? ORDER BY created_at, id", issue).fetchall()
        return [Dispatch(id=r["id"], issue=(r["repo"], r["issue_number"]), revision=r["revision"],
                         role=r["role"], attempt=r["attempt"], workspace_id=r["workspace_id"],
                         conversation_id=r["conversation_id"], candidate_sha=r["candidate_sha"],
                         deadline=r["deadline"]) for r in rows]

    def dispatch_row(self, dispatch_id: str) -> dict[str, object]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM dispatches WHERE id=?", (dispatch_id,)).fetchone()
            if row is None:
                raise KeyError(dispatch_id)
            return dict(row)

    def update_dispatch(self, dispatch_id: str, **changes: object) -> None:
        allowed = {"status", "conversation_id", "candidate_sha", "result_json", "request_hash"}
        if not changes or set(changes) - allowed:
            raise ValueError("invalid dispatch update")
        assignments = ", ".join(f"{name}=?" for name in changes)
        with self.transaction() as db:
            db.execute(f"UPDATE dispatches SET {assignments} WHERE id=?", (*changes.values(), dispatch_id))

    def active_dispatch(self) -> dict[str, object] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM dispatches WHERE status IN ('intent','retryable','created','running','resuming','uncertain','stopping') LIMIT 1").fetchone()
            return dict(row) if row else None

    def workflows(self) -> list[dict[str, object]]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM workflows ORDER BY repo, issue_number")]
