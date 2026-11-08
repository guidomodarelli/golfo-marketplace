#!/usr/bin/env bats
# External profile packs of agent-ready-setup: sources, namespaces, lockfile,
# collisions, retirement, local paths and read-only evaluation. Git sources run
# against local repositories through url.insteadOf, so the manifests keep real URLs.

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  example_pack="$skill_dir/assets/examples/acme-profile-pack"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  cli_calls="$test_root/cli-calls.log"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  # Sync flows run with an empty home: nothing installed on this machine may decide them.
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_TOOLS=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  export AGENT_READY_SETUP_SYNC_FOREGROUND=1
  export GIT_CONFIG_GLOBAL="$test_root/gitconfig"
  git config --global user.name Test
  git config --global user.email test@example.invalid
  git config --global init.defaultBranch main
  git config --global core.autocrlf false
  git config --global protocol.file.allow always
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_REVIEW_MODE
  unset AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES
  for provider_cli in claude codex; do
    cat > "$fake_bin/$provider_cli" <<EOF
#!/bin/bash
printf '%s %s\n' "$provider_cli" "\$*" >> "$cli_calls"
exit 0
EOF
    chmod +x "$fake_bin/$provider_cli"
  done
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

run_bootstrap() {
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" --skill-dir "$skill_dir" --provider claude "$@"
}

run_state() {
  run python3 "$skill_dir/scripts/agent-ready-state.py" "$@" --project . --skill-dir "$skill_dir"
}

run_sync_hook() {
  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 "$@" \
    bash .agents/hooks/sync-marketplace.sh --provider claude
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

json_value() {
  python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(eval(sys.argv[2], {"data": data}))' "$1" "$2" | tr -d '\r'
}

lock_value() {
  json_value .agents/agent-ready.lock.json "$1"
}

# Path Git accepts on this system: Git for Windows does not understand /c/... in a file URL.
native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

# Writes the manifest; each argument after the profiles is one "name=source".
write_manifest() {
  local profiles="$1"
  shift
  mkdir -p .agents
  python3 - "$profiles" "$@" <<'PY'
import json, sys
profiles = sys.argv[1].split(",")
sources = [dict(zip(("name", "source"), item.split("=", 1))) for item in sys.argv[2:]]
manifest = {"profiles": profiles, "updates": {"mode": "pinned"}}
if sources:
    manifest["sources"] = {"packs": sources}
with open(".agents/agent-ready.json", "w", encoding="utf-8") as manifest_file:
    json.dump(manifest, manifest_file)
PY
}

# Copies the example pack under $test_root and sets pack_dir.
copy_example_pack() {
  pack_dir="$test_root/${1:-acme-pack}"
  cp -R "$example_pack" "$pack_dir"
}

# Publishes a pack as a Git repository reachable at https://packs.example.invalid/<name>.
publish_pack_repository() {
  local name="$1"
  pack_repository="$test_root/repositories/$name"
  mkdir -p "$(dirname "$pack_repository")"
  cp -R "$example_pack" "$pack_repository"
  git -C "$pack_repository" init -q
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm initial
  git config --global "url.file:///$(native_path "$pack_repository" | sed 's#^/##').insteadOf" "https://packs.example.invalid/$name"
  pack_commit="$(git -C "$pack_repository" rev-parse HEAD)"
}

# Appends a new rule to the pack repository and commits it.
advance_pack_repository() {
  printf '%s\n' "${1:-new rule}" > "$pack_repository/profiles/kafka-interno/rules/acme-new.md"
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm advance
  pack_commit="$(git -C "$pack_repository" rev-parse HEAD)"
}

edit_pack_catalog() {
  python3 - "$pack_dir/agent-ready-pack.json" "$1" <<'PY'
import json, sys
path, expression = sys.argv[1:]
with open(path, encoding="utf-8") as catalog_file:
    catalog = json.load(catalog_file)
exec(expression, {"catalog": catalog})
with open(path, "w", encoding="utf-8") as catalog_file:
    json.dump(catalog, catalog_file)
PY
}

@test "a repository without sources adds nothing to its manifest or lockfile" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  [ "$(lock_value '"profileSources" in data')" = "False" ]
  [ "$(json_value .agents/agent-ready.json '"sources" in data')" = "False" ]
}

