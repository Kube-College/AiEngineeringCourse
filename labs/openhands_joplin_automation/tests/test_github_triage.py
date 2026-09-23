"""The small GitHub intake slice needed to start triage from a new issue."""

from datetime import datetime, timedelta, timezone
from email.message import Message
from urllib.parse import parse_qs, urlsplit
from urllib.error import HTTPError

import pytest

from openhands_controller.github.client import GitHubClient, GitHubRateLimit
from openhands_controller.github.polling import GitHubPoller
from openhands_controller.github.projection import Projector
from openhands_controller.persistence.store import Store


NOW = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)


def issue(number, *, created="2026-09-24T00:00:05Z", title="Broken note title", body="Steps", pr=False):
    item = {"id": 1000 + number, "number": number, "title": title, "body": body,
            "created_at": created, "updated_at": created, "state": "open",
            "user": {"login": "reporter"}}
    if pr:
        item["pull_request"] = {"url": "https://api.github.com/repos/lspinheiro/joplin/pulls/9"}
    return item


class IssueAPI:
    repo = "lspinheiro/joplin"

    def __init__(self, issues):
        self.items = issues
        self.since = []

    def list_open_issues(self, since):
        self.since.append(since)
        return list(self.items)


def test_issue_poller_ignores_existing_issues_and_prs_then_replays_new_issue(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    api = IssueAPI([issue(1, created="2026-09-23T23:00:00Z"), issue(2, pr=True), issue(3)])
    poller = GitHubPoller(store, api, clock=lambda: NOW)
    events = poller.collect()
    assert [(event.kind, event.issue, event.actor) for event in events] == [
        ("issue", ("lspinheiro/joplin", 3), "reporter")]
    assert poller.collect() == events
    assert api.since[0].endswith("Z")
    assert api.since[0] == api.since[1]
    restarted = GitHubPoller(Store(store.path), api, clock=lambda: NOW + timedelta(hours=1))
    assert restarted.collect() == events


def test_http_client_reads_every_page_and_rejects_upstream_destination():
    pages = []

    def request(method, path, body=None):
        assert method == "GET" and body is None
        pages.append(path)
        if parse_qs(urlsplit(path).query)["page"] == ["1"]:
            return [issue(number) for number in range(1, 101)]
        return [issue(101)]

    client = GitHubClient("lspinheiro/joplin", "token", request=request)
    assert len(client.list_open_issues("2026-09-24T00:00:00Z")) == 101
    assert len(pages) == 2
    assert all("since=2026-09-24T00%3A00%3A00Z" in path for path in pages)
    with pytest.raises(ValueError, match="upstream"):
        GitHubClient("laurent22/joplin", "token", request=request)


def test_client_accepts_configured_github_fork_url():
    client = GitHubClient("https://github.com/lspinheiro/joplin", "token", request=lambda *args: [])
    assert client.repo == "lspinheiro/joplin"


class CommentAPI:
    repo = "lspinheiro/joplin"

    def __init__(self):
        self.comments = []
        self.creates = 0
        self.edits = 0
        self.fail_after_create = False

    def authenticated_login(self):
        return "lspinheiro"

    def list_comments(self, number):
        return list(self.comments)

    def create_comment(self, number, body):
        self.creates += 1
        comment = {"id": self.creates, "body": body, "user": {"login": "lspinheiro"}}
        self.comments.append(comment)
        if self.fail_after_create:
            raise OSError("response lost")
        return comment

    def edit_comment(self, comment_id, body):
        self.edits += 1
        next(comment for comment in self.comments if comment["id"] == comment_id)["body"] = body


def test_projection_recovers_lost_create_without_duplicate_comment(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    store.create_workflow(("lspinheiro/joplin", 7), "revision", budget_limit=5_000_000)
    api = CommentAPI()
    projector = Projector(store, api)
    api.fail_after_create = True
    with pytest.raises(OSError, match="response lost"):
        projector.sync(("lspinheiro/joplin", 7))
    api.fail_after_create = False
    projector.sync(("lspinheiro/joplin", 7))
    assert api.creates == 1
    assert api.edits == 0
    row = store.workflow(("lspinheiro/joplin", 7))
    store.cas_workflow(row.issue, row.version, state="triaging")
    projector.sync(row.issue)
    assert api.creates == 1
    assert api.edits == 1
    assert "triaging" in api.comments[0]["body"]


@pytest.mark.parametrize("status", [429, 403])
def test_rate_limit_response_reports_retry_delay_without_exposing_token(monkeypatch, status):
    headers = Message()
    headers["Retry-After"] = "65"

    def denied(request, timeout):
        raise HTTPError(request.full_url, status, "rate limited", headers, None)

    monkeypatch.setattr("openhands_controller.github.client.urlopen", denied)
    client = GitHubClient("lspinheiro/joplin", "private-token")
    with pytest.raises(GitHubRateLimit) as error:
        client.list_open_issues("2026-09-24T00:00:00Z")
    assert error.value.retry_after == 65
    assert "private-token" not in str(error.value)
