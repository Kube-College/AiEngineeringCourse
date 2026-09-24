"""The browser gets measurements but no controller or Agent Server authority."""

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from typer.testing import CliRunner

from openhands_controller.cli import app
from openhands_controller.performance import fetch_agent_events
from test_performance_dashboard import ISSUE, _record_run


def test_event_fetch_authenticates_on_server_and_returns_only_redacted_metadata(tmp_path):
    requests = []

    class AgentServer(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get("X-Session-API-Key")))
            body = json.dumps({"items": [{"kind": "ActionEvent", "source": "agent",
                                         "timestamp": "2026-09-24T12:01:00Z",
                                         "action": {"tool_name": "terminal", "command": "PRIVATE_TOKEN"}}],
                               "next_page_id": None}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), AgentServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        (tmp_path / "runtime-auth.json").write_text(json.dumps({"server_token": "PRIVATE_TOKEN"}))
        events = fetch_agent_events(tmp_path, server.server_address[1], "conversation-17")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert requests == [(
        "/conversations/conversation-17/events/search?limit=100", "PRIVATE_TOKEN"
    )]
    assert events == [{"kind": "ActionEvent", "source": "agent", "tool": "terminal",
                       "timestamp": "2026-09-24T12:01:00Z"}]
    assert "PRIVATE_TOKEN" not in json.dumps(events)


def test_dashboard_serves_loopback_only_and_rejects_writes(tmp_path):
    from openhands_controller.performance import make_dashboard_server

    path = tmp_path / "state.sqlite"
    _record_run(path)
    server = make_dashboard_server(path, tmp_path, port=0,
                                   event_loader=lambda *_: [])
    assert server.server_address[0] == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/?issue=demo%2Fjoplin%2317"
    try:
        with urlopen(url) as response:
            page = response.read().decode()
            assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(url, data=b"rating=useful", method="POST"))
        assert exc.value.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert "Focus &lt;script&gt;secret&lt;/script&gt;" in page
    assert "PRIVATE_TOKEN" not in page


def test_dashboard_migrates_an_existing_controller_database_once(tmp_path):
    from openhands_controller.performance import make_dashboard_server
    from openhands_controller.persistence.store import Store

    path = tmp_path / "state.sqlite"
    _record_run(path)
    with Store(path).transaction() as db:
        db.execute("DROP TABLE run_history")
        db.execute("DROP TABLE agent_events")
    server = make_dashboard_server(path, tmp_path, port=0)
    try:
        with sqlite3.connect(path) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"run_history", "agent_events"} <= tables
    finally:
        server.server_close()


def test_rating_command_changes_feedback_without_starting_a_run(tmp_path):
    path = tmp_path / "controller.sqlite"
    _record_run(path)
    result = CliRunner().invoke(app, ["rate", "run-17", "--rating", "useful",
                                      "--note", "Accurate after review", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    from openhands_controller.persistence.store import Store
    store = Store(path)
    with store.connection() as db:
        rating = db.execute("SELECT rating FROM feedback WHERE dispatch_id='run-17'").fetchone()[0]
    assert rating == "useful"
    assert store.workflow(ISSUE).state == "awaiting-approval"
