#!/usr/bin/env bash
set -euo pipefail

HELPER=${HELPER:-"$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)/sibling-worktree"}
failures=0
tests_run=0
TEST_ROOT=
TEST_FAILED=false

fail() {
  TEST_FAILED=true
  printf 'FAIL: %s\n' "$1" >&2
  return 1
}

assert_status() {
  local expected=$1
  if [[ "$TEST_STATUS" -ne "$expected" ]]; then
    fail "expected exit $expected, got $TEST_STATUS; stdout: $(tr '\n' ' ' < "$STDOUT_FILE"); stderr: $(tr '\n' ' ' < "$STDERR_FILE")"
  fi
}

assert_contains() {
  local file=$1
  local expected=$2
  grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

assert_not_exists() {
  local path=$1
  [[ ! -e "$path" && ! -L "$path" ]] || fail "did not expect path to exist: $path"
}

setup_fixture() {
  TEST_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/sibling-worktree-test.XXXXXX")
  TEST_ROOT=$(cd "$TEST_ROOT" && pwd -P)
  WORK_PARENT="$TEST_ROOT/parent"
  REPO="$WORK_PARENT/repository"
  REMOTE="$TEST_ROOT/origin.git"
  STDOUT_FILE="$TEST_ROOT/stdout"
  STDERR_FILE="$TEST_ROOT/stderr"

  mkdir -p "$WORK_PARENT"
  git init -q -b main "$REPO"
  git -C "$REPO" config user.name 'Worktree Test'
  git -C "$REPO" config user.email 'worktree-test@example.com'
  printf 'base\n' > "$REPO/file.txt"
  git -C "$REPO" add file.txt
  git -C "$REPO" commit -qm 'base'
  git -C "$REPO" branch develop
  git -C "$REPO" branch feature/local

  git init --bare -q "$REMOTE"
  git -C "$REPO" remote add origin "$REMOTE"
  git -C "$REPO" push -q -u origin main
  git -C "$REMOTE" symbolic-ref HEAD refs/heads/main
  git -C "$REPO" push -q -u origin develop
  git -C "$REPO" push -q -u origin feature/local

  git -C "$REPO" checkout -qb temp/remote-source
  printf 'remote\n' >> "$REPO/file.txt"
  git -C "$REPO" add file.txt
  git -C "$REPO" commit -qm 'remote source'
  git -C "$REPO" push -q origin HEAD:refs/heads/feature/remote
  git -C "$REPO" checkout -q main
  git -C "$REPO" branch -D temp/remote-source >/dev/null
  git -C "$REPO" fetch -q origin

  export TEST_ROOT WORK_PARENT REPO REMOTE STDOUT_FILE STDERR_FILE
}

teardown_fixture() {
  if [[ -n "$TEST_ROOT" ]]; then
    rm -rf -- "$TEST_ROOT"
    TEST_ROOT=
  fi
}

run_helper() {
  set +e
  (
    cd "$REPO"
    "$HELPER" "$@"
  ) > "$STDOUT_FILE" 2> "$STDERR_FILE"
  TEST_STATUS=$?
  set -e
}

run_helper_from() {
  local working_directory=$1
  shift
  set +e
  (
    cd "$working_directory"
    "$HELPER" "$@"
  ) > "$STDOUT_FILE" 2> "$STDERR_FILE"
  TEST_STATUS=$?
  set -e
}

advance_remote_branch() {
  local branch=$1
  local marker=$2
  local remote_client="$TEST_ROOT/remote-client"

  git clone -q "$REMOTE" "$remote_client"
  git -C "$remote_client" config user.name 'Remote Test'
  git -C "$remote_client" config user.email 'remote-test@example.com'
  git -C "$remote_client" checkout -qb update "origin/$branch"
  printf '%s\n' "$marker" >> "$remote_client/file.txt"
  git -C "$remote_client" add file.txt
  git -C "$remote_client" commit -qm "$marker"
  git -C "$remote_client" push -q origin "HEAD:refs/heads/$branch"
  ADVANCED_REMOTE_OID=$(git -C "$remote_client" rev-parse HEAD)
}

test_help_and_invalid_operation() {
  setup_fixture
  run_helper --help
  assert_status 0
  assert_contains "$STDOUT_FILE" 'sibling-worktree create'

  run_helper unknown
  assert_status 2
  teardown_fixture
}

test_create_local_branch() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-local"

  run_helper create --branch feature/local --dry-run
  assert_status 0
  assert_not_exists "$target"
  assert_contains "$STDOUT_FILE" "Destino hermano: $target"

  run_helper create --branch feature/local
  assert_status 0
  [[ -d "$target" ]] || fail "expected worktree directory: $target"
  [[ "$(git -C "$target" branch --show-current)" == 'feature/local' ]] || fail 'expected local branch checkout'
  assert_contains "$STDOUT_FILE" 'Worktree creado correctamente.'
  teardown_fixture
}

