# Durable controller simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a credential-free simulation of the complete issue workflow.

**Architecture:** A synchronous state-machine core uses SQLite transactions and replaceable external adapters. A non-blocking scheduler observes external work; fake adapters reproduce recovery and failure cases.

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

- Duplicate event IDs with different payloads must report a conflict (Task 01.1).
- Crash after remote creation but before identifier persistence must not redispatch (Task 01.2).
- A stale approval label or edited comment must not authorise a new revision (Task 01.3).
- Unknown spend and replayed usage must never restore budget (Task 01.4).
- Cancel racing with completion must prevent publication (Task 01.3).

### Task 01.1: Runnable persisted simulation

**Files:** Create `pyproject.toml`, `uv.lock`, `src/openhands_controller/{__init__,contracts,config,cli,store}.py`, `src/openhands_controller/schema.sql`, `tests/{support,test_store}.py`. Modify `README.md`.

**Interfaces:** Define the shared records and `Store.workflow`, `Store.dispatches`.
Produce `Store.record_event(event: Event) -> bool` (false for identical replay;
raise `EventConflict` for a reused ID with different canonical payload).
Define `EventConflict` in `contracts.py`.

- [ ] Inspect original controller licence and record reuse decision in `docs/source-reuse.md`. Implement independently if reuse permission is absent.
- [ ] Package an independent uv project with a `controller` CLI entry point and pytest dev dependency. Select a Python version compatible with the SDK during 02.1; no parent uv workspace changes.
- [ ] Write and run the failure test:

```python
def test_event_replay_and_conflict(tmp_path):
    h = Harness(tmp_path)
    event = h.issue()
    assert h.store.record_event(event) is True
    assert h.store.record_event(event) is False
    with pytest.raises(EventConflict):
        h.store.record_event(replace(event, payload={"title": "changed"}))
```

Run `rtk proxy uv run pytest tests/test_store.py -q`; first execution must fail
on missing behaviour, then pass after implementation.
- [ ] Implement schema tables for workflows, events, dispatches, workspaces,
usage, validations, publications, and metadata. Use integer microdollars for
money, foreign keys, and explicit transactions. Add CAS workflow versions and
unique active-dispatch constraints. Reject unknown configuration keys and
nonpositive limits.
- [ ] Add restart persistence and concurrent CAS tests. Implement `Harness`
and bounded tick helpers from the index.
- [ ] Verify `rtk proxy uv run controller simulate --state-dir /tmp/openhands-demo-01`
creates a queued issue and prints its persisted state. The simulation must not
make network calls.
- [ ] Run focused tests, document the command, and commit only this task's files
with message `feat: add durable controller simulation storage`.

### Task 01.2: Dispatch, state transitions, and recovery

**Files:** Create `src/openhands_controller/{controller,scheduler}.py`,
`src/openhands_controller/adapters/{__init__,simulated}.py`,
`tests/test_dispatch.py`. Modify `tests/support.py` and `cli.py`.

**Interfaces:** Produce `Controller.handle`, `Controller.tick` and
`AgentAdapter` from the index. Fake delivery implements `Delivery`.
Expose `SimulatedAgent.created` and deterministic observations.

- [ ] Write this recovery test and parametrise equivalent faults before create,
after ID persistence, and after start:

```python
def test_ambiguous_create_is_not_replayed(tmp_path):
    h = Harness(tmp_path, fault="after_agent_create")
    h.emit("issue")
    with pytest.raises(RuntimeError):
        h.controller.tick()
    created = list(h.agent.created)
    h.restart()
    h.controller.tick()
    assert h.agent.created == created
    assert h.store.workflow(("demo/superset", 1))["state"] == "needs-human"
```

- [ ] Run `rtk proxy uv run pytest tests/test_dispatch.py -q` and record the failure.
- [ ] Implement intent → create → persist ID → start. Adapter failures after
request transmission produce uncertain state; missing remote identity does not
justify replay. Reconcile deterministic identities when supported.
- [ ] Implement allowed transitions, strict role-result validation, stale-result
rejection, one global active execution, and an exclusive OS process lock.
Use a worker/future for blocking adapter operations; `tick` must remain responsive.
- [ ] Test a second process lock rejection, two eligible issues, malformed role
outputs, and old-revision completion. Extend simulation through fake validation
and fake review with no GitHub writes.
- [ ] Run tests and commit `feat: reconcile durable agent dispatches`.

