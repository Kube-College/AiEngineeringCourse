#!/usr/bin/env bash
# PostToolUse hook for the subagent tool (Agent, or Task in earlier releases).
# Clears the pending marker once the tdd-reviewer subagent has returned.

input=$(cat)
state="${CLAUDE_PROJECT_DIR:?CLAUDE_PROJECT_DIR is not set}/.claude/state"

if printf '%s' "$input" | grep -q '"subagent_type"[[:space:]]*:[[:space:]]*"tdd-reviewer"'; then
  rm -f "$state/review-pending" "$state/stop-blocks"
fi
exit 0
