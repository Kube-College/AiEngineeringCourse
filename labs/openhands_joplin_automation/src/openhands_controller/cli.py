import json
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings
from .simulation import Scenario, run_scenario

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Durable controller for the Joplin automation lab."""


@app.command()
def simulate(
    state_dir: Annotated[Path | None, typer.Option(help="SQLite state directory; defaults to STATE_DIR.")] = None,
    scenario: Annotated[Scenario, typer.Option(help="Lifecycle to run.")] = Scenario.QUEUED,
) -> None:
    """Run a credential-free scenario and print the persisted workflow and budget."""
    settings = Settings()
    path = (state_dir or settings.state_dir) / "controller.sqlite"
    typer.echo(json.dumps(run_scenario(path, scenario, settings), sort_keys=True))
