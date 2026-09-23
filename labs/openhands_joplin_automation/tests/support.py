from openhands_controller.contracts import Event
from openhands_controller.store import Store


class Harness:
    def __init__(self, root, fault=None):
        self.root = root
        self.fault = fault
        self.store = Store(root / "state.sqlite")
        self.revision = "r1"

    def issue(self, **payload):
        return Event(
            id="issue-1", kind="issue", issue=("demo/joplin", 1),
            revision=self.revision, actor="maintainer",
            payload={"title": "Initial scope", "body": "Initial body", **payload},
        )

    def restart(self):
        self.store = Store(self.root / "state.sqlite")
