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
  [[ "$output" == *"Profiles: node,browser"* ]]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]

  [ "$(python3 -c 'import json; m=json.load(open(".agents/agent-ready.json")); print(m["updates"]["mode"], ",".join(m["profiles"]))')" = "pinned node,browser" ]
  [ "$(lock_value 'lock["source"]["plugin"]')" = "golfo-kit" ]
  [ "$(lock_value 'lock["profileOrder"]')" = "['node', 'browser']" ]

  # Every regular file the projection wrote under .agents (except state files) is owned by the lock.
  find .agents -type f ! -name 'agent-ready.json' ! -name 'agent-ready.lock.json' | LC_ALL=C sort > "$test_root/projected"
  lock_value '"\n".join(sorted(path for path in lock["assets"] if path.startswith(".agents/")))' > "$test_root/locked"
  diff -u "$test_root/projected" "$test_root/locked"
  [ "$(lock_value 'lock["blocks"][".github/pull_request_template.md"]["common"]["state"]')" = "applied" ]
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
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/node-testing.md"
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/node-security.md"

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Lockfile: .agents/agent-ready.lock.json (complete)"* ]]
  cmp -s .agents/rules/node-testing.md "$source_copy/assets/stacks/node/rules/node-testing.md"
  cmp -s .agents/rules/node-security.md "$source_copy/assets/stacks/node/rules/node-security.md"
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
  rm "$source_copy/assets/stacks/node/agents/node-perf-analyzer.md"

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

  printf '%s\n' '{"profiles": [], "updates": {"mode": "pinned"}}' > .agents/agent-ready.json
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -ne 0 ]
  [[ "$output" == *"project layer"*"'profiles' needs at least 1 item(s)"* ]]
}

@test "an explicit --stack wins over the profiles chosen in the environment" {
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh

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
  printf '%s\n' '# New upstream rule' > "$source_copy/assets/stacks/node/rules/new-upstream.md"
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
  cmp -s .agents/rules/new-upstream.md "$source_copy/assets/stacks/node/rules/new-upstream.md"

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
  run_bootstrap_with "$skill_dir" --profiles node
  [ "$status" -eq 0 ]
  printf '%s\n' '{"profiles": ["node", "browser"], "updates": {"mode": "pinned"}}' > .agents/agent-ready.json

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
  run_bootstrap_with "$skill_dir" --stack frontend
  [ "$status" -eq 0 ]
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 0 ]

  rm .claude/rules/frontend-security.md
  run python3 "$skill_dir/scripts/agent-ready-state.py" status --project . --skill-dir "$skill_dir" --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"missing: .claude/rules/frontend-security.md"* ]]
}


@test "plan and status are read-only and never call the provider CLI" {
  run_bootstrap_with "$skill_dir" --stack frontend
  [ "$status" -eq 0 ]
  printf '%s\n' 'local note' >> .agents/rules/frontend-testing.md
  rm -f "$cli_calls"
  before="$(tree_fingerprint)"

  run_bootstrap_with "$skill_dir" --plan --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"Agent Ready plan (read-only: nothing was written)"* ]]
  [[ "$output" == *"update"*".agents/rules/frontend-testing.md"*"overwrites local changes since the last apply"* ]]
  [[ "$output" == *"+local note"* ]] || [[ "$output" == *"-local note"* ]]

  run_bootstrap_with "$skill_dir" --status --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"modified: .agents/rules/frontend-testing.md"* ]]

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
  cmp -s .agents/rules/node-security.md "$skill_dir/assets/stacks/node/rules/node-security.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/node-security.md"]["state"]')" = "applied" ]
}

@test "a project file in a Claude view stays preserved after its asset could not be written" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s
' '# New upstream rule' > "$source_copy/assets/stacks/node/rules/new-upstream.md"
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
  printf '%s\n' '# New upstream rule' > "$source_copy/assets/stacks/node/rules/new-upstream.md"
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
  cmp -s .agents/rules/new-upstream.md "$source_copy/assets/stacks/node/rules/new-upstream.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/new-upstream.md"]["state"]')" = "applied" ]
  [ "$(cat .agents/rules/project-rule.md)" = "project rule" ]
}

