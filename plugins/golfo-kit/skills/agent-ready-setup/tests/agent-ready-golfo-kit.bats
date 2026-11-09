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

@test "two refs at the same commit record each its own requested ref" {
  write_manifest '{"profiles": ["node"]}'
  run_cli update golfo-kit --to "$second_revision"
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["requestedRef"]')" = "$second_revision" ]
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "main"}}}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["requestedRef"]')" = "main" ]
}

@test "offline, a ref nobody resolved yet makes the check report the source unavailable" {
  run_cli apply --stack node
  [ "$status" -eq 0 ]
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "never-resolved-branch"}}}'
  run_cli check --offline --json
  [ "$status" -eq 5 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' | tr -d '\r')" = "source-unavailable" ]
  [[ "$output" == *"never resolved 'never-resolved-branch'"* ]]
}

@test "status tells about a newer golfo-kit when the installed plugin is not a Git checkout" {
  install_engine_copy
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" status --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"golfo-kit stays at 1.0.0 (${first_revision:0:12}); the installed plugin brings $(engine_version)."* ]]
}

@test "a profile pack cannot take the name golfo-kit" {
  mkdir -p agent-packs/golfo-kit
  write_manifest '{"profiles": ["node"], "sources": {"packs": [{"name": "golfo-kit", "source": "path:./agent-packs/golfo-kit"}]}}'
  run_cli sources list
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"reserved for golfo-kit itself"* ]]
}

@test "apply --from-lock reproduces the golfo-kit revision of the lock on a fresh cache" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"ref": "main"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  before_lock="$(cat .agents/agent-ready.lock.json)"
  rule_sha="$(lock_value 'data["assets"][".agents/rules/verify-changes.md"]["sha256"]')"
  # Another machine: nothing in the cache, and the ref of the manifest is at another revision.
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup" .agents/rules/verify-changes.md

  run_cli apply --from-lock
  [ "$status" -eq 0 ]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
  [ "$(sha256sum .agents/rules/verify-changes.md | cut -d' ' -f1)" = "$rule_sha" ]
  [ "$(cat .agents/agent-ready.lock.json)" = "$before_lock" ]

  # Without --from-lock the ref in auto moves on.
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$second_revision" ]
}

@test "apply --from-lock stops before writing and names what does not match the lock" {
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  write_manifest '{"profiles": ["node", "business-flows"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  before_lock="$(cat .agents/agent-ready.lock.json)"

  run_cli apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"--from-lock cannot reproduce the lock, so nothing was changed"* ]]
  [[ "$stderr" == *"selection: the manifest resolves to"* ]]
  [ "$(cat .agents/agent-ready.lock.json)" = "$before_lock" ]
  [ ! -d .agents/skills/business-flows ] || ! ls .agents/rules | grep -q business

  # A content asset whose sha256 the lock does not match: the source is named, the file is not recreated.
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  python3 - <<'PY'
import json
path = ".agents/agent-ready.lock.json"
lock = json.load(open(path, encoding="utf-8"))
lock["assets"][".agents/rules/verify-changes.md"]["sha256"] = "0" * 64
json.dump(lock, open(path, "w", encoding="utf-8"), indent=2)
PY
  rm .agents/rules/verify-changes.md
  run_cli apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"golfo-kit: .agents/rules/verify-changes.md does not match the sha256 of the lock"* ]]
  [ ! -e .agents/rules/verify-changes.md ]
}

@test "apply --from-lock lets the engine files follow the installed plugin" {
  install_engine_copy
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  printf '\n# hook of a new engine\n' >> "$engine_copy/assets/common/hooks/check-harness-consistency.sh"

  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" apply --from-lock
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"file(s) of the engine (hooks and their settings) follow the installed plugin"* ]]
  cmp -s .agents/hooks/check-harness-consistency.sh "$engine_copy/assets/common/hooks/check-harness-consistency.sh"
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
}

@test "apply --from-lock needs a lockfile, takes no selection and previews with --dry-run" {
  run_cli apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"--from-lock needs .agents/agent-ready.lock.json"* ]]
  run_cli apply --from-lock --profiles node
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"--from-lock applies the selection and revisions of the lock"* ]]

  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  rm .agents/rules/verify-changes.md
  run_cli apply --from-lock --dry-run
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/verify-changes.md ]
}

@test "apply --from-lock checks the texts the managed block of AGENTS.md is rendered with" {
  install_engine_copy
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" apply --stack node
  [ "$status" -eq 0 ]
  printf '\nA new centralization sentence.\n' >> "$engine_copy/assets/instruction-centralization.md"
  before_agents="$(cat AGENTS.md)"

  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"what AGENTS.md is rendered with (the centralization and proxy texts) does not match the lock"* ]]
  [ "$(cat AGENTS.md)" = "$before_agents" ]
}

