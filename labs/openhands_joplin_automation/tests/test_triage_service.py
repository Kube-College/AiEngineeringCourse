from datetime import datetime, timezone
from time import sleep

import pytest

from openhands_controller.adapters.simulated import SimulatedAgent
from openhands_controller.config import Settings
from openhands_controller.engine.controller import Controller
from openhands_controller.github.polling import GitHubPoller
from openhands_controller.github.client import GitHubRateLimit
from openhands_controller.persistence.store import Store
from openhands_controller.triage import (TriageOnlyDelivery, TriageService, build_live_service,
                                          validate_live_settings)


NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)


class FakeIssueAPI:
    repo = "lspinheiro/joplin"

    def __init__(self):
        self.items = []

    def list_open_issues(self, since):
        return list(self.items)


def test_new_issue_triggers_one_triage_and_waits_for_approval(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    api = FakeIssueAPI()
    poller = GitHubPoller(store, api, clock=lambda: NOW)
    agent = SimulatedAgent()
    controller = Controller(store, agent, TriageOnlyDelivery(), lambda actor, repo: "read",
                            lambda: NOW, Settings(_env_file=None))
    service = TriageService(controller, poller, projector=None)
    try:
        service.step()
        api.items.append({"id": 17, "number": 17, "title": "Note title broken", "body": "Steps",
                          "created_at": "2026-09-24T00:00:05Z", "updated_at": "2026-09-24T00:00:05Z",
                          "state": "open", "user": {"login": "reporter"}})
        for _ in range(100):
            service.step()
            active = store.active_dispatch()
            if active and active.status == "running":
                break
            sleep(0.001)
        else:
            pytest.fail("new issue did not start triage")
        assert active.role == "triage"
        agent.complete(active.id, {"scope": "note title", "summary": "Reproduced issue",
                                   "validation_profile": "core"})
        for _ in range(100):
            service.step()
            if store.workflow((api.repo, 17)).state == "awaiting-approval":
                break
            sleep(0.001)
        assert store.workflow((api.repo, 17)).state == "awaiting-approval"
        assert len(store.dispatches((api.repo, 17))) == 1
        for _ in range(3):
            service.step()
        assert len(store.dispatches((api.repo, 17))) == 1
    finally:
        controller.close()


def test_live_start_requires_token_model_and_real_agent():
    with pytest.raises(ValueError, match="GH_TOKEN"):
        validate_live_settings(Settings(_env_file=None, agent_backend="openhands",
                                        gh_repo="lspinheiro/joplin", llm_api_key="model-key"))
    with pytest.raises(ValueError, match="AGENT_BACKEND"):
        validate_live_settings(Settings(_env_file=None, agent_backend="simulated",
                                        gh_repo="lspinheiro/joplin", gh_token="token",
                                        llm_api_key="model-key"))
    validate_live_settings(Settings(_env_file=None, agent_backend="openhands",
                                    gh_repo="lspinheiro/joplin", gh_token="token",
                                    llm_api_key="model-key"))


def test_triage_dispatch_uses_persistent_workspace_identity(tmp_path):
    store = Store(tmp_path / "state.sqlite")
    store.create_workflow(("lspinheiro/joplin", 4), "revision", budget_limit=5_000_000)
    controller = Controller(store, SimulatedAgent(), TriageOnlyDelivery(), lambda actor, repo: "read",
                            lambda: NOW, Settings(_env_file=None),
                            workspace_id_for_issue=lambda issue: f"stable-{issue[1]}")
    try:
        controller.tick()
        assert store.active_dispatch().workspace_id == "stable-4"
    finally:
        controller.close()


def test_live_service_loads_pinned_image_and_configured_fork(tmp_path):
    settings = Settings(_env_file=None, state_dir=tmp_path / "state", workspace_dir=tmp_path / "workspaces",
                        agent_backend="openhands", gh_repo="https://github.com/lspinheiro/joplin", gh_token="token",
                        llm_api_key="model-key")
    service, agent = build_live_service(settings)
    try:
        assert service.poller.client.repo == "lspinheiro/joplin"
        assert agent.base_sha == "1d6beb0443e6d958b2c241f45978bd5de069f309"
        assert agent.image_digest.startswith("sha256:")
        assert service.projector is None
    finally:
        service.controller.close()
        agent.close()


def test_run_loop_waits_for_github_rate_limit(monkeypatch):
    service = TriageService(None, None, None)
    calls, sleeps = [], []
    now = [0]

    def step(*, poll=True):
        calls.append(poll)
        if len(calls) == 1:
            raise GitHubRateLimit(65)
        if len(calls) == 4:
            raise KeyboardInterrupt

    def advance(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(service, "step", step)
    monkeypatch.setattr("openhands_controller.triage.time.sleep", advance)
    monkeypatch.setattr("openhands_controller.triage.time.monotonic", lambda: now[0])
    with pytest.raises(KeyboardInterrupt):
        service.run_forever(20)
    assert calls == [True, False, False, False]
    assert sleeps == [1, 1, 1]


def test_failed_github_poll_still_ticks_active_controller():
    class FailedPoller:
        def collect(self):
            raise GitHubRateLimit(65)

    class CountingController:
        def __init__(self):
            self.ticks = 0

        def tick(self):
            self.ticks += 1

    controller = CountingController()
    service = TriageService(controller, FailedPoller(), None)
    with pytest.raises(GitHubRateLimit):
        service.step()
    assert controller.ticks == 1
