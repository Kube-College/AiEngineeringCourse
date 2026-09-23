import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings
from .simulation import Scenario, run_scenario
from .triage import build_live_service

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


@app.command("run")
def run() -> None:
    """Poll the configured fork and run OpenHands triage for new issues."""
    settings = Settings()
    try:
        service, agent = build_live_service(settings)
    except (ValueError, KeyError, OSError) as exc:
        typer.echo(f"Cannot start triage: {exc}", err=True)
        raise typer.Exit(2) from exc
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    typer.echo(f"Watching {settings.gh_repo} every {settings.poll_seconds}s for new issues")
    if not settings.github_writes_enabled:
        typer.echo("GitHub status comments are disabled; progress appears in this terminal")
    try:
        service.run_forever(settings.poll_seconds)
    except KeyboardInterrupt:
        typer.echo("Stopping triage controller")
    finally:
        service.controller.close()
        agent.close()