@test "a preserved project file stays in place when no profile publishes that path anymore" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' '# New upstream rule' > "$source_copy/assets/stacks/node/rules/new-upstream.md"
  printf '%s\n' 'project rule' > .agents/rules/new-upstream.md
  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  rm "$source_copy/assets/stacks/node/rules/new-upstream.md"

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
  cmp -s .agents/rules/node-security.md "$skill_dir/assets/stacks/node/rules/node-security.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/node-security.md"]["state"]')" = "applied" ]
}

@test "a new release updates every managed asset, edited ones included" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack java
  [ "$status" -eq 0 ]
  printf '%s\n' 'edited locally' >> .agents/rules/java-coding-style.md
  printf '%s\n' '- New upstream guidance.' >> "$source_copy/assets/stacks/java/rules/java-testing.md"
  printf '%s\n' '- New upstream guidance.' >> "$source_copy/assets/stacks/java/rules/java-coding-style.md"

  run_bootstrap_with "$source_copy" --status
  [[ "$output" == *"Update available"* ]]

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/java-testing.md "$source_copy/assets/stacks/java/rules/java-testing.md"
  cmp -s .agents/rules/java-coding-style.md "$source_copy/assets/stacks/java/rules/java-coding-style.md"
}

@test "assets dropped from the profiles are retired, edited ones included" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ -f .agents/agents/node-perf-analyzer.md ]
  [ -f .agents/skills/node-perf-analyzer/SKILL.md ]
  printf '%s\n' 'edited locally' >> .agents/agents/node-security-scanner.md
  rm "$source_copy/assets/stacks/node/agents/node-perf-analyzer.md" "$source_copy/assets/stacks/node/agents/node-security-scanner.md"

  run_bootstrap_with "$source_copy" --plan
  [[ "$output" == *".agents/agents/node-security-scanner.md"*"removes its local changes"* ]]

  run_bootstrap_with "$source_copy"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Retired managed assets:"* ]]
  [ ! -e .agents/agents/node-perf-analyzer.md ]
  [ ! -e .agents/skills/node-perf-analyzer ]
  [ ! -e .claude/agents/node-perf-analyzer.md ]
  [ ! -e .agents/agents/node-security-scanner.md ]
  [ ! -e .claude/agents/node-security-scanner.md ]
  [ "$(lock_value '".agents/agents/node-perf-analyzer.md" in lock["assets"]')" = "False" ]
  [ "$(lock_value '".agents/agents/node-security-scanner.md" in lock["assets"]')" = "False" ]
}

@test "without a lockfile the first apply adopts existing managed files once" {
  mkdir -p .agents/rules
  printf '%s\n' 'previous template version' > .agents/rules/go-testing.md

  run_bootstrap_with "$skill_dir" --stack go
  [ "$status" -eq 0 ]
  cmp -s .agents/rules/go-testing.md "$skill_dir/assets/stacks/go/rules/go-testing.md"
  [ "$(lock_value 'lock["assets"][".agents/rules/go-testing.md"]["state"]')" = "applied" ]
}

@test "profiles that publish the same destination fail before writing anything" {
  copy_skill
  mkdir -p "$source_copy/assets/profiles/node-security-copy/rules"
  printf '%s
' '# Another node security' > "$source_copy/assets/profiles/node-security-copy/rules/node-security.md"
  python3 - "$source_copy/assets/profiles.json" <<'EOF2'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path))
