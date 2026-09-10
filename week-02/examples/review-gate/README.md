# Review gate example

Companion to stage 4 of the Week 2 lab. Three command hooks let a turn that changed code end only after the tests pass and the `tdd-reviewer` subagent has returned a verdict.

| File | Event | What it does |
| --- | --- | --- |
| `settings.fragment.json` | | Registers the three hooks. Merge into `.claude/settings.json`; do not replace the file. |
| `mark-changed.sh` | `PostToolUse` on `Edit`, `Write`, `MultiEdit` | Creates `.claude/state/review-pending`. |
| `clear-on-review.sh` | `PostToolUse` on the subagent tool | Removes the marker when the subagent was `tdd-reviewer`. |
| `stop-gate.sh` | `Stop` | With the marker present: runs the test command and blocks on failure; otherwise blocks and asks for the reviewer. Without the marker: lets the turn end. Stops blocking after three blocks in one turn. |

## Install

1. Copy the three scripts to `.claude/hooks/` in your repository.
2. Set `TEST_CMD` at the top of `stop-gate.sh` to your project's test command.
3. Merge `settings.fragment.json` into `.claude/settings.json`.
4. Add `.claude/state/` to `.gitignore`.
5. Run `/hooks` in a new session and confirm the three entries.

The scripts are invoked through `bash`, so the executable bit is not required. They use `grep` and no other dependency. The `Agent|Task` matcher covers the current and the earlier name of the subagent tool.

## How a turn flows

1. The agent edits a file. `mark-changed.sh` creates the marker.
2. The agent finishes its reply. `stop-gate.sh` finds the marker, runs the tests.
3. Tests fail: the hook exits 2 with the last 30 lines of output. The agent sees the output and continues.
4. Tests pass, no verdict yet: the hook exits 2 with a message asking for the reviewer. The agent invokes `tdd-reviewer`.
5. The reviewer returns. `clear-on-review.sh` removes the marker.
6. The agent replies with the verdict and finishes. `stop-gate.sh` finds no marker and exits 0.

If the agent edits again after the review, the marker returns and the reviewer runs again on the new diff.

## Limits

- The hook cannot invoke the reviewer itself. It returns a message; the model decides to delegate. The counter in `stop-gate.sh` ends the turn after three blocks if the model never delegates.
- The marker records that code changed, not which code. A reviewer invoked on an unrelated diff also clears it.
- The test command runs on every blocked stop. A slow suite makes every turn slow; use a filtered form where the runner supports one.
- A repository can change its own hooks and tests. The gate is feedback within a session, and independent CI stays the merge gate.
- The scripts run with your user's permissions. Read them before installing them.
