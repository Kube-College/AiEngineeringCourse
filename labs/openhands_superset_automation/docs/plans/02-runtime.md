# OpenHands Docker runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run and resume bounded real OpenHands conversations using OpenRouter.

**Architecture:** Implement the provider-neutral adapter against a qualified pinned SDK release. Persist Docker workspace and conversation state independently and enforce limits at every model-request boundary.

**Tech Stack:** Python with uv, SQLite, pytest, OpenHands SDK/Agent Server, Docker, GitHub REST, OpenRouter; Superset supplies its own Python and frontend toolchains.

**Spec:** [Approved design](../2026-09-23-openhands-design.md). Read the [plan index and interface contracts](README.md) before executing.

## Global Constraints

- Keep the course branch local during WIP. Do not push course material or open a course PR.
- Runtime: local uv-managed Python controller; Docker Agent Server.
- Provider/model: OpenRouter `openai/gpt-5.6-terra`; no silent model switching.
- Poll interval: 20 seconds. Active agent executions: one, across all roles.
- Timeout: 20 minutes per run. Iteration cap: 50 per run.
- Issue budget: US$5 across roles, retries, and the fix cycle; accrued cost survives revision changes.
- Automatic fix cycles: one per issue revision. Human approval and merge are mandatory.
- Completed workspace retention: 24 hours after workflow completion. Failed workspace retention: until explicit cleanup.
- GitHub writes: disabled until a demo fork is configured; never target `apache/superset`.
- Baseline: `c9fd9bf94f45163afd24f39f5ed9eec23a999150`; backend #44385, frontend #44466.
- Use uv for controller Python. Derive target toolchains from the pinned Superset source.
- All paths below are relative to the lab root. Run commands there, prefix shell commands with `rtk`, and stage only each task's audited files.
- Every commit is local. End each task with its focused checks and an explicit-path commit.

## Review Focus

- SDK routing must not accidentally select direct OpenAI billing (Task 02.1).
- Lost HTTP responses after conversation creation must preserve uncertainty (Task 02.2).
- SDK retries must pass through the budget gate (Task 02.2).
- Container recreation must not silently discard conversations or changes (Task 02.3).
- Cleanup must never delete active or unrelated workspaces (Task 02.3).

### Task 02.1: Qualify the SDK and model route

**Files:** Create `scripts/qualify_openhands.py`,
`src/openhands_controller/runtime/{__init__,prompts}.py`,
`tests/test_model_config.py`, `docs/evidence/runtime-qualification.md`.
Modify `pyproject.toml`, `uv.lock`, `config.py`.

**Interfaces:** Produce `build_llm_config(settings) -> dict[str, object]`.
Its output is SDK-specific and private to the runtime.
Produce strict triage, implementation/fix, and review result schemas from the index.

- [ ] Inspect official SDK release metadata, DockerWorkspace example, persistence,
LLM routing, metrics, retry, pause, and stop APIs for one selected release.
Record exact source links/revisions and callable signatures in the qualification
report. Pin the compatible packages in uv; do not invent SDK methods.
- [ ] Write failing configuration tests with a mocked SDK constructor:

```python
def test_model_route_is_openrouter(settings):
    cfg = build_llm_config(settings)
    assert cfg["base_url"] == "https://openrouter.ai/api/v1"
    assert "gpt-5.6-terra" in cfg["model"]
    assert cfg["api_key"] == settings.openrouter_api_key
```

The settings fixture uses a dummy key. Also assert no key appears in repr/logs.
- [ ] Run `rtk proxy uv run pytest tests/test_model_config.py -q`.
Implement the verified routing prefix/configuration; avoid setting conflicting
provider prefixes and endpoints.
- [ ] Create a smoke script that asks for a small file change through actual
terminal/file-editing tools in a disposable Docker checkout. Reject free-text
completion without filesystem evidence. Use no GitHub token.
- [ ] Run `rtk proxy uv run scripts/qualify_openhands.py --smoke` only with
locally configured model access. Record model/provider, image digest, tool
execution, token/cost evidence, and redacted output. If unavailable, record the
missing prerequisite and keep live execution disabled.
- [ ] Commit `feat: qualify pinned OpenHands OpenRouter configuration`.

### Task 02.2: Real adapter with bounded requests and typed outcomes