test_create_remote_tracking_branch() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-remote"

  run_helper create --branch origin/feature/remote
  assert_status 0
  [[ "$(git -C "$target" branch --show-current)" == 'feature/remote' ]] || fail 'expected remote branch to become local branch'
  [[ "$(git -C "$target" rev-parse --abbrev-ref --symbolic-full-name '@{u}')" == 'origin/feature/remote' ]] || fail 'expected remote tracking branch'
  assert_contains "$STDOUT_FILE" 'tracking local se creará'
  teardown_fixture
}

test_remote_tracking_stale_fetches_latest() {
  local target
  local old_oid
  local expected_oid
  setup_fixture
  target="$WORK_PARENT/repository-remote-stale"
  old_oid=$(git -C "$REPO" rev-parse refs/remotes/origin/feature/remote)
  advance_remote_branch feature/remote 'remote update'
  expected_oid=$ADVANCED_REMOTE_OID

  [[ "$old_oid" != "$expected_oid" ]] || fail 'expected remote branch to advance after initial fetch'
  run_helper create --branch origin/feature/remote --name remote-stale
  assert_status 0
  [[ "$(git -C "$target" rev-parse HEAD)" == "$expected_oid" ]] || fail 'worktree did not use latest remote commit'
  [[ "$(git -C "$REPO" rev-parse refs/remotes/origin/feature/remote)" == "$expected_oid" ]] || fail 'remote-tracking ref was not refreshed'
  assert_contains "$STDOUT_FILE" 'Actualizando fuente remota: origin/feature/remote'
  teardown_fixture
}

test_local_branch_fast_forwards_from_upstream() {
  local target
  local expected_oid
  setup_fixture
  target="$WORK_PARENT/repository-local-fast-forward"
  advance_remote_branch feature/local 'local upstream update'
  expected_oid=$ADVANCED_REMOTE_OID

  run_helper create --branch feature/local --name local-fast-forward
  assert_status 0
  [[ "$(git -C "$REPO" rev-parse refs/heads/feature/local)" == "$expected_oid" ]] || fail 'local branch did not fast-forward'
  [[ "$(git -C "$target" rev-parse HEAD)" == "$expected_oid" ]] || fail 'worktree did not use fast-forwarded commit'
  assert_contains "$STDOUT_FILE" 'fast-forward aplicado'
  teardown_fixture
}

test_local_branch_without_upstream_blocks() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-no-upstream"
  git -C "$REPO" branch feature/no-upstream

  run_helper create --branch feature/no-upstream
  assert_status 3
  assert_not_exists "$target"
  assert_contains "$STDERR_FILE" 'no tiene upstream remoto'
  teardown_fixture
}

