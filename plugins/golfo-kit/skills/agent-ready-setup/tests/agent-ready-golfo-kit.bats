#!/usr/bin/env bats
# golfo-kit as a pinnable source: its content at a revision of the lock, fetched with Git from
# the marketplace into the user cache, projected by the installed engine. The marketplace is a
# local repository reached through url.insteadOf, so the manifests and the lock keep the real URL.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  cli="$skill_dir/scripts/agent-ready"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  export XDG_CONFIG_HOME="$test_root/config"
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_ORGANIZATION_CONFIG="$test_root/organization/config.json"
  export AGENT_READY_SETUP_TOOLS=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  export GIT_CONFIG_GLOBAL="$test_root/gitconfig"
  git config --global user.name Test
  git config --global user.email test@example.invalid
  git config --global init.defaultBranch main
  git config --global core.autocrlf false
  git config --global protocol.file.allow always
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_REVIEW_MODE
  unset AGENT_READY_SETUP_CI AGENT_READY_SETUP_REFRESH AGENT_READY_SETUP_DETECTION
  for provider_cli in claude codex; do
    printf '#!/bin/bash\nexit 0\n' > "$fake_bin/$provider_cli"
    chmod +x "$fake_bin/$provider_cli"
  done
  publish_marketplace
  git -C "$project_dir" init -q
  cd "$project_dir"
  printf '{}\n' > package.json
}

teardown() {
  cd "$repository_root"
  local removal_attempt
  for removal_attempt in $(seq 1 50); do
    rm -rf "$test_root" 2>/dev/null && return 0
    sleep 0.2
  done
  rm -rf "$test_root"
}

run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$cli" "$@"
}

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

lock_value() {
  python3 -c 'import json,sys; data=json.load(open(".agents/agent-ready.lock.json", encoding="utf-8")); print(eval(sys.argv[1], {"data": data}))' "$1" | tr -d '\r'
}

engine_version() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$repository_root/plugins/golfo-kit/plugin.json" | tr -d '\r'
}

# A marketplace with two revisions of golfo-kit: v1 marks a rule and the consistency hook, v2
# marks the rule again and bumps the version. Both are reachable at the real repository URL.
publish_marketplace() {
  marketplace="$test_root/marketplace"
  mkdir -p "$marketplace/plugins/golfo-kit/skills"
  cp "$repository_root/plugins/golfo-kit/plugin.json" "$marketplace/plugins/golfo-kit/"
  cp -R "$repository_root/plugins/golfo-kit/.claude-plugin" "$repository_root/plugins/golfo-kit/.codex-plugin" "$marketplace/plugins/golfo-kit/"
  mkdir -p "$marketplace/plugins/golfo-kit/skills/agent-ready-setup"
  cp -R "$skill_dir/assets" "$skill_dir/scripts" "$skill_dir/SKILL.md" "$marketplace/plugins/golfo-kit/skills/agent-ready-setup/"
  rule="$marketplace/plugins/golfo-kit/skills/agent-ready-setup/assets/common/rules/verify-changes.md"
  printf '\nContent of revision one.\n' >> "$rule"
  printf '\n# hook of revision one\n' >> "$marketplace/plugins/golfo-kit/skills/agent-ready-setup/assets/common/hooks/check-harness-consistency.sh"
  set_marketplace_version 1.0.0
  git -C "$marketplace" init -q
  git -C "$marketplace" add -A
  git -C "$marketplace" commit -qm "golfo-kit 1.0.0"
  first_revision="$(git -C "$marketplace" rev-parse HEAD)"
  printf 'Content of revision two.\n' >> "$rule"
  set_marketplace_version 2.0.0
  git -C "$marketplace" commit -qam "golfo-kit 2.0.0"
  second_revision="$(git -C "$marketplace" rev-parse HEAD)"
  git config --global "url.file:///$(native_path "$marketplace" | sed 's#^/##').insteadOf" "https://github.com/guidomodarelli/golfo-marketplace"
}

set_marketplace_version() {
  python3 - "$marketplace/plugins/golfo-kit" "$1" <<'PY'
import json, os, sys
for manifest in ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
    path = os.path.join(sys.argv[1], manifest)
    data = json.load(open(path, encoding="utf-8"))
    data["version"] = sys.argv[2]
    json.dump(data, open(path, "w", encoding="utf-8"), indent=2)
PY
}

write_manifest() {
  mkdir -p .agents
  printf '%s\n' "$1" > .agents/agent-ready.json
}

@test "without sources.golfoKit an apply projects the golfo-kit of the installed engine" {
  run_cli apply --stack node
  [ "$status" -eq 0 ]
  ! grep -Fq 'Content of revision' .agents/rules/verify-changes.md
  [ ! -e "$XDG_CACHE_HOME/agent-ready-setup/golfo-kit" ]
  [ "$(lock_value 'data["generator"]["version"]')" = "$(engine_version)" ]
}

