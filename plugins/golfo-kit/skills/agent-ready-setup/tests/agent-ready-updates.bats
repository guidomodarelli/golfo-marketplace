#!/usr/bin/env bats
# How assets stay up to date: the update SessionStart runs detached, what pinned and
# auto do, what plan and status refresh, the CI check and each option that turns one
# of these mechanisms off. Git sources use local repositories through url.insteadOf.

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
  release_file="$test_root/release-the-cli"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  # Sync flows run with an empty home: nothing installed on this machine may decide them.
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_TOOLS=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  export GIT_CONFIG_GLOBAL="$test_root/gitconfig"
  git config --global user.name Test
  git config --global user.email test@example.invalid
  git config --global init.defaultBranch main
  git config --global core.autocrlf false
  git config --global protocol.file.allow always
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_REVIEW_MODE
  unset AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES AGENT_READY_SETUP_SYNC_FOREGROUND
  unset AGENT_READY_SETUP_CI AGENT_READY_SETUP_REFRESH AGENT_READY_SETUP_DETECTION
  for provider_cli in claude codex gh; do
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
  # A detached update may still be finishing; on Windows its open files block the removal.
  local removal_attempt
  for removal_attempt in $(seq 1 50); do
    rm -rf "$test_root" 2>/dev/null && return 0
    sleep 0.2
  done
  rm -rf "$test_root"
}

run_bootstrap() {
  run env PATH="$fake_bin:$PATH" bash "${source_copy:-$skill_dir}/scripts/bootstrap.sh" \
    --skill-dir "${source_copy:-$skill_dir}" --provider claude "$@"
}

# A later session: SessionStart with the source the test chose and no upgrade window.
run_session_start() {
  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="${source_copy:-$skill_dir}" "$@" \
    bash .agents/hooks/sync-marketplace.sh --provider claude
}

# The check as a CI pipeline runs it: no provider, no gh, whatever the "env" arguments set.
run_check() {
  run env PATH="$fake_bin:$PATH" "$@" python3 "${source_copy:-$skill_dir}/scripts/agent-ready-state.py" check \
    --project . --skill-dir "${source_copy:-$skill_dir}" ${check_flags:-}
}

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

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

# Writes the manifest: profiles, then a JSON object with any other field.
write_manifest() {
  local extra_fields='{}'
  [[ $# -lt 2 ]] || extra_fields="$2"
  mkdir -p .agents
  python3 - "$1" "$extra_fields" <<'PY'
import json, sys
manifest = {"profiles": sys.argv[1].split(",")}
manifest.update(json.loads(sys.argv[2]))
with open(".agents/agent-ready.json", "w", encoding="utf-8") as manifest_file:
    json.dump(manifest, manifest_file)
PY
}

publish_pack_repository() {
  local name="${1:-acme}"
  pack_repository="$test_root/repositories/$name"
  mkdir -p "$(dirname "$pack_repository")"
  cp -R "$example_pack" "$pack_repository"
  git -C "$pack_repository" init -q
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm initial
  git config --global "url.file:///$(native_path "$pack_repository" | sed 's#^/##').insteadOf" "https://packs.example.invalid/$name"
  pack_commit="$(git -C "$pack_repository" rev-parse HEAD)"
}

advance_pack_repository() {
  printf 'new rule\n' > "$pack_repository/profiles/kafka-interno/rules/acme-new.md"
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm advance
  pack_commit="$(git -C "$pack_repository" rev-parse HEAD)"
}

# A copy of the skill that tests can change, like a newer release.
copy_skill() {
  source_copy="$test_root/skill"
  cp -R "$skill_dir" "$source_copy"
}

release_new_golfo_version() {
  printf '\nA new sentence.\n' >> "$source_copy/assets/stacks/node/rules/testing.md"
}

update_report_path() {
  find "$XDG_CACHE_HOME/agent-ready-setup/updates" -name '*.json' 2>/dev/null | head -n 1
}

wait_for_background_update() {
  local attempt
  for attempt in $(seq 1 300); do
    local report
    report="$(update_report_path)"
    if [[ -n "$report" && "$(find "$XDG_CACHE_HOME/agent-ready-setup/updates" -name '*.lock' | wc -l)" -eq 0 ]]; then
      return 0
    fi
    sleep 0.2
  done
  echo "the background update did not finish" >&2
  return 1
}

@test "a manifest without options is in auto: the apply never writes a default" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json 'sorted(data)')" = "['profiles']" ]
  run python3 "$skill_dir/scripts/agent-ready-state.py" config --project . --format tsv
  [ "$status" -eq 0 ]
  [[ "$output" == *"updates.mode"$'\t'"auto"* ]]
  [[ "$output" == *"updates.refresh"$'\t'"true"* ]]

  run_bootstrap --updates pinned
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json 'data["updates"]')" = "{'mode': 'pinned'}" ]

  run_bootstrap --updates auto
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json '"updates" in data')" = "False" ]
}

