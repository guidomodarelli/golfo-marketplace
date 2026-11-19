#!/usr/bin/env bash
set -euo pipefail

HELPER=${HELPER:-"$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/review-fix-loop"}
failures=0
tests_run=0

# Cada test corre en un subshell: `exit` corta el test en el primer assert fallido.
# Con `return`, un assert intermedio fallido quedaba oculto si el último pasaba.
fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local file=$1
  local expected=$2
  grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

assert_not_contains() {
  local file=$1
  local unexpected=$2
  if grep -Fq -- "$unexpected" "$file"; then
    fail "did not expect '$unexpected' in $file"
  fi
}

assert_calls() {
  local expected=$1
  local actual
  actual=$(paste -sd ' ' "$CALL_LOG")
  [[ "$actual" == "$expected" ]] || fail "expected calls '$expected', got '$actual'"
}

setup_fixture() {
  TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/review-fix-loop-test.XXXXXX")
  REPOSITORY="$TEST_ROOT/repository"
  FAKE_BIN="$TEST_ROOT/bin"
  CALL_LOG="$TEST_ROOT/calls.log"
  STDOUT_FILE="$TEST_ROOT/stdout"
  STDERR_FILE="$TEST_ROOT/stderr"

  mkdir -p "$REPOSITORY" "$FAKE_BIN"
  : > "$CALL_LOG"

  git -C "$REPOSITORY" init -q -b main
  git -C "$REPOSITORY" config user.name 'Code Review Test'
  git -C "$REPOSITORY" config user.email 'code-review-test@example.com'
  printf 'base\n' > "$REPOSITORY/file.txt"
  git -C "$REPOSITORY" add file.txt
  git -C "$REPOSITORY" commit -qm 'base'
  git -C "$REPOSITORY" checkout -qb feature/test
  printf 'dirty\n' >> "$REPOSITORY/file.txt"

  cat > "$FAKE_BIN/provider" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
provider_name=$(basename "$0")
printf '%s\n' "$provider_name" >> "$CALL_LOG"
printf '%s\n' "$*" >> "$CALL_LOG.args"
printf 'ANTHROPIC_MODEL=%s\n' "${ANTHROPIC_MODEL:-}" >> "$CALL_LOG.args"
printf 'ANTHROPIC_BASE_URL=%s\n' "${ANTHROPIC_BASE_URL:-}" >> "$CALL_LOG.args"
printf 'ANTHROPIC_AUTH_TOKEN_SET=%s\n' "${ANTHROPIC_AUTH_TOKEN:+1}" >> "$CALL_LOG.args"
printf 'CLAUDE_CODE_SUBAGENT_MODEL=%s\n' "${CLAUDE_CODE_SUBAGENT_MODEL:-}" >> "$CALL_LOG.args"
printf 'CLAUDE_CODE_EFFORT_LEVEL=%s\n' "${CLAUDE_CODE_EFFORT_LEVEL:-}" >> "$CALL_LOG.args"
printf 'ANTHROPIC_DEFAULT_OPUS_MODEL=%s\n' "${ANTHROPIC_DEFAULT_OPUS_MODEL:-}" >> "$CALL_LOG.args"
printf 'ANTHROPIC_DEFAULT_SONNET_MODEL=%s\n' "${ANTHROPIC_DEFAULT_SONNET_MODEL:-}" >> "$CALL_LOG.args"
printf 'CLAUDE_CODE_USE_VERTEX=%s\n' "${CLAUDE_CODE_USE_VERTEX:-}" >> "$CALL_LOG.args"
printf 'CLAUDE_CODE_USE_BEDROCK=%s\n' "${CLAUDE_CODE_USE_BEDROCK:-}" >> "$CALL_LOG.args"
printf 'MCP_CONNECT_TIMEOUT_MS=%s\n' "${MCP_CONNECT_TIMEOUT_MS:-}" >> "$CALL_LOG.args"
case "$provider_name" in
  claude)
    sleep "${FAKE_CLAUDE_SLEEP_SECONDS:-0}"
    printf '%s\n' "${FAKE_CLAUDE_OUTPUT:-No actionable findings.}"
    exit "${FAKE_CLAUDE_STATUS:-0}"
    ;;
  codex)
    sleep "${FAKE_CODEX_SLEEP_SECONDS:-0}"
    printf '%s\n' "${FAKE_CODEX_OUTPUT:-No actionable findings.}"
    exit "${FAKE_CODEX_STATUS:-0}"
    ;;