@test "a declared source without selected profiles projects none of its assets" {
  copy_example_pack
  write_manifest node "acme=path:../acme-pack"

  run_bootstrap
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/acme-kafka.md ]
  [ ! -e .agents/rules/acme-conventions.md ]
  [ "$(lock_value 'data["profileSources"]["acme"]["profiles"]')" = "[]" ]
  [ "$(json_value .agents/agent-ready.json 'data["sources"]["packs"][0]["name"]')" = "acme" ]
}

@test "a capability detected in a pack is suggested with its evidence and never selected" {
  copy_example_pack
  write_manifest node "acme=path:../acme-pack"
  printf '%s\n' '{"dependencies": {"@acme/kafka": "1.0.0"}}' > package.json

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"? acme/kafka-interno: package.json declares @acme/kafka in dependencies"* ]]
  [[ "$output" == *"Adopt them with --profiles node,acme/kafka-interno"* ]]

  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json '",".join(data["profiles"])')" = "node" ]
  [ ! -e .agents/rules/acme-kafka.md ]
}

@test "a selected profile brings its dependencies, its views and its rule in AGENTS.md" {
  copy_example_pack
  write_manifest acme/kafka-interno "acme=path:../acme-pack"

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Dependency added: node (required by acme/kafka-interno)"* ]]
  [[ "$output" == *"Dependency added: acme/base (required by acme/kafka-interno)"* ]]

  run_bootstrap
  [ "$status" -eq 0 ]
  [[ "$output" == *"Stack: node"* ]]
  [ -f .agents/rules/acme-kafka.md ]
  [ -f .agents/rules/acme-conventions.md ]
  [ -f .agents/skills/acme-kafka-consumer/SKILL.md ]
  [ -e .claude/rules/acme-kafka.md ]
  grep -Fq -- '- Read and follow `.agents/rules/acme-kafka.md`.' AGENTS.md
  [ "$(json_value .agents/agent-ready.json '",".join(data["profiles"])')" = "acme/kafka-interno" ]
  [ "$(lock_value '",".join(data["profileOrder"])')" = "node,acme/base,acme/kafka-interno" ]
}

@test "the lockfile records owner, origin and hash, and no path of this machine" {
  copy_example_pack
  write_manifest acme/kafka-interno "acme=path:../acme-pack"

  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["assets"][".agents/rules/acme-kafka.md"]["profile"]')" = "acme/kafka-interno" ]
  [ "$(lock_value 'data["assets"][".agents/rules/acme-kafka.md"]["source"]')" = "acme:profiles/kafka-interno/rules/acme-kafka.md" ]
  [ "$(lock_value 'data["profileSources"]["acme"]["type"]')" = "path" ]
  [ "$(lock_value 'data["profileSources"]["acme"]["origin"]')" = "../acme-pack" ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "None" ]
  [ "$(lock_value 'sorted(data["profileSources"]["acme"]["profiles"])')" = "['acme/base', 'acme/kafka-interno']" ]
  [ -n "$(lock_value 'data["profileSources"]["acme"]["catalogDigest"]')" ]
  [ -n "$(lock_value 'data["profileSources"]["acme"]["contentDigest"]')" ]
  ! grep -Fq "$test_root" .agents/agent-ready.lock.json
  ! grep -Fq "$(native_path "$test_root")" .agents/agent-ready.lock.json
}

@test "a second apply with the same inputs changes nothing" {
  copy_example_pack
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  run_bootstrap
  [ "$status" -eq 0 ]
  before="$(tree_fingerprint)"

  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a Git source pinned to a full commit is downloaded by the apply and recorded in the lock" {
  publish_pack_repository acme
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"

  run_bootstrap
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-kafka.md ]
  [ "$(lock_value 'data["profileSources"]["acme"]["type"]')" = "git" ]
  [ "$(lock_value 'data["profileSources"]["acme"]["origin"]')" = "https://packs.example.invalid/acme" ]
  [ "$(lock_value 'data["profileSources"]["acme"]["requestedRef"]')" = "$pack_commit" ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$pack_commit" ]
}