@test "the apply keeps what a person wrote, also a value equal to a default" {
  write_manifest node '{"updates": {"mode": "auto", "refresh": false}, "ci": {"mode": "fail"}, "providers": ["codex"]}'
  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json 'sorted(data)')" = "['ci', 'profiles', 'providers', 'updates']" ]
  [ "$(json_value .agents/agent-ready.json 'data["updates"]')" = "{'mode': 'auto', 'refresh': False}" ]
  [ "$(json_value .agents/agent-ready.lock.json 'data["providers"]')" = "['codex']" ]
  before="$(cksum < .agents/agent-ready.json)"
  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(cksum < .agents/agent-ready.json)" = "$before" ]
}

@test "SessionStart with auto never waits: a blocked update does not hold the session" {
  copy_skill
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  release_new_golfo_version
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
until [ -e "$release_file" ]; do sleep 0.1; done
printf 'claude %s\n' "\$*" >> "$cli_calls"
EOF
  chmod +x "$fake_bin/claude"

  # If the hook waited for the provider CLI, this call would never return.
  run_session_start
  [ "$status" -eq 0 ]
  ! grep -Fq 'A new sentence' .agents/rules/testing.md

  touch "$release_file"
  wait_for_background_update
  grep -Fq 'A new sentence' .agents/rules/testing.md
  grep -Fq 'marketplace update' "$cli_calls"
}

@test "the result of a background update is reported once, in the next session" {
  copy_skill
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  release_new_golfo_version
  run_session_start
  [ "$status" -eq 0 ]
  wait_for_background_update

  run_session_start
  [ "$status" -eq 0 ]
  [[ "$output" == *"The last background update changed the repository: 1 updated"* ]]
  [[ "$output" == *"updated: .agents/rules/testing.md"* ]]
  wait_for_background_update

  run_session_start
  [ "$status" -eq 0 ]
  [[ "$output" != *"The last background update"* ]]
}

@test "auto follows the ref of a source in the background and the lock records the new commit" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["profileSources"]["acme"]["requestedRef"]')" = "main" ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$pack_commit" ]

  advance_pack_repository
  run_session_start
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/acme-new.md ]
  wait_for_background_update

  [ -f .agents/rules/acme-new.md ]
  [ "$(lock_value 'data["profileSources"]["acme"]["resolvedCommit"]')" = "$pack_commit" ]
  run_session_start
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme "*" -> ${pack_commit:0:12}"* ]]
}

@test "a machine that never saw a pack gets it from the background update" {
  publish_pack_repository
  write_manifest acme/kafka-interno "{\"sources\": {\"packs\": [{\"name\": \"acme\", \"source\": \"git+https://packs.example.invalid/acme#$pack_commit\"}]}}"
  run_bootstrap
  [ "$status" -eq 0 ]
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup/packs"
  rm .agents/rules/acme-kafka.md

  run_session_start
  [ "$status" -eq 0 ]
  wait_for_background_update
  [ -f .agents/rules/acme-kafka.md ]
}

