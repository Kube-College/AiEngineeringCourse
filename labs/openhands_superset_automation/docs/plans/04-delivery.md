# GitHub delivery and live demonstration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the qualified controller to a demo fork and demonstrate both issue workflows through draft PR and human handoff.

**Architecture:** GitHub polling normalises actor-attributed events into the existing state machine. A controller-owned delivery adapter publishes only validated immutable commits and reconciles uncertain external outcomes.

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

- Poll pagination and overlapping timestamps must not lose approvals (Task 04.1).
- A label already present at startup must not imply an authorised addition (Task 04.1).
- A lost PR response must not create another PR (Task 04.2).
- External branch changes invalidate exact-head review (Task 04.3).
- A budget handoff must not be reported as a successfully fixed demo (Task 04.4).

### Task 04.1: GitHub event collection and status projection

**Files:** Create `src/openhands_controller/github/{__init__,client,polling,projection}.py`,
`tests/test_github_polling.py`, `tests/test_projection.py`.
Modify `scheduler.py`, `config.py`, `cli.py`.

**Interfaces:** Produce `GitHubClient.permission(actor, repo) -> str`,
`GitHubPoller.collect() -> list[Event]`,
`GitHubPoller.ack(events: list[Event]) -> None`, and
`Projector.sync(issue: IssueKey) -> None`. Consume Controller.handle.

- [ ] Write failing HTTP-fixture tests for paginated issues/comments/timeline
events, edited comments, label additions and actors, and rate-limit backoff.
Use overlapping timestamps and duplicate pages:

```python
def test_cursor_waits_for_durable_events(poller_harness):
    h = poller_harness(fail_after_event=1)
    old_cursor = h.cursor()
    with pytest.raises(RuntimeError):
        h.poll_once()
    assert h.cursor() == old_cursor
    h.restart()
    h.poll_once()
    assert h.approval_count() == 1
```

- [ ] Run `rtk proxy uv run pytest tests/test_github_polling.py tests/test_projection.py -q`.
- [ ] Collect immutable event IDs and actor evidence. Re-read issue title/body
before approval and pre-publication checks. Persist events before moving cursors;
overlap windows and deduplicate. Treat failed permissions as unavailable, not read.
- [ ] Reconcile one status comment using a stable controller marker and stored ID.
Unknown comment-create responses trigger lookup before retry. Remove consumed
approval labels without treating the bot event as a new command.
- [ ] Project state, reasons, cost status, validation evidence and PR URL. A failed
projection remains dirty for retry without repeating workflow side effects.
- [ ] Keep webhook ingress disabled in the initial demo. If added later, route it
through this same handler and verify HMAC before parsing/processing; do not expose
an unsigned endpoint as part of this plan.
- [ ] Commit `feat: poll authorised GitHub control events and project state`.

### Task 04.2: Controller-owned Git and draft PR publication

**Files:** Create `src/openhands_controller/delivery/publication.py`,
`tests/test_publication.py`. Modify `github/client.py`, `store.py`.

**Interfaces:** Produce `GitHubDelivery` implementing Delivery.
Consume capture/validate interfaces from 03.3. `publish` checks persisted passing
validation for the exact candidate SHA, current approval, and no stop request.

- [ ] Write failing tests with local bare remotes and a fake GitHub HTTP client:

```python
def test_lost_pr_response_reconciles_existing_pr(publication_harness):
    h = publication_harness(fault="after_remote_pr_create")
    with pytest.raises(RuntimeError):
        h.publish()
    h.restart()
    h.publish()
    assert h.github.created_pr_count == 1
    assert h.remote.head(h.branch) == h.candidate_sha
```

- [ ] Run `rtk proxy uv run pytest tests/test_publication.py -q`.
- [ ] Validate destination owner/name and enforce writes-enabled configuration.
Reject upstream `apache/superset`, unexpected Git remotes, and credential-bearing
URLs. Use controller-only credentials and disable hooks; never run tests in
the publication process.
- [ ] Persist branch-push and PR-create intent before external calls. Use
deterministic branch names and compare remote head before updating. On unknown
outcomes, inspect the remote branch and PR head/base. Do not overwrite a head
that differs from the previously published SHA.
- [ ] Keep PRs draft and include source issue attribution plus exact checks.
Use fork issue references for closing text; do not generate upstream-closing
commands. Test cancellation immediately before push and immediately before
PR creation. Reconcile any already-published effects honestly.
- [ ] Commit `feat: publish validated candidates as reconciled draft PRs`.