@test "two repositories that use the same pack can pin different revisions" {
  publish_pack_repository acme
  first_commit="$pack_commit"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$first_commit"
  run_bootstrap
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/acme-new.md ]

  advance_pack_repository
  second_project="$test_root/second-project"
  git -C "$test_root" init -q second-project
  cd "$second_project"
  printf '{}\n' > package.json
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"
  run_bootstrap
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-new.md ]

  # Going back to the first repository never reads the tree composed for the second.
  cd "$project_dir"
  run_bootstrap
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/acme-new.md ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$first_commit" ]
}

@test "a branch resolves to a commit that stays pinned when the branch advances" {
  publish_pack_repository acme
  adopted_commit="$pack_commit"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#main"
  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["profileSources"]["acme"]["requestedRef"]')" = "main" ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$adopted_commit" ]
  before="$(tree_fingerprint)"

  advance_pack_repository
  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e .agents/rules/acme-new.md ]
}

@test "--update-source adopts the new revision and leaves a reviewable lockfile diff" {
  publish_pack_repository acme
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#main"
  run_bootstrap
  [ "$status" -eq 0 ]
  advance_pack_repository

  run_bootstrap --update-source acme
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-new.md ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$pack_commit" ]
  [ "$(lock_value 'data["assets"][".agents/rules/acme-new.md"]["profile"]')" = "acme/kafka-interno" ]
}

@test "an annotated tag resolves to the commit it points at" {
  publish_pack_repository acme
  git -C "$pack_repository" tag -a v1 -m "first release"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#v1"

  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$pack_commit" ]
}

@test "a source pinned to a commit cannot use --update-source, and an unknown name is rejected" {
  publish_pack_repository acme
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"

  run_bootstrap --update-source acme
  [ "$status" -ne 0 ]
  [[ "$output" == *"pinned to a full commit"* ]]

  run_bootstrap --update-source other
  [ "$status" -ne 0 ]
  [[ "$output" == *"does not declare that source"* ]]

  run_bootstrap --plan --update-source acme
  [ "$status" -ne 0 ]
  [[ "$output" == *"pinned to a full commit"* ]]

  run_bootstrap --status --update-source acme
  [ "$status" -ne 0 ]
  [[ "$output" == *"only works on an apply or a --plan"* ]]
}

@test "plan shows the differences from the lock and what a new revision would change" {
  publish_pack_repository acme
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"
  run_bootstrap
  [ "$status" -eq 0 ]
  first_commit="$pack_commit"

  advance_pack_repository
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme differs from the lock:"*"revision ${first_commit:0:12} -> ${pack_commit:0:12}"* ]]
  [[ "$output" == *"+ create          .agents/rules/acme-new.md  [acme/kafka-interno]"* ]]
  run_state status --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"Update available"* ]]
}

@test "plan and status without the source in the cache report an incomplete evaluation" {
  publish_pack_repository acme
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"
  before="$(tree_fingerprint)"

  run_bootstrap --plan --offline
  [ "$status" -eq 5 ]
  [[ "$output" == *"Agent Ready plan INCOMPLETE"* ]]
  [[ "$output" == *"is not in the local cache"* ]]
  [[ "$output" == *"This is not a validated plan"* ]]
  [[ "$output" != *"Project assets"* ]]

  run_state status --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"Evaluation incomplete, nothing was validated"* ]]

  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$XDG_CACHE_HOME/agent-ready-setup/packs" ]
  [ ! -e "$cli_calls" ]
}