catalog["profiles"]["node-security-copy"] = {"kind": "capability", "description": "Publishes the node security rule again.", "requires": ["node"], "assets": "assets/profiles/node-security-copy"}
json.dump(catalog, open(path, "w"), indent=2)
EOF2

  run_bootstrap_with "$source_copy" --profiles node-security-copy
  [ "$status" -ne 0 ]
  [[ "$output" == *"profiles 'node' and 'node-security-copy' both write .agents/rules/node-security.md"* ]]
  [ ! -e .agents ]
  [ ! -e .claude ]
}

@test "unknown profiles and profile sets without a stack are rejected with the catalog" {
  run_bootstrap_with "$skill_dir" --profiles cobol
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown profile 'cobol'; available profiles: android, browser, business-flows, frontend, go, java, node"* ]]

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
  cmp -s .agents/rules/node-security.md "$source_copy/assets/stacks/node/rules/node-security.md"
  grep -Fq 'node-testing-extras.md' AGENTS.md
  [ "$(lock_value 'lock["assets"][".agents/rules/node-testing-extras.md"]["profile"]')" = "node-testing" ]

  run_bootstrap_with "$source_copy" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"AGENTS.md: managed block is current"* ]]
}

@test "two stacks compose in one repository: each brings its own assets and the first one is the primary" {
  run_bootstrap_with "$skill_dir" --profiles frontend,node
  [ "$status" -eq 0 ]
  [[ "$output" == *"Profiles: frontend,node"* ]]
  for stack in frontend node; do
    cmp -s ".agents/rules/$stack-security.md" "$skill_dir/assets/stacks/$stack/rules/$stack-security.md"
    cmp -s ".agents/rules/$stack-testing.md" "$skill_dir/assets/stacks/$stack/rules/$stack-testing.md"
    cmp -s ".agents/agents/$stack-perf-analyzer.md" "$skill_dir/assets/stacks/$stack/agents/$stack-perf-analyzer.md"
    cmp -s ".agents/commands/$stack-review-pr.md" "$skill_dir/assets/stacks/$stack/commands/$stack-review-pr.md"
    grep -Fq ".agents/rules/$stack-security.md" AGENTS.md
    [ "$(lock_value "lock['assets']['.agents/rules/$stack-security.md']['profile']")" = "$stack" ]
  done
  cmp -s .agents/rules/node-coding-style.md "$skill_dir/assets/stacks/node/rules/node-coding-style.md"
  cmp -s .agents/rules/frontend-style.md "$skill_dir/assets/stacks/frontend/rules/frontend-style.md"
  # One base template, and a section of each stack in the order of its id.
  [ "$(grep -Fxc '# [Project Name]' AGENTS.md)" -eq 1 ]
  [ "$(grep -E '^<!-- BEGIN AGENT-READY MANAGED: [a-z]+ -->$' AGENTS.md | tr '\n' ' ')" = \
    "<!-- BEGIN AGENT-READY MANAGED: frontend --> <!-- BEGIN AGENT-READY MANAGED: node --> " ]

  run_bootstrap_with "$skill_dir" --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"AGENTS.md: managed block is current"* ]]
}

@test "an apply after the stack assets were renamed retires the files with the old names" {
  copy_skill
  mv "$source_copy/assets/stacks/node/rules/node-security.md" "$source_copy/assets/stacks/node/rules/security.md"
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  [ -f .agents/rules/security.md ]

  run_bootstrap_with "$skill_dir" --stack node
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/security.md ]
  [ ! -e .claude/rules/security.md ]
  ! grep -Fq '.agents/rules/security.md' AGENTS.md
  cmp -s .agents/rules/node-security.md "$skill_dir/assets/stacks/node/rules/node-security.md"
  [ "$(lock_value "'.agents/rules/security.md' in lock['assets']")" = "False" ]
}