esac
EOF
  # Copias en vez de symlinks: Git Bash en Windows sin modo developer no crea
  # symlinks reales y `ln -s` deja una copia sin bit de ejecución.
  local provider_name
  for provider_name in provider claude codex; do
    [[ "$provider_name" == provider ]] || cp "$FAKE_BIN/provider" "$FAKE_BIN/$provider_name"
    chmod 700 "$FAKE_BIN/$provider_name"
  done

  export TEST_ROOT REPOSITORY FAKE_BIN CALL_LOG STDOUT_FILE STDERR_FILE
  export FAKE_CLAUDE_STATUS=0 FAKE_CODEX_STATUS=0
  export FAKE_CLAUDE_SLEEP_SECONDS=0 FAKE_CODEX_SLEEP_SECONDS=0
  export FAKE_CLAUDE_OUTPUT='No actionable findings.'
  export FAKE_CODEX_OUTPUT='No actionable findings.'
  export ANTHROPIC_BASE_URL='http://inherited-config.test'
  export ANTHROPIC_AUTH_TOKEN='inherited-token'
  export ANTHROPIC_MODEL='inherited-model'
}

teardown_fixture() {
  rm -rf -- "$TEST_ROOT"
}

run_helper() {
  local status
  set +e
  (
    cd "$REPOSITORY"
    "$HELPER" \
      --mode local \
      --claude-bin "$FAKE_BIN/claude" \
      --codex-bin "$FAKE_BIN/codex" \
      "$@"
  ) > "$STDOUT_FILE" 2> "$STDERR_FILE"
  status=$?
  set -e
  return "$status"
}

test_auto_stops_after_claude_success() {
  setup_fixture
  trap teardown_fixture EXIT

  run_helper --provider auto
  assert_calls 'claude'
  assert_contains "$STDOUT_FILE" 'provider order: claude-copilot -> claude -> codex'
  assert_contains "$STDOUT_FILE" 'code-review completed by provider: claude'
}

test_claude_copilot_uses_configured_profile() {
  setup_fixture
  trap teardown_fixture EXIT
  run_helper -p claude-copilot
  assert_contains "$CALL_LOG.args" 'ANTHROPIC_MODEL=gpt-6-luna[1m]'
  assert_contains "$CALL_LOG.args" 'CLAUDE_CODE_SUBAGENT_MODEL=gpt-6-luna[1m]'
  assert_contains "$CALL_LOG.args" 'CLAUDE_CODE_EFFORT_LEVEL=max'
  assert_contains "$CALL_LOG.args" 'ANTHROPIC_BASE_URL=http://localhost:4141'
  assert_contains "$CALL_LOG.args" 'ANTHROPIC_AUTH_TOKEN_SET=1'
  assert_contains "$CALL_LOG.args" 'ANTHROPIC_DEFAULT_OPUS_MODEL=gpt-6-luna[1m]'
  assert_contains "$CALL_LOG.args" 'ANTHROPIC_DEFAULT_SONNET_MODEL=gpt-6-luna[1m]'
  assert_contains "$CALL_LOG.args" 'CLAUDE_CODE_USE_VERTEX=0'
  assert_contains "$CALL_LOG.args" 'CLAUDE_CODE_USE_BEDROCK=0'
  assert_contains "$CALL_LOG.args" 'MCP_CONNECT_TIMEOUT_MS=20000'
  assert_not_contains "$CALL_LOG.args" '--model'
  assert_not_contains "$CALL_LOG.args" '--effort'
  assert_not_contains "$CALL_LOG.args" 'ANTHROPIC_BASE_URL=http://inherited-config.test'
}

test_claude_direct_bypasses_copilot_api() {
  setup_fixture
  trap teardown_fixture EXIT

  run_helper -p claude
  assert_contains "$CALL_LOG.args" '--setting-sources project,local'
  assert_contains "$CALL_LOG.args" 'ANTHROPIC_BASE_URL='
  assert_contains "$CALL_LOG.args" 'ANTHROPIC_AUTH_TOKEN_SET='
  assert_contains "$CALL_LOG.args" 'CLAUDE_CODE_SUBAGENT_MODEL='
  assert_not_contains "$CALL_LOG.args" 'ANTHROPIC_BASE_URL=http://inherited-config.test'
  assert_not_contains "$CALL_LOG.args" 'ANTHROPIC_AUTH_TOKEN_SET=1'
}

