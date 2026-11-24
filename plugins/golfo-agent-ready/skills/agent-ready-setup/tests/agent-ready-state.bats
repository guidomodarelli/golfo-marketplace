#!/usr/bin/env bats
# Profiles, manifest, lockfile and ownership contract of agent-ready-setup.

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-agent-ready/skills/agent-ready-setup"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  cli_calls="$test_root/cli-calls.log"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  source "$BATS_TEST_DIRNAME/content-pack.bash"
  use_content_pack
  export AGENT_READY_SETUP_TOOLS=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  # The detached update has its own suite; these tests read the sync's output directly.
  export AGENT_READY_SETUP_SYNC_FOREGROUND=1
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
  # Windows cannot delete files that a detached background review still has open;
  # retry for a few seconds so it can finish before failing the test.
  local removal_attempt
  for removal_attempt in $(seq 1 50); do
    rm -rf "$test_root" 2>/dev/null && return 0
    sleep 0.2
  done
  rm -rf "$test_root"
}

# Copy of the skill whose templates a test may change, like a newer release.
copy_skill() {
  source_copy="$test_root/skill"
  cp -R "$skill_dir" "$source_copy"
  copy_content_pack
}

run_bootstrap_with() {
  local source="$1"
  shift
  # A new manifest is pinned here unless the test says otherwise; auto has its own suite.
  local updates=()
  [[ -f .agents/agent-ready.json ]] || updates=(--updates pinned)
  run env PATH="$fake_bin:$PATH" bash "$source/scripts/bootstrap.sh" --skill-dir "$source" --provider claude \
    ${updates[@]+"${updates[@]}"} "$@"
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

# Clone of the applied project whose checkout has CRLF endings, like Git for Windows by default.
clone_with_crlf_checkout() {
  git add -A >/dev/null 2>&1
  git -c user.name=Test -c user.email=test@example.invalid commit -qm applied
  git clone -q -c core.autocrlf=true . "$test_root/crlf-clone"
  cd "$test_root/crlf-clone"
}

lock_value() {
  python3 -c 'import json,sys; lock=json.load(open(".agents/agent-ready.lock.json")); print(eval(sys.argv[1], {"lock": lock}))' "$1" | tr -d '\r'
}

@test "first apply writes a pinned manifest and a lockfile that inventories every managed file" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  [[ "$output" == *"Profiles: software-development,node,browser"* ]]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]

  [ "$(python3 -c 'import json; m=json.load(open(".agents/agent-ready.json")); print(m["updates"]["mode"], ",".join(m["profiles"]))')" = "pinned node" ]
  [ "$(lock_value 'lock["source"]["name"]')" = "golfo" ]
  [ "$(lock_value 'lock["profileOrder"]')" = "['software-development', 'node', 'browser']" ]

  # Every regular file the projection wrote under .agents (except state files) is owned by the lock.
  find .agents -type f ! -name 'agent-ready.json' ! -name 'agent-ready.lock.json' | LC_ALL=C sort > "$test_root/projected"
  lock_value '"\n".join(sorted(path for path in lock["assets"] if path.startswith(".agents/")))' > "$test_root/locked"
  diff -u "$test_root/projected" "$test_root/locked"
  [ "$(lock_value 'lock["blocks"][".github/pull_request_template.md"]["software-development"]["state"]')" = "applied" ]
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

@test "right after an apply the plan has nothing pending, merged files included" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]

  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"AGENTS.md: managed block is current"* ]]
  [[ "$output" == *".claude/settings.json: managed entries are current"* ]]
  [[ "$output" == *".codex/hooks.json: managed entries are current"* ]]
  [[ "$output" == *"Summary: no changes"* ]]
}

@test "the plan prints non-ASCII diffs whatever encoding the terminal uses" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' 'nota local → con acentos' >> .agents/rules/node-testing.md

  export PYTHONIOENCODING=ascii
  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"nota local → con acentos"* ]]

  run_bootstrap_with "$skill_dir" --status
  [ "$status" -eq 0 ]
  [[ "$output" == *"modified: .agents/rules/node-testing.md"* ]]
}

@test "a CRLF checkout is not a local edit: nothing conflicts and nothing is rewritten" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  clone_with_crlf_checkout
  # Git Bash grep drops carriage returns before matching, so count the bytes instead.
  [ "$(tr -cd '\r' < .agents/rules/node-testing.md | wc -c)" -gt 0 ]

  run python3 "$source_copy/scripts/agent-ready-state.py" status --project . --skill-dir "$source_copy" --check
  [ "$status" -eq 0 ]
  [[ "$output" == *" 0 modified,"* ]]

  run_bootstrap_with "$source_copy" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"AGENTS.md: managed block is current"* ]]
  [[ "$output" == *"Summary: no changes"* ]]

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
  # The hard-link manifest is pruned from fresh clones with or without this contract.
  [ -z "$(git status --short | grep -v '\.agent-ready-hard-link-views')" ]
}

@test "a CRLF checkout receives updates and its real edits are overwritten" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  clone_with_crlf_checkout
  printf '%s\r\n' 'team specific line' >> .agents/rules/node-security.md
  printf '%s\n' '- Newer guidance.' >> "$content_dir/stacks/node/rules/node-testing.md"
  printf '%s\n' '- Newer guidance.' >> "$content_dir/stacks/node/rules/node-security.md"

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
  cmp -s .agents/rules/node-testing.md "$content_dir/stacks/node/rules/node-testing.md"
  cmp -s .agents/rules/node-security.md "$content_dir/stacks/node/rules/node-security.md"
}

@test "a manifest that cannot be read stops the sync before writing" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' '{"name": "project"}' > package.json
  printf '%s\n' '{"profiles": "node", "updates": {"mode": "pinned"}}' > .agents/agent-ready.json
  printf '%s\n' 'edited locally' >> .agents/rules/node-security.md
  rm .agents/rules/node-testing.md
  before="$(tree_fingerprint)"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *"project layer"*"'profiles' must be a list"* ]]
  [[ "$output" == *"nothing was synchronized"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -ne 0 ]
  [[ "$output" == *"project layer"*"'profiles' must be a list"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "bootstrap and the hook work when the caller disables MSYS path conversion" {
  export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
  run_bootstrap_with "$skill_dir" --stack node --updates auto
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
}

@test "assets under a symlinked parent directory are never retired" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  mv .agents/agents "$test_root/outside-agents"
  ln -s "$test_root/outside-agents" .agents/agents 2>/dev/null || true
  [ -L .agents/agents ] || skip "requiere symlinks reales (en Windows: Modo de desarrollador o una shell elevada)"
  rm "$content_dir/stacks/node/agents/node-perf-analyzer.md"

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [ -f "$test_root/outside-agents/node-perf-analyzer.md" ]
  [[ "$output" == *".agents/agents/node-perf-analyzer.md: a parent directory is a symlink"* ]]
  [ "$(lock_value 'lock["assets"][".agents/agents/node-perf-analyzer.md"]["state"]')" = "retired-preserved" ]
}

@test "a release that only changes instruction templates counts as an update" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  run_bootstrap_with "$source_copy" --status
  [[ "$output" == *"Source matches the lock"* ]]

  printf '%s\n' '- Newer centralization rule.' >> "$source_copy/assets/instruction-centralization.md"
  run_bootstrap_with "$source_copy" --status
  [ "$status" -eq 0 ]
  [[ "$output" == *"Update available"* ]]
}

@test "status --check fails when the selected profiles cannot be resolved" {
  run_bootstrap_with "$skill_dir" --stack go
  [ "$status" -eq 0 ]
  printf '%s\n' '{"profiles": ["nonexistent"], "updates": {"mode": "pinned"}}' > .agents/agent-ready.json

  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"unknown profile 'nonexistent'"* ]]
}

@test "an explicit --stack wins over the profiles chosen in the environment" {
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
  cp "$skill_dir/assets/common/hooks/agent-ready-skill-source.sh" .agents/hooks/

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    AGENT_READY_SETUP_PROFILES=node bash .agents/hooks/sync-marketplace.sh --provider claude --stack go
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["primaryStack"]')" = "go" ]
}