@test "SessionStart in a pinned repository reports updates without writing" {
  copy_skill
  run_bootstrap_with "$source_copy" --stack node
  [ "$status" -eq 0 ]
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/node-testing.md"
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
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/node-testing.md"
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/node-security.md"
  printf '%s\n' '# Newer hook release.' >> "$source_copy/assets/common/hooks/sync-marketplace.sh"
  rm .claude/rules/node-testing.md
  printf '%s\n' 'local view policy' > .claude/rules/node-testing.md

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_copy" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider codex
  [ "$status" -eq 0 ]
  [[ "$output" == *"Sync hook updated; restarting with latest version."* ]]
  [ -L .claude/rules/node-testing.md ] || [ .claude/rules/node-testing.md -ef .agents/rules/node-testing.md ]
  cmp -s .agents/rules/node-testing.md "$source_copy/assets/stacks/node/rules/node-testing.md"
  cmp -s .agents/rules/node-security.md "$source_copy/assets/stacks/node/rules/node-security.md"
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
  printf '%s\n' '- Newer guidance.' >> "$source_copy/assets/stacks/node/rules/node-testing.md"
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
  [ "$(lock_value 'lock["profileOrder"]')" = "['android']" ]
  for asset in rules/android-coding-style.md rules/android-security.md rules/android-testing.md agents/android-perf-analyzer.md agents/android-security-scanner.md commands/android-review-pr.md; do
    cmp -s ".agents/$asset" "$skill_dir/assets/stacks/android/$asset"
    [ -L ".claude/$asset" ] || [ ".claude/$asset" -ef ".agents/$asset" ]
  done
  grep -Fq -- '- Read and follow `.agents/rules/android-coding-style.md`.' AGENTS.md
  [ ! -e .mcp.json ]
}

@test "SessionStart detects Android modules before the generic Gradle stack" {
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
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
  printf '%s\n' 'plugins {}' > build.gradle.kts

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["primaryStack"]')" = "java" ]
}

@test "SessionStart keeps a React Native project with an android directory on the frontend stack" {
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json
  mkdir -p android/app/src/main
  printf '%s\n' '<manifest />' > android/app/src/main/AndroidManifest.xml

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["primaryStack"]')" = "frontend" ]
}

@test "the business-flows profile adds its assets to any stack and needs one" {
  run_bootstrap_with "$skill_dir" --profiles business-flows
  [ "$status" -ne 0 ]
  [[ "$output" == *"select at least one stack profile"* ]]

  for stack in android frontend; do
    stack_project="$test_root/$stack-flows"
    mkdir -p "$stack_project"
    git -C "$stack_project" -c init.defaultBranch=main init -q
    cd "$stack_project"

    run_bootstrap_with "$skill_dir" --profiles "$stack,business-flows"
    [ "$status" -eq 0 ]
    [ "$(lock_value 'lock["primaryStack"]')" = "$stack" ]
    cmp -s .agents/rules/business-flows.md "$skill_dir/assets/profiles/business-flows/rules/business-flows.md"
    cmp -s .agents/skills/business-flow-design/SKILL.md "$skill_dir/assets/profiles/business-flows/skills/business-flow-design/SKILL.md"
    grep -Fq -- '- Read and follow `.agents/rules/business-flows.md`.' AGENTS.md
    [ -L .claude/rules/business-flows.md ] || [ .claude/rules/business-flows.md -ef .agents/rules/business-flows.md ]
    [ "$(lock_value 'lock["assets"][".agents/rules/business-flows.md"]["profile"]')" = "business-flows" ]
  done
}

@test "profiles without browser never install browser tools" {
  mkdir -p "$test_root/home"
  run env HOME="$test_root/home" PATH="$fake_bin:$PATH" AGENT_READY_SETUP_TOOLS=1 \
    AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 bash "$skill_dir/scripts/bootstrap.sh" \
    --skill-dir "$skill_dir" --provider claude --profiles node
  [ "$status" -eq 0 ]
  [[ "$output" == *"Browser installation skipped: no selected profile needs browser tools"* ]]
  [ ! -e "$test_root/home/.local/share/agent-ready-setup" ]
  [ ! -e .mcp.json ]
  [ ! -e .codex/config.toml ]
}