test_short_provider_selects_codex_only() {
  setup_fixture
  trap teardown_fixture EXIT

  run_helper -p codex
  assert_calls 'codex'
  assert_contains "$STDOUT_FILE" 'provider: codex'
}

test_quota_failure_falls_back_to_codex() {
  setup_fixture
  trap teardown_fixture EXIT
  export FAKE_CLAUDE_STATUS=1
  export FAKE_CLAUDE_OUTPUT='You hit your spend cap set by the owner of your workspace.'

  run_helper
  assert_calls 'claude claude codex'
  assert_contains "$STDERR_FILE" 'quota_exceeded'
  assert_contains "$STDOUT_FILE" 'code-review completed by provider: codex'
}

test_timeout_falls_back_to_codex() {
  setup_fixture
  trap teardown_fixture EXIT
  export FAKE_CLAUDE_SLEEP_SECONDS=2

  run_helper --timeout-seconds 1
  assert_calls 'claude claude codex'
  assert_contains "$STDERR_FILE" 'infrastructure_error'
  assert_contains "$STDOUT_FILE" 'code-review completed by provider: codex'
}

test_missing_claude_falls_back_to_codex() {
  setup_fixture
  trap teardown_fixture EXIT

  set +e
  (
    cd "$REPOSITORY"
    "$HELPER" --mode local \
      --claude-bin "$FAKE_BIN/missing-claude" \
      --codex-bin "$FAKE_BIN/codex"
  ) > "$STDOUT_FILE" 2> "$STDERR_FILE"
  status=$?
  set -e

  [[ "$status" -eq 0 ]] || fail "expected fallback success, got exit $status"
  assert_calls 'codex'
  assert_contains "$STDERR_FILE" 'provider_unavailable'
}

test_auth_failure_reaches_codex() {
  setup_fixture
  trap teardown_fixture EXIT
  export FAKE_CLAUDE_STATUS=1
  export FAKE_CLAUDE_OUTPUT='Authentication required. Run login.'

  run_helper
  assert_calls 'claude claude codex'
  assert_contains "$STDERR_FILE" 'not_authenticated'
  assert_contains "$STDOUT_FILE" 'code-review completed by provider: codex'
}

test_explicit_provider_never_falls_back() {
  setup_fixture
  trap teardown_fixture EXIT
  export FAKE_CLAUDE_STATUS=1
  export FAKE_CLAUDE_OUTPUT='You hit your spend cap.'

  if run_helper -p claude; then
    fail 'expected explicit Claude failure'
  fi
  assert_calls 'claude'
  assert_not_contains "$CALL_LOG" 'codex'
}

test_unknown_failure_never_falls_back() {
  setup_fixture
  trap teardown_fixture EXIT
  export FAKE_CLAUDE_STATUS=1
  export FAKE_CLAUDE_OUTPUT='Unexpected adapter response.'

  if run_helper; then
    fail 'expected unknown provider failure'
  fi
  assert_calls 'claude'
  assert_contains "$STDERR_FILE" 'unknown_provider_error'
}

test_completed_review_with_findings_never_falls_back() {
  setup_fixture
  trap teardown_fixture EXIT
  export FAKE_CLAUDE_OUTPUT='Finding: file.txt:1 produces incorrect behavior.'

  run_helper
  assert_calls 'claude'
  assert_contains "$STDOUT_FILE" 'Finding: file.txt:1'
  assert_contains "$STDOUT_FILE" 'code-review completed by provider: claude'
}

test_failed_parallel_tests_do_not_trigger_fallback() {
  setup_fixture
  trap teardown_fixture EXIT

  if run_helper --parallel-tests false; then
    fail 'expected failed tests to fail closeout'
  fi
  assert_calls 'claude'
  assert_contains "$STDOUT_FILE" 'tests exit: 1'
}

test_dry_run_does_not_invoke_providers() {
  setup_fixture
  trap teardown_fixture EXIT

  run_helper --dry-run
  [[ ! -s "$CALL_LOG" ]] || fail 'dry-run invoked a provider'
  assert_contains "$STDOUT_FILE" 'review[claude-copilot]:'
  assert_contains "$STDOUT_FILE" 'review[claude]:'
  assert_contains "$STDOUT_FILE" 'review[codex]:'
}

