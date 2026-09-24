"""Reconcile one controller-owned status comment on a triaged issue."""

import json
from html import escape

from ..domain.models import IssueKey
from ..persistence.store import Store
from .client import GitHubClient


MARKER = "<!-- openhands-joplin-controller:triage -->"
AGENT_MARKER = "<!-- openhands-joplin-controller:agent:{} -->"
STATE_PREFIX = "agent:state:"


def _public_text(value: object, limit: int = 1200) -> str:
    return escape(str(value)[:limit], quote=False)


class Projector:
    def __init__(self, store: Store, client: GitHubClient):
        self.store = store
        self.client = client
        self._login: str | None = None
        self._repository_labels: set[str] | None = None

    def sync(self, issue: IssueKey) -> None:
        row = self.store.workflow(issue)
        if issue[0] != self.client.repo:
            raise ValueError("issue belongs to a different repository")
        lines = [MARKER, "## OpenHands triage", f"State: **{row.state}**"]
        if row.state == "awaiting-approval":
            completed = [d for d in self.store.dispatches(issue) if d.role == "triage" and d.result_json]
            if completed:
                result = json.loads(completed[-1].result_json)
                lines.extend([f"Scope: {_public_text(result['scope'])}",
                              f"Summary: {_public_text(result['summary'])}",
                              f"Validation profile: `{_public_text(row.validation_profile)}`"])
        if row.reason:
            lines.append("Reason: see controller logs for details")
        body = "\n\n".join(lines) + "\n"
        if self._login is None:
            self._login = self.client.authenticated_login()
        comments = self.client.list_comments(issue[1])
        self._sync_comment(issue[1], MARKER, body, comments)
        for dispatch in self.store.dispatches(issue):
            if dispatch.status != "finished" or not dispatch.result_json:
                continue
            marker = AGENT_MARKER.format(dispatch.id)
            result = json.loads(dispatch.result_json)
            role = str(dispatch.role).capitalize()
            if dispatch.role == "triage":
                details = [f"Scope: {_public_text(result['scope'])}",
                           f"Summary: {_public_text(result['summary'])}",
                           f"Validation profile: {_public_text(result['validation_profile'])}"]
            elif dispatch.role in {"implementation", "fix"}:
                paths = ", ".join(f"`{_public_text(path, 180).replace('`', '')}`"
                                  for path in result["changed_paths"][:20])
                details = [f"Summary: {_public_text(result['summary'])}", f"Changed paths: {paths}"]
            else:
                details = [f"Verdict: {_public_text(result['verdict'])}",
                           f"Findings: {len(result['findings'])}"]
            agent_body = f"{marker}\n\n## {role} agent result\n\n" + "\n\n".join(details) + "\n"
            self._sync_comment(issue[1], marker, agent_body, comments)
        self._sync_labels(issue[1], str(row.state),
                          consume_approval=row.approval_revision == row.revision and row.state != "awaiting-approval")

    def _sync_comment(self, number: int, marker: str, body: str, comments: list[dict]) -> None:
        owned = [comment for comment in comments
                 if marker in str(comment.get("body") or "")
                 and (comment.get("user") or {}).get("login") == self._login]
        if owned:
            comment = owned[-1]
            if comment["body"] != body:
                self.client.edit_comment(int(comment["id"]), body)
        else:
            comment = self.client.create_comment(number, body)
            comments.append(comment)

    def _sync_labels(self, number: int, state: str, *, consume_approval: bool) -> None:
        wanted = STATE_PREFIX + state
        current = {str(label["name"]) for label in self.client.list_issue_labels(number)}
        if wanted not in current:
            if self._repository_labels is None:
                self._repository_labels = {str(label["name"]) for label in self.client.list_repository_labels()}
            if wanted not in self._repository_labels:
                self.client.create_label(wanted, "4338ca", "Controller workflow state")
                self._repository_labels.add(wanted)
            self.client.add_issue_labels(number, [wanted])
        for name in sorted(current):
            if name.startswith(STATE_PREFIX) and name != wanted:
                self.client.remove_issue_label(number, name)
        if consume_approval and "agent:implement" in current:
            self.client.remove_issue_label(number, "agent:implement")
