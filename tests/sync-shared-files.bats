#!/usr/bin/env bats

# Exercises scripts/sync-shared-files.js against a temporary repository with one shared
# reference, one shared tool directory (with a tests/ directory that is never copied) and
# two plugins.

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
  test_root="$(mktemp -d)"
  repo_dir="$test_root/repo"
  mkdir -p "$repo_dir/scripts/lib" "$repo_dir/shared/references" "$repo_dir/shared/tools/demo/lib" "$repo_dir/shared/tools/demo/tests"
  cp "$repository_root/scripts/sync-shared-files.js" "$repo_dir/scripts/"
  cp "$repository_root/scripts/lib/terminal-output.js" "$repo_dir/scripts/lib/"
  mkdir -p "$repo_dir/plugins/alpha" "$repo_dir/plugins/beta"
  printf '%s\n' '# Shared reference' > "$repo_dir/shared/references/shared-guide.md"
  printf '%s\n' 'export const main = 1;' > "$repo_dir/shared/tools/demo/main.mjs"
  printf '%s\n' 'export const helper = 2;' > "$repo_dir/shared/tools/demo/lib/helper.mjs"
  printf '%s\n' 'test only' > "$repo_dir/shared/tools/demo/tests/demo.test.mjs"
  cat > "$repo_dir/shared/shared-files.json" <<'JSON'
{
  "entries": [
    { "source": "references/shared-guide.md", "plugins": ["alpha", "beta"] },
    { "source": "tools/demo", "exclude": ["tests"], "plugins": ["alpha"] }
  ]
}
JSON
  export NO_COLOR=1
  unset GITHUB_ACTIONS
  cd "$repo_dir"
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

sync_files() {
  run node scripts/sync-shared-files.js "$@"
}

@test "--check fails and lists every missing copy before the first sync" {
  sync_files --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"plugins/alpha/references/shared-guide.md: missing copy of shared/references/shared-guide.md"* ]]
  [[ "$output" == *"plugins/beta/references/shared-guide.md: missing copy"* ]]
  [[ "$output" == *"plugins/alpha/tools/demo/lib/helper.mjs: missing copy"* ]]
}

@test "sync writes identical copies, skips excluded directories, and --check passes afterwards" {
  sync_files
  [ "$status" -eq 0 ]
  cmp shared/references/shared-guide.md plugins/beta/references/shared-guide.md
  cmp shared/tools/demo/lib/helper.mjs plugins/alpha/tools/demo/lib/helper.mjs
  [ ! -e plugins/alpha/tools/demo/tests ]
  [ ! -e plugins/beta/tools ]
  sync_files --check
  [ "$status" -eq 0 ]
  [[ "$output" == *"shared files in sync (4 copies)"* ]]
}

@test "--check reports a copy edited by hand and sync restores it" {
  sync_files
  printf '%s\n' 'edited by hand' >> plugins/alpha/references/shared-guide.md
  sync_files --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"plugins/alpha/references/shared-guide.md: differs from shared/references/shared-guide.md"* ]]
  sync_files
  [ "$status" -eq 0 ]
  cmp shared/references/shared-guide.md plugins/alpha/references/shared-guide.md
}

@test "a file left in a copied directory is reported by --check and removed by sync" {
  sync_files
  printf '%s\n' 'stale' > plugins/alpha/tools/demo/lib/stale.mjs
  sync_files --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"plugins/alpha/tools/demo/lib/stale.mjs: not in shared/tools/demo"* ]]
  sync_files
  [ "$status" -eq 0 ]
  [ ! -e plugins/alpha/tools/demo/lib/stale.mjs ]
}

@test "an entry naming a missing plugin or a missing source fails" {
  cat > shared/shared-files.json <<'JSON'
{
  "entries": [
    { "source": "references/shared-guide.md", "plugins": ["gamma"] },
    { "source": "references/absent.md", "plugins": ["alpha"] }
  ]
}
JSON
  sync_files --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"references/shared-guide.md: plugin gamma does not exist"* ]]
  [[ "$output" == *"shared/references/absent.md: source does not exist"* ]]
}

@test "an unknown argument fails with a usage hint" {
  sync_files --force
  [ "$status" -eq 1 ]
  [[ "$output" == *"invalid argument '--force'"* ]]
}
