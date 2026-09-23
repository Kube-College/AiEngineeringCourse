from datetime import datetime, timedelta, timezone

from openhands_controller.adapters.simulated import SimulatedAgent, SimulatedDelivery
from openhands_controller.config import Settings
from openhands_controller.domain.models import Event
from openhands_controller.domain.states import DispatchStatus, Role
from openhands_controller.simulation import ISSUE, Simulation


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 9, 23, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


class Harness(Simulation):
    max_ticks = 200

    def __init__(self, root, fault=None, settings=None):
        self.root = root
        self.revision = "r1"
        self.next_event = 0
        super().__init__(root / "state.sqlite", settings=settings or Settings(_env_file=None),
                         clock=FakeClock(), agent=SimulatedAgent(fault), delivery=SimulatedDelivery())

    def issue(self, **payload):
        return Event(
            id="issue-1", kind="issue", issue=ISSUE,
            revision=self.revision, actor="maintainer",
            payload={"title": "Initial scope", "body": "Initial body", **payload},
        )

    def emit(self, kind, **payload):
        self.next_event += 1
        event = Event(f"event-{self.next_event}", kind, ISSUE,
                      payload.pop("revision", self.revision), "maintainer", payload)
        self.controller.handle(event)
        return event

    def run_to(self, state):
        try:
            self.store.workflow(ISSUE)
        except KeyError:
            self.emit("issue", title="Initial scope", body="Initial body")
        for _ in range(self.max_ticks):
            current = self.store.workflow(ISSUE).state
            if current == state:
                active = self.store.active_dispatch()
                if state != "implementing" or (active and active.role == Role.IMPLEMENTATION
                                               and active.status == DispatchStatus.RUNNING):
                    return
            if state in {"awaiting-approval", "implementing"} and current == "triaging":
                self.complete(Role.TRIAGE, scope="test issue", summary="test scope", validation_profile="core")
            if state == "implementing" and current == "awaiting-approval":
                self.emit("command", body="/agent implement")
            self.step()
        raise AssertionError(f"state {state} not reached; got {self.store.workflow(ISSUE).state}")
