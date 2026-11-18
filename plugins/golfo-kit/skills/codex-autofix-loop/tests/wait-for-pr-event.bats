#!/usr/bin/env bats

# The watcher only talks to GitHub through `gh`; a fake `gh` on PATH replays one
# scripted answer per call so each test controls what every poll observes.

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  watcher="$repository_root/plugins/golfo-kit/skills/codex-autofix-loop/scripts/wait-for-pr-event.sh"
  test_root="$(mktemp -d)"
  fake_bin="$test_root/bin"
  export FAKE_GH_DIR="$test_root/gh"
  mkdir -p "$fake_bin" "$FAKE_GH_DIR"
  cat > "$fake_bin/gh" <<'FAKE_GH'
#!/usr/bin/env bash
# Picks the answer file by request kind; line N answers the N-th call (last line repeats).
printf '%s\n' "$*" >> "$FAKE_GH_DIR/calls.log"
case "$*" in
  "pr view"*) kind=pr-view ;;
  "pr checks"*) kind=checks ;;
  *"/reviews"*) kind=reviews ;;
  *"issues/"*"/comments"*) kind=issue-comments ;;
  *"pulls/"*"/comments"*) kind=pull-comments ;;
  *) echo "fake gh: unexpected call: $*" >&2; exit 64 ;;
esac
# An optional "<kind>.delay" file holds the seconds each call of that kind takes.
[[ -f "$FAKE_GH_DIR/$kind.delay" ]] && sleep "$(cat "$FAKE_GH_DIR/$kind.delay")"
answers="$FAKE_GH_DIR/$kind"
counter="$FAKE_GH_DIR/$kind.calls"
calls=$(( $(cat "$counter" 2>/dev/null || echo 0) + 1 ))
echo "$calls" > "$counter"
[[ -f "$answers" ]] || exit 0
total=$(wc -l < "$answers")
line=$(sed -n "$(( calls < total ? calls : total ))p" "$answers")
case "$line" in
  FAIL) exit 1 ;;
  EMPTY) exit 0 ;;
  *) printf '%s\n' "$line" ;;
esac
FAKE_GH
  chmod +x "$fake_bin/gh"
  export PATH="$fake_bin:$PATH"
  bash_path="$(command -v bash)"
  printf 'OPEN aaaaaaa1111111\n' > "$FAKE_GH_DIR/pr-view"
  printf '1\n' > "$FAKE_GH_DIR/reviews"
  printf 'pass=2\n' > "$FAKE_GH_DIR/checks"
}

teardown() {
  rm -rf "$test_root"
}

run_watcher() {
  run bash "$watcher" --repo acme/widgets --pr 42 --poll-seconds 1 "$@"
}

# PATH holding only the fake gh plus wrappers for the tools the watcher and the
# fake gh need, so `timeout` is absent as on macOS and the portable fallback runs.
use_path_without_timeout() {
  local tools_bin="$test_root/tools" tool_name tool_path
  mkdir -p "$tools_bin"
  for tool_name in awk bash cat date mktemp rm sed sleep wc; do
    tool_path="$(command -v "$tool_name")"
    printf '#!%s
exec "%s" "$@"
' "$bash_path" "$tool_path" > "$tools_bin/$tool_name"
    chmod +x "$tools_bin/$tool_name"
  done
  restricted_path="$fake_bin:$tools_bin"
  PATH="$restricted_path" "$bash_path" -c 'command -v timeout' >/dev/null && skip "timeout is still reachable"
  return 0
}

run_watcher_without_timeout() {
  run env PATH="$restricted_path" "$bash_path" "$watcher" --repo acme/widgets --pr 42 --poll-seconds 1 "$@"
}

@test "exits 0 and reports the new head when the PR head changes" {
  printf 'OPEN aaaaaaa1111111\nOPEN bbbbbbb2222222\n' > "$FAKE_GH_DIR/pr-view"

  run_watcher --timeout-seconds 10 --max-polls 3

  [ "$status" -eq 0 ]
  [[ "$output" == *"EVENT head bbbbbbb"* ]]
}

@test "exits 0 when Codex posts a new comment" {
  printf 'EMPTY\nEVENT comment 987\n' > "$FAKE_GH_DIR/pull-comments"

  run_watcher --timeout-seconds 10 --max-polls 3

  [ "$status" -eq 0 ]
  [[ "$output" == *"EVENT comment 987"* ]]
}

@test "with --bot claude[bot] it watches the Claude reviewer instead of Codex" {
  printf 'EMPTY\nEVENT comment 654\n' > "$FAKE_GH_DIR/pull-comments"

  run_watcher --timeout-seconds 10 --max-polls 3 --bot 'claude[bot]'

  [ "$status" -eq 0 ]
  [[ "$output" == *"EVENT comment 654"* ]]
  grep -q 'pulls/42/comments.*select(.user.login=="claude\[bot\]")' "$FAKE_GH_DIR/calls.log"
  grep -q 'pulls/42/reviews.*select(.user.login=="claude\[bot\]")' "$FAKE_GH_DIR/calls.log"
  ! grep -q 'chatgpt-codex-connector' "$FAKE_GH_DIR/calls.log"
}