@test "apply --from-lock aligns AGENTS.md with the pack revision of the lock, not a newer cached one" {
  pack_repository="$test_root/acme"
  cp -R "$skill_dir/assets/examples/acme-profile-pack" "$pack_repository"
  git -C "$pack_repository" init -q
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm initial
  git config --global "url.file:///$(native_path "$pack_repository" | sed 's#^/##').insteadOf" "https://packs.example.invalid/acme"
  write_manifest '{"profiles": ["node", "acme/kafka-interno"], "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme#main"}]}}'
  run_cli apply
  [ "$status" -eq 0 ]
  # The pack moves on and a preview brings its new revision into the cache; the lock stays.
  printf 'new rule\n' > "$pack_repository/profiles/kafka-interno/rules/acme-new.md"
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm advance
  run_cli plan
  before_lock="$(cat .agents/agent-ready.lock.json)"

  run_cli apply --from-lock
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/acme-new.md ]
  ! grep -Fq 'acme-new' AGENTS.md
  [ "$(cat .agents/agent-ready.lock.json)" = "$before_lock" ]
}

@test "apply --from-lock reproduces a lock with a retired asset the project kept" {
  run_cli apply --profiles node,business-flows
  [ "$status" -eq 0 ]
  rm .agents/rules/business-flows.md
  mkdir .agents/rules/business-flows.md
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["assets"][".agents/rules/business-flows.md"]["state"]')" = "retired-preserved" ]

  run_cli apply --from-lock
  [ "$status" -eq 0 ]
  [ -d .agents/rules/business-flows.md ]
}

@test "apply --from-lock verifies the content of an asset the lock records in conflict" {
  install_engine_copy
  agent_ready() { run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" "$@"; }
  agent_ready apply --stack node
  [ "$status" -eq 0 ]
  rm .agents/rules/verify-changes.md
  mkdir .agents/rules/verify-changes.md
  agent_ready apply
  [ "$(lock_value 'data["assets"][".agents/rules/verify-changes.md"]["state"]')" = "conflict" ]

  # The same sources reproduce the lock, conflict included.
  agent_ready apply --from-lock
  [ "$status" -eq 0 ]
  [ -d .agents/rules/verify-changes.md ]

  # The source changed what it publishes there: the lock cannot be reproduced.
  rmdir .agents/rules/verify-changes.md
  printf '\nAn edit of the source.\n' >> "$engine_copy/assets/common/rules/verify-changes.md"
  agent_ready apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"golfo-kit: .agents/rules/verify-changes.md does not match the sha256 of the lock"* ]]
  [ ! -e .agents/rules/verify-changes.md ]
}

# A branch of the marketplace from $2 whose golfo-kit catalog gets the fields $3; prints its commit.
catalog_branch() {
  git -C "$marketplace" checkout -q -b "$1" "$2"
  python3 - "$marketplace/plugins/golfo-kit/skills/agent-ready-setup/assets/profiles.json" "$3" <<'PY'
import json, sys
catalog = json.load(open(sys.argv[1], encoding="utf-8"))
catalog.update(json.loads(sys.argv[2]))
json.dump(catalog, open(sys.argv[1], "w", encoding="utf-8"), indent=2)
PY
  git -C "$marketplace" commit -qam "catalog of $1"
  git -C "$marketplace" rev-parse HEAD
  git -C "$marketplace" checkout -q main
}

@test "golfo-kit content that needs a newer engine stops before writing" {
  future_revision="$(catalog_branch future "$second_revision" '{"minEngine": "99.0.0"}')"
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  before_lock="$(cat .agents/agent-ready.lock.json)"

  run_cli update golfo-kit --to "$future_revision"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"the golfo-kit catalog needs the agent-ready-setup engine 99.0.0 or newer"* ]]
  [ "$(cat .agents/agent-ready.lock.json)" = "$before_lock" ]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
}

@test "update golfo-kit --dry-run shows its version jump and the changes it declares" {
  changelog_revision="$(catalog_branch changelog "$second_revision" '{"changes": [{"version": "2.0.0", "summary": "Rules renamed", "breaking": true}, {"version": "1.5.0", "summary": "A new rule"}, {"version": "1.0.0", "summary": "First"}]}')"
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]

  run_cli update golfo-kit --to "$changelog_revision" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"golfo-kit 1.0.0 -> 2.0.0  (major version jump)"* ]]
  [[ "$output" == *"! breaking 2.0.0: Rules renamed"* ]]
  [[ "$output" == *"- 1.5.0: A new rule"* ]]
  [[ "$output" != *"- 1.0.0: First"* ]]
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]
}

