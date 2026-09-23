# Joplin fixtures and validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a pinned Joplin image and independently reproducible shared-logic and desktop UI regression fixtures.

**Architecture:** Build from the approved immutable source revision. Controller-owned validation profiles apply trusted regressions to clean candidate checkouts in credential-free containers.

**Tech Stack:** Python with uv, SQLite, pytest, OpenHands SDK/Agent Server, Docker, GitHub REST, OpenRouter; Joplin uses TypeScript, Yarn workspaces, Jest, and Electron/Playwright.

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
- GitHub writes: disabled until a demo fork is configured; never target `laurent22/joplin`.
- Baseline: `1d6beb0443e6d958b2c241f45978bd5de069f309`; core #16638, desktop #16261.
- Use uv for controller Python. Derive target toolchains from the pinned Joplin source.
- All paths below are relative to the lab root. Run commands there, prefix shell commands with `rtk`, and stage only each task's audited files.
- Every commit is local. End each task with its focused checks and an explicit-path commit.

## Review Focus

- Dependency installation must follow the pinned source, not host defaults (Task 03.1).
- Issue reports may describe behaviour absent at the pinned commit (Task 03.2).
- A dialog screenshot may appear correct while an unwanted tag persists (Task 03.2).
- Candidate edits may weaken tests or redirect validation commands (Task 03.3).
- Symlinks and unusual filenames must not escape the checkout (Task 03.3).

### Task 03.1: Reproducible Node/Electron image

**Files:** Create `docker/joplin-agent.Dockerfile`, `docker/versions.json`,
`scripts/build_joplin_image.sh`, `tests/test_image_manifest.py`,
`docs/evidence/joplin-baseline.md`.

**Interfaces:** Produce `docker/versions.json` with `joplin_sha`,
`agent_server_version`, `base_image_digest`, `python_version`,
`node_version`, `package_manager`, and `built_image_digest`.
Only a fully populated validated manifest may enable live runs.

- [ ] Fetch the exact approved commit into ignored disposable storage. Inspect
root package.json, .yarnrc.yml, yarn.lock, devbox.json, package scripts, and CI
commands. The source selects Yarn 4.16.0 through packageManager and yarnPath;
engines.yarn says 4.14.1. Resolve the mismatch using the committed Yarn binary
and record actual install behaviour. Node must satisfy >=22.19. Record source paths and values; never assume the course's pnpm choice
applies to Joplin. Keep Python/uv for the controller and SDK only.
- [ ] Write failing manifest tests:

```python
def test_manifest_pins_baseline_and_image(manifest):
    assert manifest["joplin_sha"] == "1d6beb0443e6d958b2c241f45978bd5de069f309"
    assert "@sha256:" in manifest["base_image_digest"]
    assert manifest["built_image_digest"].startswith("sha256:")
```

The manifest fixture loads the JSON produced by the image build, not invented
version strings. Run `rtk proxy uv run pytest tests/test_image_manifest.py -q`.
- [ ] Build the Agent Server-compatible image with the Joplin Node toolchain,
OpenHands Python runtime, and
locked dependencies. Include native module build prerequisites, Electron shared
libraries and Xvfb. Use the committed Yarn binary for an immutable install;
record required build scripts and dependency layers. Disable live sync, use
disposable profiles, and mount no real user data or host display. Avoid baking
credentials or private paths into layers.
- [ ] Run the baseline's focused core and desktop Jest suites inside the
image. Capture exact commands and failures in the baseline report. Record host
architecture and whether image emulation was necessary.
- [ ] Run manifest checks and commit `build: pin Joplin agent development image`.

### Task 03.2: Qualify the replacement issue pair

**Files:** Create `fixtures/issues/{16638,16261}.json`,
`validation/regressions/core_16638.patch`,
`validation/regressions/desktop_16261.patch`,
`validation/desktop_16261.spec.ts`, `docs/evidence/issue-qualification.md`.

**Interfaces:** Each fixture records `source_url`, `captured_at`, `base_sha`,
`scope`, `description`, `validation_profile`, and `expected_failure`.
Regression patches contain tests only and remain controller-owned.