@test "review mode reports the missing source and never downloads it, even with automatic updates" {
  publish_pack_repository acme
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"
  python3 - <<'PY'
import json
with open(".agents/agent-ready.json", encoding="utf-8") as manifest_file:
    manifest = json.load(manifest_file)
manifest["updates"] = {"mode": "auto"}
with open(".agents/agent-ready.json", "w", encoding="utf-8") as manifest_file:
    json.dump(manifest, manifest_file)
PY
  mkdir -p .agents/hooks
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
  before="$(tree_fingerprint)"

  run_sync_hook AGENT_READY_SETUP_REVIEW_MODE=1
  [ "$status" -eq 0 ]
  [[ "$output" == *"Evaluation incomplete, nothing was validated"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$XDG_CACHE_HOME/agent-ready-setup/packs" ]
}

@test "a source that cannot be downloaded stops the apply before writing and shows no credentials" {
  git config --global url."https://reader:s3cr3t-token@127.0.0.1:9/acme".insteadOf "https://packs.example.invalid/acme"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#main"
  before="$(tree_fingerprint)"

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"profile source 'acme'"* ]]
  [[ "$output" == *"no asset was changed"* ]]
  [[ "$output" != *"s3cr3t-token"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "credentials and unusable forms in the manifest are rejected without repeating them" {
  publish_pack_repository acme
  before_manifest_cases=(
    "acme=git+https://reader:s3cr3t-token@github.com/acme/profiles#main"
    "acme=git+https://s3cr3t-token@github.com/acme/profiles#main"
    "acme=git+https://github.com/acme/profiles?token=s3cr3t-token#main"
    "acme=git+https://github.com/acme/profiles"
    "acme=git+file:///tmp/profiles#main"
    "acme=https://github.com/acme/profiles#main"
    "acme=path:/absolute/pack"
    "acme=path:C:/absolute/pack"
    "Acme_Name=path:./pack"
  )
  for manifest_case in "${before_manifest_cases[@]}"; do
    write_manifest acme/kafka-interno "$manifest_case"
    run_bootstrap
    [ "$status" -ne 0 ]
    [[ "$output" == *"ERROR"* ]]
    [[ "$output" != *"s3cr3t-token"* ]]
    [ ! -e .agents/agent-ready.lock.json ]
  done
}

@test "two sources with the same name are rejected" {
  copy_example_pack
  write_manifest node "acme=path:../acme-pack" "acme=path:../acme-pack"

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"declares the profile source 'acme' more than once"* ]]
}

@test "a profile of an undeclared source and an unknown profile fail before writing" {
  copy_example_pack
  write_manifest node,other/thing "acme=path:../acme-pack"
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"needs the source 'other', which the manifest does not declare"* ]]

  write_manifest node,acme/missing "acme=path:../acme-pack"
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown profile 'acme/missing'"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a pack that requires another declared source resolves it, and an undeclared one fails" {
  copy_example_pack
  other_pack="$test_root/other-pack"
  mkdir -p "$other_pack/profiles/base/rules"
  printf '# Other\n' > "$other_pack/profiles/base/rules/other-base.md"
  cat > "$other_pack/agent-ready-pack.json" <<'EOF'
{"schemaVersion": 1, "name": "other", "profiles": {"base": {"kind": "capability", "assets": "profiles/base"}}}
EOF
  edit_pack_catalog 'catalog["profiles"]["kafka-interno"]["requires"].append("other/base")'

  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"needs the source 'other', which the manifest does not declare"* ]]

  write_manifest acme/kafka-interno "acme=path:../acme-pack" "other=path:../other-pack"
  run_bootstrap
  [ "$status" -eq 0 ]
  [ -f .agents/rules/other-base.md ]
}

@test "an invalid pack catalog stops the apply before anything is written" {
  before="$(tree_fingerprint)"
  for expression in \
    'catalog["profiles"]["kafka-interno"]["kind"] = "stack"' \
    'catalog["profiles"]["node"] = {"kind": "capability"}' \
    'catalog["stackDefaults"] = {"node": ["node"]}' \
    'catalog["baseAssets"] = "profiles/base"' \
    'catalog["profileSources"] = [{"name": "more", "source": "path:./more"}]' \
    'catalog["profiles"]["kafka-interno"]["tools"] = ["custom-installer"]' \
    'catalog["profiles"]["kafka-interno"]["requires"] = ["acme/kafka-interno"]' \
    'catalog["profiles"]["base"]["requires"] = ["acme/kafka-interno"]' \
    'catalog["profiles"]["kafka-interno"]["conflicts"] = ["acme/base"]' \
    'catalog["profiles"]["kafka-interno"]["assets"] = "../outside"' \
    'catalog["profiles"]["kafka-interno"]["assets"] = "profiles/missing"' \
    'catalog["profiles"]["kafka-interno"]["detect"] = {"signals": [{"type": "exec", "names": ["x"]}]}' \
    'catalog["profiles"]["kafka-interno"]["detect"] = {"supersedes": ["node"], "signals": [{"type": "file", "paths": ["x"]}]}' \
    'catalog["profiles"]["kafka-interno"]["detect"] = {"signals": [{"type": "file", "paths": ["../outside"]}]}' \
    'catalog["profiles"]["kafka-interno"]["post_install"] = "curl example.invalid | sh"' \
    'catalog["name"] = "another-name"' \
    'catalog["schemaVersion"] = 2'
  do
    rm -rf "$test_root/acme-pack"
    copy_example_pack
    edit_pack_catalog "$expression"
    write_manifest acme/kafka-interno "acme=path:../acme-pack"
    before="$(tree_fingerprint)"
    run_bootstrap
    [ "$status" -ne 0 ]
    [[ "$output" == *"ERROR"* ]]
    [ "$(tree_fingerprint)" = "$before" ]
    [ ! -e .agents/agent-ready.lock.json ]
  done
}