@test "an edited Claude view of a managed asset is reported and then relinked" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  rm .claude/rules/node-security.md
  printf '%s\n' 'local policy' > .claude/rules/node-security.md

  run_bootstrap_with "$skill_dir" --status
  [[ "$output" == *"modified: .claude/rules/node-security.md"* ]]
  run_bootstrap_with "$skill_dir" --plan
  [[ "$output" == *"update"*".claude/rules/node-security.md"*"relinking the view overwrites them"* ]]
  [ "$(cat .claude/rules/node-security.md)" = "local policy" ]

  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
  [ -L .claude/rules/node-security.md ] || [ .claude/rules/node-security.md -ef .agents/rules/node-security.md ]
}

@test "a project file where a new asset gets its Claude view is preserved until it is removed" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' '# New upstream rule' > "$content_dir/stacks/node/rules/new-upstream.md"
  printf '%s\n' 'project view content' > .claude/rules/new-upstream.md

  run_bootstrap_with "$source_copy" --plan
  [[ "$output" == *"conflict"*".claude/rules/new-upstream.md"* ]]

  for attempt in first second; do
    run_bootstrap_with "$source_copy"
    [ "$status" -eq 0 ]
    [[ "$output" == *".claude/rules/new-upstream.md: never applied by agent-ready-setup; preserved"* ]]
    [[ "$output" == *"applied with 1 preserved conflict(s)"* ]]
    [ "$(cat .claude/rules/new-upstream.md)" = "project view content" ]
  done
  cmp -s .agents/rules/new-upstream.md "$content_dir/stacks/node/rules/new-upstream.md"

  rm .claude/rules/new-upstream.md
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
  [ -L .claude/rules/new-upstream.md ] || [ .claude/rules/new-upstream.md -ef .agents/rules/new-upstream.md ]
}

@test "a Claude view detached with the applied content is relinked without a conflict" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  rm .claude/rules/node-security.md
  cp .agents/rules/node-security.md .claude/rules/node-security.md

  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
  [ -L .claude/rules/node-security.md ] || [ .claude/rules/node-security.md -ef .agents/rules/node-security.md ]
}

@test "status --check notices a profile added to the manifest without assets of its own" {
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["node"], "excludedDefaults": ["browser"], "updates": {"mode": "pinned"}}' > .agents/agent-ready.json
  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  # browser, a default of node without assets, comes back once the repository stops leaving it out.
  printf '%s\n' '{"profiles": ["node"], "updates": {"mode": "pinned"}}' > .agents/agent-ready.json

  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"Update available"* ]]
}

@test "status --check notices a merged file that was deleted" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  rm .codex/hooks.json

  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"missing: .codex/hooks.json"* ]]
}

@test "status --check notices a Claude view that was deleted" {
  run_bootstrap_with "$skill_dir" --stack react
  [ "$status" -eq 0 ]
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 0 ]

  rm .claude/rules/react-security.md
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"missing: .claude/rules/react-security.md"* ]]
}


@test "plan and status are read-only and never call the provider CLI" {
  run_bootstrap_with "$skill_dir" --stack react
  [ "$status" -eq 0 ]
  printf '%s\n' 'local note' >> .agents/rules/react-testing.md
  rm -f "$cli_calls"
  before="$(tree_fingerprint)"

  run_bootstrap_with "$skill_dir" --plan --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"Agent Ready plan (read-only: nothing was written)"* ]]
  [[ "$output" == *"update"*".agents/rules/react-testing.md"*"overwrites local changes since the last apply"* ]]
  [[ "$output" == *"+local note"* ]] || [[ "$output" == *"-local note"* ]]

  run_bootstrap_with "$skill_dir" --status --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"modified: .agents/rules/react-testing.md"* ]]

  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$cli_calls" ]
}

@test "a locally modified managed asset is overwritten by the next apply, and plan warns first" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' 'team specific line' >> .agents/rules/node-security.md

  run_bootstrap_with "$skill_dir" --plan
  [[ "$output" == *".agents/rules/node-security.md"*"overwrites local changes since the last apply"* ]]
  [[ "$output" == *"team specific line"* ]]
  [ "$(tail -n 1 .agents/rules/node-security.md)" = "team specific line" ]

  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
  cmp -s .agents/rules/node-security.md "$content_pack/stacks/node/rules/node-security.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/node-security.md"]["state"]')" = "applied" ]
}

@test "a project file in a Claude view stays preserved after its asset could not be written" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s
' '# New upstream rule' > "$content_dir/stacks/node/rules/new-upstream.md"
  printf '%s
' 'project view content' > .claude/rules/new-upstream.md
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]

  rm .agents/rules/new-upstream.md
  mkdir .agents/rules/new-upstream.md
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  rmdir .agents/rules/new-upstream.md

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [ "$(cat .claude/rules/new-upstream.md)" = "project view content" ]
  [[ "$output" == *".claude/rules/new-upstream.md: never applied by agent-ready-setup; preserved"* ]]
}

@test "a project file that a release starts publishing is preserved until it is renamed" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' '# New upstream rule' > "$content_dir/stacks/node/rules/new-upstream.md"
  printf '%s\n' 'project rule' > .agents/rules/new-upstream.md

  for attempt in first second; do
    run_bootstrap_with "$source_copy"
    [ "$status" -eq 0 ]
    [[ "$output" == *".agents/rules/new-upstream.md: never applied by agent-ready-setup; preserved"* ]]
    [[ "$output" == *"applied with 1 preserved conflict(s)"* ]]
    [ "$(cat .agents/rules/new-upstream.md)" = "project rule" ]
    [ "$(lock_value 'lock["assets"][".agents/rules/new-upstream.md"]["state"]')" = "conflict" ]
  done

  mv .agents/rules/new-upstream.md .agents/rules/project-rule.md
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/new-upstream.md "$content_dir/stacks/node/rules/new-upstream.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/new-upstream.md"]["state"]')" = "applied" ]
  [ "$(cat .agents/rules/project-rule.md)" = "project rule" ]
}

@test "a preserved project file stays in place when no profile publishes that path anymore" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' '# New upstream rule' > "$content_dir/stacks/node/rules/new-upstream.md"
  printf '%s\n' 'project rule' > .agents/rules/new-upstream.md
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  rm "$content_dir/stacks/node/rules/new-upstream.md"

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
  [ "$(cat .agents/rules/new-upstream.md)" = "project rule" ]
  [ "$(lock_value '".agents/rules/new-upstream.md" in lock["assets"]')" = "False" ]
}

@test "a write that failed before having an applied base is retried by the next apply" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' 'stale content' > .agents/rules/node-security.md
  python3 - <<'EOF'
import json

path = ".agents/agent-ready.lock.json"
with open(path, encoding="utf-8") as lock_file:
    lock = json.load(lock_file)
lock["assets"][".agents/rules/node-security.md"].update(sha256=None, state="failed")
with open(path, "w", encoding="utf-8") as lock_file:
    json.dump(lock, lock_file)
EOF

  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/node-security.md "$content_pack/stacks/node/rules/node-security.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/node-security.md"]["state"]')" = "applied" ]
}

@test "a new release updates every managed asset, edited ones included" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack java
  [ "$status" -eq 0 ]
  printf '%s\n' 'edited locally' >> .agents/rules/java-coding-style.md
  printf '%s\n' '- New upstream guidance.' >> "$content_dir/stacks/java/rules/java-testing.md"
  printf '%s\n' '- New upstream guidance.' >> "$content_dir/stacks/java/rules/java-coding-style.md"

  run_bootstrap_with "$source_copy" --status
  [[ "$output" == *"Update available"* ]]

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/java-testing.md "$content_dir/stacks/java/rules/java-testing.md"
  cmp -s .agents/rules/java-coding-style.md "$content_dir/stacks/java/rules/java-coding-style.md"
}

