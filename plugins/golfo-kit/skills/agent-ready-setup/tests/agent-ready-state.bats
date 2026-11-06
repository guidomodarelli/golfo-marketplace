#!/usr/bin/env bats
# Profiles, manifest, lockfile and ownership contract of agent-ready-setup.

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  cli_calls="$test_root/cli-calls.log"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  export AGENT_READY_SETUP_BROWSER_INSTALL=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_REVIEW_MODE
  # Fake provider CLIs record every call, so tests can prove read-only modes stay offline.
  for provider_cli in claude codex; do
    cat > "$fake_bin/$provider_cli" <<EOF
#!/bin/bash
printf '%s %s\n' "$provider_cli" "\$*" >> "$cli_calls"
exit 0
EOF
    chmod +x "$fake_bin/$provider_cli"
  done
  git -C "$project_dir" -c init.defaultBranch=main init -q
  cd "$project_dir"
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

# Copy of the skill whose templates a test may change, like a newer release.
copy_skill() {
  source_copy="$test_root/skill"
  cp -R "$skill_dir" "$source_copy"
}

run_bootstrap_with() {
  local source="$1"
  shift
  run env PATH="$fake_bin:$PATH" bash "$source/scripts/bootstrap.sh" --skill-dir "$source" --provider claude "$@"
}

# Content fingerprint of the project tree, including symlink targets.
tree_fingerprint() {
  find . -path ./.git -prune -o -print | LC_ALL=C sort | while IFS= read -r path; do
    if [[ -L "$path" ]]; then
      printf 'L %s %s\n' "$path" "$(readlink "$path")"
    elif [[ -f "$path" ]]; then
      printf 'F %s %s\n' "$path" "$(cksum < "$path")"
    else
      printf 'D %s\n' "$path"
    fi
  done
}

lock_value() {
  python3 -c 'import json,sys; lock=json.load(open(".agents/agent-ready.lock.json")); print(eval(sys.argv[1], {"lock": lock}))' "$1"
}

@test "first apply writes a pinned manifest and a lockfile that inventories every managed file" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  [[ "$output" == *"Profiles: node,browser"* ]]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]

  [ "$(python3 -c 'import json; m=json.load(open(".agents/agent-ready.json")); print(m["updates"], ",".join(m["profiles"]))')" = "pinned node,browser" ]
  [ "$(lock_value 'lock["source"]["plugin"]')" = "golfo-kit" ]
  [ "$(lock_value 'lock["profileOrder"]')" = "['node', 'browser']" ]

  # Every regular file the projection wrote under .agents (except state files) is owned by the lock.
  find .agents -type f ! -name 'agent-ready.json' ! -name 'agent-ready.lock.json' | LC_ALL=C sort > "$test_root/projected"
  lock_value '"\n".join(sorted(path for path in lock["assets"] if path.startswith(".agents/")))' > "$test_root/locked"
  diff -u "$test_root/projected" "$test_root/locked"
  [ "$(lock_value 'lock["assets"][".github/pull_request_template.md"]["state"]')" = "applied" ]
}

@test "reapplying the same resolution changes nothing, including the lockfile bytes" {
  run_bootstrap_with "$skill_dir" --stack go
  [ "$status" -eq 0 ]
  cp .agents/agent-ready.lock.json "$test_root/first-lock.json"
  before="$(tree_fingerprint)"

  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  cmp -s .agents/agent-ready.lock.json "$test_root/first-lock.json"
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "plan and status are read-only and never call the provider CLI" {
  run_bootstrap_with "$skill_dir" --stack frontend
  [ "$status" -eq 0 ]
  printf '%s\n' 'local note' >> .agents/rules/testing.md
  rm -f "$cli_calls"
  before="$(tree_fingerprint)"

  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Agent Ready plan (read-only: nothing was written)"* ]]
  [[ "$output" == *"conflict"*".agents/rules/testing.md"*"local changes since the last apply"* ]]
  [[ "$output" == *"+local note"* ]] || [[ "$output" == *"-local note"* ]]

  run_bootstrap_with "$skill_dir" --status
  [ "$status" -eq 0 ]
  [[ "$output" == *"modified: .agents/rules/testing.md"* ]]

  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$cli_calls" ]
}

@test "a locally modified managed asset is preserved as a conflict until --force" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' 'team specific line' >> .agents/rules/security.md

  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *".agents/rules/security.md: local changes since the last apply; preserved"* ]]
  [[ "$output" == *"applied with 1 preserved conflict(s)"* ]]
  [ "$(tail -n 1 .agents/rules/security.md)" = "team specific line" ]
  [ "$(lock_value 'lock["assets"][".agents/rules/security.md"]["state"]')" = "conflict" ]

  run_bootstrap_with "$skill_dir" --force
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/security.md "$skill_dir/assets/stacks/node/rules/security.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/security.md"]["state"]')" = "applied" ]
}

