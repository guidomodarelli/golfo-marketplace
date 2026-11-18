#!/usr/bin/env bash
# wait-for-pr-event.sh
# Bounded watcher for codex-autofix-loop on agents without the Claude Code
# `Monitor` tool. It takes a baseline of the pull request (head, Codex reviews,
# CI checks), polls GitHub until something changes, and exits with a code that
# tells the caller what to do next. It never waits past --timeout-seconds or
# --max-polls, so it cannot outlive its supervisor indefinitely.
#
# Exit codes:
#   0  event detected (one "EVENT <kind> <detail>" line per event on stdout)
#   2  invalid usage
#   3  timeout or poll cap reached with no event ("TIMEOUT ...")
#   4  GitHub unreachable for --max-failures consecutive polls ("GH_UNAVAILABLE ...")
#   5  pull request is no longer OPEN ("PR_NOT_OPEN <state>")

set -euo pipefail

readonly EXIT_EVENT=0
readonly EXIT_USAGE=2
readonly EXIT_TIMEOUT=3
readonly EXIT_GH_UNAVAILABLE=4
readonly EXIT_PR_NOT_OPEN=5
readonly DEFAULT_BOT_LOGIN='chatgpt-codex-connector[bot]'
readonly DEFAULT_POLL_SECONDS=30
readonly DEFAULT_TIMEOUT_SECONDS=300
readonly DEFAULT_MAX_POLLS=100
readonly DEFAULT_MAX_FAILURES=5
readonly GH_CALL_TIMEOUT_SECONDS=60

repository=""
pull_request=""
bot_login="$DEFAULT_BOT_LOGIN"
poll_seconds="$DEFAULT_POLL_SECONDS"
timeout_seconds="$DEFAULT_TIMEOUT_SECONDS"
max_polls="$DEFAULT_MAX_POLLS"
max_failures="$DEFAULT_MAX_FAILURES"

usage() {
  cat <<'USAGE'
Usage: wait-for-pr-event.sh --repo OWNER/REPO --pr NUMBER [options]

Options:
  --poll-seconds N    Seconds between polls (default 30, minimum 1).
  --timeout-seconds N Wall-clock budget in seconds (default 300).
  --max-polls N       Maximum number of polls (default 100).
  --max-failures N    Consecutive failed polls before giving up (default 5).
  --bot LOGIN         Reviewer bot login (default chatgpt-codex-connector[bot]).
  -h, --help          Show this help.

Exit codes: 0 event, 2 usage, 3 timeout, 4 GitHub unavailable, 5 PR not open.
USAGE
}

fail_usage() {
  printf 'wait-for-pr-event: %s\n' "$1" >&2
  usage >&2
  exit "$EXIT_USAGE"
}

require_positive_integer() {
  local flag_name="$1" flag_value="$2"
  [[ "$flag_value" =~ ^[1-9][0-9]*$ ]] || fail_usage "$flag_name must be a positive integer, got '$flag_value'"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo|--pr|--bot|--poll-seconds|--timeout-seconds|--max-polls|--max-failures)
      [[ $# -ge 2 && -n "${2:-}" ]] || fail_usage "$1 requires a value"
      case "$1" in
        --repo) repository="$2" ;;
        --pr) pull_request="$2" ;;
        --bot) bot_login="$2" ;;
        --poll-seconds) poll_seconds="$2" ;;
        --timeout-seconds) timeout_seconds="$2" ;;
        --max-polls) max_polls="$2" ;;
        --max-failures) max_failures="$2" ;;
      esac
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail_usage "unknown argument '$1'"
      ;;
  esac
done