@test "a pinned repository never applies on its own, and a later session reports what is pending" {
  copy_skill
  publish_pack_repository
  write_manifest acme/kafka-interno '{"updates": {"mode": "pinned"}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  before="$(tree_fingerprint)"
  advance_pack_repository
  release_new_golfo_version

  run_session_start
  [ "$status" -eq 0 ]
  [[ "$output" == *"Repository pinned"* ]]
  wait_for_background_update
  [ "$(tree_fingerprint)" = "$before" ]

  run_session_start
  [ "$status" -eq 0 ]
  [[ "$output" == *"ref main is at ${pack_commit:0:12}"* ]]
  [[ "$output" == *"Update available"* ]]
  wait_for_background_update
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a source can be pinned in a repository in auto, and its drift stops the sync with no call to run bootstrap" {
  cp -R "$example_pack" "$test_root/acme-pack"
  write_manifest acme/kafka-interno '{"sources": {"packs": [{"name": "acme", "source": "path:../acme-pack", "updates": "pinned"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  before="$(tree_fingerprint)"
  printf 'changed locally\n' >> "$test_root/acme-pack/profiles/kafka-interno/rules/acme-kafka.md"

  run_session_start AGENT_READY_SETUP_SYNC_FOREGROUND=1 AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1
  [ "$status" -eq 0 ]
  [[ "$output" == *"is pinned and differs from the lock"* ]]
  [[ "$output" == *"local projection skipped"* ]]
  [[ "$output" != *"bootstrap"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a pinned source without selected profiles keeps its lock entry after a sync" {
  cp -R "$example_pack" "$test_root/acme-pack"
  write_manifest node '{"sources": {"packs": [{"name": "acme", "source": "path:../acme-pack", "updates": "pinned"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  locked_digest="$(lock_value 'data["profileSources"]["acme"]["catalogDigest"]')"
  printf '{"schemaVersion": 1, "name": "acme", "profiles": {"base": {"kind": "capability", "assets": "profiles/base"}}}' > "$test_root/acme-pack/agent-ready-pack.json"

  run_session_start AGENT_READY_SETUP_SYNC_FOREGROUND=1 AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1
  [ "$status" -eq 0 ]
  [ "$(lock_value 'data["profileSources"]["acme"]["catalogDigest"]')" = "$locked_digest" ]
}

@test "a local source in auto adopts its changes in the sync" {
  cp -R "$example_pack" "$test_root/acme-pack"
  write_manifest acme/kafka-interno '{"sources": {"packs": [{"name": "acme", "source": "path:../acme-pack"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  printf 'changed locally\n' >> "$test_root/acme-pack/profiles/kafka-interno/rules/acme-kafka.md"

  run_session_start AGENT_READY_SETUP_SYNC_FOREGROUND=1 AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1
  [ "$status" -eq 0 ]
  grep -Fq 'changed locally' .agents/rules/acme-kafka.md
}

@test "a source in auto updates a pinned repository, unless golfo-kit has a release pending" {
  copy_skill
  publish_pack_repository
  write_manifest acme/kafka-interno '{"updates": {"mode": "pinned"}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main", "updates": "auto"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]

  advance_pack_repository
  run_session_start AGENT_READY_SETUP_SYNC_FOREGROUND=1 AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-new.md ]

  printf 'newer rule\n' > "$pack_repository/profiles/kafka-interno/rules/acme-newer.md"
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm newer
  release_new_golfo_version
  run_session_start AGENT_READY_SETUP_SYNC_FOREGROUND=1 AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1
  [ "$status" -eq 0 ]
  [[ "$output" == *"pins golfo-kit and has a release pending"* ]]
  [[ "$output" != *"bootstrap"* ]]
  [ ! -e .agents/rules/acme-newer.md ]
  ! grep -Fq 'A new sentence' .agents/rules/testing.md
}

@test "AGENT_READY_SETUP_UPDATES turns auto off on one machine without touching the manifest" {
  copy_skill
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  release_new_golfo_version
  before="$(tree_fingerprint)"

  run_session_start AGENT_READY_SETUP_UPDATES=pinned AGENT_READY_SETUP_SYNC_FOREGROUND=1 AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1
  [ "$status" -eq 0 ]
  [[ "$output" == *"Repository pinned"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  [ "$(json_value .agents/agent-ready.json '"updates" in data')" = "False" ]
}

@test "review mode starts no update, uses no network and writes nothing" {
  copy_skill
  publish_pack_repository
  write_manifest acme/kafka-interno '{"sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  advance_pack_repository
  release_new_golfo_version
  rm -f "$cli_calls"
  before="$(tree_fingerprint)"
  rm -rf "$pack_repository"

  run_session_start AGENT_READY_SETUP_REVIEW_MODE=1
  [ "$status" -eq 0 ]
  [[ "$output" == *"Review mode"* ]]
  sleep 1
  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$cli_calls" ]
  [ -z "$(update_report_path)" ]
}

@test "a local edit the background update overwrote is reported with its backup" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  printf 'local edit\n' >> .agents/rules/testing.md
  rm .agents/rules/security.md

  run_session_start
  [ "$status" -eq 0 ]
  wait_for_background_update
  ! grep -Fq 'local edit' .agents/rules/testing.md

  run_session_start
  [ "$status" -eq 0 ]
  [[ "$output" == *"The last background update changed the repository: 2 restored"* ]]
  [[ "$output" == *"restored: .agents/rules/testing.md"* ]]
  [[ "$output" == *"restored: .agents/rules/security.md"* ]]
  [[ "$output" == *"Local backups directory:"* ]]
}

@test "a sync that times out is stopped with its children before anything else can run" {
  marker="$test_root/child-kept-writing"
  cat > "$test_root/slow-sync.sh" <<EOF
#!/bin/bash
(sleep 3; touch "$marker") &
wait
EOF
  run python3 - "$skill_dir/scripts/agent-ready-state.py" "$test_root/slow-sync.sh" <<'PY'
import importlib.util, os, shutil, sys
spec = importlib.util.spec_from_file_location("agent_ready_state", sys.argv[1])
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)
output, status = state.run_sync([shutil.which("bash"), sys.argv[2]], os.getcwd(), dict(os.environ), 1)
print(status, output)
PY
  [ "$status" -eq 0 ]
  [[ "$output" == *"1 ERROR: the sync did not finish in 1 seconds and was stopped"* ]]
  sleep 4
  [ ! -e "$marker" ]
}

@test "a conflict the background update preserved is reported in the next session" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  rm .agents/rules/security.md
  mkdir .agents/rules/security.md

  run_session_start
  [ "$status" -eq 0 ]
  wait_for_background_update

  run_session_start
  [ "$status" -eq 0 ]
  [[ "$output" == *"The last background update reported: preserved conflict: .agents/rules/security.md"* ]]
}

