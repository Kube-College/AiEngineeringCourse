---
type: Repository Guide
title: OpenHands Joplin Automation quickstart
description: Navigation and change guidance for the durable controller that triages Joplin fork issues and runs human-approved OpenHands implementation work.
tags: [openhands, joplin, github, sqlite]
openwiki:
  roles: [repository, workflow]
  source_paths: [README.md, pyproject.toml, src/openhands_controller/cli.py]
  symbols: [app, simulate, run, dashboard, rate]
  test_paths: [tests/test_triage_service.py, tests/test_commands.py]
  validation_commands: ["uv run pytest tests/test_triage_service.py -q"]
---
# OpenHands Joplin Automation

This lab is a Python/uv controller for a Joplin fork. It persists issue workflows in SQLite, polls GitHub for new issues and a post-triage approval label, and dispatches one OpenHands conversation at a time. The live path intentionally ends in `needs-human` after implementation: validation and draft-PR publication are not enabled by `TriageOnlyDelivery`.

Start with [controller lifecycle](architecture/controller-lifecycle.md) for workflow semantics, [GitHub triage](integrations/github-triage.md) for the fork-facing contract, [runtime and workspaces](architecture/runtime-and-workspaces.md) for OpenHands and Docker boundaries, and [local console](operations/local-console.md) for persisted evidence and feedback.

## Operating modes

`controller simulate` is credential-free and uses the simulated backend. `controller run` requires the live configuration validated by `validate_live_settings`: OpenHands backend, configured fork, GitHub token, and model API key. `make run` wraps the live command with the runtime dependency extra; `make dashboard` serves the local read-only console. Configuration is parsed by `Settings` in `src/openhands_controller/config.py`; `.env` is ignored and must not be placed in this wiki.

## Task routing

| Change area or user intent | Relevant wiki page | Exact source entry points | Important symbols or types | Focused tests | Minimal validation command |
| --- | --- | --- | --- | --- | --- |
| Add or change a workflow transition, command, stop rule, or dispatch behavior | [Controller lifecycle](architecture/controller-lifecycle.md) | `src/openhands_controller/engine/controller.py`, `src/openhands_controller/domain/states.py` | `Controller`, `WorkflowState`, `DispatchStatus`, `StopRequest` | `tests/test_dispatch.py`, `tests/test_commands.py`, `tests/test_triage_service.py` | `uv run pytest tests/test_dispatch.py tests/test_commands.py -q` |
| Change issue polling, approval-label authorization, status comments, or labels | [GitHub triage](integrations/github-triage.md) | `src/openhands_controller/github/polling.py`, `src/openhands_controller/github/projection.py`, `src/openhands_controller/triage.py` | `GitHubPoller`, `Projector`, `TriageService` | `tests/test_github_triage.py`, `tests/test_triage_service.py` | `uv run pytest tests/test_github_triage.py tests/test_triage_service.py -q` |
| Add a role, revise tools/instructions, or change OpenRouter model accounting | [Runtime and workspaces](architecture/runtime-and-workspaces.md) | `src/openhands_controller/runtime/agents.py`, `src/openhands_controller/runtime/live.py` | `AGENTS`, `AgentProfile`, `ModelRoute`, `LiveTriageAgent` | `tests/test_agent_profiles.py`, `tests/test_model_config.py`, `tests/test_openhands_adapter.py` | `uv run pytest tests/test_agent_profiles.py tests/test_model_config.py -q` |
| Change workspace recovery, container identity, or Agent Server connection | [Runtime and workspaces](architecture/runtime-and-workspaces.md) | `src/openhands_controller/runtime/workspaces.py`, `src/openhands_controller/runtime/live.py` | `WorkspaceManager`, `ContainerSpec`, `load_runtime_tokens` | `tests/test_workspaces.py`, `tests/test_live_triage.py` | `uv run pytest tests/test_workspaces.py tests/test_live_triage.py -q` |
| Change SQLite facts, dashboard output, event redaction, or human rating | [Local console](operations/local-console.md) | `src/openhands_controller/persistence/schema.sql`, `src/openhands_controller/performance.py`, `src/openhands_controller/cli.py` | `Store`, `PerformanceReader`, `make_dashboard_server`, `rate` | `tests/test_performance_store.py`, `tests/test_performance_http.py`, `tests/test_performance_dashboard.py` | `uv run pytest tests/test_performance_store.py tests/test_performance_http.py -q` |
| Modify command-line surface or local developer commands | This page and [Local console](operations/local-console.md) | `src/openhands_controller/cli.py`, `Makefile`, `pyproject.toml` | `app`, `simulate`, `run`, `dashboard`, `rate` | `tests/test_commands.py`, `tests/test_performance_http.py` | `uv run pytest tests/test_commands.py -q` |

Use `-q` for focused checks. Run `uv run pytest -q` only when a change crosses several listed seams. The authenticated Docker/OpenRouter runtime qualification is conditional: use `controller qualify-runtime --image-digest ...` only when changing the pinned live runtime, SDK integration, image, or credentials-dependent behavior.

## Change boundaries

The controller has a database-level single-active-dispatch invariant, so do not parallelize scheduling by changing a single call site. GitHub label changes are not commands except a newly added `agent:implement` label after entry to `awaiting-approval`; see [GitHub triage](integrations/github-triage.md). Role tool selection is not an operating-system write barrier—triage and review prompts ask for no edits, but terminal access can write—so changes needing enforced read-only execution belong at the workspace boundary described in [runtime and workspaces](architecture/runtime-and-workspaces.md).

## Backlog

- `src/openhands_controller/triage.py` — live candidate validation and draft PR publication remain intentionally unavailable through `TriageOnlyDelivery`; document a delivery workflow once an implementation exists.
