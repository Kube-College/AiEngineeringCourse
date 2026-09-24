import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings
from .simulation import Scenario, run_scenario
from .triage import build_live_service
from .persistence.store import Store
from .performance import make_dashboard_server

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
    """Poll issues, run triage, and start implementation after label approval."""
    settings = Settings()
    try:
        service, agent = build_live_service(settings)
    except (ValueError, KeyError, OSError) as exc:
        typer.echo(f"Cannot start triage: {exc}", err=True)
        raise typer.Exit(2) from exc
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    typer.echo(f"Watching {settings.gh_repo} every {settings.poll_seconds}s for issues and approvals")
    if not settings.github_writes_enabled:
        typer.echo("GitHub status comments are disabled; progress appears in this terminal")
    try:
        service.run_forever(settings.poll_seconds)
    except KeyboardInterrupt:
        typer.echo("Stopping triage controller")
    finally:
        service.controller.close()
        agent.close()


@app.command()
def dashboard(
    state_dir: Annotated[Path | None, typer.Option(help="Controller state directory.")] = None,
    port: Annotated[int, typer.Option(min=1, max=65535, help="Loopback HTTP port.")] = 8765,
) -> None:
    """Serve a local, read-only agent performance console."""
    directory = state_dir or Settings().state_dir
    try:
        server = make_dashboard_server(directory / "controller.sqlite", directory, port=port)
    except (FileNotFoundError, OSError) as exc:
        typer.echo(f"Cannot start dashboard: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"Agent performance: http://127.0.0.1:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        typer.echo("Stopping dashboard")
    finally:
        server.server_close()


@app.command()
def rate(
    dispatch_id: Annotated[str, typer.Argument(help="Run ID shown in the performance console.")],
    rating: Annotated[str, typer.Option(help="useful, partly-useful, or incorrect")],
    note: Annotated[str, typer.Option(help="Short reason for the rating.")] = "",
    state_dir: Annotated[Path | None, typer.Option(help="Controller state directory.")] = None,
) -> None:
    """Record human quality feedback without advancing the workflow."""
    directory = state_dir or Settings().state_dir
    path = directory / "controller.sqlite"
    if not path.is_file():
        typer.echo("Controller database not found", err=True)
        raise typer.Exit(2)
    try:
        Store(path).rate_dispatch(dispatch_id, rating, note)
    except (ValueError, KeyError) as exc:
        typer.echo(f"Cannot rate run: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"Recorded {rating} for {dispatch_id}")