### Task 01.3: Approval, revision changes, and control commands

**Files:** Create `src/openhands_controller/{commands,revision}.py`,
`tests/test_commands.py`. Modify `controller.py`, `tests/support.py`.

**Interfaces:** Produce `parse_command(body: str) -> tuple[str, str | None] | None`
and `revision_hash(title: str, body: str) -> str`. Commands consume
normalised events with actor and immutable event identity; permissions use the
callable in the index.

- [ ] Add failing parameterised parsing tests for exact commands, quoted examples,
fenced code, trailing prose, edited comments, and repeated command IDs.
- [ ] Add the race and revision tests:

```python
def test_cancel_wins_over_finished_agent(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.emit("command", body="/agent cancel")
    h.complete("implementation", summary="done", changed_paths=["superset/a.py"])
    h.controller.tick()
    assert h.delivery.published == []

def test_issue_edit_revokes_approval(tmp_path):
    h = Harness(tmp_path)
    h.run_to("implementing")
    h.emit("issue", title="new scope", body="changed", revision="r2")
    h.emit("command", body="/agent resume")
    assert h.store.workflow(("demo/superset", 1))["approval_revision"] is None
```

- [ ] Run `rtk proxy uv run pytest tests/test_commands.py -q` and observe failure.
- [ ] Implement exact standalone parsing; authorise write/maintain/admin only.
Reject early approval, unavailable permissions, stale events, and label presence
without an actor-attributed addition event.
- [ ] Record requested stop separately from confirmed paused/cancelled state.
Block publication immediately on stop request. Revision changes stop execution
and require new triage/approval. Resume requires valid approval and reconciled
budget; it never clears unknown dispatch state.
- [ ] Test read-only actors, bot projection events, ordinary discussion comments,
unresponsive stop, and repeated pause/resume. Run checks and commit
`feat: enforce revision-bound human control`.

### Task 01.4: Issue-wide budget and complete simulated workflow

**Files:** Create `src/openhands_controller/budget.py`, `tests/test_budget.py`,
`tests/test_simulation.py`. Modify `controller.py`, `cli.py`, `config.py`,
`.env.example`, `README.md`.

**Interfaces:** Produce `Budget.reserve(issue, request_id, estimate_microusd) -> bool`,
`Budget.settle(issue, request_id, actual_microusd: int | None) -> None`,
and `Budget.increase(issue, total_microusd, event_id) -> None`.
A null settlement marks spend unknown. Reservations and settlements are durable.

- [ ] Add failing tests for duplicated settlements, cumulative observation replay,
budget command rejection for negative/NaN/infinite amounts, restart, and revision changes:

```python
def test_unknown_spend_blocks_next_call(budget):
    assert budget.reserve(("demo/superset", 1), "req-1", 100_000)
    budget.settle(("demo/superset", 1), "req-1", None)
    assert not budget.reserve(("demo/superset", 1), "req-2", 100_000)
```

The `budget` fixture constructs `Budget` with a temporary Store and US$5 cap.
- [ ] Run `rtk proxy uv run pytest tests/test_budget.py -q` before implementation.
- [ ] Implement integer accounting, reservation reconciliation, explicit increases,
and no budget reset on revision/retry. Unknown costs require reconciliation,
not a budget increase alone. Show reported versus estimated costs separately.
- [ ] Implement simulation scenarios `happy`, `duplicate`, `restart`,
`budget`, and `cancel`. Add CLI tests that assert persisted outcomes after
reopening SQLite. Advance fake time to verify timeout and iteration exhaustion.
- [ ] Run `rtk proxy uv run pytest tests/test_store.py tests/test_dispatch.py tests/test_commands.py tests/test_budget.py tests/test_simulation.py -q`.
- [ ] Commit `feat: enforce issue budgets and demonstrate controller lifecycle`.

## Completion gate

All simulations run without credentials. Restarts preserve state and spend.
No test substitutes a successful summary for validated state transitions.