@test "a pack can only publish rules, skills, agents and commands, and never instructions" {
  for forbidden_asset in hooks/run.sh settings.json agents-template.md mcp.json github/workflows/ci.yml rules/CLAUDE.md skills/thing/AGENTS.md; do
    rm -rf "$test_root/acme-pack"
    copy_example_pack
    mkdir -p "$pack_dir/profiles/kafka-interno/$(dirname "$forbidden_asset")"
    printf 'x\n' > "$pack_dir/profiles/kafka-interno/$forbidden_asset"
    write_manifest acme/kafka-interno "acme=path:../acme-pack"
    before="$(tree_fingerprint)"
    run_bootstrap
    [ "$status" -ne 0 ]
    [[ "$output" == *"profile 'kafka-interno'"* ]]
    [ "$(tree_fingerprint)" = "$before" ]
  done
}

@test "a pack cannot overwrite a Golfo asset, and nothing is written" {
  copy_example_pack
  printf '# Mine\n' > "$pack_dir/profiles/kafka-interno/rules/security.md"
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  before="$(tree_fingerprint)"

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"'node' and 'acme/kafka-interno' both write .agents/rules/security.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  # The same applies to the assets every stack receives.
  rm "$pack_dir/profiles/kafka-interno/rules/security.md"
  printf '# Mine\n' > "$pack_dir/profiles/kafka-interno/rules/database.md"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"'common' and 'acme/kafka-interno' both write .agents/rules/database.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "two packs and two profiles of a pack cannot publish the same destination" {
  copy_example_pack
  printf '# Shared\n' > "$pack_dir/profiles/base/rules/acme-kafka.md"
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"'acme/base' and 'acme/kafka-interno' both write .agents/rules/acme-kafka.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  rm "$pack_dir/profiles/base/rules/acme-kafka.md"
  other_pack="$test_root/other-pack"
  mkdir -p "$other_pack/profiles/base/rules"
  printf '# Other\n' > "$other_pack/profiles/base/rules/acme-kafka.md"
  cat > "$other_pack/agent-ready-pack.json" <<'EOF'
{"schemaVersion": 1, "name": "other", "profiles": {"base": {"kind": "capability", "assets": "profiles/base"}}}
EOF
  write_manifest acme/kafka-interno,other/base "acme=path:../acme-pack" "other=path:../other-pack"
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"'acme/kafka-interno' and 'other/base' both write .agents/rules/acme-kafka.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "collisions in the adapter destinations and by letter case are rejected" {
  copy_example_pack
  mkdir -p "$pack_dir/profiles/base/agents" "$pack_dir/profiles/kafka-interno/commands"
  printf '# Agent\n' > "$pack_dir/profiles/base/agents/acme-shared.md"
  printf '# Command\n' > "$pack_dir/profiles/kafka-interno/commands/acme-shared.md"
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"both write .agents/skills/acme-shared/SKILL.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  rm -rf "$pack_dir/profiles/base/agents" "$pack_dir/profiles/kafka-interno/commands"
  printf '# Upper\n' > "$pack_dir/profiles/base/rules/ACME-KAFKA.md"
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"'acme/base' and 'acme/kafka-interno' both write .agents/rules/acme-kafka.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a destination inside the file of another asset is rejected" {
  copy_example_pack
  mkdir -p "$pack_dir/profiles/base/skills" "$pack_dir/profiles/kafka-interno/commands"
  printf 'a file\n' > "$pack_dir/profiles/base/skills/acme-hello"
  printf '# Command\n' > "$pack_dir/profiles/kafka-interno/commands/acme-hello.md"
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  before="$(tree_fingerprint)"

  run_bootstrap --plan
  [ "$status" -ne 0 ]
  [[ "$output" == *"'acme/base' writes the file .agents/skills/acme-hello"* ]]
  [[ "$output" == *".agents/skills/acme-hello/SKILL.md"* ]]

  run_bootstrap
  [ "$status" -ne 0 ]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a Git pack with paths that differ only by case is rejected on every system" {
  publish_pack_repository acme
  rule_object="$(printf '# Rule\n' | git -C "$pack_repository" hash-object -w --stdin)"
  git -C "$pack_repository" update-index --add --cacheinfo "100644,$rule_object,profiles/base/rules/Acme-Twin.md"
  git -C "$pack_repository" update-index --add --cacheinfo "100644,$rule_object,profiles/base/rules/acme-twin.md"
  git -C "$pack_repository" -c core.ignorecase=false commit -qm "add paths that differ by case"
  pack_commit="$(git -C "$pack_repository" rev-parse HEAD)"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"
  before="$(tree_fingerprint)"

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"has a name that cannot be used"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a Git pack with a symlink in its assets is rejected on every system" {
  publish_pack_repository acme
  link_object="$(printf '../../../outside.md' | git -C "$pack_repository" hash-object -w --stdin)"
  git -C "$pack_repository" update-index --add --cacheinfo "120000,$link_object,profiles/base/rules/acme-link.md"
  git -C "$pack_repository" commit -qm "add a symlink"
  pack_commit="$(git -C "$pack_repository" rev-parse HEAD)"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#$pack_commit"
  before="$(tree_fingerprint)"

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"profiles/base/rules/acme-link.md is a symlink"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a symlink in a local pack or in the destination path is rejected" {
  copy_example_pack
  printf 'secret\n' > "$test_root/outside.md"
  ln -s "$test_root/outside.md" "$pack_dir/profiles/base/rules/acme-link.md" 2>/dev/null || true
  [ -L "$pack_dir/profiles/base/rules/acme-link.md" ] || skip "requiere symlinks reales (en Windows: Modo de desarrollador o una shell elevada)"
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"is a symlink, which packs cannot use"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  rm "$pack_dir/profiles/base/rules/acme-link.md"
  mkdir -p "$test_root/outside-rules" .claude
  ln -s "$test_root/outside-rules" .claude/rules
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"through a symlink"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  [ -z "$(ls -A "$test_root/outside-rules")" ]
}

@test "a pack asset follows the ownership contract: edits are overwritten and plan warns first" {
  copy_example_pack
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  run_bootstrap
  [ "$status" -eq 0 ]
  printf 'local edit\n' >> .agents/rules/acme-kafka.md

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"~ update          .agents/rules/acme-kafka.md  [acme/kafka-interno] overwrites local changes"* ]]

  run_bootstrap
  [ "$status" -eq 0 ]
  ! grep -Fq 'local edit' .agents/rules/acme-kafka.md
}