@test "assets dropped from the profiles are retired, edited ones included" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ -f .agents/agents/node-perf-analyzer.md ]
  [ -f .codex/agents/node-perf-analyzer.toml ]
  printf '%s\n' 'edited locally' >> .agents/agents/node-security-scanner.md
  rm "$content_dir/stacks/node/agents/node-perf-analyzer.md" "$content_dir/stacks/node/agents/node-security-scanner.md"

  run_bootstrap_with "$source_copy" --plan
  [[ "$output" == *".agents/agents/node-security-scanner.md"*"removes its local changes"* ]]

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Retired managed assets:"* ]]
  [ ! -e .agents/agents/node-perf-analyzer.md ]
  [ ! -e .codex/agents/node-perf-analyzer.toml ]
  [ ! -e .claude/agents/node-perf-analyzer.md ]
  [ ! -e .agents/agents/node-security-scanner.md ]
  [ ! -e .claude/agents/node-security-scanner.md ]
  [ "$(lock_value '".agents/agents/node-perf-analyzer.md" in lock["assets"]')" = "False" ]
  [ "$(lock_value '".agents/agents/node-security-scanner.md" in lock["assets"]')" = "False" ]
  [ "$(lock_value '".codex/agents/node-perf-analyzer.toml" in lock["assets"]')" = "False" ]
  [ "$(lock_value '".codex/agents/node-security-scanner.toml" in lock["assets"]')" = "False" ]
}

# The TOML checks read the file with tomllib, which Python has from 3.11.
require_tomllib() {
  python3 -c 'import tomllib' 2>/dev/null || skip "reading TOML needs Python 3.11+"
}

# One key of the TOML of a native Codex subagent, as Python's TOML parser reads it.
codex_agent_value() {
  python3 -c 'import sys, tomllib; sys.stdout.write(tomllib.load(open(sys.argv[1], "rb"))[sys.argv[2]])' "$1" "$2"
}

# The body of a Markdown subagent: what follows its frontmatter, without the blank lines around it.
subagent_body() {
  python3 -c 'import sys; text = open(sys.argv[1], encoding="utf-8").read().replace("\r\n", "\n"); sys.stdout.write(text.split("\n---\n", 1)[1].strip("\n") + "\n")' "$1"
}

@test "each subagent becomes a native Codex subagent with valid TOML, and no skill adapter" {
  require_tomllib
  run_bootstrap_with "$skill_dir" --stack react
  [ "$status" -eq 0 ]
  for agent in a11y-reviewer lint-reviewer react-perf-analyzer react-security-scanner test-reviewer; do
    [ "$(codex_agent_value ".codex/agents/$agent.toml" name)" = "$agent" ]
    [ -n "$(codex_agent_value ".codex/agents/$agent.toml" description)" ]
    [ "$(codex_agent_value ".codex/agents/$agent.toml" developer_instructions)" = "$(subagent_body ".agents/agents/$agent.md")" ]
    [ ! -e ".agents/skills/$agent" ]
    [ "$(lock_value "lock['assets']['.codex/agents/$agent.toml']['state']")" = "applied" ]
  done
  # A command still reaches Codex as a skill of the same name.
  [ -f .agents/skills/react-review-pr/SKILL.md ]

  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Codex sees "*" 6 skills and 5 subagents"* ]]
  [[ "$output" == *"Summary: no changes"* ]]
}