@test "a pinned golfo-kit keeps its revision when the marketplace publishes a new one" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
  [ "$(lock_value '[data["source"][key] for key in ("kind", "revision", "origin", "version")]')" = \
    "['git', '$first_revision', 'https://github.com/guidomodarelli/golfo-marketplace', '1.0.0']" ]
  # The engine projected it: the lock names the engine, and its hooks are the engine's.
  [ "$(lock_value 'data["generator"]["version"]')" = "$(engine_version)" ]
  cmp -s .agents/hooks/check-harness-consistency.sh "$skill_dir/assets/common/hooks/check-harness-consistency.sh"

  # Recreating a deleted asset and applying again stay on revision one, while main is at two.
  rm .agents/rules/verify-changes.md
  run_cli apply
  [ "$status" -eq 0 ]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
  ! grep -Fq 'Content of revision two.' .agents/rules/verify-changes.md
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]
}

@test "agent-ready update golfo-kit --to adopts only that revision of golfo-kit" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]

  run_cli update golfo-kit --to main --dry-run
  [ "$status" -eq 0 ]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
  ! grep -Fq 'Content of revision two.' .agents/rules/verify-changes.md

  run_cli update golfo-kit --to main
  [ "$status" -eq 0 ]
  grep -Fq 'Content of revision two.' .agents/rules/verify-changes.md
  [ "$(lock_value '[data["source"][key] for key in ("revision", "version", "requestedRef")]')" = "['$second_revision', '2.0.0', 'main']" ]
}

@test "a declared ref is followed in auto and waits for an update when pinned" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "main"}}}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$second_revision" ]

  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "main", "updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  printf 'Content of revision three.\n' >> "$rule"
  git -C "$marketplace" commit -qam "golfo-kit 3.0.0"
  run_cli apply
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]
  run_cli update golfo-kit
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$(git -C "$marketplace" rev-parse HEAD)" ]
  grep -Fq 'Content of revision three.' .agents/rules/verify-changes.md
}

@test "SessionStart keeps a pinned golfo-kit and follows the ref of one in auto" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_SYNC_FOREGROUND=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]
  ! grep -Fq 'Content of revision two.' .agents/rules/verify-changes.md

  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "main"}}}'
  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_SYNC_FOREGROUND=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$second_revision" ]
  grep -Fq 'Content of revision two.' .agents/rules/verify-changes.md
  # The hook the repository runs is the engine's, never the one of the pinned revision.
  cmp -s .agents/hooks/check-harness-consistency.sh "$skill_dir/assets/common/hooks/check-harness-consistency.sh"
}

@test "status says when the installed plugin brings a newer golfo-kit than the pinned one" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  run_cli status --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"golfo-kit stays at 1.0.0 (${first_revision:0:12}); the installed plugin brings $(engine_version)"* ]]
  [[ "$output" == *"Adopt it with: agent-ready update golfo-kit"* ]]
}

@test "update --to needs exactly one source and golfo-kit is always a known source" {
  run_cli update --to main
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"--to needs exactly one source"* ]]
  run_cli update golfo-kit acme --to main
  [ "$status" -eq 2 ]
  run_cli update nonexistent
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"the sources are: golfo-kit"* ]]
}

@test "a revision that cannot be fetched stops the apply before writing" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to 0123456789abcdef0123456789abcdef01234567
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"could not download commit 0123456789abcdef0123456789abcdef01234567"* ]]
  [ ! -e .agents/agent-ready.lock.json ]
  [ ! -e .agents/rules ]
}

# A session start hands the sync to a detached process; this waits for its report.
wait_for_background_update() {
  local attempt
  for attempt in $(seq 1 300); do
    if [ -n "$(find "$XDG_CACHE_HOME/agent-ready-setup/updates" -name '*.json' 2>/dev/null | head -n 1)" ] && \
      [ "$(find "$XDG_CACHE_HOME/agent-ready-setup/updates" -name '*.lock' 2>/dev/null | wc -l)" -eq 0 ]; then
      return 0
    fi
    sleep 0.2
  done
  echo "the background update did not finish" >&2
  return 1
}

@test "an apply downloads the pinned revision it lost from the cache, even with updates.refresh off" {
  write_manifest '{"profiles": ["node"], "updates": {"refresh": false}, "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"
  rm .agents/rules/verify-changes.md

  run_cli apply
  [ "$status" -eq 0 ]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]

  # Plan and status may compare offline with the installed content; they write nothing.
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"
  before="$(cat .agents/agent-ready.lock.json)"
  run_cli status --offline
  [[ "$stderr" == *"golfo-kit ${first_revision:0:12} is not in the cache of this machine yet"* ]]
  [ "$(cat .agents/agent-ready.lock.json)" = "$before" ]
}

@test "the check of a pinned repository compares with the pinned content" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  run_cli check --offline
  [ "$status" -eq 0 ]

  # Offline without the revision it cannot compare: the source is unavailable, nothing is outdated.
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"
  run_cli check --offline
  [ "$status" -eq 5 ]
  [[ "$output" == *"source not available"* ]]
  [[ "$output" == *"golfo-kit ${first_revision:0:12} is not in the cache of this machine yet"* ]]
  run_cli check
  [ "$status" -eq 0 ]
}

