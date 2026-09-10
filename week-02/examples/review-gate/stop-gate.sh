#!/usr/bin/env bash
# Stop hook. When code changed in this turn, require passing tests and a tdd-reviewer verdict
# before the turn ends. Exit 2 blocks the stop and feeds stderr back to the agent.

TEST_CMD="${TEST_CMD:-npm test --silent}"   # set to your project's test command
MAX_BLOCKS=3                                 # blocks per turn before the gate stops blocking

cat >/dev/null  # consume the event JSON; this hook does not use any of its fields

project="${CLAUDE_PROJECT_DIR:?CLAUDE_PROJECT_DIR is not set}"
state="$project/.claude/state"

# No code changed in this turn: nothing to gate.
[ -f "$state/review-pending" ] || exit 0

# Stop blocking after MAX_BLOCKS so the gate cannot loop without end.
count=$(( $(cat "$state/stop-blocks" 2>/dev/null || echo 0) + 1 ))
echo "$count" > "$state/stop-blocks"
if [ "$count" -gt "$MAX_BLOCKS" ]; then
  echo "stop-gate: blocked $MAX_BLOCKS times without a reviewer verdict; letting the turn end. Review the diff manually." >&2
  rm -f "$state/review-pending" "$state/stop-blocks"
  exit 0
fi

# Tests first. A failing suite is a more useful observation than a review request.
cd "$project" || exit 0
if ! output=$($TEST_CMD 2>&1); then
  printf 'stop-gate: tests failed. Fix them before finishing.\n%s\n' "$(printf '%s' "$output" | tail -n 30)" >&2
  exit 2
fi

# Tests pass but no reviewer verdict has been recorded for this change.
echo "stop-gate: code changed in this turn and no tdd-reviewer verdict was recorded. Invoke the tdd-reviewer subagent on the current git diff, passing the issue number and the changed files, and include its verdict in your reply." >&2
exit 2
