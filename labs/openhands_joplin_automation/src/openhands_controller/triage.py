"""Run triage and label-approved implementation on the configured fork."""

import logging
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .domain.models import Dispatch, IssueKey, ValidationResult
from .engine.controller import Controller
from .github.polling import GitHubPoller
from .github.projection import Projector
from .github.client import GitHubClient, GitHubRateLimit
from .persistence.store import Store
from .runtime.live import LiveTriageAgent, load_runtime_tokens
from .runtime.workspaces import DockerCLI, WorkspaceManager


LOG = logging.getLogger(__name__)


def validate_live_settings(settings: Settings) -> None:
    if settings.agent_backend != "openhands":
        raise ValueError("AGENT_BACKEND=openhands is required for live triage")
    if not settings.gh_repo:
        raise ValueError("GH_REPO must name the demo fork")
    if not settings.gh_token.get_secret_value():
        raise ValueError("GH_TOKEN is required for GitHub polling")
    if not settings.llm_api_key.get_secret_value():
        raise ValueError("LLM_API_KEY is required for OpenHands triage")
    if settings.gateway_port < 1024 or settings.gateway_port > 65535:
        raise ValueError("GATEWAY_PORT must be between 1024 and 65535")


def build_live_service(settings: Settings) -> tuple["TriageService", LiveTriageAgent]:
    validate_live_settings(settings)
    lab_root = Path(__file__).resolve().parents[2]
    manifest = json.loads((lab_root / "docker" / "versions.json").read_text())
    base_sha, image_digest = manifest["joplin_sha"], manifest["built_image_digest"]
    store = Store(settings.state_dir / "controller.sqlite")
    server_token, gateway_token = load_runtime_tokens(settings.state_dir)
    client = GitHubClient(settings.gh_repo, settings.gh_token.get_secret_value())
    manager = WorkspaceManager(store, settings.workspace_dir, docker=DockerCLI(),
                               server_token=server_token, image_repository=None)
    agent = LiveTriageAgent(store, settings, manager, base_sha=base_sha, image_digest=image_digest,
                            gateway_token=gateway_token, gateway_port=settings.gateway_port)
    controller = Controller(
        store, agent, TriageOnlyDelivery(),
        client.permission,
        lambda: datetime.now(timezone.utc), settings,
        workspace_id_for_issue=manager.identifier,
    )
    poller = GitHubPoller(store, client, clock=lambda: datetime.now(timezone.utc))
    projector = Projector(store, client) if settings.github_writes_enabled else None
    return TriageService(controller, poller, projector), agent


class TriageOnlyDelivery:
    """Stop after implementation while validation and publication are unavailable."""

    stop_after_implementation = True

    def capture(self, dispatch: Dispatch) -> str:
        raise RuntimeError("implementation delivery is not enabled")

    def validate(self, candidate_sha: str, profile: str) -> ValidationResult:
        raise RuntimeError("implementation validation is not enabled")

    def publish(self, issue: IssueKey, candidate_sha: str) -> str:
        raise RuntimeError("draft PR publication is not enabled")


class TriageService:
    def __init__(self, controller: Controller, poller: GitHubPoller, projector: Projector | None):
        self.controller = controller
        self.poller = poller
        self.projector = projector
        self._seen: dict[IssueKey, str] = {}

    def step(self, *, poll: bool = True) -> None:
        polling_error = None
        if poll:
            try:
                for event in self.poller.collect():
                    self.controller.handle(event)
            except Exception as exc:
                polling_error = exc
        self.controller.tick()
        if polling_error is not None:
            raise polling_error
        for row in self.controller.store.workflows():
            if row.issue[0] != self.poller.client.repo:
                continue
            if self._seen.get(row.issue) != row.state:
                LOG.info("%s#%s: %s", row.repo, row.issue_number, row.state)
                self._seen[row.issue] = row.state
            if poll and self.projector is not None:
                try:
                    self.projector.sync(row.issue)
                except GitHubRateLimit:
                    raise
                except Exception:
                    LOG.exception("status comment update failed for %s#%s", *row.issue)

    def run_forever(self, poll_seconds: int) -> None:
        next_poll = time.monotonic()
        while True:
            now = time.monotonic()
            poll = now >= next_poll
            if poll:
                next_poll = now + poll_seconds
            try:
                self.step(poll=poll)
            except GitHubRateLimit as exc:
                next_poll = now + max(poll_seconds, exc.retry_after)
                LOG.warning("GitHub rate limited; retrying in %ss", max(poll_seconds, exc.retry_after))
            except Exception:
                LOG.exception("triage cycle failed; retrying")
            time.sleep(1)
