"""The small GitHub intake slice needed to start triage from a new issue."""

from datetime import datetime, timedelta, timezone
from email.message import Message
from urllib.parse import parse_qs, urlsplit
from urllib.error import HTTPError

import pytest

from openhands_controller.github.client import GitHubClient, GitHubRateLimit
from openhands_controller.github.polling import GitHubPoller
from openhands_controller.github.projection import Projector
from openhands_controller.adapters.simulated import SimulatedAgent
from openhands_controller.config import Settings
from openhands_controller.engine.controller import Controller
from openhands_controller.persistence.store import Store
from openhands_controller.triage import TriageOnlyDelivery
from openhands_controller.domain.models import Dispatch


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
        self.issue_events = {}

    def list_open_issues(self, since):
        self.since.append(since)
        return list(self.items)

    def list_issue_events(self, number):
        return self.issue_events.get(number, [])


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


def test_reverted_issue_edit_restores_current_title(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    api = IssueAPI([issue(4, title="original")])
    poller = GitHubPoller(store, api, clock=lambda: NOW)
    controller = Controller(store, SimulatedAgent(), TriageOnlyDelivery(), lambda actor, repo: "read",
                            lambda: NOW, Settings(_env_file=None))
    try:
        for title, updated_at in (("original", "2026-09-24T00:00:05Z"),
                                  ("edited", "2026-09-24T00:00:06Z"),
                                  ("original", "2026-09-24T00:00:07Z")):
            api.items[0]["title"] = title
            api.items[0]["updated_at"] = updated_at
            for event in poller.collect():
                controller.handle(event)
        assert store.workflow((api.repo, 4)).title == "original"
    finally:
        controller.close()


def test_poller_emits_only_new_approval_additions_with_immutable_actor_and_id(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    api = IssueAPI([issue(7)])
    poller = GitHubPoller(store, api, clock=lambda: NOW)
    api.issue_events[7] = [
        {"id": 70, "event": "labeled", "created_at": "2026-09-23T23:00:00Z",
         "actor": {"login": "owner"}, "label": {"name": "agent:implement"}},
        {"id": 71, "event": "unlabeled", "created_at": "2026-09-24T00:00:06Z",
         "actor": {"login": "owner"}, "label": {"name": "agent:implement"}},
        {"id": 72, "event": "labeled", "created_at": "2026-09-24T00:00:07Z",
         "actor": {"login": "reviewer"}, "label": {"name": "agent:implement"}},
    ]
    events = poller.collect()
    assert [(event.kind, event.id, event.actor, event.payload) for event in events[1:]] == [
        ("label", "github:label:lspinheiro/joplin:7:72", "reviewer",
         {"action": "added", "label": "agent:implement", "created_at": "2026-09-24T00:00:07Z"})
    ]


def test_replaying_label_after_issue_edit_keeps_its_original_revision(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    api = IssueAPI([issue(7)])
    poller = GitHubPoller(store, api, clock=lambda: NOW)
    api.issue_events[7] = [{"id": 72, "event": "labeled", "created_at": "2026-09-24T00:00:07Z",
                            "actor": {"login": "owner"}, "label": {"name": "agent:implement"}}]
    controller = Controller(store, SimulatedAgent(), TriageOnlyDelivery(), lambda *_: "write",
                            lambda: NOW, Settings(_env_file=None))
    try:
        original = poller.collect()
        for event in original:
            controller.handle(event)
        api.items[0]["title"] = "Changed report"
        api.items[0]["updated_at"] = "2026-09-24T00:01:00Z"
        replay = poller.collect()
        for event in replay:
            controller.handle(event)
        assert replay[-1].revision == original[-1].revision
        assert store.workflow((api.repo, 7)).title == "Changed report"
    finally:
        controller.close()


def test_client_reads_issue_events_and_actor_permission():
    paths = []

    def request(method, path, body=None):
        paths.append((method, path))
        if "/events?" in path:
            return [{"id": 1, "event": "labeled"}]
        return {"permission": "write"}

    client = GitHubClient("lspinheiro/joplin", "token", request=request)
    assert client.list_issue_events(7) == [{"id": 1, "event": "labeled"}]
    assert client.permission("reviewer", client.repo) == "write"
    assert paths == [
        ("GET", "/repos/lspinheiro/joplin/issues/7/events?per_page=100&page=1"),
        ("GET", "/repos/lspinheiro/joplin/collaborators/reviewer/permission"),
    ]


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
        self.labels = {}
        self.repository_labels = set()

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

    def list_repository_labels(self):
        return [{"name": name} for name in self.repository_labels]

    def create_label(self, name, color, description):
        self.repository_labels.add(name)

    def list_issue_labels(self, number):
        return [{"name": name} for name in self.labels.get(number, set())]

    def add_issue_labels(self, number, names):
        assert set(names) <= self.repository_labels
        self.labels.setdefault(number, set()).update(names)

    def remove_issue_label(self, number, name):
        self.labels[number].remove(name)


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


def test_projection_keeps_one_state_label_and_preserves_unrelated_labels(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    issue_key = ("lspinheiro/joplin", 7)
    store.create_workflow(issue_key, "revision", budget_limit=5_000_000)
    api = CommentAPI()
    api.labels[7] = {"bug", "agent:state:triaging"}
    projector = Projector(store, api)
    projector.sync(issue_key)
    assert api.labels[7] == {"bug", "agent:state:queued"}
    row = store.workflow(issue_key)
    store.cas_workflow(issue_key, row.version, state="awaiting-approval")
    projector.sync(issue_key)
    projector.sync(issue_key)
    assert api.labels[7] == {"bug", "agent:state:awaiting-approval"}
    assert api.repository_labels == {"agent:state:queued", "agent:state:awaiting-approval"}


def test_projection_posts_one_agent_outcome_comment_even_after_lost_response(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    issue_key = ("lspinheiro/joplin", 7)
    store.create_workflow(issue_key, "revision", budget_limit=5_000_000)
    api = CommentAPI()
    projector = Projector(store, api)
    projector.sync(issue_key)
    dispatch = Dispatch("run-7", issue_key, "revision", "triage", 1, "workspace-7", None, None,
                        "2026-09-24T00:20:00+00:00")
    store.create_dispatch(dispatch)
    store.transition_dispatch("run-7", issue_key, store.workflow(issue_key).version,
                              "awaiting-approval", "finished",
                              '{"scope":"desktop","summary":"Reproduced focus loss","validation_profile":"core"}')
    api.fail_after_create = True
    with pytest.raises(OSError, match="response lost"):
        projector.sync(issue_key)
    api.fail_after_create = False
    projector.sync(issue_key)
    projector.sync(issue_key)
    assert api.creates == 2
    assert len(api.comments) == 2
    assert "Triage agent" in api.comments[1]["body"]
    assert "Reproduced focus loss" in api.comments[1]["body"]
    assert "Scope: desktop" in api.comments[1]["body"]
    assert "Validation profile: core" in api.comments[1]["body"]


def test_implementation_agent_comment_reports_changed_paths(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    issue_key = ("lspinheiro/joplin", 7)
    store.create_workflow(issue_key, "revision", budget_limit=5_000_000)
    dispatch = Dispatch("run-impl-7", issue_key, "revision", "implementation", 1,
                        "workspace-7", None, None, "2026-09-24T00:20:00+00:00")
    store.create_dispatch(dispatch)
    store.transition_dispatch(dispatch.id, issue_key, store.workflow(issue_key).version,
                              "needs-human", "finished",
                              '{"summary":"Updated focus","changed_paths":["packages/app-desktop/gui/Note.tsx"]}')
    api = CommentAPI()
    Projector(store, api).sync(issue_key)
    assert len(api.comments) == 2
    assert "Implementation agent" in api.comments[1]["body"]
    assert "Changed paths: `packages/app-desktop/gui/Note.tsx`" in api.comments[1]["body"]


def test_projection_consumes_approval_label_after_implementation_starts(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    issue_key = ("lspinheiro/joplin", 7)
    store.create_workflow(issue_key, "revision", budget_limit=5_000_000)
    row = store.workflow(issue_key)
    store.cas_workflow(issue_key, row.version, state="implementing", approval_revision="revision")
    api = CommentAPI()
    api.labels[7] = {"agent:implement", "bug"}
    Projector(store, api).sync(issue_key)
    assert api.labels[7] == {"agent:state:implementing", "bug"}


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