### Task 04.3: Exact-head review, one fix, and lifecycle closure

**Files:** Create `tests/test_review_cycle.py`,
`tests/test_workflow_completion.py`. Modify `controller.py`,
`runtime/prompts.py`, `delivery/publication.py`, `github/polling.py`.

**Interfaces:** Consume strict review results from the index. Review Dispatch
requires candidate_sha. Fix resumes the implementation conversation when supported;
otherwise record a replacement attempt against the preserved workspace.

- [ ] Write failure tests for stale review head, invalid findings, and fix limits:

```python
def test_review_of_old_head_cannot_release_issue(tmp_path):
    h = Harness(tmp_path)
    h.run_to("reviewing")
    h.complete("review", candidate_sha="obsolete",
               verdict="pass", findings=[])
    h.controller.tick()
    assert h.store.workflow(("demo/superset", 1))["state"] == "needs-human"
```

- [ ] Run `rtk proxy uv run pytest tests/test_review_cycle.py tests/test_workflow_completion.py -q`.
- [ ] Create clean review checkout at candidate SHA and present trusted evidence.
Discard review edits. Require revalidation, PR update, and new review after a fix.
Count at most one automatic correction cycle, including validation-driven
correction; later failures require human action.
- [ ] Poll PR head and merge status. External commits require reconciliation and
fresh validation/review. Closed unmerged PR goes to needs-human; only the intended
merged PR leads to completed and starts the retention clock.
- [ ] Test issue edits during review, budget exhaustion before fix, ordinary
comments, merge observation replay, and cleanup after completion.
- [ ] Commit `feat: gate handoff on exact-head review and bounded correction`.

### Task 04.4: Repeatable two-issue demo and operational evidence

**Files:** Create `scripts/prepare_demo.py`, `scripts/run_demo.py`,
`docs/demo-runbook.md`, `docs/evidence/demo-results.md`,
`tests/test_demo_setup.py`. Modify `README.md`, `.env.example`, `cli.py`.

**Interfaces:** `prepare_demo.py --repo OWNER/REPO --dry-run` previews fork issue
setup; `--apply` performs idempotent issue creation after destination selection.
`run_demo.py --scenario backend|frontend|recovery` drives the documented workflow
while preserving genuine human approval.

- [ ] Write tests proving dry-run has no writes, upstream is refused, existing
fixture issues are reused, and partial setup can resume:

```python
def test_demo_setup_dry_run_has_no_writes(demo_setup):
    result = demo_setup.run(repo="demo/superset", apply=False)
    assert len(result.planned_issues) == 2
    assert demo_setup.github.write_calls == []
```

- [ ] Run `rtk proxy uv run pytest tests/test_demo_setup.py -q`.
- [ ] Write runbook steps for uv setup, image qualification, local secrets,
configured fork permissions, fixture preview/application, controller start,
label/comment approval, pause/resume/cancel, budget increase, and cleanup.
Commands must match the implemented CLI, not planned flags.
- [ ] Run all credential-free controller tests. Run qualified live lifecycle
checks only when external prerequisites are present.
- [ ] Preview fixture setup for the explicitly selected fork, then apply it
within user-authorised scope. Do not create a fork or upstream issue implicitly.
- [ ] Execute backend and frontend separately with the US$5 issue cap.
Capture base/candidate/image SHAs, commands and results, provider/model,
actual/estimated costs, conversation IDs, draft PR URLs, and review outcomes.
Attach each created PR to the current Codex task. Keep raw transcripts ignored.
- [ ] Demonstrate one duplicate delivery, one controller restart, and a
pause/resume without duplicate dispatch or cost reset.
- [ ] Record each outcome as completed fix, budget handoff, failed qualification,
or missing prerequisite. Do not mark an unexecuted live case passing.
- [ ] Commit `docs: document verified OpenHands Superset demo runs` locally.

## Completion gate

Each accepted fixture has either a fully evidenced draft-PR/human-handoff result
or an explicit incomplete outcome. The overall demo is complete only when both
fixes meet the design acceptance criteria. Course exercises and course publishing
remain outside this implementation.