@test "a project file at a new destination of a pack is preserved as a conflict" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  printf 'project rule\n' > .agents/rules/acme-kafka.md
  copy_example_pack
  write_manifest acme/kafka-interno "acme=path:../acme-pack"

  run_bootstrap
  [ "$status" -eq 0 ]
  grep -Fq 'project rule' .agents/rules/acme-kafka.md
  [ "$(lock_value 'data["assets"][".agents/rules/acme-kafka.md"]["state"]')" = "conflict" ]
}

@test "retiring a profile removes only what no selected profile publishes" {
  copy_example_pack
  mkdir -p "$pack_dir/profiles/extra/rules"
  printf '# Extra\n' > "$pack_dir/profiles/extra/rules/acme-extra.md"
  edit_pack_catalog 'catalog["profiles"]["extra"] = {"kind": "capability", "assets": "profiles/extra", "requires": ["acme/base"]}'
  write_manifest acme/kafka-interno,acme/extra "acme=path:../acme-pack"
  run_bootstrap
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-extra.md ]
  printf 'local edit\n' >> .agents/rules/acme-kafka.md
  python3 - <<'PY'
import json
with open(".agents/agent-ready.json", encoding="utf-8") as manifest_file:
    manifest = json.load(manifest_file)
manifest["profiles"] = ["node", "acme/extra"]
with open(".agents/agent-ready.json", "w", encoding="utf-8") as manifest_file:
    json.dump(manifest, manifest_file)