test_output_captures_provider_result() {
  setup_fixture
  trap teardown_fixture EXIT
  local saved_output="$TEST_ROOT/review.log"

  run_helper -p codex --output "$saved_output"
  assert_contains "$saved_output" '--- codex review output ---'
  assert_contains "$saved_output" 'No actionable findings.'
}

test_invalid_provider_returns_usage_error() {
  setup_fixture
  trap teardown_fixture EXIT

  set +e
  run_helper -p invalid
  status=$?
  set -e
  [[ "$status" -eq 2 ]] || fail "expected exit 2, got $status"
  [[ ! -s "$CALL_LOG" ]] || fail 'invalid provider invoked a binary'
  assert_contains "$STDERR_FILE" 'invalid --provider: invalid'
}

test_invalid_timeout_returns_usage_error() {
  setup_fixture
  trap teardown_fixture EXIT

  set +e
  run_helper --timeout-seconds invalid
  status=$?
  set -e
  [[ "$status" -eq 2 ]] || fail "expected exit 2, got $status"
  assert_contains "$STDERR_FILE" 'invalid --timeout-seconds: invalid'
}

test_round_above_cap_stops_without_provider() {
  setup_fixture
  trap teardown_fixture EXIT

  set +e
  run_helper --round 4 --max-rounds 3
  status=$?
  set -e
  [[ "$status" -eq 3 ]] || fail "expected exit 3, got $status"
  [[ ! -s "$CALL_LOG" ]] || fail 'round cap invoked a provider'
  assert_contains "$STDERR_FILE" 'round cap reached: round 4 exceeds max 3'
}

test_round_within_cap_runs_review() {
  setup_fixture
  trap teardown_fixture EXIT

  run_helper -p claude --round 3
  assert_calls 'claude'
  assert_contains "$STDOUT_FILE" 'round: 3/3'
}

test_invalid_round_returns_usage_error() {
  setup_fixture
  trap teardown_fixture EXIT

  set +e
  run_helper --round 0
  status=$?
  set -e
  [[ "$status" -eq 2 ]] || fail "expected exit 2, got $status"
  assert_contains "$STDERR_FILE" 'invalid --round: 0'
}

test_since_reviews_only_later_changes() {
  setup_fixture
  trap teardown_fixture EXIT
  local since_sha
  since_sha=$(git -C "$REPOSITORY" rev-parse HEAD)

  run_helper -p claude --since "$since_sha"
  assert_contains "$STDOUT_FILE" 'code-review target: delta'
  assert_contains "$CALL_LOG.args" "only the changes made after ${since_sha}"

  : > "$CALL_LOG.args"
  run_helper -p codex --since "$since_sha"
  assert_contains "$CALL_LOG.args" "review --base ${since_sha}"
}

test_invalid_since_returns_usage_error() {
  setup_fixture
  trap teardown_fixture EXIT

  set +e
  run_helper --since does-not-exist
  status=$?
  set -e
  [[ "$status" -eq 2 ]] || fail "expected exit 2, got $status"
  [[ ! -s "$CALL_LOG" ]] || fail 'invalid --since invoked a provider'
  assert_contains "$STDERR_FILE" 'invalid --since: does-not-exist is not a commit'
}

test_known_findings_reach_review_prompt() {
  setup_fixture
  trap teardown_fixture EXIT
  local known_findings="$TEST_ROOT/known-findings.md"
  printf -- '- file.txt:1 rejected: intentional trailing line\n' > "$known_findings"

  run_helper -p claude --known-findings "$known_findings"
  assert_contains "$CALL_LOG.args" 'Do not report them again'
  assert_contains "$CALL_LOG.args" 'file.txt:1 rejected: intentional trailing line'
}

test_missing_known_findings_returns_usage_error() {
  setup_fixture
  trap teardown_fixture EXIT

  set +e
  run_helper --known-findings "$TEST_ROOT/missing.md"
  status=$?
  set -e
  [[ "$status" -eq 2 ]] || fail "expected exit 2, got $status"
  assert_contains "$STDERR_FILE" 'unreadable --known-findings file'
}

test_review_prompt_requests_labels_and_count() {
  setup_fixture
  trap teardown_fixture EXIT

  run_helper -p claude
  assert_contains "$CALL_LOG.args" 'Important (must be fixed before merge), Nit (optional, never blocking), Pre-existing'
  assert_contains "$CALL_LOG.args" 'Start the result with the finding count per label'
  assert_contains "$CALL_LOG.args" 'read REVIEW.md, CLAUDE.md, and AGENTS.md'
}