@test "a new release updates untouched assets and keeps edited ones" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack java
  [ "$status" -eq 0 ]
  printf '%s\n' 'edited locally' >> .agents/rules/coding-style.md
  printf '%s\n' '- New upstream guidance.' >> "$source_copy/assets/stacks/java/rules/testing.md"
  printf '%s\n' '- New upstream guidance.' >> "$source_copy/assets/stacks/java/rules/coding-style.md"

  run_bootstrap_with "$source_copy" --status
  [[ "$output" == *"Update available"* ]]

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/testing.md "$source_copy/assets/stacks/java/rules/testing.md"
  [ "$(tail -n 1 .agents/rules/coding-style.md)" = "edited locally" ]
}

@test "assets dropped from the profiles are retired only when unmodified" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ -f .agents/agents/perf-analyzer.md ]
  [ -f .agents/skills/perf-analyzer/SKILL.md ]
  printf '%s\n' 'kept on purpose' >> .agents/agents/security-scanner.md
  rm "$source_copy/assets/stacks/node/agents/perf-analyzer.md" "$source_copy/assets/stacks/node/agents/security-scanner.md"

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Retired managed assets:"* ]]
  [ ! -e .agents/agents/perf-analyzer.md ]
  [ ! -e .agents/skills/perf-analyzer ]
  [ ! -e .claude/agents/perf-analyzer.md ]
  [ -f .agents/agents/security-scanner.md ]
  [[ "$output" == *".agents/agents/security-scanner.md: retired from the profiles but modified locally"* ]]
  [ "$(lock_value 'lock["assets"][".agents/agents/security-scanner.md"]["state"]')" = "retired-modified" ]
  [ "$(lock_value '".agents/agents/perf-analyzer.md" in lock["assets"]')" = "False" ]
}

@test "without a lockfile the first apply adopts existing managed files once" {
  mkdir -p .agents/rules
  printf '%s\n' 'previous template version' > .agents/rules/testing.md

  run_bootstrap_with "$skill_dir" --stack go
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/testing.md "$skill_dir/assets/stacks/go/rules/testing.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/testing.md"]["state"]')" = "applied" ]
}

@test "profiles that publish the same destination fail before writing anything" {
  run_bootstrap_with "$skill_dir" --profiles frontend,node
  [ "$status" -ne 0 ]
  [[ "$output" == *"profiles 'frontend' and 'node' both"* ]]
  [ ! -e .agents ]
  [ ! -e .claude ]
}

@test "unknown profiles and profile sets without a stack are rejected with the catalog" {
  run_bootstrap_with "$skill_dir" --profiles android
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown profile 'android'; available profiles: browser, frontend, go, java, node"* ]]

  run_bootstrap_with "$skill_dir" --profiles browser
  [ "$status" -ne 0 ]
  [[ "$output" == *"select at least one stack profile"* ]]
}

@test "composable profiles add their assets on top of a stack without duplicating it" {
  copy_skill
  mkdir -p "$source_copy/assets/profiles/node-testing/rules"
  printf '%s\n' '# Node testing extras' > "$source_copy/assets/profiles/node-testing/rules/node-testing-extras.md"
  python3 - "$source_copy/assets/profiles.json" <<'EOF'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path))
