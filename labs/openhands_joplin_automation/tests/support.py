from datetime import datetime, timedelta, timezone
from time import sleep

from openhands_controller.adapters.simulated import SimulatedAgent
from openhands_controller.contracts import Event, ValidationResult
from openhands_controller.controller import Controller
from openhands_controller.store import Store


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 9, 23, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class FakeDelivery:
    def __init__(self):
        self.published: list[str] = []
        self.passes = True

    def capture(self, dispatch):
        return f"sha-{dispatch.id}"

    def validate(self, candidate_sha, profile):
        return ValidationResult(candidate_sha, profile, self.passes, "fake-evidence")

    def publish(self, issue, candidate_sha):
        self.published.append(candidate_sha)
        return f"https://example.invalid/{issue[1]}/draft"


class Harness:
    def __init__(self, root, fault=None):
        self.root = root
        self.fault = fault
        self.store = Store(root / "state.sqlite")
        self.revision = "r1"
        self.clock = FakeClock()
        self.agent = SimulatedAgent(fault)
        self.delivery = FakeDelivery()
        self.controller = Controller(self.store, self.agent, self.delivery, lambda actor, repo: "write", self.clock)
        self.next_event = 0

    def issue(self, **payload):
        return Event(
            id="issue-1", kind="issue", issue=("demo/joplin", 1),
            revision=self.revision, actor="maintainer",
            payload={"title": "Initial scope", "body": "Initial body", **payload},
        )

    def restart(self):
        self.controller.close()
        self.store = Store(self.root / "state.sqlite")
        self.controller = Controller(self.store, self.agent, self.delivery, lambda actor, repo: "write", self.clock)

    def emit(self, kind, **payload):
        self.next_event += 1
        event = Event(f"event-{self.next_event}", kind, ("demo/joplin", 1),
                      payload.pop("revision", self.revision), "maintainer", payload)
        self.controller.handle(event)
        return event

    def complete(self, role, **result):
        dispatches = self.store.dispatches(("demo/joplin", 1))
        dispatch = next(d for d in reversed(dispatches) if d.role == role)
        for _ in range(200):
            if self.store.dispatch_row(dispatch.id)["status"] == "running":
                break
            self.controller.tick()
            sleep(0.001)
        else:
            raise AssertionError(f"dispatch {dispatch.id} did not start")
        self.agent.complete(dispatch.id, result)

    def run_to(self, state, max_ticks=200):
        for _ in range(max_ticks):
            if self.store.workflow(("demo/joplin", 1))["state"] == state:
                return
            self.controller.tick()
            sleep(0.001)
        raise AssertionError(f"state {state} not reached; got {self.store.workflow(('demo/joplin', 1))['state']}")