@test "a pre-release engine below the minEngine of the content stops before writing" {
  install_engine_copy
  python3 - "$installed_plugin" <<'PY'
import json, os, sys
for manifest in ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
    path = os.path.join(sys.argv[1], manifest)
    data = json.load(open(path, encoding="utf-8"))
    data["version"] = "1.0.0-rc.1"
    json.dump(data, open(path, "w", encoding="utf-8"), indent=2)
PY
  future_revision="$(catalog_branch rc "$second_revision" '{"minEngine": "1.0.0-rc.2"}')"
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'

  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$engine_copy/scripts/agent-ready" update golfo-kit --to "$future_revision"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"needs the agent-ready-setup engine 1.0.0-rc.2 or newer, and this installation runs golfo-kit 1.0.0-rc.1"* ]]
  [ ! -e .agents/agent-ready.lock.json ]
}

@test "the version golfo-kit's catalog declares is the version of its content" {
  declared_revision="$(catalog_branch declared "$first_revision" '{"version": "2.5.0", "changes": [{"version": "2.5.0", "summary": "Declared in the catalog"}]}')"
  write_manifest '{"profiles": ["node"], "sources": {"golfoKit": {"updates": "pinned"}}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["version"]')" = "1.0.0" ]

  run_cli update golfo-kit --to "$declared_revision" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"golfo-kit 1.0.0 -> 2.5.0  (major version jump)"* ]]
  [[ "$output" == *"- 2.5.0: Declared in the catalog"* ]]
  run_cli update golfo-kit --to "$declared_revision"
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["source"]["version"]')" = "2.5.0" ]
}

config_value() {
  run_cli config get "$1"
  [ "$status" -eq 0 ]
  printf '%s' "$output" | tr -d '\r'
}

@test "agent-ready preset delivered sets what a delivered solution needs, and each value can be overridden" {
  write_manifest '{"profiles": ["node"]}'
  # Without configuration nothing changes: updates stay auto.
  [ "$(config_value updates.mode)" = auto ]
  [ "$(config_value updates.fromLock)" = false ]
  run_cli preset
  [ "$status" -eq 0 ]
  [[ "$output" == *"* none"* ]]

  run_cli preset delivered
  [ "$status" -eq 0 ]
  [ "$(python3 -c 'import json; print(json.load(open(".agents/agent-ready.json"))["updates"]["preset"])' | tr -d '\r')" = delivered ]
  [ "$(config_value updates.mode)" = pinned ]
  [ "$(config_value sources.golfoKit.updates)" = pinned ]
  [ "$(config_value updates.refresh)" = false ]
  [ "$(config_value updates.fromLock)" = true ]
  [ "$(config_value ci.mode)" = fail ]
  run_cli config explain updates.fromLock
  [[ "$output" == *"preset updates.preset=delivered"* ]]

  run_cli config set updates.refresh true
  [ "$status" -eq 0 ]
  [ "$(config_value updates.refresh)" = true ]
  [ "$(config_value updates.mode)" = pinned ]
  run_cli preset
  [[ "$output" == *"* delivered"* ]]
  run_cli preset frozen
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"unknown preset 'frozen'"* ]]
}

@test "a delivered repository keeps its golfo-kit revision, and only an update adopts a new one" {
  write_manifest '{"profiles": ["node"], "updates": {"preset": "delivered"}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md

  # main is at revision two: a deleted asset comes back from the revision of the lock.
  rm .agents/rules/verify-changes.md
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"updates.fromLock: this run reproduces the lock"* ]]
  grep -Fq 'Content of revision one.' .agents/rules/verify-changes.md
  ! grep -Fq 'Content of revision two.' .agents/rules/verify-changes.md
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]

  run_cli update golfo-kit --to main
  [ "$status" -eq 0 ]
  grep -Fq 'Content of revision two.' .agents/rules/verify-changes.md
  [ "$(lock_value 'data["source"]["revision"]')" = "$second_revision" ]
}

@test "a delivered repository does not apply a selection changed by hand, only an explicit one" {
  write_manifest '{"profiles": ["node"], "updates": {"preset": "delivered"}}'
  run_cli update golfo-kit --to "$first_revision"
  [ "$status" -eq 0 ]
  python3 - <<'PY'
import json
path = ".agents/agent-ready.json"
manifest = json.load(open(path, encoding="utf-8"))
manifest["profiles"] = ["node", "browser"]
json.dump(manifest, open(path, "w", encoding="utf-8"), indent=2)
PY

  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"cannot reproduce the lock"*"selection"* ]]
  [ "$(lock_value 'data["profileOrder"]')" = "['node']" ]

  run_cli apply --profiles node,browser
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["profileOrder"]')" = "['node', 'browser']" ]
  [ "$(lock_value 'data["source"]["revision"]')" = "$first_revision" ]

  # profiles add|remove change the manifest and name the explicit apply that projects it.
  run_cli profiles remove browser
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"Run agent-ready apply --profiles node to project them"* ]]
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["profileOrder"]')" = "['node']" ]
}