@test "a failed background update is reported, changes nothing and stops retrying for a while" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  before="$(tree_fingerprint)"
  rm -rf "$pack_repository"

  run_session_start
  [ "$status" -eq 0 ]
  wait_for_background_update
  [ "$(tree_fingerprint)" = "$before" ]

  report="$(update_report_path)"
  python3 - "$report" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as report_file:
    report = json.load(report_file)
assert any("profile source" in problem or "profile sources" in problem for problem in report["problems"]), report
report["consecutiveFailures"] = 3
with open(sys.argv[1], "w", encoding="utf-8") as report_file:
    json.dump(report, report_file)
PY
  run_session_start
  [ "$status" -eq 0 ]
  [[ "$output" == *"The last background update reported:"* ]]
  wait_for_background_update
  [ "$(json_value "$report" 'data["consecutiveFailures"]')" = "3" ]
}

@test "plan and status refresh the cache by default and report a moved ref without writing" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"updates": {"mode": "pinned"}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  before="$(tree_fingerprint)"
  advance_pack_repository
  rm -f "$cli_calls"

  run_bootstrap --status
  [ "$status" -eq 0 ]
  [[ "$output" == *"ref main is at ${pack_commit:0:12}"* ]]
  [[ "$output" == *"Update available"* ]]
  grep -Fq 'marketplace update' "$cli_calls"

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"adopt it with --update-source acme"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "--offline uses neither the network nor the provider CLI" {
  publish_pack_repository
  write_manifest acme/kafka-interno "{\"updates\": {\"mode\": \"pinned\"}, \"sources\": {\"packs\": [{\"name\": \"acme\", \"source\": \"git+https://packs.example.invalid/acme\", \"ref\": \"main\"}]}}"
  run_bootstrap
  [ "$status" -eq 0 ]
  advance_pack_repository
  rm -rf "$pack_repository"
  rm -f "$cli_calls"

  run_bootstrap --plan --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"Offline plan"* ]]
  [[ "$output" != *"could not read"* ]]
  run_bootstrap --status --offline
  [ "$status" -eq 0 ]
  [ ! -e "$cli_calls" ]
}