test_local_branch_divergence_blocks_without_reset() {
  local target
  local local_oid
  setup_fixture
  target="$WORK_PARENT/repository-divergent"

  git -C "$REPO" checkout -q feature/local
  printf 'local divergent\n' >> "$REPO/file.txt"
  git -C "$REPO" add file.txt
  git -C "$REPO" commit -qm 'local divergent'
  local_oid=$(git -C "$REPO" rev-parse HEAD)
  git -C "$REPO" checkout -q main
  advance_remote_branch feature/local 'remote divergent'

  run_helper create --branch feature/local --name divergent
  assert_status 3
  assert_not_exists "$target"
  [[ "$(git -C "$REPO" rev-parse refs/heads/feature/local)" == "$local_oid" ]] || fail 'divergent local branch was overwritten'
  assert_contains "$STDERR_FILE" 'diverge'
  teardown_fixture
}

test_local_branch_ahead_is_preserved() {
  local target
  local expected_oid
  setup_fixture
  target="$WORK_PARENT/repository-local-ahead"

  git -C "$REPO" checkout -q feature/local
  printf 'local ahead\n' >> "$REPO/file.txt"
  git -C "$REPO" add file.txt
  git -C "$REPO" commit -qm 'local ahead'
  expected_oid=$(git -C "$REPO" rev-parse HEAD)
  git -C "$REPO" checkout -q main

  run_helper create --branch feature/local --name local-ahead
  assert_status 0
  [[ "$(git -C "$target" rev-parse HEAD)" == "$expected_oid" ]] || fail 'local ahead commit was not preserved'
  assert_contains "$STDOUT_FILE" 'adelantada; no se sobrescribirá'
  teardown_fixture
}

test_fetch_failure_blocks_without_creating_worktree() {
  local target
  local local_oid
  setup_fixture
  target="$WORK_PARENT/repository-fetch-failure"
  local_oid=$(git -C "$REPO" rev-parse refs/heads/feature/local)
  git -C "$REPO" remote set-url origin "$TEST_ROOT/missing-origin.git"

  run_helper create --branch feature/local --name fetch-failure
  assert_status 1
  assert_not_exists "$target"
  [[ "$(git -C "$REPO" rev-parse refs/heads/feature/local)" == "$local_oid" ]] || fail 'fetch failure changed local branch'
  assert_contains "$STDERR_FILE" 'no se pudo actualizar fuente remota'
  teardown_fixture
}

test_dry_run_does_not_refresh_remote_tracking_ref() {
  local target
  local old_oid
  local expected_oid
  setup_fixture
  target="$WORK_PARENT/repository-remote-dry-run"
  old_oid=$(git -C "$REPO" rev-parse refs/remotes/origin/feature/remote)
  advance_remote_branch feature/remote 'remote dry-run update'
  expected_oid=$ADVANCED_REMOTE_OID

  run_helper create --branch origin/feature/remote --name remote-dry-run --dry-run
  assert_status 0
  assert_not_exists "$target"
  [[ "$(git -C "$REPO" rev-parse refs/remotes/origin/feature/remote)" == "$old_oid" ]] || fail 'dry-run changed remote-tracking ref'
  [[ "$old_oid" != "$expected_oid" ]] || fail 'expected remote branch to advance'
  assert_contains "$STDOUT_FILE" 'Dry-run: fetch previsto sin modificar referencias.'
  teardown_fixture
}

test_explicit_remote_source_updates_local_homonym() {
  local target
  local expected_oid
  setup_fixture
  target="$WORK_PARENT/repository-remote-homonym"
  git -C "$REPO" branch feature/remote refs/remotes/origin/feature/remote
  advance_remote_branch feature/remote 'remote homonym update'
  expected_oid=$ADVANCED_REMOTE_OID

  run_helper create --branch refs/remotes/origin/feature/remote --name remote-homonym
  assert_status 0
  [[ "$(git -C "$REPO" rev-parse refs/heads/feature/remote)" == "$expected_oid" ]] || fail 'explicit remote source did not update local homonym'
  [[ "$(git -C "$target" rev-parse HEAD)" == "$expected_oid" ]] || fail 'worktree did not use explicit remote source'
  teardown_fixture
}

