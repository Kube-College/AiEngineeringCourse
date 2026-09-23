import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

from .adapters.simulated import SimulatedAgent, SimulatedDelivery
from .budget import Budget
from .contracts import Event
from .controller import Controller
from .store import Store


ISSUE = ("demo/joplin", 1)


def _until(controller: Controller, store: Store, *, state: str | None = None, role: str | None = None):
    for _ in range(500):
        row = store.workflow(ISSUE)
        active = store.active_dispatch()
        if state is not None and row["state"] == state:
            return
        if role is not None and active and active["role"] == role and active["status"] == "running":
            return
        controller.tick()
        sleep(0.001)
    raise RuntimeError(f"simulation did not reach {state or role}; got {store.workflow(ISSUE)['state']}")


def _run_scenario(store: Store, scenario: str) -> dict[str, object]:
    agent = SimulatedAgent()
    delivery = SimulatedDelivery()
    controller = Controller(store, agent, delivery, lambda actor, repo: "write",
                            lambda: datetime.now(timezone.utc))
    try:
        event = Event("demo-issue-1", "issue", ISSUE, "r1", "maintainer",
                      {"title": "Joplin demo issue", "body": "Credential-free simulation"})
        controller.handle(event)
        if scenario == "queued":
            return store.workflow(ISSUE)
        if scenario == "duplicate":
            controller.handle(event)
        if scenario == "budget":
            row = store.workflow(ISSUE)
            store.cas_workflow(ISSUE, row["version"], budget_limit=500_000)
            _until(controller, store, state="needs-human")
            return store.workflow(ISSUE)
        _until(controller, store, role="triage")
        if scenario == "restart":
            controller.close()
            store = Store(store.path)
            controller = Controller(store, agent, delivery, lambda actor, repo: "write",
                                    lambda: datetime.now(timezone.utc))
        triage = store.dispatches(ISSUE)[-1]
        agent.complete(triage.id, {"scope": "shared note logic", "summary": "test note title change",
                                   "validation_profile": "core"})
        _until(controller, store, state="awaiting-approval")
        controller.handle(Event("demo-approval-1", "command", ISSUE, "r1", "maintainer",
                                {"body": "/agent implement"}))
        _until(controller, store, role="implementation")
        if scenario == "cancel":
            controller.handle(Event("demo-cancel-1", "command", ISSUE, "r1", "maintainer",
                                    {"body": "/agent cancel"}))
            _until(controller, store, state="cancelled")
            return store.workflow(ISSUE)
        implementation = store.dispatches(ISSUE)[-1]
        agent.complete(implementation.id, {"summary": "changed note title logic",
                                           "changed_paths": ["packages/lib/models/Note.ts"]})
        _until(controller, store, role="review")
        review = store.dispatches(ISSUE)[-1]
        agent.complete(review.id, {"candidate_sha": store.workflow(ISSUE)["candidate_sha"],
                                   "verdict": "pass", "findings": []})
        _until(controller, store, state="ready-for-human")
        return store.workflow(ISSUE)
    finally:
        controller.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="controller")
    commands = parser.add_subparsers(dest="command", required=True)
    simulate = commands.add_parser("simulate")
    simulate.add_argument("--state-dir", type=Path, required=True)
    simulate.add_argument("--scenario", choices=["queued", "happy", "duplicate", "restart", "budget", "cancel"], default="queued")
    args = parser.parse_args(argv)
    store = Store(args.state_dir / "controller.sqlite")
    row = _run_scenario(store, args.scenario)
    print(json.dumps({**row, "budget": Budget(Store(store.path)).snapshot(ISSUE)}, sort_keys=True))