@test "a refresh that fails compares with the cache and says so" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"updates": {"mode": "pinned"}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  rm -rf "$pack_repository"

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING: comparing with the local cache"* ]]
  [[ "$output" == *"Project assets"* ]]
}

@test "--offline is not an option of an apply" {
  run_bootstrap --stack node --offline
  [ "$status" -ne 0 ]
  [[ "$output" == *"--offline only works with --plan, --status or --config"* ]]
}

@test "updates.refresh false in the manifest keeps plan, status and a pinned SessionStart off the network" {
  write_manifest node '{"updates": {"mode": "pinned", "refresh": false}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json 'data["updates"]["refresh"]')" = "False" ]
  rm -f "$cli_calls"

  run_bootstrap --plan
  [ "$status" -eq 0 ]
  run_bootstrap --status
  [ "$status" -eq 0 ]
  run_session_start
  [ "$status" -eq 0 ]
  sleep 1
  [ ! -e "$cli_calls" ]
  [ -z "$(update_report_path)" ]
}

@test "AGENT_READY_SETUP_REFRESH turns the refresh off on one machine" {
  write_manifest node '{"updates": {"mode": "pinned"}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  rm -f "$cli_calls"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_REFRESH=off bash "$skill_dir/scripts/bootstrap.sh" --skill-dir "$skill_dir" --provider claude --plan
  [ "$status" -eq 0 ]
  [ ! -e "$cli_calls" ]
}

@test "detection off removes the signals and suggestions from the plan" {
  write_manifest node '{"detection": {"enabled": false}}'
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}, "devDependencies": {"@playwright/test": "1.0.0"}}' > package.json

  run_bootstrap --plan --offline
  [ "$status" -eq 0 ]
  [[ "$output" != *"Detection"* ]]
  [[ "$output" != *"Suggestions"* ]]
  [[ "$output" != *"Signals point to"* ]]
}

