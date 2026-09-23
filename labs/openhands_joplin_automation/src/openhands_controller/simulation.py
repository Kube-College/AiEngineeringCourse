"""Credential-free controller runs shared by the CLI and the tests."""

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable

from .adapters.simulated import SimulatedAgent, SimulatedDelivery
from .config import Settings
from .domain.models import Event
from .domain.states import DispatchStatus, Role, WorkflowState
from .engine.controller import Controller
from .persistence.budget import Budget
from .persistence.store import Store

ISSUE = ("demo/joplin", 1)


class Scenario(StrEnum):
    QUEUED = "queued"
    HAPPY = "happy"
    DUPLICATE = "duplicate"
    RESTART = "restart"
    BUDGET = "budget"
    CANCEL = "cancel"


def allow_writes(actor: str, repo: str) -> str:
    return "write"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Simulation:
    """A controller over simulated adapters that can be restarted on the same state."""

    max_ticks = 500

    def __init__(self, path: Path, *, settings: Settings | None = None,
                 clock: Callable[[], datetime] = utc_now,
                 agent: SimulatedAgent | None = None, delivery: SimulatedDelivery | None = None):
        self.path, self.settings, self.clock = path, settings, clock
        self.agent = agent or SimulatedAgent()
        self.delivery = delivery or SimulatedDelivery()
        self._open()

    def _open(self) -> None:
        self.store = Store(self.path)
        self.controller = Controller(self.store, self.agent, self.delivery, allow_writes, self.clock,
                                     self.settings)

    def restart(self) -> None:
        self.controller.close()
        self._open()

    def close(self) -> None:
        self.controller.close()

    def step(self) -> None:
        self.controller.tick()
        self.controller.wait(1)

    def until(self, *, state: WorkflowState | None = None, role: Role | None = None) -> None:
        """Tick until the demo issue reaches `state` or a `role` dispatch is running."""
        for _ in range(self.max_ticks):
            if state is not None and self.store.workflow(ISSUE).state == state:
                return
            active = self.store.active_dispatch()
            if role is not None and active and active.role == role and active.status == DispatchStatus.RUNNING:
                return
            self.step()
        raise RuntimeError(f"simulation did not reach {state or role}; got {self.store.workflow(ISSUE).state}")

    def complete(self, role: Role, **result: object) -> None:
        """Finish the running `role` dispatch with `result`."""
        self.until(role=role)
        self.agent.complete(self.store.active_dispatch().id, result)

    def snapshot(self) -> dict[str, object]:
        return {**self.store.workflow(ISSUE).model_dump(mode="json"),
                "budget": Budget(self.store).snapshot(ISSUE).model_dump()}


def run_scenario(path: Path, scenario: Scenario, settings: Settings | None = None) -> dict[str, object]:
    sim = Simulation(path, settings=settings)
    try:
        issue = Event("demo-issue-1", "issue", ISSUE, "r1", "maintainer",
                      {"title": "Joplin demo issue", "body": "Credential-free simulation"})
        sim.controller.handle(issue)
        if scenario is Scenario.QUEUED:
            return sim.snapshot()
        if scenario is Scenario.DUPLICATE:
            sim.controller.handle(issue)
        if scenario is Scenario.BUDGET:
            row = sim.store.workflow(ISSUE)
            sim.store.cas_workflow(ISSUE, row.version, budget_limit=500_000)
            sim.until(state=WorkflowState.NEEDS_HUMAN)
            return sim.snapshot()
        if scenario is Scenario.RESTART:
            sim.until(role=Role.TRIAGE)
            sim.restart()
        sim.complete(Role.TRIAGE, scope="shared note logic", summary="test note title change",
                     validation_profile="core")
        sim.until(state=WorkflowState.AWAITING_APPROVAL)
        sim.controller.handle(Event("demo-approval-1", "command", ISSUE, "r1", "maintainer",
                                    {"body": "/agent implement"}))
        if scenario is Scenario.CANCEL:
            sim.until(role=Role.IMPLEMENTATION)
            sim.controller.handle(Event("demo-cancel-1", "command", ISSUE, "r1", "maintainer",
                                        {"body": "/agent cancel"}))
            sim.until(state=WorkflowState.CANCELLED)
            return sim.snapshot()
        sim.complete(Role.IMPLEMENTATION, summary="changed note title logic",
                     changed_paths=["packages/lib/models/Note.ts"])
        sim.until(role=Role.REVIEW)
        sim.complete(Role.REVIEW, candidate_sha=sim.store.workflow(ISSUE).candidate_sha,
                     verdict="pass", findings=[])
        sim.until(state=WorkflowState.READY_FOR_HUMAN)
        return sim.snapshot()
    finally:
        sim.close()
