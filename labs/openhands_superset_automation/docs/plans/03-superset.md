# Superset fixtures and validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a pinned Superset image and independently reproducible backend/frontend regression fixtures.

**Architecture:** Build from the approved immutable source revision. Controller-owned validation profiles apply trusted regressions to clean candidate checkouts in credential-free containers.

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

- Dependency installation must follow the pinned source, not host defaults (Task 03.1).
- Issue reports may describe behaviour absent at the pinned commit (Task 03.2).
- Frontend data assertions may pass while rendered labels still collide (Task 03.2).
- Candidate edits may weaken tests or redirect validation commands (Task 03.3).
- Symlinks and unusual filenames must not escape the checkout (Task 03.3).

### Task 03.1: Reproducible dual-toolchain image

**Files:** Create `docker/superset-agent.Dockerfile`, `docker/versions.json`,
`scripts/build_superset_image.sh`, `tests/test_image_manifest.py`,
`docs/evidence/superset-baseline.md`.

**Interfaces:** Produce `docker/versions.json` with `superset_sha`,
`agent_server_version`, `base_image_digest`, `python_version`,
`node_version`, `package_manager`, and `built_image_digest`.
Only a fully populated validated manifest may enable live runs.

- [ ] Fetch the exact approved commit into ignored disposable storage. Inspect
its Dockerfiles, Python metadata, frontend package/lock files, and CI test
commands. Record source paths and values; never assume the course's pnpm choice
applies to Superset.
- [ ] Write failing manifest tests:

```python
def test_manifest_pins_baseline_and_image(manifest):
    assert manifest["superset_sha"] == "c9fd9bf94f45163afd24f39f5ed9eec23a999150"
    assert "@sha256:" in manifest["base_image_digest"]
    assert manifest["built_image_digest"].startswith("sha256:")
```

The manifest fixture loads the JSON produced by the image build, not invented
version strings. Run `rtk proxy uv run pytest tests/test_image_manifest.py -q`.
- [ ] Build the Agent Server-compatible image with both target toolchains and
locked dependencies. Use image build layers for dependency caching. Avoid baking
credentials or private paths into layers.
- [ ] Run the baseline's focused backend and frontend test suites inside the
image. Capture exact commands and failures in the baseline report. Record host
architecture and whether image emulation was necessary.
- [ ] Run manifest checks and commit `build: pin Superset agent development image`.

### Task 03.2: Reproduce the accepted issue pair

**Files:** Create `fixtures/issues/{44385,44466}.json`,
`validation/regressions/backend_44385.patch`,
`validation/regressions/frontend_44466.patch`,
`validation/render_44466.mjs`, `docs/evidence/issue-qualification.md`.

**Interfaces:** Each fixture records `source_url`, `captured_at`, `base_sha`,
`scope`, `description`, `validation_profile`, and `expected_failure`.
Regression patches contain tests only and are controlled by the controller.

- [ ] Capture concise attributed problem descriptions. Recheck issue/PR state
for evidence dating, without changing the accepted base. Exclude proposed
solution patches from agent input.
- [ ] Add a backend regression to the existing pinned test harness with this
behaviour for both dashboard and Explore surfaces:

```python
first = create_state(tab_id="1", value="State A")
delete_state(first)
assert read_state(first).status_code == 404
second = create_state(tab_id="1", value="State B")
assert second != first
```

Here the operations must call actual pinned Superset APIs using its existing
authenticated client fixtures. Add different-tab and different-session controls.
The patch must preserve existing API coverage.
- [ ] Run the new backend test on the baseline and capture the expected failure.
Do not accept import, fixture, or environment failures as reproduction.
- [ ] Add frontend tests to the pinned ECharts transformer tests for small
non-zero stacked values plus a large outlier. Cover OutsideEnd, InsideCenter,
Auto, both orientations, normal readable segments, and non-bar charts.
- [ ] Add headless rendered-chart evidence using the same dataset and options.
Measure/display label bounding-box collisions; preserve screenshots/SVG and
geometry output. The pass criterion must allow normal readable labels and
suppress or reposition labels that cannot fit. Record exact assertions once
the pinned renderer's geometry API is inspected.
- [ ] Run frontend regressions on the baseline and record the intended failure.
If either report cannot reproduce, stop qualification and document the evidence;
do not silently substitute a different issue or claim a working fixture.
- [ ] Commit `test: capture Superset backend and frontend demo regressions`.

### Task 03.3: Trusted candidate validation

**Files:** Create `validation/profiles.json`,
`src/openhands_controller/delivery/{__init__,candidate,validation}.py`,
`tests/test_candidate.py`, `tests/test_validation.py`.

**Interfaces:** Produce `capture_candidate(workspace_id: str, base_sha: str) -> str`
and `validate_candidate(candidate_sha: str, profile: str) -> ValidationResult`.
Plan 04's Delivery implementation delegates to them.

- [ ] Write failing candidate tests against temporary local Git repositories:
unexpected HEAD, test deletion, hook changes, symlink escape, path traversal,
untracked source files, and filenames containing whitespace or leading dashes.
Use subprocess argument arrays and NUL-delimited Git output.
- [ ] Write the validation contract test:

```python
def test_validation_ignores_agent_supplied_command(validation_harness):
    h = validation_harness()
    result = h.validate(profile="backend-44385",
                        agent_output={"command": "true"})
    assert h.runner.commands == h.trusted_profile.commands
    assert result.candidate_sha == h.candidate_sha
```

The harness wraps the production validator and injects a fake container runner.
- [ ] Run `rtk proxy uv run pytest tests/test_candidate.py tests/test_validation.py -q`.
- [ ] Reconstruct an audited diff from the pinned baseline in a clean
controller-owned checkout. Reject altered history, unsupported scopes, changed
trusted profiles, weakened existing tests, and unexpected submodule changes.
Never run repository hooks during controller Git operations.
- [ ] Write exact argv-based profiles using commands proven in Tasks 03.1–03.2:
backend tests/lint; frontend tests/lint/type checking/render evidence; combined
profile runs both. Mount trusted regression inputs read-only outside the
agent's checkout and apply them in a disposable validation clone.
- [ ] Run checks in credential-free containers with command timeouts. Return
false for timeout, missing evidence, or baseline/candidate SHA mismatch.
Record immutable check logs and image digest alongside ValidationResult.
- [ ] Verify a controlled correction makes each regression green, retaining
red/green evidence separately from agent prompts. Use a temporary validation
branch; do not embed the solution in the input fixture.
- [ ] Commit `feat: validate immutable Superset candidates with trusted checks`.

## Completion gate

Both reports reproduce on the accepted snapshot. Validation commands and image
pins are concrete outputs of qualification, not guesses in the plan. Working
fixtures must exist before spending the issue budget on a full agent run.