@test "a pinned repository follows a golfo-kit in auto on SessionStart" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  write_manifest '{"profiles": ["node"], "updates": {"mode": "pinned"}, "sources": {"golfoKit": {"updates": "auto", "ref": "main"}}}'

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_SYNC_FOREGROUND=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$second_revision" ]
  grep -Fq 'Content of revision two.' .agents/rules/verify-changes.md
}

@test "a session start resolves no golfo-kit ref in the foreground: the detached sync does" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "main"}}}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$second_revision" ]
  # The marketplace is unreachable from now on: only the cache answers.
  git config --global --remove-section "url.file:///$(native_path "$marketplace" | sed 's#^/##')"
  git config --global "url.file:///$(native_path "$test_root/unreachable" | sed 's#^/##').insteadOf" \
    "https://github.com/guidomodarelli/golfo-marketplace"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" != *"could not prepare the golfo-kit content"* ]]
  wait_for_background_update
  [ "$(lock_value 'data["source"]["revision"]')" = "$second_revision" ]
}

# An installed plugin outside the repository, so a test can change its engine.
install_engine_copy() {
  installed_plugin="$test_root/installed/golfo-kit"
  engine_copy="$installed_plugin/skills/agent-ready-setup"
  mkdir -p "$engine_copy"
  cp "$repository_root/plugins/golfo-kit/plugin.json" "$installed_plugin/"
  cp -R "$repository_root/plugins/golfo-kit/.claude-plugin" "$repository_root/plugins/golfo-kit/.codex-plugin" "$installed_plugin/"
  cp -R "$skill_dir/assets" "$skill_dir/scripts" "$skill_dir/SKILL.md" "$engine_copy/"
}

@test "a new engine does not stop the sync of a pinned golfo-kit" {
  install_engine_copy
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  # Only the engine changes: a hook, which is never pinned.
  printf '\n# hook of a new engine\n' >> "$engine_copy/assets/common/hooks/check-harness-consistency.sh"
  rm .agents/rules/verify-changes.md

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$engine_copy" AGENT_READY_SETUP_SYNC_FOREGROUND=1 \
    bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" != *"has a release pending"* ]]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
  cmp -s .agents/hooks/check-harness-consistency.sh "$engine_copy/assets/common/hooks/check-harness-consistency.sh"
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]
}

@test "a check that cannot fetch the pinned revision reports it unavailable under ci.mode warn" {
  write_manifest '{"profiles": ["node"], "ci": {"mode": "warn"}, "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"
  git config --global --remove-section "url.file:///$(native_path "$marketplace" | sed 's#^/##')"
  git config --global "url.file:///$(native_path "$test_root/unreachable" | sed 's#^/##').insteadOf" \
    "https://github.com/guidomodarelli/golfo-marketplace"

  run_cli check --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data["status"], data["ci"]["mode"])' | tr -d '\r')" = \
    "source-unavailable warn" ]
}

@test "profiles list and add read the catalog of the pinned golfo-kit" {
  git -C "$marketplace" checkout -q -b legacy "$first_revision"
  python3 - "$marketplace/plugins/golfo-kit/skills/agent-ready-setup/assets/profiles.json" <<'PY'
import json, sys
catalog = json.load(open(sys.argv[1], encoding="utf-8"))
catalog["profiles"]["legacy-capability"] = dict(catalog["profiles"]["business-flows"], description="Only in this revision.")
json.dump(catalog, open(sys.argv[1], "w", encoding="utf-8"), indent=2)
PY
  git -C "$marketplace" commit -qam "golfo-kit with a legacy capability"
  legacy_revision="$(git -C "$marketplace" rev-parse HEAD)"
  git -C "$marketplace" checkout -q main
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$legacy_revision"
  [ "$status" -eq 0 ]

  run_cli profiles list
  [ "$status" -eq 0 ]
  [[ "$output" == *"legacy-capability"* ]]
  run_cli profiles add legacy-capability
  [ "$status" -eq 0 ]
  [ "$(python3 -c 'import json; print(json.load(open(".agents/agent-ready.json", encoding="utf-8"))["profiles"])' | tr -d '\r')" = \
    "['node', 'legacy-capability']" ]
}

@test "offline, a followed ref this machine never resolved takes the revision of the lock" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "main"}}}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$second_revision" ]
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup/packs/latest"

  run_cli check --offline
  [ "$status" -eq 0 ]
}

@test "plan and status compare with the known revision of a ref when the remote cannot be reached" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "main"}}}'
  run_cli apply
  [ "$status" -eq 0 ]
  git config --global --remove-section "url.file:///$(native_path "$marketplace" | sed 's#^/##')"
  git config --global "url.file:///$(native_path "$test_root/unreachable" | sed 's#^/##').insteadOf" \
    "https://github.com/guidomodarelli/golfo-marketplace"

  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"could not resolve 'main'"* ]]
  run_cli status
  [ "$status" -eq 0 ]
  # An apply still needs the remote: it stops before writing.
  before="$(cat .agents/agent-ready.lock.json)"
  run_cli apply
  [ "$status" -ne 0 ]
  [ "$(cat .agents/agent-ready.lock.json)" = "$before" ]
}
