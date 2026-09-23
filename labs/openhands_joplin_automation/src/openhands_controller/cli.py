import argparse
import json
from pathlib import Path

from .contracts import Event
from .store import Store


def main() -> None:
    parser = argparse.ArgumentParser(prog="controller")
    commands = parser.add_subparsers(dest="command", required=True)
    simulate = commands.add_parser("simulate")
    simulate.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    store = Store(args.state_dir / "controller.sqlite")
    event = Event("demo-issue-1", "issue", ("demo/joplin", 1), "r1", "maintainer",
                  {"title": "Joplin demo issue", "body": "Credential-free simulation"})
    store.record_event(event)
    store.create_workflow(event.issue, event.revision, title=str(event.payload["title"]), body=str(event.payload["body"]))
    print(json.dumps(store.workflow(event.issue), sort_keys=True))
