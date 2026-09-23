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


@app.command("qualify-runtime")
def qualify_runtime(
    image_digest: Annotated[str, typer.Option(help="Immutable Agent Server sha256 image digest.")],
) -> None:
    """Run the opt-in authenticated Docker and OpenRouter marker smoke."""
    settings = Settings()
    if not settings.llm_api_key.get_secret_value():
        typer.echo("OpenRouter key unavailable; live smoke disabled")
        raise typer.Exit(2)
    from .adapters.openhands import CapabilityError, run_smoke

    try:
        outcome = run_smoke(settings, image_digest)
    except CapabilityError as exc:
        typer.echo(str(exc))
        raise typer.Exit(2) from exc
    raise typer.Exit(outcome)