@test "the TOML of a subagent keeps quotes, backslashes and triple quotes of its text exactly" {
  require_tomllib
  copy_skill
  cat > "$content_dir/stacks/node/agents/tricky-reviewer.md" <<'EOF'
---
name: tricky-reviewer
description: "Revisa \"comillas\" y C:\\rutas: todo"
---

# Tricky
Una ruta C:\temp\nuevo y tres comillas """ en el medio.
Termina con comilla "
EOF

  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ "$(codex_agent_value .codex/agents/tricky-reviewer.toml description)" = 'Revisa "comillas" y C:\rutas: todo' ]
  [ "$(codex_agent_value .codex/agents/tricky-reviewer.toml developer_instructions)" = "$(subagent_body .agents/agents/tricky-reviewer.md)" ]
}

@test "a trailing YAML comment in the frontmatter is not part of the name or the description" {
  require_tomllib
  copy_skill
  cat > "$content_dir/stacks/node/agents/commented-reviewer.md" <<'EOF'
---
name: commented-reviewer # must match the file name
description: 'Revisa lo que haga falta' # quoted, then a comment
---
Body.
EOF

  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ "$(codex_agent_value .codex/agents/commented-reviewer.toml name)" = "commented-reviewer" ]
  [ "$(codex_agent_value .codex/agents/commented-reviewer.toml description)" = "Revisa lo que haga falta" ]
}

@test "a subagent whose name is not its file name stops the apply before writing" {
  copy_skill
  printf '%s\n' '---' 'name: other-name' 'description: Revisa.' '---' 'Body.' > "$content_dir/stacks/node/agents/misnamed.md"

  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -ne 0 ]
  [[ "$output" == *"agents/misnamed.md: the subagent is named 'other-name'; it must be 'misnamed'"* ]]
  [ ! -e .codex/agents ]
}

@test "a hand edit of a managed Codex subagent shows in the plan and the apply restores it" {
  run_bootstrap_with "$skill_dir" --stack react
  [ "$status" -eq 0 ]
  cp .codex/agents/test-reviewer.toml "$test_root/applied.toml"
  printf '%s\n' '# edited by hand' >> .codex/agents/test-reviewer.toml

  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *".codex/agents/test-reviewer.toml"*"overwrites local changes since the last apply"* ]]
  [[ "$output" == *"-# edited by hand"* ]]

  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  cmp -s .codex/agents/test-reviewer.toml "$test_root/applied.toml"
}

@test "a Codex subagent the project wrote is preserved as a conflict, never overwritten" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  mkdir -p .codex/agents
  printf '%s\n' 'name = "test-reviewer"' 'description = "Ours."' 'developer_instructions = "Ours."' > .codex/agents/test-reviewer.toml
  cp .codex/agents/test-reviewer.toml "$test_root/ours.toml"

  run_bootstrap_with "$skill_dir" --profiles node,react
  [[ "$output" == *".codex/agents/test-reviewer.toml"* ]]
  cmp -s .codex/agents/test-reviewer.toml "$test_root/ours.toml"
  [ "$(lock_value "lock['assets']['.codex/agents/test-reviewer.toml']['state']")" = "conflict" ]
  grep -Fxq 'name = "a11y-reviewer"' .codex/agents/a11y-reviewer.toml
}

@test "without a lockfile the first apply adopts existing managed files once" {
  mkdir -p .agents/rules
  printf '%s\n' 'previous template version' > .agents/rules/go-testing.md

  run_bootstrap_with "$skill_dir" --stack go
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/go-testing.md "$content_pack/stacks/go/rules/go-testing.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/go-testing.md"]["state"]')" = "applied" ]
}

@test "profiles that publish the same destination fail before writing anything" {
  copy_skill
  mkdir -p "$content_dir/profiles/node-security-copy/rules"
  printf '%s
' '# Another node security' > "$content_dir/profiles/node-security-copy/rules/node-security.md"
  python3 - "$content_dir/agent-ready-pack.json" <<'EOF2'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path))
catalog["profiles"]["node-security-copy"] = {"kind": "capability", "description": "Publishes the node security rule again.", "requires": ["node"], "assets": "profiles/node-security-copy"}
json.dump(catalog, open(path, "w"), indent=2)
EOF2

  run_bootstrap_with "$source_copy" --profiles node-security-copy
  [ "$status" -ne 0 ]
  [[ "$output" == *"profiles 'node' and 'node-security-copy' both write .agents/rules/node-security.md"* ]]
  [ ! -e .agents ]
  [ ! -e .claude ]
}

@test "unknown profiles are rejected with the catalog, and a selection without a stack applies" {
  run_bootstrap_with "$skill_dir" --profiles cobol
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown profile 'cobol'; available profiles: android, browser, business-flows, go, java, learning, memory-engram, nextjs, nextjs-app-router, node, react, software-development"* ]]

  run_bootstrap_with "$skill_dir" --profiles browser
  [ "$status" -eq 0 ]
  [[ "$output" == *"Stack: none"* ]]
  [ "$(lock_value 'lock["primaryStack"]')" = "None" ]
}

@test "composable profiles add their assets on top of a stack without duplicating it" {
  copy_skill
  mkdir -p "$content_dir/profiles/node-testing/rules"
  printf '%s\n' '# Node testing extras' > "$content_dir/profiles/node-testing/rules/node-testing-extras.md"
  python3 - "$content_dir/agent-ready-pack.json" <<'EOF'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path))
catalog["profiles"]["node-testing"] = {"kind": "capability", "description": "Extra testing rules.", "requires": ["node"], "assets": "profiles/node-testing"}
json.dump(catalog, open(path, "w"), indent=2)
EOF

  run_bootstrap_with "$source_copy" --profiles node-testing
  [ "$status" -eq 0 ]
  [[ "$output" == *"Profiles: software-development,node,node-testing"* ]]
  cmp -s .agents/rules/node-testing-extras.md "$content_dir/profiles/node-testing/rules/node-testing-extras.md"
  cmp -s .agents/rules/node-security.md "$content_dir/stacks/node/rules/node-security.md"
  grep -Fq 'node-testing-extras.md' AGENTS.md
  [ "$(lock_value 'lock["assets"][".agents/rules/node-testing-extras.md"]["profile"]')" = "node-testing" ]

  run_bootstrap_with "$source_copy" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"AGENTS.md: managed block is current"* ]]
}

@test "two stacks compose in one repository: each brings its own assets and the first one is the primary" {
  run_bootstrap_with "$skill_dir" --profiles react,node
  [ "$status" -eq 0 ]
  [[ "$output" == *"Profiles: software-development,react,node"* ]]
  for stack in react node; do
    cmp -s ".agents/rules/$stack-security.md" "$content_pack/stacks/$stack/rules/$stack-security.md"
    cmp -s ".agents/rules/$stack-testing.md" "$content_pack/stacks/$stack/rules/$stack-testing.md"
    cmp -s ".agents/agents/$stack-perf-analyzer.md" "$content_pack/stacks/$stack/agents/$stack-perf-analyzer.md"
    cmp -s ".agents/commands/$stack-review-pr.md" "$content_pack/stacks/$stack/commands/$stack-review-pr.md"
    grep -Fq ".agents/rules/$stack-security.md" AGENTS.md
    [ "$(lock_value "lock['assets']['.agents/rules/$stack-security.md']['profile']")" = "$stack" ]
  done
  cmp -s .agents/rules/node-coding-style.md "$content_pack/stacks/node/rules/node-coding-style.md"
  cmp -s .agents/rules/react-style.md "$content_pack/stacks/react/rules/react-style.md"
  # One base template, and a section of each stack in the order of its id.
  [ "$(grep -Fxc '# [Project Name]' AGENTS.md)" -eq 1 ]
  [ "$(grep -E '^<!-- BEGIN AGENT-READY MANAGED: [a-z]+ -->$' AGENTS.md | tr '\n' ' ')" = \
    "<!-- BEGIN AGENT-READY MANAGED: react --> <!-- BEGIN AGENT-READY MANAGED: node --> " ]

  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"AGENTS.md: managed block is current"* ]]
}

@test "an apply after the stack assets were renamed retires the files with the old names" {
  copy_skill
  mv "$content_dir/stacks/node/rules/node-security.md" "$content_dir/stacks/node/rules/security.md"
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ -f .agents/rules/security.md ]

  # The released content again: the shared content pack, not the renamed copy.
  export AGENT_READY_SETUP_CONTENT_DIR="$content_pack"
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/security.md ]
  [ ! -e .claude/rules/security.md ]
  ! grep -Fq '.agents/rules/security.md' AGENTS.md
  cmp -s .agents/rules/node-security.md "$content_pack/stacks/node/rules/node-security.md"
  [ "$(lock_value "'.agents/rules/security.md' in lock['assets']")" = "False" ]
}

@test "SessionStart in a pinned repository reports updates without writing" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' '- Newer guidance.' >> "$content_dir/stacks/node/rules/node-testing.md"
  before="$(tree_fingerprint)"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_copy" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *"Repository pinned"* ]]
  [[ "$output" == *"Update available"* ]]
  # Teammates who only receive the committed hook may not have the skill to run.
  [[ "$output" != *"/agent-ready-setup plan"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "SessionStart with automatic updates overwrites managed assets and keeps a backup" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node --updates auto
  [ "$status" -eq 0 ]
  printf '%s\n' 'edited locally' >> .agents/rules/node-security.md
  printf '%s\n' '- Newer guidance.' >> "$content_dir/stacks/node/rules/node-testing.md"
  printf '%s\n' '- Newer guidance.' >> "$content_dir/stacks/node/rules/node-security.md"
  printf '%s\n' '# Newer hook release.' >> "$source_copy/assets/common/hooks/sync-marketplace.sh"
  rm .claude/rules/node-testing.md
  printf '%s\n' 'local view policy' > .claude/rules/node-testing.md

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_copy" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider codex
  [ "$status" -eq 0 ]
  [[ "$output" == *"Sync hook updated; restarting with latest version."* ]]
  [ -L .claude/rules/node-testing.md ] || [ .claude/rules/node-testing.md -ef .agents/rules/node-testing.md ]
  cmp -s .agents/rules/node-testing.md "$content_dir/stacks/node/rules/node-testing.md"
  cmp -s .agents/rules/node-security.md "$content_dir/stacks/node/rules/node-security.md"
  [[ "$output" == *"Local backups directory:"* ]]
  backup_directory="$(sed -n 's/^Local backups directory: //p' <<< "$output")"
  grep -rq 'edited locally' "$backup_directory"
  grep -rq 'local view policy' "$backup_directory"
  [ -z "$(find "$TMPDIR" -name 'agent-ready-plan*' -print -quit)" ]
}

@test "settings saved during the merge are preserved, by bootstrap and by the hook" {
  run_bootstrap_with "$skill_dir" --stack node --updates auto
  [ "$status" -eq 0 ]
  # Saves a project setting right when the merger ends, before its output is written.
  mkdir -p "$test_root/edit-during-merge"
  cat > "$test_root/edit-during-merge/sitecustomize.py" <<'EOF'
import atexit
import json
import sys


def save_concurrent_setting():
    with open(".claude/settings.json", encoding="utf-8") as settings_file:
        settings = json.load(settings_file)
    settings["concurrentSetting"] = True
    with open(".claude/settings.json", "w", encoding="utf-8") as settings_file:
        json.dump(settings, settings_file)


if sys.argv[0].endswith("merge-managed-settings.py"):
    atexit.register(save_concurrent_setting)
EOF
  export PYTHONPATH="$test_root/edit-during-merge"

  run_bootstrap_with "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *".claude/settings.json changed during synchronization"* ]]
  grep -q 'concurrentSetting' .claude/settings.json

  sed 's/, "concurrentSetting": true//' .claude/settings.json > .claude/settings.json.clean
  mv .claude/settings.json.clean .claude/settings.json
  run grep -c 'concurrentSetting' .claude/settings.json
  [ "$output" = 0 ]
  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *".claude/settings.json changed during synchronization"* ]]
  grep -q 'concurrentSetting' .claude/settings.json
}

@test "review mode never synchronizes, even with automatic updates" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node --updates auto
  [ "$status" -eq 0 ]
  printf '%s\n' '- Newer guidance.' >> "$content_dir/stacks/node/rules/node-testing.md"
  before="$(tree_fingerprint)"
  rm -f "$cli_calls"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_copy" AGENT_READY_SETUP_FORCE_UPGRADE=1 \
    AGENT_READY_SETUP_REVIEW_MODE=1 bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *"Review mode: the marketplace upgrade is skipped."* ]]
  [[ "$output" == *"nothing was synchronized"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$cli_calls" ]
}

@test "status --check exits with the drift status when the checkout differs from the lock" {
  run_bootstrap_with "$skill_dir" --stack go
  [ "$status" -eq 0 ]
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 0 ]

  rm .agents/rules/go-security.md
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"missing: .agents/rules/go-security.md"* ]]
}

@test "the android stack projects its own assets and does not select browser tools" {
  run_bootstrap_with "$skill_dir" --stack android
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["primaryStack"]')" = "android" ]
  [ "$(lock_value 'lock["profileOrder"]')" = "['software-development', 'android']" ]
  for asset in rules/android-coding-style.md rules/android-security.md rules/android-testing.md agents/android-perf-analyzer.md agents/android-security-scanner.md commands/android-review-pr.md; do
    cmp -s ".agents/$asset" "$content_pack/stacks/android/$asset"
    [ -L ".claude/$asset" ] || [ ".claude/$asset" -ef ".agents/$asset" ]
  done
  grep -Fq -- '- Read and follow `.agents/rules/android-coding-style.md`.' AGENTS.md
  [ ! -e .mcp.json ]
}

@test "SessionStart detects Android modules before the generic Gradle stack" {
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
  cp "$skill_dir/assets/common/hooks/agent-ready-skill-source.sh" .agents/hooks/
  printf '%s\n' 'plugins {}' > build.gradle.kts
  mkdir -p feature/login/src/main
  printf '%s\n' '<manifest />' > feature/login/src/main/AndroidManifest.xml

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["primaryStack"]')" = "android" ]
}

@test "SessionStart keeps a Gradle service without an Android manifest on the java stack" {
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
  cp "$skill_dir/assets/common/hooks/agent-ready-skill-source.sh" .agents/hooks/
  printf '%s\n' 'plugins {}' > build.gradle.kts

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["primaryStack"]')" = "java" ]
}

@test "SessionStart keeps a React Native project with an android directory on the react stack" {
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
  cp "$skill_dir/assets/common/hooks/agent-ready-skill-source.sh" .agents/hooks/
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json
  mkdir -p android/app/src/main
  printf '%s\n' '<manifest />' > android/app/src/main/AndroidManifest.xml

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["primaryStack"]')" = "react" ]
}

@test "the business-flows profile adds its assets to any stack, and applies without one" {
  run_bootstrap_with "$skill_dir" --profiles business-flows
  [ "$status" -eq 0 ]
  [ -f .agents/rules/business-flows.md ]

  for stack in android react; do
    stack_project="$test_root/$stack-flows"
    mkdir -p "$stack_project"
    git -C "$stack_project" -c init.defaultBranch=main init -q
    cd "$stack_project"

    run_bootstrap_with "$skill_dir" --profiles "$stack,business-flows"
    [ "$status" -eq 0 ]
    [ "$(lock_value 'lock["primaryStack"]')" = "$stack" ]
    cmp -s .agents/rules/business-flows.md "$content_pack/profiles/business-flows/rules/business-flows.md"
    cmp -s .agents/skills/business-flow-design/SKILL.md "$content_pack/profiles/business-flows/skills/business-flow-design/SKILL.md"
    grep -Fq -- '- Read and follow `.agents/rules/business-flows.md`.' AGENTS.md
    [ -L .claude/rules/business-flows.md ] || [ .claude/rules/business-flows.md -ef .agents/rules/business-flows.md ]
    [ "$(lock_value 'lock["assets"][".agents/rules/business-flows.md"]["profile"]')" = "business-flows" ]
  done
}

@test "profiles without browser never install browser tools" {
  mkdir -p "$test_root/home"
  run env HOME="$test_root/home" PATH="$fake_bin:$PATH" AGENT_READY_SETUP_TOOLS=1 \
    AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 bash "$skill_dir/scripts/bootstrap.sh" \
    --skill-dir "$skill_dir" --provider claude --profiles android
  [ "$status" -eq 0 ]
  [[ "$output" == *"Browser installation skipped: no selected profile needs browser tools"* ]]
  [ ! -e "$test_root/home/.local/share/agent-ready-setup" ]
  [ ! -e .mcp.json ]
  [ ! -e .codex/config.toml ]
}

# The context budget of the plan, as JSON: one field of plan --format json.
context_field() {
  local key="$1"
  shift
  python3 "$skill_dir/scripts/agent-ready-state.py" plan --project "$project_dir" --skill-dir "$skill_dir" --format json "$@" \
    | python3 -c 'import json, sys; context = json.load(sys.stdin)["context"]
for key in sys.argv[1].split("."):
    context = context[key]
print(context)' "$key" | tr -d '\r'
}

# Sets a key of the conflicts module in the manifest.
set_budget() {
  python3 - "$1" "$2" <<'PY'
import json, sys
path = ".agents/agent-ready.json"
manifest = json.load(open(path, encoding="utf-8"))
manifest.setdefault("conflicts", {}).setdefault("contextBudget", {})[sys.argv[1]] = json.loads(sys.argv[2])
json.dump(manifest, open(path, "w", encoding="utf-8"), indent=2)
PY
}

@test "the plan measures AGENTS.md as the apply writes it, and counts only rules without paths" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  [ "$(context_field agentsMd.bytes)" = "$(wc -c < AGENTS.md | tr -d ' ')" ]

  rules_before="$(context_field rulesLoadedAtStart.bytes)"
  printf -- '---\npaths:\n  - "src/**"\n---\n# Scoped\n' > .agents/rules/scoped.md
  [ "$(context_field rulesLoadedAtStart.bytes)" = "$rules_before" ]
  printf '# Always\n\nLoaded in every session.\n' > .agents/rules/always.md
  [ "$(context_field rulesLoadedAtStart.bytes)" = "$((rules_before + $(wc -c < .agents/rules/always.md)))" ]
  [ "$(context_field agentsMd.exceeded)" = "False" ]
  # AGENT_READY_SETUP_TOOLS=0: the browser servers are not registered, so they are not counted.
  [ "$(context_field mcpServers)" = "0" ]
}

@test "the rules of a profile the selection drops do not count as the project's own" {
  run_bootstrap_with "$skill_dir" --stack react
  [ "$status" -eq 0 ]
  [ -f .agents/rules/react-style.md ]

  # Switching to node retires the react rules: they are not the project's and the budget leaves them out.
  [[ "$(context_field rulesLoadedAtStart.largest --profiles node)" != *"'project'"* ]]
  [ "$(context_field rulesLoadedAtStart.bytes --profiles node)" -lt "$(context_field rulesLoadedAtStart.bytes)" ]
}

@test "the plan warns past each context threshold and names the profiles that add most" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]

  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Context at the start of a session: AGENTS.md ~"* ]]
  [[ "$output" != *"! AGENTS.md passes"* ]]
  [[ "$output" != *"! The rules without paths pass"* ]]

  set_budget bytes 1024
  set_budget rulesBytes 1024
  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"! AGENTS.md passes 1024 bytes (conflicts.contextBudget.bytes)"*"Largest: node ("* ]]
  [[ "$output" == *"! The rules without paths pass 1024 bytes (conflicts.contextBudget.rulesBytes)"*"software-development ("* ]]

  set_budget enabled false
  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" != *"Context at the start of a session"* ]]
}

@test "the budget starts from a CLAUDE.md the apply moves, and keeps each section's whole size" {
  python3 -c 'open("CLAUDE.md", "w").write("# Own instructions\n" + "x" * 40000 + "\n")'
  [ "$(context_field agentsMd.exceeded --profiles node)" = "True" ]
  rm CLAUDE.md

  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  # The node section is already in AGENTS.md: the plan still attributes all of it to node.
  [[ "$(context_field agentsMd.largest)" == *"'profile': 'node'"* ]]
  [[ "$(context_field agentsMd.largest)" != *"'bytes': 0"* ]]
}

@test "a rule the apply keeps for a conflict is measured as the local file" {
  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  template_total="$(context_field rulesLoadedAtStart.bytes --profiles react)"
  python3 -c 'open(".agents/rules/react-style.md", "w").write("# Local\n" + "y" * 50000 + "\n")'
  [ "$(context_field rulesLoadedAtStart.bytes --profiles react)" -gt "$((template_total + 30000))" ]

  # Applied with the conflict, then dropped: the file stays, now as the project's own rule.
  run_bootstrap_with "$skill_dir" --stack react
  [ "$status" -eq 0 ]
  [[ "$(context_field rulesLoadedAtStart.largest --profiles node)" == *"'profile': 'project'"* ]]
}

# The plan as text, for the selection given.
plan_text() {
  run python3 "$skill_dir/scripts/agent-ready-state.py" plan --project "$project_dir" --skill-dir "$skill_dir" "$@"
}

@test "plan reports a rule whose assumption the repository contradicts, with the file that shows it" {
  printf '{"name": "app", "dependencies": {"react": "18"}, "devDependencies": {"jest": "29"}}\n' > package.json
  : > package-lock.json
  mkdir -p .agents/rules
  printf -- '---\nassumes:\n  packageManager: pnpm\n---\n# Ours\n' > .agents/rules/ours.md
  plan_text --profiles react
  [ "$status" -eq 0 ]
  [[ "$output" == *"! .agents/rules/react-testing.md (react) assumes test runner vitest, but the repository uses jest (package.json)"* ]]
  [[ "$output" == *"! .agents/rules/ours.md (project) assumes package manager pnpm, but the repository uses npm (package-lock.json)"* ]]

  # With the tools the rules assume, nothing is reported.
  printf '{"name": "app", "dependencies": {"react": "18"}, "devDependencies": {"vitest": "2"}}\n' > package.json
  rm package-lock.json
  : > pnpm-lock.yaml
  plan_text --profiles react
  [ "$status" -eq 0 ]
  [[ "$output" != *"assumes test runner"* ]]
  [[ "$output" != *"assumes package manager"* ]]
}

@test "an assumption the catalog does not know is reported as not checked, and the check turns off" {
  mkdir -p .agents/rules
  printf -- '---\nassumes:\n  linter: biome\n---\n# Ours\n' > .agents/rules/ours.md
  printf 'root = true\n[*]\nindent_style = tab\n' > .editorconfig
  # A blank line and a comment inside assumes, and a Prettier config that leaves indentation to .editorconfig.
  printf -- '---\nassumes:\n\n  # format\n  indentation: spaces # why\n---\n# Format\n' > .agents/rules/format.md
  printf '{"semi": false}\n' > .prettierrc
  plan_text --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" == *"~ .agents/rules/ours.md (project) assumes linter: biome, which assets/repo-facts.json does not know; it is not checked"* ]]
  [[ "$output" == *"! .agents/rules/format.md (project) assumes indentation spaces, but the repository uses tabs (.editorconfig)"* ]]

  printf '{"conflicts": {"repoReality": {"enabled": false}}}\n' > .agents/agent-ready.json
  plan_text --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" != *"assumes"* ]]
}

@test "plan reports permissions, hooks and formatters that collide across the settings layers" {
  printf '{"name": "app"}\n' > package.json
  mkdir -p .claude "$test_root/home/.claude"
  printf '%s\n' '{"permissions": {"allow": ["Bash(npm run *)"]}, "hooks": {"PostToolUse": [{"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "npx prettier --write ."}]}]}}' > .claude/settings.json
  printf '%s\n' '{"hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "npx biome format --write ."}]}]}}' > .claude/settings.local.json
  printf '%s\n' '{"permissions": {"deny": ["Bash(npm run *)"]}, "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "bash .agents/hooks/sync-marketplace.sh --provider claude"}]}]}}' > "$test_root/home/.claude/settings.json"
  run env -u CLAUDE_CONFIG_DIR HOME="$test_root/home" python3 "$skill_dir/scripts/agent-ready-state.py" plan --project "$project_dir" --skill-dir "$skill_dir" --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" == *"! permission Bash(npm run *): allowed in .claude/settings.json and denied in ~/.claude/settings.json; Claude Code applies the deny"* ]]
  [[ "$output" == *"~ claude hook SessionStart \`bash .agents/hooks/sync-marketplace.sh --provider claude\` is registered in .claude/settings.json (golfo-agent-ready) and ~/.claude/settings.json"* ]]
  [[ "$output" == *"~ claude PostToolUse runs two formatters that can rewrite the same files: prettier (.claude/settings.json) and biome (.claude/settings.local.json)"* ]]

  # Different matchers never touch the same files; each check turns off on its own.
  printf '%s\n' '{"hooks": {"PostToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "npx biome format --write ."}]}]}}' > .claude/settings.local.json
  mkdir -p .agents
  printf '{"conflicts": {"permissions": {"enabled": false}}}\n' > .agents/agent-ready.json
  run env -u CLAUDE_CONFIG_DIR HOME="$test_root/home" python3 "$skill_dir/scripts/agent-ready-state.py" plan --project "$project_dir" --skill-dir "$skill_dir" --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" != *"runs two formatters"* ]]
  [[ "$output" != *"! permission"* ]]
  [[ "$output" == *"is registered in"* ]]

  # With the hooks check off, neither the duplicated hook nor the formatters are compared.
  printf '%s\n' '{"hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "npx biome format --write ."}]}]}}' > .claude/settings.local.json
  printf '{"conflicts": {"hooks": {"enabled": false}}}\n' > .agents/agent-ready.json
  run env -u CLAUDE_CONFIG_DIR HOME="$test_root/home" python3 "$skill_dir/scripts/agent-ready-state.py" plan --project "$project_dir" --skill-dir "$skill_dir" --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" != *"is registered in"* ]]
  [[ "$output" != *"runs two formatters"* ]]
  [[ "$output" == *"! permission Bash(npm run *)"* ]]
}

@test "plan shows what each provider sees, the hooks only one runs and a CI job that already checks" {
  printf '{"name": "app"}\n' > package.json
  mkdir -p .claude .github/workflows .agents
  printf '%s\n' '{"hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "npm run lint"}]}]}}' > .claude/settings.json
  printf 'name: own\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n      - run: sh .agents/ci/agent-ready-check.sh\n' > .github/workflows/own.yml
  printf '{"ci": {"provider": "github"}}\n' > .agents/agent-ready.json
  run env -u CLAUDE_CONFIG_DIR HOME="$test_root/home" python3 "$skill_dir/scripts/agent-ready-state.py" plan --project "$project_dir" --skill-dir "$skill_dir" --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" == *"Providers: Claude Code sees "*" rules ("*" only for their paths)"*"; Codex sees "*" rules in AGENTS.md, "*" skills and "*" subagents"* ]]
  [[ "$output" == *"~ claude runs the PostToolUse hook \`npm run lint\` (.claude/settings.json) and codex does not"* ]]
  [[ "$output" == *"~ .github/workflows/own.yml already runs the Agent Ready check; the managed .github/workflows/agent-ready.yml runs it again"* ]]
  # The golfo-agent-ready hooks of each provider match, except the ones declared for one provider.
  [[ "$output" != *"runs the SessionStart hook"* ]]
  [[ "$output" != *"UserPromptSubmit"* ]]

  printf '{"ci": {"provider": "github"}, "conflicts": {"providerParity": {"enabled": false}, "ciJobs": {"enabled": false}}}\n' > .agents/agent-ready.json
  run env -u CLAUDE_CONFIG_DIR HOME="$test_root/home" python3 "$skill_dir/scripts/agent-ready-state.py" plan --project "$project_dir" --skill-dir "$skill_dir" --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" != *"Providers: Claude Code sees"* ]]
  [[ "$output" != *"already runs the Agent Ready check"* ]]
}

# 157: the memory of Engram. A copy of the content that publishes the profile memory-engram, with a rule
# and, as an option, a capability that requires it.
add_memory_profile() {
  unset AGENT_READY_SETUP_MEMORY
  copy_skill
  mkdir -p "$content_dir/profiles/memory-engram/rules"
  printf '%s\n' '# Memory' '' '<!-- rule id=memory/facts-in-engram -->' '- Save the facts of a case in Engram.' \
    > "$content_dir/profiles/memory-engram/rules/memory-engram.md"
  python3 - "$content_dir/agent-ready-pack.json" "${1:-}" <<'EOF2'
import json, sys
path, with_requirer = sys.argv[1], sys.argv[2]
catalog = json.load(open(path))
catalog["profiles"]["memory-engram"] = {"kind": "capability", "description": "Engram memory.", "assets": "profiles/memory-engram"}
if with_requirer:
    catalog["profiles"]["case-notes"] = {"kind": "capability", "description": "Needs the memory.", "requires": ["memory-engram"]}
json.dump(catalog, open(path, "w"), indent=2)
EOF2
}

@test "memory.engram brings the memory-engram profile to every selection, even one without a stack" {
  add_memory_profile
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["profileOrder"]')" = "['software-development', 'node', 'browser', 'memory-engram']" ]
  [ -f .agents/rules/memory-engram.md ]

  rm -rf .agents .claude .codex AGENTS.md CLAUDE.md .gitignore .mcp.json
  run_bootstrap_with "$source_copy" --profiles none
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["profileOrder"]')" = "['memory-engram']" ]
  [ -f .agents/rules/memory-engram.md ]
}

@test "memory.engram false leaves memory-engram out even when the selection names it, and retires what it wrote" {
  add_memory_profile
  run_bootstrap_with "$source_copy" --profiles browser
  [ "$status" -eq 0 ]
  [ -f .agents/rules/memory-engram.md ]

  python3 - <<'EOF2'
import json
path = ".agents/agent-ready.json"
manifest = json.load(open(path))
manifest["memory"] = {"engram": False}
manifest["profiles"] = ["browser", "memory-engram"]
json.dump(manifest, open(path, "w"), indent=2)
EOF2
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["profileOrder"]')" = "['browser']" ]
  [ ! -e .agents/rules/memory-engram.md ]
}

@test "with memory.engram false a profile that requires memory-engram fails before writing" {
  add_memory_profile with-requirer
  mkdir -p .agents
  printf '%s\n' '{"memory": {"engram": false}}' > .agents/agent-ready.json
  run_bootstrap_with "$source_copy" --profiles case-notes
  [ "$status" -ne 0 ]
  [[ "$output" == *"profile 'case-notes' requires 'memory-engram', which memory.engram turned off"* ]]
  [ ! -e .agents/agent-ready.lock.json ]
}

# 169b: the learning profile names the merge drivers in .gitattributes, and each apply registers them.
learning_with_merge_attributes() {
  copy_skill
  mkdir -p "$content_dir/profiles/learning/blocks"
  printf '%s\n' '.agents/rules/**/*.md merge=agent-ready-rules' \
    '.agents/learning/candidates.json merge=agent-ready-candidates' '.agents/learning/log.md merge=agent-ready-log' \
    > "$content_dir/profiles/learning/blocks/.gitattributes"
}

# The learning registry with one candidate per name, as learn record writes it.
write_registry_entries() {
  python3 - "$@" <<'PY'
import json, sys
entries = [{"id": f"learn-{name}", "statement": name, "status": "candidate", "evidence": []} for name in sys.argv[1:]]
json.dump({"version": 1, "candidates": entries}, open(".agents/learning/candidates.json", "w"), indent=2, sort_keys=True)
PY
}

@test "two machines that learned different rules of one file, and each added a log line, merge without conflict" {
  learning_with_merge_attributes
  run_bootstrap_with "$source_copy" --profiles learning
  [ "$status" -eq 0 ]
  grep -Fq '.agents/rules/**/*.md merge=agent-ready-rules' .gitattributes
  [[ "$(git config --local --get merge.agent-ready-rules.driver)" == *"agent-ready-merge"*"agent-ready-rules %O %A %B %P" ]]
  mkdir -p .agents/rules .agents/learning
  printf '%s\n' '# Learned' '' '<!-- rule id=learned/base -->' '- Keep the base.' > .agents/rules/learned.md
  printf '%s\n' '# Learning log' '' '- base' > .agents/learning/log.md
  write_registry_entries base
  git add -A
  git commit -qm base
  remote="$test_root/remote.git"
  git init -q --bare "$remote"
  git remote add origin "$remote"
  git push -q origin HEAD:main

  # The second machine: its own clone, whose apply registers the drivers of its installation.
  other="$test_root/other"
  git clone -q -b main "$remote" "$other"
  cd "$other"
  run_bootstrap_with "$source_copy" --profiles learning
  [ "$status" -eq 0 ]
  printf '%s\n' '' '<!-- rule id=learned/dates -->' '- Dates go first.' >> .agents/rules/learned.md
  printf '%s\n' '- dates' >> .agents/learning/log.md
  write_registry_entries base dates
  git commit -qam "learn dates"
  git push -q origin HEAD:main

  cd "$project_dir"
  printf '%s\n' '' '<!-- rule id=learned/signature -->' '- Sign at the end.' >> .agents/rules/learned.md
  printf '%s\n' '- signature' >> .agents/learning/log.md
  write_registry_entries base signature
  git commit -qam "learn signature"
  git pull -q --no-rebase --no-edit origin main
  [ -z "$(git diff --name-only --diff-filter=U)" ]
  grep -Fxq -- '- Dates go first.' .agents/rules/learned.md
  grep -Fxq -- '- Sign at the end.' .agents/rules/learned.md
  grep -Fxq -- '- Keep the base.' .agents/rules/learned.md
  ! grep -q '^<<<<<<<' .agents/rules/learned.md
  grep -Fxq -- '- dates' .agents/learning/log.md
  grep -Fxq -- '- signature' .agents/learning/log.md
  [ "$(python3 -c 'import json; print(sorted(entry["id"] for entry in json.load(open(".agents/learning/candidates.json"))["candidates"]))' | tr -d '\r')" = \
    "['learn-base', 'learn-dates', 'learn-signature']" ]
}

@test "the same rule changed in two ways is a conflict of that rule only, and the others merge" {
  learning_with_merge_attributes
  run_bootstrap_with "$source_copy" --profiles learning
  [ "$status" -eq 0 ]
  mkdir -p .agents/rules
  printf '%s\n' '# Learned' '' '<!-- rule id=learned/header -->' '- Put the date in the header.' '' \
    '<!-- rule id=learned/footer -->' '- Sign in the footer.' > .agents/rules/learned.md
  git add -A
  git commit -qm base
  git checkout -qb other
  sed -i.bak 's/Put the date in the header./Put the date and the case in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  printf '%s\n' '' '<!-- rule id=learned/margin -->' '- Leave a wide margin.' >> .agents/rules/learned.md
  git commit -qam other
  git checkout -q -
  sed -i.bak 's/Put the date in the header./Put the case number in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  git commit -qam ours
  run git merge -q --no-edit other
  [ "$status" -ne 0 ]
  [ "$(grep -c '^<<<<<<< ours$' .agents/rules/learned.md)" -eq 1 ]
  grep -Fxq -- '- Put the case number in the header.' .agents/rules/learned.md
  grep -Fxq -- '- Put the date and the case in the header.' .agents/rules/learned.md
  # Outside the conflict, each rule is whole and once.
  [ "$(grep -c '^- Sign in the footer.$' .agents/rules/learned.md)" -eq 1 ]
  grep -Fxq -- '- Leave a wide margin.' .agents/rules/learned.md
}

@test "a rule removed on one side and changed on the other is a conflict of that rule, whichever side removed it" {
  printf '%s\n' '# Learned' '' '<!-- rule id=learned/a -->' '- Use A.' '' '<!-- rule id=learned/b -->' '- Use B.' > base.md
  printf '%s\n' '# Learned' '' '<!-- rule id=learned/a -->' '- Use A.' > removed.md
  sed 's/- Use B./- Use B always./' base.md > changed.md
  cp removed.md ours.md
  run python3 "$skill_dir/scripts/agent-ready-merge" agent-ready-rules base.md ours.md changed.md learned.md
  [ "$status" -eq 1 ]
  grep -Fxq -- '- Use B always.' ours.md
  [ "$(grep -c '^<<<<<<< ours$' ours.md)" -eq 1 ]
  cp changed.md ours.md
  run python3 "$skill_dir/scripts/agent-ready-merge" agent-ready-rules base.md ours.md removed.md learned.md
  [ "$status" -eq 1 ]
  grep -Fxq -- '- Use B always.' ours.md
  # Removed on one side and untouched on the other is a removal, without conflict.
  cp removed.md ours.md
  run python3 "$skill_dir/scripts/agent-ready-merge" agent-ready-rules base.md ours.md base.md learned.md
  [ "$status" -eq 0 ]
  ! grep -q 'Use B' ours.md
}

@test "the personal rules of each person get no Claude view and no line in AGENTS.md, unlike the rules of the team" {
  copy_skill
  mkdir -p .agents/rules/learned/users/ana-notebook
  printf '%s\n' '# Learned' '' '<!-- rule id=learned/team-dates -->' '- Dates go first.' > .agents/rules/learned.md
  printf '%s\n' '# Personal rules' '' '<!-- rule id=learned/users/ana-notebook/dates -->' '- Dates go last.' \
    > .agents/rules/learned/users/ana-notebook/learned.md
  run_bootstrap_with "$source_copy" --profiles learning
  [ "$status" -eq 0 ]
  [ -e .claude/rules/learned.md ]
  grep -Fq '.agents/rules/learned.md' AGENTS.md
  [ ! -e .claude/rules/learned/users ]
  ! grep -Fq 'learned/users' AGENTS.md
}

# The frontmatter line of a key, from a Markdown view.
frontmatter_line() {
  sed -n '2,/^---$/p' "$1" | grep -E "^$2:" || true
}

@test "access and model-tier of a subagent render the tools and the model of each provider" {
  require_tomllib
  copy_skill
  printf '%s\n' '---' 'name: quick-reviewer' 'description: Revisa rápido.' 'access: read-only' 'model-tier: fast' '---' '# Quick' 'Review.' \
    > "$content_dir/stacks/node/agents/quick-reviewer.md"

  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  # Antigravity reads .agents/agents/ as it is: its tools and model, without the portable keys.
  [ "$(frontmatter_line .agents/agents/quick-reviewer.md tools)" = 'tools: ["view_file", "list_dir", "find_by_name", "grep_search"]' ]
  [ "$(frontmatter_line .agents/agents/quick-reviewer.md model)" = 'model: flash' ]
  [ -z "$(frontmatter_line .agents/agents/quick-reviewer.md access)" ]
  # Claude Code gets a file of its own, not a view of the Antigravity one.
  [ ! -L .claude/agents/quick-reviewer.md ]
  ! [ .claude/agents/quick-reviewer.md -ef .agents/agents/quick-reviewer.md ]
  [ "$(frontmatter_line .claude/agents/quick-reviewer.md tools)" = 'tools: Read, Grep, Glob' ]
  [ "$(frontmatter_line .claude/agents/quick-reviewer.md model)" = 'model: haiku' ]
  grep -Fxq 'Review.' .claude/agents/quick-reviewer.md
  [ "$(codex_agent_value .codex/agents/quick-reviewer.toml model_reasoning_effort)" = low ]
  python3 -c 'import tomllib; assert tomllib.load(open(".codex/agents/quick-reviewer.toml", "rb"))["features"] == {"shell_tool": False}'

  run_bootstrap_with "$source_copy" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Summary: no changes"* ]]
  [[ "$output" == *"~ .agents/agents/quick-reviewer.md: Codex keeps the sandbox of the session that starts the subagent, so a read-only subagent can still edit files (codex)"* ]]

  # Without metadata the subagent goes back to a copy and its Claude view, as any other.
  printf '%s\n' '---' 'name: quick-reviewer' 'description: Revisa rápido.' '---' '# Quick' 'Review.' \
    > "$content_dir/stacks/node/agents/quick-reviewer.md"
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  cmp -s .agents/agents/quick-reviewer.md "$content_dir/stacks/node/agents/quick-reviewer.md"
  [ -L .claude/agents/quick-reviewer.md ] || [ .claude/agents/quick-reviewer.md -ef .agents/agents/quick-reviewer.md ]
  python3 -c 'import tomllib; data = tomllib.load(open(".codex/agents/quick-reviewer.toml", "rb")); assert "features" not in data and "model_reasoning_effort" not in data, data'
  # The rendered Claude file is not retired: an identical apply keeps the view and changes nothing.
  [[ "$output" != *"retire"* && "$output" != *"preserved"* ]]
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [ -L .claude/agents/quick-reviewer.md ] || [ .claude/agents/quick-reviewer.md -ef .agents/agents/quick-reviewer.md ]
  run_bootstrap_with "$source_copy" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Summary: no changes"* ]]
}

@test "model-tier deep and access full map to opus, pro and high effort, and a subagent without metadata keeps the views of A" {
  require_tomllib
  copy_skill
  printf '%s\n' '---' 'name: deep-reviewer' 'description: Revisa a fondo.' 'access: full' 'model-tier: deep' '---' 'Body.' \
    > "$content_dir/stacks/node/agents/deep-reviewer.md"
  printf '%s\n' '---' 'name: plain-reviewer' 'description: Revisa sin metadatos.' '---' 'Body.' \
    > "$content_dir/stacks/node/agents/plain-reviewer.md"
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ "$(frontmatter_line .claude/agents/deep-reviewer.md model)" = 'model: opus' ]
  [ -z "$(frontmatter_line .claude/agents/deep-reviewer.md tools)" ]
  [ "$(frontmatter_line .agents/agents/deep-reviewer.md model)" = 'model: pro' ]
  [[ "$(frontmatter_line .agents/agents/deep-reviewer.md tools)" == *'"run_command"'* ]]
  [ "$(codex_agent_value .codex/agents/deep-reviewer.toml model_reasoning_effort)" = high ]
  # A subagent that declares nothing: copy, view and TOML of part A.
  cmp -s .agents/agents/plain-reviewer.md "$content_dir/stacks/node/agents/plain-reviewer.md"
  [ -L .claude/agents/plain-reviewer.md ] || [ .claude/agents/plain-reviewer.md -ef .agents/agents/plain-reviewer.md ]
  [ -f .codex/agents/plain-reviewer.toml ]
}

@test "an access or model-tier outside its values stops the apply before writing, naming the file" {
  copy_skill
  printf '%s\n' '---' 'name: odd-reviewer' 'description: Revisa.' 'access: readonly' '---' 'Body.' \
    > "$content_dir/stacks/node/agents/odd-reviewer.md"
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -ne 0 ]
  [[ "$output" == *"agents/odd-reviewer.md: access is 'readonly'; it must be one of read-only, edit, full"* ]]
  [ ! -e .agents/agents ]
}

@test "a subagent that gains access replaces its previous Claude view, and a block sequence of tools is replaced whole" {
  copy_skill
  printf '%s\n' '---' 'name: late-reviewer' 'description: Revisa.' 'tools:' '  - Read' '  - Bash' '---' 'Body.' \
    > "$content_dir/stacks/node/agents/late-reviewer.md"
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ -L .claude/agents/late-reviewer.md ] || [ .claude/agents/late-reviewer.md -ef .agents/agents/late-reviewer.md ]

  printf '%s\n' '---' 'name: late-reviewer' 'description: Revisa.' 'tools:' '  - Read' '  - Bash' 'access: read-only' '---' 'Body.' \
    > "$content_dir/stacks/node/agents/late-reviewer.md"
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" != *"never applied by agent-ready-setup"* ]]
  [ ! -L .claude/agents/late-reviewer.md ]
  [ "$(frontmatter_line .claude/agents/late-reviewer.md tools)" = 'tools: Read, Grep, Glob' ]
  [[ "$(frontmatter_line .agents/agents/late-reviewer.md tools)" == 'tools: ["view_file"'* ]]
  # The items of the replaced sequence leave with it.
  ! grep -Fq -- '- Bash' .claude/agents/late-reviewer.md
  ! grep -Fq -- '- Bash' .agents/agents/late-reviewer.md

  run_bootstrap_with "$source_copy" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Summary: no changes"* ]]
}

@test "a subagent that declares only model-tier keeps its own tools, and one that declares only access keeps its model" {
  copy_skill
  printf '%s\n' '---' 'name: tier-reviewer' 'description: Revisa.' 'tools: Read, Grep' 'model-tier: fast' '---' 'Body.' \
    > "$content_dir/stacks/node/agents/tier-reviewer.md"
  printf '%s\n' '---' 'name: access-reviewer' 'description: Revisa.' 'model: sonnet' 'access: read-only' '---' 'Body.' \
    > "$content_dir/stacks/node/agents/access-reviewer.md"
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ "$(frontmatter_line .claude/agents/tier-reviewer.md tools)" = 'tools: Read, Grep' ]
  [ "$(frontmatter_line .claude/agents/tier-reviewer.md model)" = 'model: haiku' ]
  [ "$(frontmatter_line .claude/agents/access-reviewer.md model)" = 'model: sonnet' ]
  [ "$(frontmatter_line .claude/agents/access-reviewer.md tools)" = 'tools: Read, Grep, Glob' ]
}