@test "exits 0 when Codex submits a new review or checks change" {
  printf '1\n2\n' > "$FAKE_GH_DIR/reviews"
  printf 'pass=2\npass=1,fail=1\n' > "$FAKE_GH_DIR/checks"

  run_watcher --timeout-seconds 10 --max-polls 3

  [ "$status" -eq 0 ]
  [[ "$output" == *"EVENT review 2"* ]]
  [[ "$output" == *"EVENT checks pass=1,fail=1"* ]]
}

@test "exits 3 after the poll cap when nothing changes" {
  run_watcher --timeout-seconds 30 --max-polls 2

  [ "$status" -eq 3 ]
  [[ "$output" == *"TIMEOUT no event on PR #42 after 2 polls"* ]]
  [ "$(cat "$FAKE_GH_DIR/pr-view.calls")" -eq 3 ]
}

@test "exits 3 when the wall-clock timeout expires before the poll cap" {
  SECONDS=0
  run_watcher --timeout-seconds 2 --max-polls 100

  [ "$status" -eq 3 ]
  [[ "$output" == *"TIMEOUT"* ]]
  [ "$SECONDS" -lt 10 ]
}

@test "exits 3 within the budget when GitHub answers slower than the timeout" {
  printf '3
' > "$FAKE_GH_DIR/pr-view.delay"
  SECONDS=0

  run_watcher --timeout-seconds 1 --max-polls 100

  [ "$status" -eq 3 ]
  [[ "$output" == *"TIMEOUT budget of 1s exhausted while reading the baseline of PR #42"* ]]
  [ "$SECONDS" -lt 3 ]
}

@test "exits 3 when slow baseline reads exhaust the budget before polling" {
  printf '1
' > "$FAKE_GH_DIR/reviews.delay"
  printf '1
' > "$FAKE_GH_DIR/checks.delay"
  SECONDS=0

  run_watcher --timeout-seconds 1 --max-polls 100

  [ "$status" -eq 3 ]
  [[ "$output" == *"TIMEOUT budget of 1s exhausted while reading the baseline"* ]]
  [ "$SECONDS" -lt 4 ]
}

@test "without the timeout executable a slow GitHub call is still cut at the budget" {
  use_path_without_timeout
  printf '3
' > "$FAKE_GH_DIR/pr-view.delay"
  SECONDS=0

  run_watcher_without_timeout --timeout-seconds 1 --max-polls 100

  [ "$status" -eq 3 ]
  [[ "$output" == *"TIMEOUT budget of 1s exhausted while reading the baseline of PR #42"* ]]
  [ "$SECONDS" -lt 3 ]
}

@test "without the timeout executable the watcher still reports events" {
  use_path_without_timeout
  printf 'OPEN aaaaaaa1111111
OPEN bbbbbbb2222222
' > "$FAKE_GH_DIR/pr-view"

  run_watcher_without_timeout --timeout-seconds 10 --max-polls 3

  [ "$status" -eq 0 ]
  [[ "$output" == *"EVENT head bbbbbbb"* ]]
}

@test "exits 5 when the PR is no longer open" {
  printf 'OPEN aaaaaaa1111111\nMERGED aaaaaaa1111111\n' > "$FAKE_GH_DIR/pr-view"

  run_watcher --timeout-seconds 10 --max-polls 3

  [ "$status" -eq 5 ]
  [[ "$output" == *"PR_NOT_OPEN MERGED"* ]]
}

@test "exits 5 immediately when the PR is already closed" {
  printf 'CLOSED aaaaaaa1111111\n' > "$FAKE_GH_DIR/pr-view"

  run_watcher --timeout-seconds 10 --max-polls 3

  [ "$status" -eq 5 ]
  [ "$(cat "$FAKE_GH_DIR/pr-view.calls")" -eq 1 ]
}

@test "exits 4 after consecutive GitHub failures" {
  printf 'OPEN aaaaaaa1111111\nFAIL\n' > "$FAKE_GH_DIR/pr-view"

  run_watcher --timeout-seconds 30 --max-polls 10 --max-failures 2

  [ "$status" -eq 4 ]
  [[ "$output" == *"GH_UNAVAILABLE 2 consecutive failed polls"* ]]
}

@test "a single transient failure does not stop the watcher" {
  printf 'OPEN aaaaaaa1111111\nFAIL\nOPEN ccccccc3333333\n' > "$FAKE_GH_DIR/pr-view"

  run_watcher --timeout-seconds 10 --max-polls 3 --max-failures 2

  [ "$status" -eq 0 ]
  [[ "$output" == *"EVENT head ccccccc"* ]]
}

@test "exits 2 on invalid arguments without calling GitHub" {
  run bash "$watcher" --repo acme/widgets --pr 0
  [ "$status" -eq 2 ]

  run bash "$watcher" --repo 'not a repo' --pr 42
  [ "$status" -eq 2 ]

  run bash "$watcher" --repo acme/widgets --pr 42 --timeout-seconds -5
  [ "$status" -eq 2 ]

  run bash "$watcher" --repo acme/widgets --pr 42 --unknown
  [ "$status" -eq 2 ]

  [ ! -f "$FAKE_GH_DIR/pr-view.calls" ]
}