test_explicit_path_and_existing_path_block() {
  local target
  setup_fixture
  target="$WORK_PARENT/custom-worktree"

  run_helper create --branch feature/local --path "$target"
  assert_status 0
  [[ -d "$target" ]] || fail 'expected explicit path worktree'

  run_helper create --branch feature/local --path "$target"
  assert_status 3
  assert_contains "$STDERR_FILE" 'ruta destino ya existe'
  teardown_fixture
}

test_primary_branch_requires_confirmation() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-main-copy"

  run_helper create --branch main --path "$target"
  assert_status 3
  [[ "$(git -C "$REPO" branch --show-current)" == 'main' ]] || fail 'principal changed without confirmation'
  assert_not_exists "$target"
  assert_contains "$STDERR_FILE" 'requiere confirmación explícita'
  teardown_fixture
}

test_confirmed_primary_switch_to_develop() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-main-copy"

  run_helper create --branch main --path "$target" --confirm-primary-switch-to-develop --dry-run
  assert_status 0
  [[ "$(git -C "$REPO" branch --show-current)" == 'main' ]] || fail 'dry-run changed principal'
  assert_not_exists "$target"

  run_helper create --branch main --path "$target" --confirm-primary-switch-to-develop
  assert_status 0
  [[ "$(git -C "$REPO" branch --show-current)" == 'develop' ]] || fail 'expected principal to move to develop'
  [[ "$(git -C "$target" branch --show-current)" == 'main' ]] || fail 'expected requested branch in new worktree'
  teardown_fixture
}

test_dirty_primary_blocks_confirmed_switch() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-main-copy"
  printf 'local change\n' >> "$REPO/file.txt"

  run_helper create --branch main --path "$target" --confirm-primary-switch-to-develop
  assert_status 3
  [[ "$(git -C "$REPO" branch --show-current)" == 'main' ]] || fail 'dirty principal changed'
  assert_not_exists "$target"
  assert_contains "$STDERR_FILE" 'cambios no committeados'
  teardown_fixture
}

test_dry_run_does_not_mutate() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-local"

  run_helper create --branch feature/local --name ignored-name --dry-run
  assert_status 0
  assert_not_exists "$WORK_PARENT/repository-ignored-name"
  assert_contains "$STDOUT_FILE" 'Dry-run: comandos previstos:'
  teardown_fixture
}

test_list_reports_worktrees() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-local"
  run_helper create --branch feature/local
  assert_status 0

  run_helper list
  assert_status 0
  assert_contains "$STDOUT_FILE" 'rol: principal/actual'
  assert_contains "$STDOUT_FILE" 'rama: feature/local'
  assert_contains "$STDOUT_FILE" "ruta: $target"
  teardown_fixture
}

test_remove_clean_worktree_preserves_branch() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-local"
  run_helper create --branch feature/local
  assert_status 0

  run_helper remove --branch feature/local --dry-run
  assert_status 0
  [[ -d "$target" ]] || fail 'dry-run removed worktree'

  run_helper remove --branch feature/local
  assert_status 0
  assert_not_exists "$target"
  git -C "$REPO" show-ref --verify --quiet refs/heads/feature/local || fail 'remove deleted local branch'
  teardown_fixture
}

test_remove_dirty_or_ignored_worktree_blocks() {
  local target
  setup_fixture
  target="$WORK_PARENT/repository-local"
  run_helper create --branch feature/local
  assert_status 0
  printf 'local change\n' >> "$target/file.txt"

  run_helper remove --branch feature/local
  assert_status 3
  [[ -d "$target" ]] || fail 'dirty worktree was removed'
  assert_contains "$STDERR_FILE" 'cambios o archivos ignorados'
  teardown_fixture
}

