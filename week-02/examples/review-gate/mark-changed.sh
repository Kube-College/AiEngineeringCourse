#!/usr/bin/env bash
# PostToolUse hook for Edit, Write, and MultiEdit.
# Records that code changed in this turn so that stop-gate.sh requires tests and a review.

cat >/dev/null  # consume the event JSON; this hook does not use any of its fields

state="${CLAUDE_PROJECT_DIR:?CLAUDE_PROJECT_DIR is not set}/.claude/state"
mkdir -p "$state"
touch "$state/review-pending"
exit 0