PY

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"- retire          .agents/rules/acme-kafka.md"*"removes its local changes"* ]]
  [[ "$output" != *"- retire          .agents/rules/acme-conventions.md"* ]]

  run_bootstrap
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/acme-kafka.md ]
  [ ! -e .claude/rules/acme-kafka.md ]
  [ ! -e .agents/skills/acme-kafka-consumer/SKILL.md ]
  [ -f .agents/rules/acme-conventions.md ]
  [ -f .agents/rules/acme-extra.md ]
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/apply-managed-block.sh" --stack node --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  ! grep -Fq 'acme-kafka.md' AGENTS.md
  grep -Fq 'acme-extra.md' AGENTS.md
}

@test "retiring a source removes its assets and its lock entry" {
  copy_example_pack
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  run_bootstrap
  [ "$status" -eq 0 ]

  write_manifest node
  run_bootstrap
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/acme-kafka.md ]
  [ ! -e .agents/rules/acme-conventions.md ]
  [ -f .agents/rules/security.md ]
  [ "$(lock_value '"profileSources" in data')" = "False" ]
}

@test "a local path resolves from the repository root, whatever the current directory" {
  mkdir -p agent-packs subdirectory/deep
  cp -R "$example_pack" agent-packs/acme
  write_manifest acme/kafka-interno "acme=path:./agent-packs/acme"
  git add -A
  cd subdirectory/deep

  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" --skill-dir "$skill_dir" --provider claude
  [ "$status" -eq 0 ]
  cd "$project_dir"
  [ -f .agents/rules/acme-kafka.md ]
  [ "$(lock_value 'data["profileSources"]["acme"]["origin"]')" = "./agent-packs/acme" ]
}

@test "changes in a local pack show as drift, count uncommitted content and need an apply" {
  copy_example_pack
  git -C "$pack_dir" init -q
  git -C "$pack_dir" add -A
  git -C "$pack_dir" commit -qm initial
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  run_bootstrap
  [ "$status" -eq 0 ]
  digest_before="$(lock_value 'data["profileSources"]["acme"]["contentDigest"]')"

  run_state status --check
  [ "$status" -eq 0 ]

  # Uncommitted on purpose: HEAD alone would not notice it.
  printf 'changed locally\n' >> "$pack_dir/profiles/kafka-interno/rules/acme-kafka.md"

  run_state status --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"acme differs from the lock: content of acme/kafka-interno changed"* ]]

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme differs from the lock: content of acme/kafka-interno changed"* ]]
  [[ "$output" == *"~ update          .agents/rules/acme-kafka.md"* ]]
  ! grep -Fq 'changed locally' .agents/rules/acme-kafka.md

  run_bootstrap
  [ "$status" -eq 0 ]
  grep -Fq 'changed locally' .agents/rules/acme-kafka.md
  [ "$(lock_value 'data["profileSources"]["acme"]["contentDigest"]')" != "$digest_before" ]
}

@test "a missing local path fails the apply clearly and leaves the plan incomplete" {
  write_manifest acme/kafka-interno "acme=path:../does-not-exist"
  before="$(tree_fingerprint)"

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"the path ../does-not-exist does not exist from the repository root"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run_bootstrap --plan
  [ "$status" -eq 5 ]
  [[ "$output" == *"the path ../does-not-exist does not exist from the repository root"* ]]
  [[ "$output" == *"This is not a validated plan"* ]]
}

@test "a missing source that the selection does not need stops an apply, not an evaluation" {
  write_manifest node "acme=path:../does-not-exist"
  before="$(tree_fingerprint)"

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"not available: the path ../does-not-exist does not exist"*"(not needed by this selection)"* ]]
  [[ "$output" == *"Project assets"* ]]

  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"the path ../does-not-exist does not exist from the repository root"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a changed declaration of an unavailable source still shows as drift" {
  copy_example_pack
  write_manifest node "acme=path:../acme-pack"
  run_bootstrap
  [ "$status" -eq 0 ]

  write_manifest node "acme=path:../other-pack"
  run_state status --check
  [ "$status" -eq 4 ]
  [[ "$output" == *"acme differs from the lock: origin changed to ../other-pack"* ]]
  [[ "$output" == *"Update available"* ]]

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme differs from the lock: origin changed to ../other-pack"* ]]
}