**Files:** Create `src/openhands_controller/adapters/openhands.py`,
`tests/test_openhands_adapter.py`. Modify `budget.py`, `runtime/prompts.py`,
`scripts/qualify_openhands.py`.

**Interfaces:** Implement all `AgentAdapter` methods. Translate remote statuses
into `RunObservation`. Consume `Budget.reserve/settle`. Keep SDK objects private.

- [ ] Add adapter tests using a transport double with create/start/status/stop
response scripts. Include malformed result, waiting-for-input, provider 429,
timeout, and create-response loss.
- [ ] Add a per-request gate test; `adapter_harness` supplies an SDK transport
double and a real temporary budget ledger:

```python
def test_retry_is_budgeted(adapter_harness):
    h = adapter_harness(budget_microusd=100_000)
    h.transport.responses = ["429", "success"]
    h.run()
    assert h.transport.model_calls <= h.budget.authorised_request_count
    assert h.budget.unaccounted_request_count == 0
```

Implement the two count properties on the test ledger wrapper from stored records.
- [ ] Run `rtk proxy uv run pytest tests/test_openhands_adapter.py -q`.
- [ ] Connect verified SDK request hooks to reservation and settlement for every
request and retry. Disable hidden automatic retries if they bypass the gate.
Preserve unknown cost after ambiguous provider outcomes. Enforce token caps,
iteration cap, deadline, and cancellation. Unsupported hooks keep the live
profile disabled and produce a specific capability failure.
- [ ] Extract strict role outputs; terminal status alone is not successful
completion. Waiting-for-input becomes a human handoff with the question.
Reject review results without the exact candidate SHA.
- [ ] Run focused tests plus the real smoke with a deliberately tiny budget
to demonstrate stopping. Do not claim hard billing ceilings.
- [ ] Commit `feat: add bounded OpenHands conversation adapter`.

### Task 02.3: Persistent isolated workspace lifecycle

**Files:** Create `src/openhands_controller/runtime/workspaces.py`,
`tests/test_workspaces.py`, `tests/live/test_runtime_lifecycle.py`.
Modify `scheduler.py`, `cli.py`, `scripts/qualify_openhands.py`,
`docs/evidence/runtime-qualification.md`.

**Interfaces:** Produce `WorkspaceManager.ensure(issue, base_sha, image_digest) -> str`,
`reattach(workspace_id) -> None`, `stop(workspace_id) -> None`,
and `cleanup(now) -> list[str]`. Persist IDs and version metadata in Store.

- [ ] Write failing tests for workspace identity, persisted volume paths,
loopback/auth configuration, forbidden mounts, and retention:

```python
def test_cleanup_keeps_active_failed_and_foreign_workspaces(manager):
    manager.seed("active", state="implementing", age_hours=48)
    manager.seed("failed", state="needs-human", age_hours=48)
    manager.seed("foreign", state="completed", age_hours=48, owned=False)
    assert manager.cleanup(manager.clock.now()) == []
```

The manager fixture uses fake Docker inspection and temporary Store records.
- [ ] Run `rtk proxy uv run pytest tests/test_workspaces.py -q`.
- [ ] Provision deterministic owned container/volume labels. Mount only issue
storage and required conversation data. Exclude GitHub credentials, Docker
socket, home directories, and course sources. Use authenticated Agent Server
bound to loopback; verify the chosen SDK actually honours these settings.
- [ ] Reattach after controller restart; recreate after container loss with the
same image and storage. Refuse incompatible saved-state versions.
Confirm stop before changing durable state; terminate unresponsive runtimes.
- [ ] Add live tests that edit a marker file, pause, restart the controller,
recreate the container, resume, and verify the file and conversation continuity.
Assert only one dispatch was created. Test forced stop and unknown-state handoff.
- [ ] Run `rtk proxy uv run pytest tests/live/test_runtime_lifecycle.py -m live -q`
with explicit local credentials and Docker access. Sanitise evidence; retain
failure workspaces until explicit cleanup.
- [ ] Commit `feat: persist and recover isolated agent workspaces`.

## Completion gate

Enable the live profile only when recorded evidence demonstrates routing,
tool execution, limits, budget hooks, persistence, restart, and cancellation.
A completed SDK installation is not qualification.
