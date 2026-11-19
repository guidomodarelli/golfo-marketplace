#!/usr/bin/env bash
# Claude Code PostToolUse hook: after a successful `git push` run through the Bash tool,
# refreshes the file-count marker of the open PR of the pushed checkout with
# skills/pr-description-template/scripts/refresh-file-count.sh.
#
# It never blocks or fails the tool call: every problem ends in exit 0, and the result
# reaches the agent as additionalContext so it does not recompute the count by hand.
# Set GOLFO_PR_FILE_COUNT_REFRESH=0 to turn it off.
set -uo pipefail

readonly HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REFRESH_SCRIPT="${HOOK_DIR}/../skills/pr-description-template/scripts/refresh-file-count.sh"
readonly DISABLED_VALUE='0'
readonly HOOK_EVENT_NAME='PostToolUse'
# `git push` as a command of its own (start of the line or after ; & | ( or a space), with
# optional global options such as `-C <dir>` between `git` and `push`.
readonly GIT_PUSH_REGEX='(^|[;&|(]|[[:space:]])git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+push([[:space:]]|$)'
readonly DRY_RUN_REGEX='[[:space:]]push[^;&|]*[[:space:]](--dry-run|-n)([[:space:]]|$)'
readonly GIT_DIR_OPTION_REGEX='git[[:space:]]+-C[[:space:]]+("([^"]+)"|'"'"'([^'"'"']+)'"'"'|([^[:space:];&|]+))'
readonly LEADING_CD_REGEX='^[[:space:]]*cd[[:space:]]+("([^"]+)"|'"'"'([^'"'"']+)'"'"'|([^[:space:];&|]+))'

[[ "${GOLFO_PR_FILE_COUNT_REFRESH:-1}" == "$DISABLED_VALUE" ]] && exit 0

hook_input="$(cat)"

# Prints the string field at <path> of the hook input (jq, or node when jq is missing).
read_input_field() {
  field_path="$1"
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$hook_input" | jq -r "${field_path} // empty"
  elif command -v node >/dev/null 2>&1; then
    printf '%s' "$hook_input" | node -e '
      let raw = "";
      process.stdin.on("data", (chunk) => { raw += chunk; });
      process.stdin.on("end", () => {
        const value = process.argv[1].split(".").filter(Boolean).reduce((node, key) => (node == null ? node : node[key]), JSON.parse(raw));
        if (typeof value === "string") process.stdout.write(value);
      });
    ' "$field_path"
  fi
}

push_command="$(read_input_field '.tool_input.command')"
[[ -n "$push_command" && "$push_command" =~ $GIT_PUSH_REGEX ]] || exit 0
[[ "$push_command" =~ $DRY_RUN_REGEX ]] && exit 0

checkout_dir="$(read_input_field '.cwd')"
if [[ "$push_command" =~ $GIT_DIR_OPTION_REGEX ]] || [[ "$push_command" =~ $LEADING_CD_REGEX ]]; then
  pushed_dir="${BASH_REMATCH[2]}${BASH_REMATCH[3]}${BASH_REMATCH[4]}"
  [[ "$pushed_dir" = /* || "$pushed_dir" =~ ^[A-Za-z]: || -z "$checkout_dir" ]] && checkout_dir="$pushed_dir" || checkout_dir="${checkout_dir}/${pushed_dir}"
fi
[[ -n "$checkout_dir" ]] && { cd "$checkout_dir" 2>/dev/null || exit 0; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
command -v gh >/dev/null 2>&1 || exit 0

if ! refresh_output="$(bash "$REFRESH_SCRIPT" 2>&1)"; then
  # The last line is the script's own actionable message; earlier lines are raw git/gh noise.
  refresh_output="FAILED: $(printf '%s\n' "$refresh_output" | tail -n 1)"
fi
case "$refresh_output" in
  SKIPPED:*) exit 0 ;;
esac

context="pr-description-template refreshed the PR file-count marker after git push: ${refresh_output}"
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg event "$HOOK_EVENT_NAME" --arg context "$context" \
    '{hookSpecificOutput: {hookEventName: $event, additionalContext: $context}}'
elif command -v node >/dev/null 2>&1; then
  node -e 'process.stdout.write(JSON.stringify({hookSpecificOutput: {hookEventName: process.argv[1], additionalContext: process.argv[2]}}))' \
    "$HOOK_EVENT_NAME" "$context"
fi
exit 0