@test "detection off asks for an explicit selection in a repository without a manifest" {
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json
  before="$(tree_fingerprint)"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_DETECTION=off bash "$skill_dir/scripts/bootstrap.sh" --skill-dir "$skill_dir" --provider claude
  [ "$status" -ne 0 ]
  [[ "$output" == *"Detection is off"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_DETECTION=off bash "$skill_dir/scripts/bootstrap.sh" --skill-dir "$skill_dir" --provider claude --stack frontend
  [ "$status" -eq 0 ]
}

@test "the options of the manifest and the environment reject values they do not know" {
  for field in '"updates": {"mode": "sometimes"}' '"ci": {"mode": "maybe"}' '"updates": {"refresh": "later"}' '"detection": {"enabled": "partial"}'; do
    write_manifest node "{$field}"
    run_bootstrap --plan --offline
    [ "$status" -ne 0 ]
    [[ "$output" == *"project layer"* ]]
  done
  rm .agents/agent-ready.json

  run_check AGENT_READY_SETUP_CI=maybe
  [ "$status" -eq 2 ]
  [[ "$output" == *"configuration error"* ]]
  [[ "$output" == *"environment layer (AGENT_READY_SETUP_CI): 'ci.mode' must be one of fail, warn"* ]]
}

@test "a source accepts ref or a revision in its URL, not both, and a path takes no ref" {
  for source_entry in \
    '{"name": "acme", "source": "git+https://packs.example.invalid/acme#main", "ref": "main"}' \
    '{"name": "acme", "source": "git+https://packs.example.invalid/acme"}' \
    '{"name": "acme", "source": "path:../pack", "ref": "main"}' \
    '{"name": "acme", "source": "path:../pack", "updates": "sometimes"}' \
    '{"name": "acme", "source": "path:../pack", "extra": "field"}'
  do
    write_manifest node "{\"sources\": {\"packs\": [$source_entry]}}"
    run_bootstrap --plan --offline
    [ "$status" -ne 0 ]
    [[ "$output" == *"ERROR"* ]]
  done
}

@test "the check passes when everything is up to date and writes nothing" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/apply-managed-block.sh" --stack node --skill-dir "$skill_dir"
  before="$(tree_fingerprint)"
  rm -f "$cli_calls"

  run_check
  [ "$status" -eq 0 ]
  [[ "$output" == *"Agent Ready check: up to date (ci.mode: fail)"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  [ ! -e "$cli_calls" ]
}

@test "the check fails with a source out of date, also when it is pinned" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"updates": {"mode": "pinned"}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  advance_pack_repository

  run_check
  [ "$status" -eq 4 ]
  [[ "$output" == *"updates pending (ci.mode: fail)"* ]]
  [[ "$output" == *"profile source acme"*"ref main is at ${pack_commit:0:12}"* ]]
}

@test "a source pinned to a full commit is never out of date for the check" {
  publish_pack_repository
  write_manifest acme/kafka-interno "{\"sources\": {\"packs\": [{\"name\": \"acme\", \"source\": \"git+https://packs.example.invalid/acme#$pack_commit\"}]}}"
  run_bootstrap
  [ "$status" -eq 0 ]
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/apply-managed-block.sh" --stack node --skill-dir "$skill_dir"
  advance_pack_repository

  run_check
  [ "$status" -eq 0 ]
}

@test "the check fails with a new golfo-kit release and with committed assets out of date" {
  copy_skill
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  run_check
  [ "$status" -eq 0 ]

  printf 'local edit\n' >> .agents/rules/security.md
  rm .agents/rules/coding-style.md
  run_check
  [ "$status" -eq 4 ]
  [[ "$output" == *".agents/rules/security.md: modified"* ]]
  [[ "$output" == *".agents/rules/coding-style.md: missing"* ]]

  run_bootstrap
  [ "$status" -eq 0 ]
  release_new_golfo_version
  run_check
  [ "$status" -eq 4 ]
  [[ "$output" == *"golfo-kit: the lock has"* ]]
}

@test "the check fails when the selection differs from the lock, even with no file to change" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/apply-managed-block.sh" --stack node --skill-dir "$skill_dir"
  write_manifest node

  run_check
  [ "$status" -eq 4 ]
  [[ "$output" == *"the lock has the profiles node, browser; the selection resolves to node"* ]]
}

@test "the check fails when a CLAUDE.md proxy is missing, in the root or beside an AGENTS.md" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/apply-managed-block.sh" --stack node --skill-dir "$skill_dir"
  run_check
  [ "$status" -eq 0 ]

  rm CLAUDE.md
  mkdir -p services/billing
  printf '# Billing\n' > services/billing/AGENTS.md
  run_check
  [ "$status" -eq 4 ]
  [[ "$output" == *"CLAUDE.md: an apply would normalize it to the proxy"* ]]
  [[ "$output" == *"services/billing/CLAUDE.md: an apply would normalize it to the proxy"* ]]
}

@test "ci warn reports the same problems and passes" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"ci": {"mode": "warn"}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json 'data["ci"]')" = "{'mode': 'warn'}" ]
  advance_pack_repository

  run_check
  [ "$status" -eq 0 ]
  [[ "$output" == *"updates pending (ci.mode: warn)"* ]]
}