[[ "$repository" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail_usage "--repo must look like OWNER/REPO, got '$repository'"
require_positive_integer --pr "$pull_request"
require_positive_integer --poll-seconds "$poll_seconds"
require_positive_integer --timeout-seconds "$timeout_seconds"
require_positive_integer --max-polls "$max_polls"
require_positive_integer --max-failures "$max_failures"
command -v gh >/dev/null 2>&1 || fail_usage "gh CLI not found in PATH"

# The whole run, baseline included, must fit in --timeout-seconds.
deadline_epoch=$(( $(date +%s) + timeout_seconds ))

remaining_budget_seconds() { printf '%s
' "$(( deadline_epoch - $(date +%s) ))"; }

deadline_reached() { (( $(remaining_budget_seconds) <= 0 )); }

# Portable stand-in for `timeout` (macOS and minimal images lack it). Output goes
# through temp files so a process left behind by the killed command cannot keep
# the caller's command substitution open.
run_with_time_limit() {
  local limit_seconds="$1" output_file error_file command_pid watchdog_pid command_status=0
  shift
  output_file=$(mktemp)
  error_file=$(mktemp)
  "$@" >"$output_file" 2>"$error_file" &
  command_pid=$!
  (
    sleep "$limit_seconds" &
    sleeper_pid=$!
    trap 'kill "$sleeper_pid" 2>/dev/null; exit 0' TERM
    wait "$sleeper_pid"
    kill -TERM "$command_pid" 2>/dev/null
  ) >/dev/null 2>&1 &
  watchdog_pid=$!
  wait "$command_pid" || command_status=$?
  kill -TERM "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  cat "$output_file"
  cat "$error_file" >&2
  rm -f "$output_file" "$error_file"
  return "$command_status"
}

# Bound every GitHub call by min(GH_CALL_TIMEOUT_SECONDS, remaining budget) so
# a slow or hung request cannot stretch the watcher past --timeout-seconds.
run_gh() {
  local remaining_seconds limit_seconds
  remaining_seconds=$(remaining_budget_seconds)
  (( remaining_seconds > 0 )) || return 124
  limit_seconds=$(( remaining_seconds < GH_CALL_TIMEOUT_SECONDS ? remaining_seconds : GH_CALL_TIMEOUT_SECONDS ))
  if command -v timeout >/dev/null 2>&1; then
    timeout "$limit_seconds" gh "$@"
  else
    run_with_time_limit "$limit_seconds" gh "$@"
  fi
}

read_pull_request_snapshot() {
  run_gh pr view "$pull_request" --repo "$repository" --json state,headRefOid -q '.state + " " + .headRefOid'
}

# --paginate prints one count per page; a failed call must not yield a partial sum.
count_bot_reviews() {
  local page_counts
  page_counts=$(run_gh api "repos/$repository/pulls/$pull_request/reviews" --paginate \
    --jq "[.[] | select(.user.login==\"$bot_login\")] | length") || return 1
  printf '%s\n' "$page_counts" | awk '{ total += $1 } END { print total + 0 }'
}

read_checks_signature() {
  run_gh pr checks "$pull_request" --repo "$repository" --json bucket \
    -q 'group_by(.bucket) | map("\(.[0].bucket)=\(length)") | join(",")' 2>/dev/null || true
}

list_new_bot_comments() {
  local since_timestamp="$1" endpoint
  for endpoint in "issues/$pull_request/comments" "pulls/$pull_request/comments"; do
    run_gh api "repos/$repository/$endpoint?since=$since_timestamp" \
      --jq ".[] | select(.user.login==\"$bot_login\") | \"EVENT comment \(.id)\""
  done
}

utc_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

report_baseline_timeout() {
  printf 'TIMEOUT budget of %ss exhausted while reading the baseline of PR #%s
' "$timeout_seconds" "$pull_request"
  exit "$EXIT_TIMEOUT"
}

if ! baseline_snapshot=$(read_pull_request_snapshot); then
  deadline_reached && report_baseline_timeout
  printf 'GH_UNAVAILABLE could not read PR #%s of %s\n' "$pull_request" "$repository"
  exit "$EXIT_GH_UNAVAILABLE"
fi
baseline_state=${baseline_snapshot%% *}
baseline_head=${baseline_snapshot#* }
if [[ "$baseline_state" != "OPEN" ]]; then
  printf 'PR_NOT_OPEN %s\n' "$baseline_state"
  exit "$EXIT_PR_NOT_OPEN"
fi
baseline_reviews=$(count_bot_reviews || printf '0')
baseline_checks=$(read_checks_signature)
deadline_reached && report_baseline_timeout
since_timestamp=$(utc_now)
consecutive_failures=0
poll_count=0

while (( poll_count < max_polls )); do
  remaining_seconds=$(remaining_budget_seconds)
  (( remaining_seconds > 0 )) || break
  sleep "$(( poll_seconds < remaining_seconds ? poll_seconds : remaining_seconds ))"
  poll_count=$(( poll_count + 1 ))
  poll_started_at=$(utc_now)

  if ! snapshot=$(read_pull_request_snapshot); then
    deadline_reached && break
    consecutive_failures=$(( consecutive_failures + 1 ))
    if (( consecutive_failures >= max_failures )); then
      printf 'GH_UNAVAILABLE %s consecutive failed polls on PR #%s\n' "$consecutive_failures" "$pull_request"
      exit "$EXIT_GH_UNAVAILABLE"
    fi
    continue
  fi
  consecutive_failures=0
  current_state=${snapshot%% *}
  current_head=${snapshot#* }
  if [[ "$current_state" != "OPEN" ]]; then
    printf 'PR_NOT_OPEN %s\n' "$current_state"
    exit "$EXIT_PR_NOT_OPEN"
  fi

  events=()
  if [[ -n "$current_head" && "$current_head" != "$baseline_head" ]]; then
    events+=("EVENT head ${current_head:0:7}")
  fi
  while IFS= read -r comment_event; do
    [[ -n "$comment_event" ]] && events+=("$comment_event")
  done < <(list_new_bot_comments "$since_timestamp" 2>/dev/null || true)
  current_reviews=$(count_bot_reviews 2>/dev/null || printf '%s' "$baseline_reviews")
  if (( current_reviews > baseline_reviews )); then
    events+=("EVENT review $current_reviews")
  fi
  current_checks=$(read_checks_signature)
  if [[ -n "$current_checks" && "$current_checks" != "$baseline_checks" ]]; then
    events+=("EVENT checks $current_checks")
  fi

  if (( ${#events[@]} > 0 )); then
    printf '%s\n' "${events[@]}"
    exit "$EXIT_EVENT"
  fi
  since_timestamp="$poll_started_at"
done

printf 'TIMEOUT no event on PR #%s after %s polls\n' "$pull_request" "$poll_count"
exit "$EXIT_TIMEOUT"
