#!/usr/bin/env bats

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
  launcher="$repository_root/scripts/run-bats.sh"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  # A suite with one tagged test that records the root bats ran from, and one that always fails.
  cat > "$test_root/sample.bats" <<'EOF'
# bats test_tags=area:sample
@test "records the root of bats" {
  printf '%s\n' "$BATS_ROOT" > "$BATS_TEST_DIRNAME/bats-root"
}

@test "fails on purpose" {
  false
}
EOF
}

# The bats under test runs without the timeout of the bats running this file: in Git Bash the watchdog of
# that timeout outlives its test, and `run` waits for it to close the output.
run_launcher() {
  run env -u BATS_TEST_TIMEOUT bash "$@"
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

@test "runs the bats pinned in package.json" {
  pinned_version="$(node -p 'require(process.argv[1]).devDependencies.bats' "$repository_root/package.json")"

  run_launcher "$launcher" --version

  [ "$status" -eq 0 ]
  [ "$output" = "Bats $pinned_version" ]
}

@test "passes its options and files to bats and returns its exit status" {
  run_launcher "$launcher" --filter-tags area:sample "$test_root/sample.bats"

  [ "$status" -eq 0 ]
  [[ "$output" == *"ok 1 records the root of bats"* ]]
  [[ "$output" != *"fails on purpose"* ]]

  run_launcher "$launcher" "$test_root/sample.bats"

  [ "$status" -eq 1 ]
  [[ "$output" == *"not ok 2 fails on purpose"* ]]
}

@test "starts bats from a path without a drive letter" {
  run_launcher "$launcher" --filter-tags area:sample "$test_root/sample.bats"

  [ "$status" -eq 0 ]
  bats_root="$(cat "$test_root/bats-root")"
  [[ "$bats_root" == */node_modules/* ]]
  [[ ! "$bats_root" =~ ^[A-Za-z]: ]]
}

@test "starts bats from a path without a drive letter when it is called by its Windows path" {
  command -v cygpath >/dev/null || skip "only Windows paths carry a drive letter"

  # The way the Windows CI calls it: by $GITHUB_WORKSPACE, a D:\ path.
  run_launcher "$(cygpath -w "$launcher")" --filter-tags area:sample "$test_root/sample.bats"

  [ "$status" -eq 0 ]
  bats_root="$(cat "$test_root/bats-root")"
  [[ ! "$bats_root" =~ ^[A-Za-z]: ]]
}

@test "says to run pnpm install when bats is not installed" {
  mkdir -p "$test_root/repository/scripts"
  cp "$launcher" "$test_root/repository/scripts/run-bats.sh"

  run_launcher "$test_root/repository/scripts/run-bats.sh" --version

  [ "$status" -eq 1 ]
  [[ "$output" == "run-bats: bats is not installed in $test_root/repository/node_modules;"* ]]
  [[ "$output" == *"run pnpm install"* ]]
}