test_create_from_sibling_uses_primary_path() {
  local first_target
  local second_target
  local nested_target
  setup_fixture
  first_target="$WORK_PARENT/repository-local"
  second_target="$WORK_PARENT/repository-from-sibling"
  nested_target="$first_target/repository-from-sibling"

  run_helper create --branch feature/local
  assert_status 0
  run_helper_from "$first_target" create --branch develop --name from-sibling
  assert_status 0
  [[ -d "$second_target" ]] || fail 'sibling invocation used wrong destination root'
  assert_not_exists "$nested_target"
  assert_contains "$STDOUT_FILE" "Destino hermano: $second_target"
  teardown_fixture
}

test_nested_path_blocks_before_fetch() {
  local nested_target
  setup_fixture
  nested_target="$REPO/.claude/worktrees/nested"
  mkdir -p "$(dirname "$nested_target")"

  run_helper create --branch feature/local --path "$nested_target"
  assert_status 3
  assert_not_exists "$nested_target"
  assert_contains "$STDERR_FILE" 'ruta debe ser hermana inmediata'
  teardown_fixture
}

test_invalid_path_and_symlink_block() {
  local existing_target
  local symlink_target
  setup_fixture
  existing_target="$WORK_PARENT/existing"
  symlink_target="$WORK_PARENT/repository-symlink"
  mkdir -p "$existing_target"
  ln -s "$existing_target" "$symlink_target"

  run_helper create --branch feature/local --path "$existing_target"
  assert_status 3
  run_helper create --branch feature/local --path "$symlink_target"
  assert_status 3
  assert_contains "$STDERR_FILE" 'ruta destino ya existe'
  teardown_fixture
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
  TEST_FAILED=false
  "$2" || true
  if [[ "$TEST_FAILED" == false ]]; then
    exit 0
  fi
  teardown_fixture
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

trap teardown_fixture EXIT

run_test 'help and invalid operation' test_help_and_invalid_operation
run_test 'create local branch' test_create_local_branch
run_test 'create remote tracking branch' test_create_remote_tracking_branch
run_test 'stale remote tracking fetches latest' test_remote_tracking_stale_fetches_latest
run_test 'local branch fast-forwards from upstream' test_local_branch_fast_forwards_from_upstream
run_test 'local branch without upstream gate' test_local_branch_without_upstream_blocks
run_test 'local branch divergence gate' test_local_branch_divergence_blocks_without_reset
run_test 'local branch ahead is preserved' test_local_branch_ahead_is_preserved
run_test 'fetch failure gate' test_fetch_failure_blocks_without_creating_worktree
run_test 'dry-run preserves remote tracking ref' test_dry_run_does_not_refresh_remote_tracking_ref
run_test 'explicit remote source with local homonym' test_explicit_remote_source_updates_local_homonym
run_test 'explicit and existing path handling' test_explicit_path_and_existing_path_block
run_test 'primary branch confirmation gate' test_primary_branch_requires_confirmation
run_test 'confirmed primary switch to develop' test_confirmed_primary_switch_to_develop
run_test 'dirty primary confirmation gate' test_dirty_primary_blocks_confirmed_switch
run_test 'dry-run does not mutate' test_dry_run_does_not_mutate
run_test 'list reports worktrees' test_list_reports_worktrees
run_test 'remove clean worktree preserves branch' test_remove_clean_worktree_preserves_branch
run_test 'remove dirty worktree gate' test_remove_dirty_or_ignored_worktree_blocks
run_test 'create from sibling uses primary path' test_create_from_sibling_uses_primary_path
run_test 'nested path gate' test_nested_path_blocks_before_fetch
run_test 'invalid path and symlink gate' test_invalid_path_and_symlink_block

if [[ "$failures" -ne 0 ]]; then
  printf '%d/%d tests fallaron\n' "$failures" "$tests_run" >&2
  exit 1
fi

printf '%d tests pasaron\n' "$tests_run"
