import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from ..domain.errors import EventConflict, VersionConflict
from ..domain.models import Dispatch, DispatchRecord, Event, IssueKey, ValidationResult, Workflow
from ..domain.states import ACTIVE_DISPATCH, DispatchStatus

_WORKFLOW_FIELDS = Workflow.model_fields.keys() - {"repo", "issue_number", "version"}
_TRANSITION_FIELDS = _WORKFLOW_FIELDS - {"state", "revision", "title", "body", "budget_limit"}
_DISPATCH_FIELDS = {"status", "conversation_id", "candidate_sha", "result_json", "request_hash", "iterations"}
_ACTIVE = ", ".join(f"'{status}'" for status in sorted(ACTIVE_DISPATCH))


def _assignments(changes: dict[str, object], allowed: set[str], what: str) -> str:
    if set(changes) - allowed:
        raise ValueError(f"invalid {what} fields")
    return "".join(f", {name}=?" for name in changes)


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript(files(__package__).joinpath("schema.sql").read_text())
            columns = {row["name"] for row in db.execute("PRAGMA table_info(dispatches)")}
        if "iterations" not in columns:
            with self.transaction() as db:
                db.execute("ALTER TABLE dispatches ADD COLUMN iterations INTEGER NOT NULL DEFAULT 0")
        with self.connection() as db:
            workspace_columns = {row["name"] for row in db.execute("PRAGMA table_info(workspaces)")}
        for name, definition in {
            "schema_version": "INTEGER NOT NULL DEFAULT 1",
            "sdk_version": "TEXT NOT NULL DEFAULT '1.48.0'",
            "owned": "INTEGER NOT NULL DEFAULT 1",
            "host_port": "INTEGER",
            "auth_hash": "TEXT",
        }.items():
            if name not in workspace_columns:
                with self.transaction() as db:
                    db.execute(f"ALTER TABLE workspaces ADD COLUMN {name} {definition}")

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

    def event_outcome(self, event_id: str) -> str:
        with self.connection() as db:
            row = db.execute("SELECT outcome FROM events WHERE event_id=?", (event_id,)).fetchone()
            if not row:
                raise KeyError(event_id)
            return row["outcome"]

    def mark_event_processed(self, event_id: str) -> None:
        with self.transaction() as db:
            db.execute("UPDATE events SET outcome='processed' WHERE event_id=?", (event_id,))

    def create_workflow(self, issue: IssueKey, revision: str, *, budget_limit: int, title: str = "", body: str = "") -> bool:
        with self.transaction() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO workflows(repo,issue_number,revision,title,body,state,budget_limit) VALUES(?,?,?,?,?,'queued',?)",
                (*issue, revision, title, body, budget_limit),
            )
            return cursor.rowcount == 1

    def workflow(self, issue: IssueKey) -> Workflow:
        with self.connection() as db:
            row = db.execute("SELECT * FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
        if row is None:
            raise KeyError(issue)
        return Workflow.model_validate(dict(row))

    def workflows(self) -> list[Workflow]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM workflows ORDER BY repo, issue_number").fetchall()
        return [Workflow.model_validate(dict(row)) for row in rows]

    def cas_workflow(self, issue: IssueKey, version: int, **changes: object) -> Workflow:
        if not changes:
            raise ValueError("invalid workflow update")
        extra = _assignments(changes, _WORKFLOW_FIELDS, "workflow update")
        with self.transaction() as db:
            row = db.execute(
                f"UPDATE workflows SET version=version+1{extra} WHERE repo=? AND issue_number=? AND version=? RETURNING *",
                (*changes.values(), *issue, version),
            ).fetchone()
        if row is None:
            raise VersionConflict(issue)
        return Workflow.model_validate(dict(row))

    def create_dispatch(self, dispatch: Dispatch, *, status: DispatchStatus = DispatchStatus.INTENT) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO dispatches(id,repo,issue_number,revision,role,attempt,workspace_id,conversation_id,candidate_sha,deadline,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (dispatch.id, *dispatch.issue, dispatch.revision, dispatch.role, dispatch.attempt,
                 dispatch.workspace_id, dispatch.conversation_id, dispatch.candidate_sha, dispatch.deadline, status),
            )

    def dispatches(self, issue: IssueKey) -> list[DispatchRecord]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM dispatches WHERE repo=? AND issue_number=? ORDER BY rowid", issue).fetchall()
        return [DispatchRecord.model_validate(dict(row)) for row in rows]

    def dispatch(self, dispatch_id: str) -> DispatchRecord:
        with self.connection() as db:
            row = db.execute("SELECT * FROM dispatches WHERE id=?", (dispatch_id,)).fetchone()
        if row is None:
            raise KeyError(dispatch_id)
        return DispatchRecord.model_validate(dict(row))

    def active_dispatch(self) -> DispatchRecord | None:
        with self.connection() as db:
            row = db.execute(f"SELECT * FROM dispatches WHERE status IN ({_ACTIVE}) LIMIT 1").fetchone()
        return DispatchRecord.model_validate(dict(row)) if row else None

    def update_dispatch(self, dispatch_id: str, **changes: object) -> None:
        if not changes:
            raise ValueError("invalid dispatch update")
        assignments = _assignments(changes, _DISPATCH_FIELDS, "dispatch update").removeprefix(", ")
        with self.transaction() as db:
            db.execute(f"UPDATE dispatches SET {assignments} WHERE id=?", (*changes.values(), dispatch_id))

    def transition_dispatch(self, dispatch_id: str, issue: IssueKey, version: int,
                            state: str, status: str, result_json: str | None = None,
                            **changes: object) -> None:
        extra = _assignments(changes, _TRANSITION_FIELDS, "workflow transition")
        with self.transaction() as db:
            updated = db.execute("UPDATE dispatches SET status=?, result_json=? WHERE id=? AND repo=? AND issue_number=?",
                                 (status, result_json, dispatch_id, *issue))
            if updated.rowcount != 1:
                raise KeyError(dispatch_id)
            updated = db.execute(
                f"UPDATE workflows SET state=?, version=version+1{extra} WHERE repo=? AND issue_number=? AND version=?",
                (state, *changes.values(), *issue, version),
            )
            if updated.rowcount != 1:
                raise VersionConflict(issue)

    def record_validation(self, issue: IssueKey, candidate_sha: str, result: ValidationResult) -> None:
        with self.transaction() as db:
            db.execute("INSERT INTO validations(repo,issue_number,candidate_sha,profile,passed,evidence_dir) VALUES(?,?,?,?,?,?)",
                       (*issue, candidate_sha, result.profile, int(result.passed), result.evidence_dir))