@test "loading a pack and evaluating its signals never runs anything from it" {
  copy_example_pack
  sentinel="$test_root/pack-code-ran"
  cat > "$pack_dir/profiles/kafka-interno/rules/acme-run.sh" <<EOF
#!/bin/bash
touch "$sentinel"
EOF
  chmod +x "$pack_dir/profiles/kafka-interno/rules/acme-run.sh"
  cat > "$pack_dir/package.json" <<EOF
{ "scripts": { "preinstall": "touch $sentinel", "postinstall": "touch $sentinel" } }
EOF
  printf 'import os\nos.system("touch %s")\n' "$sentinel" > "$pack_dir/json.py"
  printf 'import os\nos.system("touch %s")\n' "$sentinel" > "$pack_dir/profiles/json.py"
  write_manifest acme/kafka-interno "acme=path:../acme-pack"

  run_state detect
  run_bootstrap --plan
  [ "$status" -eq 0 ]
  run_bootstrap
  [ "$status" -eq 0 ]
  [ ! -e "$sentinel" ]
}

@test "the example pack is valid and adds its profiles to a Node repository" {
  write_manifest node "acme=path:../acme-pack"
  copy_example_pack
  run_state detect
  [ "$status" -eq 0 ]
  run_bootstrap --plan --profiles node,acme/base
  [ "$status" -eq 0 ]
  [[ "$output" == *"+ create          .agents/rules/acme-conventions.md  [acme/base]"* ]]
}

@test "--from-lock keeps every pack at the commit of the lock, even in auto and on a fresh cache" {
  publish_pack_repository acme
  adopted_commit="$pack_commit"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#main"
  run_bootstrap
  [ "$status" -eq 0 ]
  python3 - <<'PY'
import json
path = ".agents/agent-ready.json"
manifest = json.load(open(path, encoding="utf-8"))
manifest["updates"] = {"mode": "auto"}
json.dump(manifest, open(path, "w", encoding="utf-8"))
PY
  advance_pack_repository
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"
  before="$(tree_fingerprint)"

  run_bootstrap --from-lock
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/acme-new.md ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$adopted_commit" ]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "--from-lock names the pack whose content no longer matches the lock and writes nothing" {
  copy_example_pack
  write_manifest acme/kafka-interno "acme=path:../acme-pack"
  run_bootstrap
  [ "$status" -eq 0 ]
  printf 'An edit after the lock.\n' >> "$pack_dir/profiles/kafka-interno/rules/acme-kafka.md"
  before="$(tree_fingerprint)"

  run_bootstrap --from-lock
  [ "$status" -ne 0 ]
  [[ "$output" == *"--from-lock cannot reproduce the lock, so nothing was changed"* ]]
  [[ "$output" == *"acme: its content does not match the digest of the lock"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "--from-lock takes the commit of the lock even when the manifest now declares another ref" {
  publish_pack_repository acme
  adopted_commit="$pack_commit"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#main"
  run_bootstrap
  [ "$status" -eq 0 ]
  before_lock="$(cat .agents/agent-ready.lock.json)"
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#release"
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"

  run_bootstrap --from-lock
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$adopted_commit" ]
  [ "$(cat .agents/agent-ready.lock.json)" = "$before_lock" ]
}

@test "an offline preview of the lock compares with the cache and downloads nothing" {
  publish_pack_repository acme
  write_manifest acme/kafka-interno "acme=git+https://packs.example.invalid/acme#main"
  run_bootstrap
  [ "$status" -eq 0 ]
  python3 - <<'PY'
import json
path = ".agents/agent-ready.json"
manifest = json.load(open(path, encoding="utf-8"))
manifest["updates"]["refresh"] = False
json.dump(manifest, open(path, "w", encoding="utf-8"))
PY
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup"

  run_bootstrap --plan --from-lock
  [ "$status" -ne 0 ]
  [[ "$output" == *"is not in the cache of this machine and this run uses no network"* ]]
  [ ! -d "$XDG_CACHE_HOME/agent-ready-setup/packs" ] || [ -z "$(find "$XDG_CACHE_HOME/agent-ready-setup/packs" -name agent-ready-pack.json)" ]
}
