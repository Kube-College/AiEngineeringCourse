"""Read-only, local evidence view for controller-owned agent runs."""

import json
import re
import sqlite3
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import UUID

from .domain.models import IssueKey


SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")
SAFE_TIME = re.compile(r"[0-9TZ:+. -]{1,48}\Z")
SAFE_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
TERMINAL = {"finished", "failed", "stale", "cancelled"}
PUBLIC_REASONS = {
    "issue changed", "remote start cannot be reconciled",
    "remote creation identity is uncertain", "budget exhausted or unknown",
    "run timed out", "remote status after deadline is uncertain",
    "invalid role result", "review correction exhausted", "validation failed",
    "implementation finished; validation and publication are not enabled",
}


class PerformanceReader:
    """Query a controller database without running migrations or writing state."""

    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    def _connect(self):
        uri = f"file:{quote(str(self.path), safe='/')}?mode=ro"
        db = sqlite3.connect(uri, uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        return db

    def runs(self) -> list[dict[str, object]]:
        with self._connect() as db:
            rows = db.execute("""SELECT d.id, d.repo, d.issue_number, d.role, d.attempt,
                d.status, d.iterations, d.model, d.profile_hash, d.conversation_id,
                d.created_at, w.title, w.state AS workflow_state, w.reason,
                f.rating, f.note,
                COUNT(u.request_id) AS recorded_requests,
                COALESCE(SUM(CASE WHEN u.status='settled' THEN u.actual_microusd ELSE 0 END),0)
                    AS actual_microusd,
                COALESCE(SUM(CASE WHEN u.status='unknown' THEN 1 ELSE 0 END),0)
                    AS unknown_requests,
                COALESCE(SUM(CASE WHEN u.status='reserved' THEN 1 ELSE 0 END),0)
                    AS open_requests
                FROM dispatches d
                JOIN workflows w ON w.repo=d.repo AND w.issue_number=d.issue_number
                LEFT JOIN usage u ON u.dispatch_id=d.id
                LEFT JOIN feedback f ON f.dispatch_id=d.id
                GROUP BY d.id ORDER BY d.rowid DESC""").fetchall()
            runs = [dict(row) for row in rows]
            for run in runs:
                history = db.execute(
                    "SELECT value,created_at FROM run_history WHERE dispatch_id=? AND kind='dispatch' ORDER BY id",
                    (run["id"],),
                ).fetchall()
                started = next((row["created_at"] for row in history if row["value"] == "running"), None)
                ended = next((row["created_at"] for row in reversed(history)
                              if row["value"] in TERMINAL), None)
                run["started_at"], run["finished_at"] = started, ended
                run["elapsed_seconds"] = _seconds_between(started, ended)
        return runs

    def issue(self, repo: str, number: int) -> dict[str, object]:
        with self._connect() as db:
            workflow = db.execute("SELECT repo,issue_number,title,state,reason,pr_url FROM workflows "
                                  "WHERE repo=? AND issue_number=?", (repo, number)).fetchone()
            if workflow is None:
                raise KeyError((repo, number))
            history = db.execute(
                "SELECT kind,value,dispatch_id,created_at FROM run_history "
                "WHERE repo=? AND issue_number=? ORDER BY id", (repo, number),
            ).fetchall()
            validations = db.execute(
                "SELECT profile,passed,created_at FROM validations WHERE repo=? AND issue_number=? ORDER BY id",
                (repo, number),
            ).fetchall()
            workspace = db.execute("SELECT host_port,status,storage_id FROM workspaces WHERE repo=? AND issue_number=?",
                                   (repo, number)).fetchone()
            events = db.execute("""SELECT e.kind,e.source,e.tool,e.timestamp FROM agent_events e
                JOIN dispatches d ON d.id=e.dispatch_id
                WHERE d.repo=? AND d.issue_number=? ORDER BY e.rowid DESC LIMIT 100""",
                (repo, number)).fetchall()
        return {
            "workflow": dict(workflow), "history": [dict(row) for row in history],
            "validations": [dict(row) for row in validations],
            "workspace": dict(workspace) if workspace else None,
            "agent_events": [dict(row) for row in reversed(events)],
            "runs": [run for run in self.runs() if (run["repo"], run["issue_number"]) == (repo, number)],
        }


def _seconds_between(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        return max(0.0, (datetime.fromisoformat(end.replace("Z", "+00:00"))
                         - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds())
    except ValueError:
        return None


def safe_event_metadata(item: object) -> dict[str, str | None] | None:
    """Keep only bounded, inert labels from an untrusted agent event."""
    if not isinstance(item, dict):
        return None
    identifier = item.get("id")
    if identifier is not None and (not isinstance(identifier, str) or not SAFE_NAME.fullmatch(identifier)):
        identifier = None
    action = item.get("action")
    candidate_tool = ((action.get("tool_name") or action.get("kind"))
                      if isinstance(action, dict) else item.get("tool"))
    kind = item.get("kind")
    source = item.get("source")
    timestamp = item.get("timestamp")
    return {
        "id": identifier,
        "kind": kind if isinstance(kind, str) and SAFE_NAME.fullmatch(kind) else "OtherEvent",
        "source": source if isinstance(source, str) and source in {"agent", "user", "environment", "tool"} else "other",
        "tool": candidate_tool if isinstance(candidate_tool, str)
        and SAFE_NAME.fullmatch(candidate_tool) else None,
        "timestamp": timestamp if isinstance(timestamp, str) and SAFE_TIME.fullmatch(timestamp) else "",
    }


def normalise_events(raw: list[object]) -> list[dict[str, str | None]]:
    """Deliberately omit messages, commands, tool arguments and results."""
    cleaned = []
    for item in raw:
        event = safe_event_metadata(item)
        if event is None:
            continue
        event.pop("id")
        cleaned.append(event)
    return cleaned


def read_workspace_events(storage: Path, conversation_id: str | None) -> list[dict[str, object]]:
    """Read persisted SDK events without following links planted in the workspace."""
    if not conversation_id:
        return []
    try:
        identifier = UUID(conversation_id).hex
    except ValueError:
        return []
    root = Path(storage)
    parts = (root / "workspace", root / "workspace" / "conversations",
             root / "workspace" / "conversations" / identifier)
    directory = parts[-1] / "events"
    if any(path.is_symlink() for path in (*parts, directory)) or not directory.is_dir():
        return []
    events = []
    for path in sorted(directory.glob("event-*.json")):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        item = json.loads(path.read_text())
        metadata = safe_event_metadata(item)
        if metadata and metadata["id"]:
            events.append(metadata)
    return events


def fetch_agent_events(state_dir: Path, host_port: int | None,
                       conversation_id: str | None) -> list[dict[str, str | None]]:
    """Read a running Agent Server; its key stays in this local process."""
    if not host_port or not 1 <= host_port <= 65535 or not conversation_id \
            or not SAFE_NAME.fullmatch(conversation_id):
        return []
    auth = json.loads((state_dir / "runtime-auth.json").read_text())
    key = auth["server_token"]
    items: list[object] = []
    page: str | None = None
    for _ in range(5):
        query = {"limit": "100"}
        if page:
            query["page_id"] = page
        url = (f"http://127.0.0.1:{host_port}/conversations/{conversation_id}/events/search?"
               + urlencode(query))
        request = Request(url, headers={"X-Session-API-Key": key})
        with urlopen(request, timeout=2) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ValueError("Agent Server returned invalid event data")
        items.extend(payload["items"])
        page = payload.get("next_page_id")
        if not isinstance(page, str) or not page:
            break
    return normalise_events(items[-100:])


def profile_snapshot(role, settings) -> tuple[str, str]:
    """Identify the model and exact instructions/tool selection for comparison."""
    from .runtime.agents import AGENTS, CONTENT_DIR, resolve_model

    profile = AGENTS[role]
    model = resolve_model(role, settings).name
    contents = [
        (CONTENT_DIR / "common.md").read_bytes(),
        (CONTENT_DIR / profile.prompt).read_bytes(),
        *((CONTENT_DIR / "skills" / name).read_bytes() for name in profile.skills),
    ]
    digest = hashlib.sha256(json.dumps({
        "role": role, "model": model, "tools": profile.tools,
        "skills": profile.skills, "prompt": profile.prompt,
        "content_hashes": [hashlib.sha256(content).hexdigest() for content in contents],
    }, sort_keys=True).encode()).hexdigest()
    return model, digest


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _cost(microusd: object) -> str:
    return f"${int(microusd or 0) / 1_000_000:.4f}"


def _run_cost(run: dict[str, object]) -> str:
    if not run["recorded_requests"]:
        return "No charge recorded"
    cost = _cost(run["actual_microusd"])
    return cost + (" · Cost uncertain" if run["unknown_requests"] else "")


def _issue_link(repo: str, number: int) -> str:
    return "/?" + urlencode({"issue": f"{repo}#{number}"})


def render_dashboard(reader: PerformanceReader, *, selected: IssueKey | None = None,
                     agent_events: list[dict[str, str | None]] | None = None,
                     event_error: str | None = None) -> str:
    runs = reader.runs()
    detail = reader.issue(*selected) if selected else None
    active = sum(run["status"] in {"intent", "created", "running", "resuming", "stopping"}
                 for run in runs)
    assessed = sum(run["rating"] is not None for run in runs)
    rows = []
    for run in runs:
        issue = f"{run['repo']}#{run['issue_number']}"
        cost = _run_cost(run)
        rows.append(
            f'<tr><td><a href="{_e(_issue_link(str(run["repo"]), int(run["issue_number"]))) }">'
            f'{_e(issue)}</a><span class="sub">{_e(run["title"])}</span></td>'
            f'<td>{_e(run["role"])}<span class="sub">{_e(run["model"] or "model unrecorded")}</span></td>'
            f'<td>{_e(run["status"])}<span class="sub">{_e(run["workflow_state"])}</span></td>'
            f'<td>{_e(cost)}</td><td>{_e(run["rating"] or "Not rated")}</td></tr>'
        )
    table = "".join(rows) or '<tr><td colspan="5" class="empty">No agent runs yet. Start the controller and create an issue in the configured fork.</td></tr>'
    detail_html = ""
    if detail:
        workflow = detail["workflow"]
        reason = workflow["reason"]
        display_reason = reason if reason in PUBLIC_REASONS else "See controller logs for details"
        selected_runs = detail["runs"]
        history = "".join(
            f'<li><time>{_e(row["created_at"])}</time><strong>{_e(row["value"])}</strong>'
            f'<span>{_e(row["kind"])}</span></li>' for row in detail["history"]
        ) or '<li class="empty">History predates this console.</li>'
        event_rows = "".join(
            f'<li><time>{_e(row["timestamp"])}</time><strong>{_e(row["kind"])}</strong>'
            f'<span>{_e(row["tool"] or row["source"])}</span></li>'
            for row in (agent_events or detail["agent_events"])
        ) or f'<li class="empty">{_e(event_error or "No live event metadata available")}</li>'
        run_rows = "".join(
            f'<tr><td>{_e(run["role"])} · {_e(run["attempt"])}'
            f'<span class="sub"><code>{_e(run["id"])}</code></span></td>'
            f'<td>{_e(run["model"] or "unrecorded")}'
            f'<span class="sub">profile {_e(str(run["profile_hash"])[:12] if run["profile_hash"] else "unrecorded")}</span></td>'
            f'<td>{_e(run["iterations"])}</td>'
            f'<td>{_e(round(run["elapsed_seconds"])) if run["elapsed_seconds"] is not None else "—"} s</td>'
            f'<td>{_e(_run_cost(run))}</td>'
            f'<td>{_e(run["rating"] or "Not rated")}</td></tr>' for run in selected_runs
        )
        validations = "".join(
            f'<li>{_e(row["profile"])}: {"passed" if row["passed"] else "failed"}</li>'
            for row in detail["validations"]
        ) or '<li>No validation recorded</li>'
        notes = "".join(f'<p><strong>{_e(run["role"])} feedback:</strong> {_e(run["note"])}</p>'
                        for run in selected_runs if run["note"])
        detail_html = f'''<section class="detail" aria-labelledby="issue-heading">
          <div class="section-head"><div><h2 id="issue-heading">{_e(workflow["repo"])}#{_e(workflow["issue_number"])}</h2>
          <p>{_e(workflow["title"])}</p></div><a href="/">All runs</a></div>
          <p class="state-line">Current state <strong>{_e(workflow["state"])}</strong></p>
          {f'<p class="reason">Reason: {_e(display_reason)}</p>' if reason else ""}
          <div class="table-wrap"><table><caption>Dispatch measurements</caption><thead><tr>
          <th>Role</th><th>Model</th><th>Iterations</th><th>Elapsed</th><th>Actual cost</th><th>Human rating</th>
          </tr></thead><tbody>{run_rows}</tbody></table></div>
          <div class="evidence-grid"><section><h3>Controller history</h3><ol class="timeline">{history}</ol></section>
          <section><h3>Agent activity</h3><p class="hint">Event metadata only. Messages and tool arguments are withheld.</p>
          <ol class="timeline">{event_rows}</ol></section></div>
          <section><h3>Outcome evidence</h3><ul>{validations}</ul>{notes}</section>
          </section>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <meta http-equiv="refresh" content="15"><meta name="referrer" content="no-referrer">
      <title>Agent performance · Joplin lab</title>
      <style>{_CSS}</style></head><body><main>
      <header><div><h1>Agent performance</h1><p>Local evidence from the Joplin automation controller.</p></div>
      <a class="refresh" href="{_e(_issue_link(*selected)) if selected else '/'}">Refresh</a></header>
      <p class="overview"><strong>{len(runs)}</strong> recorded runs <span>·</span>
      <strong>{active}</strong> active <span>·</span> <strong>{assessed}</strong> rated</p>
      <section aria-labelledby="runs-heading"><div class="section-head"><h2 id="runs-heading">Runs</h2>
      <p>Completion, cost and human quality are shown separately.</p></div>
      <div class="table-wrap"><table><thead><tr><th>Issue</th><th>Agent</th><th>Run state</th>
      <th>Actual cost</th><th>Human rating</th></tr></thead><tbody>{table}</tbody></table></div></section>
      {detail_html}<footer>Local view · Refreshes every 15 seconds · Agent Server credentials stay on this machine</footer>
      </main></body></html>'''


_CSS = """
:root{color-scheme:light dark;--bg:#fbfaf8;--surface:#fff;--fg:#1a1a1a;--muted:#5b616e;
--border:#e7e3dc;--accent:#4338ca;--soft:#eef0fb;font-family:Inter,system-ui,sans-serif}
@media(prefers-color-scheme:dark){:root{--bg:#0e1116;--surface:#161a22;--fg:#e8e6e1;
--muted:#9ba3b0;--border:#232936;--accent:#a5b4fc;--soft:#1b1f2e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);line-height:1.5}
main{max-width:1180px;margin:auto;padding:40px 24px 72px}header,.section-head{display:flex;
align-items:baseline;justify-content:space-between;gap:20px}header{align-items:center;border-bottom:1px solid var(--border);padding-bottom:28px}
h1{font-size:clamp(2rem,4vw,2.75rem);letter-spacing:-.025em;line-height:1.15;margin:0 0 8px}
h2{font-size:1.5rem;letter-spacing:-.02em;margin:0}h3{font-size:1.1rem;margin:0 0 12px}
p{margin:0 0 12px}header p,.section-head p,.hint,.sub,footer{color:var(--muted)}
a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:3px}a:focus-visible{outline:2px solid var(--accent);outline-offset:4px}
.refresh{border:1px solid var(--border);border-radius:6px;padding:8px 14px;text-decoration:none;white-space:nowrap}
.overview{margin:28px 0 42px;font-size:1.05rem}.overview strong{font-variant-numeric:tabular-nums}.overview span{margin:0 12px;color:var(--muted)}
section{margin-top:40px}.table-wrap{overflow-x:auto;border-top:2px solid var(--fg);margin-top:16px}
table{border-collapse:collapse;width:100%;min-width:680px;text-align:left}caption{text-align:left;font-weight:600;margin:16px 0 8px}
th,td{padding:14px 12px;border-bottom:1px solid var(--border);vertical-align:top}th{font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
td{font-size:.94rem}td:first-child,th:first-child{padding-left:0}.sub{display:block;font-size:.81rem;margin-top:2px;max-width:36ch;overflow-wrap:anywhere}
.empty{color:var(--muted);padding:24px 0}.detail{margin-top:64px;border-top:1px solid var(--border);padding-top:28px}
.detail .section-head p{margin-top:7px}.state-line{padding:12px 16px;background:var(--soft);margin:24px 0 0;border-radius:6px}
.state-line strong{margin-left:8px}.reason{margin-top:12px}.evidence-grid{display:grid;grid-template-columns:1fr 1fr;gap:48px}
.timeline{list-style:none;padding:0;margin:0;border-top:1px solid var(--border)}.timeline li{display:grid;grid-template-columns:minmax(145px,1fr) 1fr auto;gap:12px;
padding:10px 0;border-bottom:1px solid var(--border);font-size:.85rem}.timeline time{font-family:ui-monospace,Menlo,monospace;color:var(--muted);overflow-wrap:anywhere}
.timeline span{color:var(--muted)}.hint{font-size:.82rem;margin-bottom:12px}footer{border-top:1px solid var(--border);margin-top:64px;padding-top:18px;font-size:.82rem}
@media(max-width:760px){main{padding:24px 16px 48px}header,.section-head{align-items:flex-start;flex-direction:column;gap:8px}
.overview{margin:24px 0 32px}.evidence-grid{grid-template-columns:1fr;gap:8px}.detail{margin-top:48px}.timeline li{grid-template-columns:1fr auto}.timeline time{grid-column:1/-1}}
"""


def make_dashboard_server(db_path: Path, state_dir: Path, *, port: int = 8765,
                          event_loader=fetch_agent_events) -> ThreadingHTTPServer:
    """Create a loopback-only, GET-only console. The browser never receives auth."""
    if not Path(db_path).is_file():
        raise FileNotFoundError(db_path)
    from .persistence.store import Store

    # Upgrade older controller databases once; all HTTP requests use read-only connections.
    Store(db_path)
    reader = PerformanceReader(db_path)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path != "/":
                self.send_error(404)
                return
            issue_text = parse_qs(parsed.query).get("issue", [None])[0]
            selected = None
            if issue_text is not None:
                repo, marker, number = issue_text.rpartition("#")
                if not marker or not SAFE_REPO.fullmatch(repo) or not number.isdigit():
                    self.send_error(400, "Invalid issue selection")
                    return
                selected = (repo, int(number))
            try:
                detail = reader.issue(*selected) if selected else None
            except KeyError:
                self.send_error(404, "Issue not found")
                return
            events = []
            error = None
            if detail and detail["runs"]:
                latest = detail["runs"][0]
                workspace = detail["workspace"]
                try:
                    events = event_loader(state_dir, workspace["host_port"] if workspace else None,
                                          latest["conversation_id"])
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    error = "Agent events are unavailable while the runtime is stopped."
                if not events and workspace and workspace["storage_id"]:
                    try:
                        events = normalise_events(read_workspace_events(
                            Path(workspace["storage_id"]), latest["conversation_id"]
                        ))
                    except (OSError, ValueError, json.JSONDecodeError):
                        pass
            body = render_dashboard(reader, selected=selected, agent_events=events,
                                    event_error=error).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.send_error(405, "Dashboard is read only")

        def log_message(self, *_):
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
