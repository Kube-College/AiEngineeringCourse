"""Replayable new-issue intake. The demo scans from its persisted start time."""

from datetime import datetime, timedelta, timezone
from typing import Callable

from ..domain.models import Event
from ..domain.revision import revision_hash
from ..persistence.store import Store
from .client import GitHubClient


class GitHubPoller:
    def __init__(self, store: Store, client: GitHubClient, *, clock: Callable[[], datetime]):
        self.store = store
        self.client = client
        key = f"github-triage-start:{client.repo}"
        with store.transaction() as db:
            row = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            if row is None:
                # GitHub timestamps have second precision. A short overlap keeps
                # an issue created at the startup boundary eligible for intake.
                start = (clock().astimezone(timezone.utc) - timedelta(seconds=2)).replace(microsecond=0)
                self.since = start.strftime("%Y-%m-%dT%H:%M:%SZ")
                db.execute("INSERT INTO metadata(key,value) VALUES(?,?)", (key, self.since))
            else:
                self.since = row["value"]

    def collect(self) -> list[Event]:
        events = []
        for item in self.client.list_open_issues(self.since):
            if "pull_request" in item or item.get("state") != "open":
                continue
            if str(item["created_at"]) < self.since:
                continue
            title, body = str(item["title"]), str(item.get("body") or "")
            revision = revision_hash(title, body)
            number = int(item["number"])
            events.append(Event(
                id=f"github:issue:{self.client.repo}:{number}:{revision}", kind="issue",
                issue=(self.client.repo, number), revision=revision,
                actor=str(item["user"]["login"]), payload={"title": title, "body": body},
            ))
        return events