- [ ] Snapshot attributed reports for #16638 and #16261. Record open/stale/linked
PR state at qualification time. Their selection is provisional; reproduction
is required. Exclude proposed solution patches and private reporter identifiers
from agent inputs.
- [ ] Trace `Note.defaultTitleFromBody(body: string)` in
`packages/lib/models/Note.ts`, which delegates to `markdownUtils.titleFromBody`.
Use the existing `packages/lib/models/Note.test.ts` test harness.
Add cases equivalent to this contract to the existing Jest suite:

```typescript
it.each(['YYYY_MM', 'YYYY_MM_', 'YYYY_MM_DD'])(
  'preserves internal underscores in %s', body => {
    expect(Note.defaultTitleFromBody(body)).toBe(body);
  },
);
```

Use the existing Note import in the test file. Test `_emphasis_`,
headings, Unicode, empty content, and user-supplied titles against established
behaviour. Do not remove all Markdown normalisation to satisfy the new case.
- [ ] Run the focused library tests through the pinned package script:
`yarn workspace @joplin/lib test --runInBand --runTestsByPath models/Note.test.ts`.
If the production helper is elsewhere, use that exact test file instead and
record the final argv in the profile. Accept only the intended assertion failure
as reproduction; environment failures do not qualify the issue.
- [ ] Follow `packages/app-desktop/gui/WindowCommandsAndDialogs/commands/setTags.ts`
to the actual dialog under `packages/app-desktop/gui`. Add a Jest
interaction test using existing component fixtures. The behavioural sequence is:

```typescript
await user.type(input, 'existing');
await user.clear(input);
await user.keyboard('{Enter}');
expect(savedTagIds()).toEqual(originalTagIds);
expect(dialogIsOpen()).toBe(false);
```

Bind `input`, `savedTagIds`, and `dialogIsOpen` to the actual component and note
model in the existing test harness. Cover keyboard and mouse selection, clearing
with repeated Backspace, Escape, and deliberately submitting a new tag.
- [ ] Extend the existing Electron Playwright harness from
`packages/app-desktop/playwright.config.ts` for the same scenario. Use a new
disposable note/profile and existing tag; assert persisted associations after
closing and reopening the dialog. Capture a screenshot and interaction trace.
- [ ] Run with `xvfb-run -a yarn workspace @joplin/app-desktop test-ui` filtered
to the new spec using the verified Playwright argument syntax. Keep Electron's
sandbox enabled; do not add privileged Docker or host mounts to make the test pass.
- [ ] Demonstrate the expected failures on the pinned source, then use controlled
corrections in a temporary validation checkout for red/green evidence. If Linux
cannot reproduce a platform-specific issue, stop qualification and report the
evidence; do not silently replace the candidate or claim success.
- [ ] Commit `test: capture Joplin core and desktop demo regressions`.

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
    result = h.validate(profile="core-16638",
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
core Jest/ESLint/TypeScript; desktop Jest/ESLint/TypeScript/Electron interaction; combined
profile runs both. Use `linter-ci`, not the root auto-fixing `linter` script.
Package type checks use `yarn workspace @joplin/lib tsc` and
`yarn workspace @joplin/app-desktop tsc`; record pre-existing failures separately. Mount trusted regression inputs read-only outside the
agent's checkout and apply them in a disposable validation clone.
- [ ] Run checks in credential-free containers with command timeouts. Return
false for timeout, missing evidence, or baseline/candidate SHA mismatch.
Record immutable check logs and image digest alongside ValidationResult.
- [ ] Verify a controlled correction makes each regression green, retaining
red/green evidence separately from agent prompts. Use a temporary validation
branch; do not embed the solution in the input fixture.
- [ ] Commit `feat: validate immutable Joplin candidates with trusted checks`.

## Completion gate

Both reports reproduce on the accepted snapshot. Validation commands and image
pins are concrete outputs of qualification, not guesses in the plan. Working
fixtures must exist before spending the issue budget on a full agent run.
