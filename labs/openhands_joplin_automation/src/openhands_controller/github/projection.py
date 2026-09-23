"""Reconcile one controller-owned status comment on a triaged issue."""

import json

from ..domain.models import IssueKey
from ..persistence.store import Store
from .client import GitHubClient


MARKER = "<!-- openhands-joplin-controller:triage -->"


class Projector:
    def __init__(self, store: Store, client: GitHubClient):
        self.store = store
        self.client = client
        self._login: str | None = None

    def sync(self, issue: IssueKey) -> None:
        row = self.store.workflow(issue)
        if issue[0] != self.client.repo:
            raise ValueError("issue belongs to a different repository")
        lines = [MARKER, "## OpenHands triage", f"State: **{row.state}**"]
        if row.state == "awaiting-approval":
            completed = [d for d in self.store.dispatches(issue) if d.role == "triage" and d.result_json]
            if completed:
                result = json.loads(completed[-1].result_json)
                lines.extend([f"Scope: {result['scope']}", f"Summary: {result['summary']}",
                              f"Validation profile: `{row.validation_profile}`"])
        if row.reason:
            lines.append(f"Reason: {row.reason}")
        body = "\n\n".join(lines) + "\n"
        if self._login is None:
            self._login = self.client.authenticated_login()
        owned = [comment for comment in self.client.list_comments(issue[1])
                 if MARKER in str(comment.get("body") or "")
                 and (comment.get("user") or {}).get("login") == self._login]
        if owned:
            comment = owned[-1]
            if comment["body"] != body:
                self.client.edit_comment(int(comment["id"]), body)
        else:
            self.client.create_comment(issue[1], body)
