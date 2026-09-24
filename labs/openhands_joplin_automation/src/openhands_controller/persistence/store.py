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
        for name in ("model", "profile_hash"):
            if name not in columns:
                with self.transaction() as db:
                    db.execute(f"ALTER TABLE dispatches ADD COLUMN {name} TEXT")
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
        with self.connection() as db:
            usage_columns = {row["name"] for row in db.execute("PRAGMA table_info(usage)")}
        if "dispatch_id" not in usage_columns:
            with self.transaction() as db:
                db.execute("ALTER TABLE usage ADD COLUMN dispatch_id TEXT")
        # Older model requests predate explicit cost attribution. Their IDs
        # contain the dispatch ID, so backfill only exact owned matches.
        with self.transaction() as db:
            rows = db.execute("SELECT repo,issue_number,request_id FROM usage WHERE dispatch_id IS NULL").fetchall()
            for row in rows:
                candidate = row["request_id"].split(":model:", 1)[0]
                owned = db.execute(
                    "SELECT id FROM dispatches WHERE id=? AND repo=? AND issue_number=?",
                    (candidate, row["repo"], row["issue_number"]),
                ).fetchone()
                if owned:
                    db.execute("UPDATE usage SET dispatch_id=? WHERE repo=? AND issue_number=? AND request_id=?",
                               (candidate, row["repo"], row["issue_number"], row["request_id"]))
            # A pre-history database has no timestamp for its current state.
            # Establish a new approval baseline at upgrade time, so only labels
            # added after this restart can authorise an awaiting workflow.
            legacy = db.execute("""SELECT w.repo,w.issue_number,w.state FROM workflows w
                WHERE NOT EXISTS (SELECT 1 FROM run_history h WHERE h.repo=w.repo
                AND h.issue_number=w.issue_number AND h.kind='workflow')""").fetchall()
            for row in legacy:
                self._history(db, (row["repo"], row["issue_number"]), "workflow", row["state"])

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

    def recorded_event(self, event_id: str) -> Event | None:
        with self.connection() as db:
            row = db.execute("SELECT canonical_json FROM events WHERE event_id=?", (event_id,)).fetchone()
        if row is None:
            return None
        saved = json.loads(row["canonical_json"])
        return Event(saved["id"], saved["kind"], tuple(saved["issue"]),
                     saved["revision"], saved["actor"], saved["payload"])

    def mark_event_processed(self, event_id: str) -> None:
        with self.transaction() as db:
            db.execute("UPDATE events SET outcome='processed' WHERE event_id=?", (event_id,))

    def create_workflow(self, issue: IssueKey, revision: str, *, budget_limit: int, title: str = "", body: str = "") -> bool:
        with self.transaction() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO workflows(repo,issue_number,revision,title,body,state,budget_limit) VALUES(?,?,?,?,?,'queued',?)",
                (*issue, revision, title, body, budget_limit),
            )
            if cursor.rowcount == 1:
                self._history(db, issue, "workflow", "queued")
            return cursor.rowcount == 1

    @staticmethod
    def _history(db: sqlite3.Connection, issue: IssueKey, kind: str, value: str,
                 dispatch_id: str | None = None) -> None:
        db.execute("INSERT INTO run_history(repo,issue_number,dispatch_id,kind,value) VALUES(?,?,?,?,?)",
                   (*issue, dispatch_id, kind, value))

    def workflow(self, issue: IssueKey) -> Workflow:
        with self.connection() as db:
            row = db.execute("SELECT * FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
        if row is None:
            raise KeyError(issue)
        return Workflow.model_validate(dict(row))

    def state_entered_at(self, issue: IssueKey, state: str) -> str | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT created_at FROM run_history WHERE repo=? AND issue_number=? "
                "AND kind='workflow' AND value=? ORDER BY id DESC LIMIT 1",
                (*issue, state),
            ).fetchone()
        return str(row["created_at"]) if row else None

    def workflows(self) -> list[Workflow]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM workflows ORDER BY repo, issue_number").fetchall()
        return [Workflow.model_validate(dict(row)) for row in rows]

    def cas_workflow(self, issue: IssueKey, version: int, **changes: object) -> Workflow:
        if not changes:
            raise ValueError("invalid workflow update")
        extra = _assignments(changes, _WORKFLOW_FIELDS, "workflow update")
        with self.transaction() as db:
            before = db.execute("SELECT state FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
            row = db.execute(
                f"UPDATE workflows SET version=version+1{extra} WHERE repo=? AND issue_number=? AND version=? RETURNING *",
                (*changes.values(), *issue, version),
            ).fetchone()
            if row is not None and before and before["state"] != row["state"]:
                self._history(db, issue, "workflow", row["state"])
        if row is None:
            raise VersionConflict(issue)
        return Workflow.model_validate(dict(row))

    def create_dispatch(self, dispatch: Dispatch, *, status: DispatchStatus = DispatchStatus.INTENT,
                        model: str | None = None, profile_hash: str | None = None) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT INTO dispatches(id,repo,issue_number,revision,role,attempt,workspace_id,conversation_id,candidate_sha,deadline,status,model,profile_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (dispatch.id, *dispatch.issue, dispatch.revision, dispatch.role, dispatch.attempt,
                 dispatch.workspace_id, dispatch.conversation_id, dispatch.candidate_sha, dispatch.deadline,
                 status, model, profile_hash),
            )
            self._history(db, dispatch.issue, "dispatch", str(status), dispatch.id)

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
            before = db.execute("SELECT repo,issue_number,status FROM dispatches WHERE id=?", (dispatch_id,)).fetchone()
            db.execute(f"UPDATE dispatches SET {assignments} WHERE id=?", (*changes.values(), dispatch_id))
            if before and "status" in changes and str(changes["status"]) != before["status"]:
                self._history(db, (before["repo"], before["issue_number"]), "dispatch",
                              str(changes["status"]), dispatch_id)

    def transition_dispatch(self, dispatch_id: str, issue: IssueKey, version: int,
                            state: str, status: str, result_json: str | None = None,
                            **changes: object) -> None:
        extra = _assignments(changes, _TRANSITION_FIELDS, "workflow transition")
        with self.transaction() as db:
            before = db.execute("SELECT status FROM dispatches WHERE id=?", (dispatch_id,)).fetchone()
            prior = db.execute("SELECT state FROM workflows WHERE repo=? AND issue_number=?", issue).fetchone()
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
            if before and before["status"] != status:
                self._history(db, issue, "dispatch", str(status), dispatch_id)
            if prior and prior["state"] != state:
                self._history(db, issue, "workflow", str(state), dispatch_id)

    def rate_dispatch(self, dispatch_id: str, rating: str, note: str = "") -> None:
        if rating not in {"useful", "partly-useful", "incorrect"}:
            raise ValueError("rating must be useful, partly-useful, or incorrect")
        if len(note) > 2000:
            raise ValueError("feedback note is too long")
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM dispatches WHERE id=?", (dispatch_id,)).fetchone() is None:
                raise KeyError(dispatch_id)
            db.execute("""INSERT INTO feedback(dispatch_id,rating,note) VALUES(?,?,?)
                ON CONFLICT(dispatch_id) DO UPDATE SET rating=excluded.rating,note=excluded.note,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (dispatch_id, rating, note))

    def record_agent_events(self, dispatch_id: str, events: list[dict[str, object]]) -> None:
        """Keep only safe event metadata, keyed for replay and cleanup recovery."""
        from ..performance import safe_event_metadata

        with self.transaction() as db:
            if db.execute("SELECT 1 FROM dispatches WHERE id=?", (dispatch_id,)).fetchone() is None:
                raise KeyError(dispatch_id)
            for item in events:
                event = safe_event_metadata(item)
                if event is None or not event["id"]:
                    continue
                db.execute("""INSERT OR IGNORE INTO agent_events
                    (dispatch_id,event_id,kind,source,tool,timestamp) VALUES(?,?,?,?,?,?)""",
                    (dispatch_id, event["id"], event["kind"], event["source"],
                     event["tool"], event["timestamp"]))

    def record_validation(self, issue: IssueKey, candidate_sha: str, result: ValidationResult) -> None:
        with self.transaction() as db:
            db.execute("INSERT INTO validations(repo,issue_number,candidate_sha,profile,passed,evidence_dir) VALUES(?,?,?,?,?,?)",
                       (*issue, candidate_sha, result.profile, int(result.passed), result.evidence_dir))