catalog["profiles"]["node-testing"] = {"kind": "capability", "description": "Extra testing rules.", "requires": ["node"], "assets": "assets/profiles/node-testing"}
json.dump(catalog, open(path, "w"), indent=2)
EOF

  run_bootstrap_with "$source_copy" --profiles node-testing
  [ "$status" -eq 0 ]
  [[ "$output" == *"Profiles: node,node-testing"* ]]
  cmp -s .agents/rules/node-testing-extras.md "$source_copy/assets/profiles/node-testing/rules/node-testing-extras.md"
  cmp -s .agents/rules/security.md "$source_copy/assets/stacks/node/rules/security.md"
  grep -Fq 'node-testing-extras.md' AGENTS.md
  [ "$(lock_value 'lock["assets"][".agents/rules/node-testing-extras.md"]["profile"]')" = "node-testing" ]
}

@test "SessionStart in a pinned repository reports updates without writing" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/testing.md"
  before="$(tree_fingerprint)"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_copy" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *"Repository pinned"* ]]
  [[ "$output" == *"Update available"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "SessionStart with automatic updates applies the ownership gate" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node --updates auto
  [ "$status" -eq 0 ]
  printf '%s\n' 'edited locally' >> .agents/rules/security.md
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/testing.md"
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/security.md"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_copy" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider codex
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/testing.md "$source_copy/assets/stacks/node/rules/testing.md"
  [ "$(tail -n 1 .agents/rules/security.md)" = "edited locally" ]
  [[ "$output" == *".agents/rules/security.md: local changes since the last apply; preserved"* ]]
}

@test "review mode never synchronizes, even with automatic updates" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node --updates auto
  [ "$status" -eq 0 ]
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/testing.md"
  before="$(tree_fingerprint)"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_copy" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    AGENT_READY_SETUP_REVIEW_MODE=1 bash .agents/hooks/sync-marketplace.sh --provider codex
  [ "$status" -eq 0 ]
  [[ "$output" == *"Review mode"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "status --check exits with the drift status when the checkout differs from the lock" {
  run_bootstrap_with "$skill_dir" --stack go
  [ "$status" -eq 0 ]
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 0 ]

  rm .agents/rules/security.md
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"missing: .agents/rules/security.md"* ]]
}

@test "profiles without browser never install browser tools" {
  mkdir -p "$test_root/home"
  run env HOME="$test_root/home" PATH="$fake_bin:$PATH" AGENT_READY_SETUP_BROWSER_INSTALL=1 \
    AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 bash "$skill_dir/scripts/bootstrap.sh" \
    --skill-dir "$skill_dir" --provider claude --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" == *"Browser installation skipped: no selected profile needs browser tools"* ]]
  [ ! -e "$test_root/home/.local/share/agent-ready-setup" ]
  [ ! -e .mcp.json ]
  [ ! -e .codex/config.toml ]
}

@test "harness consistency check uses codex exec for Codex edits without a Claude binary" {
  mkdir -p .agents/rules codex-only-bin
  cp "$fake_bin/codex" codex-only-bin/codex
  for tool in bash python3 git cat dirname; do
    ln -s "$(command -v "$tool")" "codex-only-bin/$tool"
  done
  payload='{"tool_name":"apply_patch","tool_input":{"command":"*** Update File: .agents/rules/example.md"}}'

  run env PATH="$PWD/codex-only-bin" bash "$skill_dir/assets/common/hooks/check-harness-consistency.sh" <<< "$payload"
  [ "$status" -eq 0 ]
  grep -Fq 'codex exec --sandbox read-only --skip-git-repo-check' "$cli_calls"
  ! grep -q '^claude ' "$cli_calls"

  rm codex-only-bin/codex
  run env PATH="$PWD/codex-only-bin" bash "$skill_dir/assets/common/hooks/check-harness-consistency.sh" <<< "$payload"
  [ "$status" -eq 0 ]
  [[ "$output" == *"codex CLI is not available; consistency check skipped."* ]]
}