@test "ci.enabled false runs nothing: no git, no provider and no cache" {
  write_manifest acme/kafka-interno '{"ci": {"enabled": false}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  # Every command the check could run records its call and fails.
  for command_name in git bash; do
    printf '#!/bin/sh\nprintf "%%s\\n" "%s" >> "%s"\nexit 1\n' "$command_name" "$cli_calls" > "$fake_bin/$command_name"
    chmod +x "$fake_bin/$command_name"
  done
  rm -f "$cli_calls"
  before="$(tree_fingerprint)"

  run_check
  [ "$status" -eq 0 ]
  [[ "$output" == *"skipped (ci.enabled: false)"* ]]
  [ ! -e "$cli_calls" ]
  [ ! -e "$XDG_CACHE_HOME/agent-ready-setup" ]
  rm "$fake_bin/git" "$fake_bin/bash"
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "the check has one exit status per result, also in JSON" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/apply-managed-block.sh" --stack node --skill-dir "$skill_dir"
  check_flags="--format json"

  run_check
  [ "$status" -eq 0 ]
  printf '%s' "$output" > "$test_root/check.json"
  [ "$(json_value "$test_root/check.json" '[data["status"], data["exitStatus"], data["ci"]]')" = "['up-to-date', 0, {'enabled': True, 'mode': 'fail'}]" ]

  advance_pack_repository
  run_check
  [ "$status" -eq 4 ]
  printf '%s' "$output" > "$test_root/check.json"
  [ "$(json_value "$test_root/check.json" 'data["status"]')" = "outdated" ]
  [ "$(json_value "$test_root/check.json" 'len(data["problems"]) > 0')" = "True" ]

  rm -rf "$pack_repository"
  run_check
  [ "$status" -eq 5 ]
  printf '%s' "$output" > "$test_root/check.json"
  [ "$(json_value "$test_root/check.json" 'data["status"]')" = "source-unavailable" ]
  [ "$(json_value "$test_root/check.json" 'len(data["unavailable"])')" = "1" ]

  run_check AGENT_READY_SETUP_CI=warn
  [ "$status" -eq 0 ]
  printf '%s' "$output" > "$test_root/check.json"
  [ "$(json_value "$test_root/check.json" '[data["status"], data["exitStatus"]]')" = "['source-unavailable', 0]" ]

  printf '{"profiles": "not-a-list"}' > .agents/agent-ready.json
  run_check AGENT_READY_SETUP_CI=warn
  [ "$status" -eq 2 ]
  printf '%s' "$output" > "$test_root/check.json"
  [ "$(json_value "$test_root/check.json" 'data["status"]')" = "config-error" ]
}

@test "an invalid pack or selection is a configuration error, not an outdated repository" {
  write_manifest node,other/thing
  run_check
  [ "$status" -eq 2 ]
  [[ "$output" == *"configuration error"* ]]
  [[ "$output" == *"needs the source 'other'"* ]]
}

@test "the check works from a subdirectory and without any provider or GitHub tool" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/apply-managed-block.sh" --stack node --skill-dir "$skill_dir"
  rm -f "$cli_calls"
  mkdir -p src/deep
  cd src/deep
  run env -u GITHUB_ACTIONS -u GITHUB_TOKEN -u GH_TOKEN PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready-state.py" check --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"up to date"* ]]
  [ ! -e "$cli_calls" ]
}

@test "the setup never creates a CI workflow in the repository" {
  run_bootstrap --stack node
  [ "$status" -eq 0 ]
  [ ! -e .github/workflows ]
  [ -f .github/pull_request_template.md ]
}

@test "AGENT_READY_SETUP_CI overrides the manifest" {
  publish_pack_repository
  write_manifest acme/kafka-interno '{"ci": {"mode": "warn"}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  run_bootstrap
  [ "$status" -eq 0 ]
  advance_pack_repository

  run_check AGENT_READY_SETUP_CI=fail
  [ "$status" -eq 4 ]
}

@test "a token in the environment of Git reaches a source, shows nowhere and needs no gh" {
  write_manifest acme/kafka-interno '{"sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}'
  rm -f "$cli_calls"

  run_check GIT_CONFIG_COUNT=1 "GIT_CONFIG_KEY_0=url.https://reader:s3cr3t-token@127.0.0.1:9/acme.insteadOf" GIT_CONFIG_VALUE_0=https://packs.example.invalid/acme
  [ "$status" -eq 5 ]
  [[ "$output" == *"source not available (ci.mode: fail)"* ]]
  [[ "$output" != *"s3cr3t-token"* ]]
  [ ! -e "$cli_calls" ]

  run_check AGENT_READY_SETUP_CI=warn GIT_CONFIG_COUNT=1 "GIT_CONFIG_KEY_0=url.https://reader:s3cr3t-token@127.0.0.1:9/acme.insteadOf" GIT_CONFIG_VALUE_0=https://packs.example.invalid/acme
  [ "$status" -eq 0 ]
  [[ "$output" == *"source not available (ci.mode: warn)"* ]]
}