# Cada test corre en su propio proceso bajo `timeout`, que corta el grupo de procesos
# completo: un test colgado falla a los TEST_TIMEOUT_SECONDS en vez de bloquear la suite.
readonly DEFAULT_TEST_TIMEOUT_SECONDS=30
readonly TIMEOUT_EXIT_STATUS=124
readonly SINGLE_TEST_FLAG=--run-single-test
TEST_TIMEOUT_SECONDS=${TEST_TIMEOUT_SECONDS:-$DEFAULT_TEST_TIMEOUT_SECONDS}
TEST_SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
TIMEOUT_COMMAND=$(command -v timeout || command -v gtimeout || true)

run_isolated_test() {
  local test_function=$1
  if [[ -z "$TIMEOUT_COMMAND" ]]; then
    bash "$TEST_SCRIPT_PATH" "$SINGLE_TEST_FLAG" "$test_function"
    return
  fi
  "$TIMEOUT_COMMAND" --kill-after=5 "$TEST_TIMEOUT_SECONDS" bash "$TEST_SCRIPT_PATH" "$SINGLE_TEST_FLAG" "$test_function"
}

report_test_result() {
  local name=$1
  local status=$2
  if [[ "$status" -eq 0 ]]; then
    printf 'ok %d - %s\n' "$tests_run" "$name"
    return
  fi
  failures=$((failures + 1))
  if [[ "$status" -eq "$TIMEOUT_EXIT_STATUS" ]]; then
    printf 'not ok %d - %s (timeout: superó %ss)\n' "$tests_run" "$name" "$TEST_TIMEOUT_SECONDS"
  else
    printf 'not ok %d - %s\n' "$tests_run" "$name"
  fi
}

if [[ "${1:-}" == "$SINGLE_TEST_FLAG" ]]; then
  # Dentro de `if`, igual que antes del aislamiento: errexit no corta los tests que esperan exit != 0.
  if "$2"; then
    exit 0
  fi
  exit 1
fi

run_test() {
  local name=$1
  local test_function=$2
  local status=0
  tests_run=$((tests_run + 1))
  run_isolated_test "$test_function" || status=$?
  report_test_result "$name" "$status"
}

run_test 'auto stops after Claude success' test_auto_stops_after_claude_success
run_test 'Claude Copilot uses configured profile' test_claude_copilot_uses_configured_profile
run_test 'Claude direct bypasses Copilot API' test_claude_direct_bypasses_copilot_api
run_test 'short provider flag selects Codex only' test_short_provider_selects_codex_only
run_test 'quota failure falls back to Codex' test_quota_failure_falls_back_to_codex
run_test 'timeout falls back to Codex' test_timeout_falls_back_to_codex
run_test 'missing Claude falls back to Codex' test_missing_claude_falls_back_to_codex
run_test 'auth failure reaches Codex' test_auth_failure_reaches_codex
run_test 'explicit provider never falls back' test_explicit_provider_never_falls_back
run_test 'unknown failure never falls back' test_unknown_failure_never_falls_back
run_test 'completed review with findings never falls back' test_completed_review_with_findings_never_falls_back
run_test 'failed parallel tests do not trigger fallback' test_failed_parallel_tests_do_not_trigger_fallback
run_test 'dry-run does not invoke providers' test_dry_run_does_not_invoke_providers
run_test 'output captures provider result' test_output_captures_provider_result
run_test 'invalid provider returns usage error' test_invalid_provider_returns_usage_error
run_test 'invalid timeout returns usage error' test_invalid_timeout_returns_usage_error
run_test 'round above cap stops without provider' test_round_above_cap_stops_without_provider
run_test 'round within cap runs review' test_round_within_cap_runs_review
run_test 'invalid round returns usage error' test_invalid_round_returns_usage_error
run_test 'since reviews only later changes' test_since_reviews_only_later_changes
run_test 'invalid since returns usage error' test_invalid_since_returns_usage_error
run_test 'known findings reach review prompt' test_known_findings_reach_review_prompt
run_test 'missing known findings returns usage error' test_missing_known_findings_returns_usage_error
run_test 'review prompt requests labels and count' test_review_prompt_requests_labels_and_count

if [[ "$failures" -ne 0 ]]; then
  printf '%d/%d tests failed\n' "$failures" "$tests_run" >&2
  exit 1
fi

printf '%d tests passed\n' "$tests_run"
