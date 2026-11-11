#!/usr/bin/env bats
# Layered configuration: one schema per feature under assets/config/, layers from the
# defaults up to the flags of one run, strict validation before anything is written, the
# sparse manifest, the origin of every value, sensitive keys that the project cannot
# loosen without the approval of the machine, organization locks and presets.

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
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp" "$test_root/organization"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  export XDG_CONFIG_HOME="$test_root/config"
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  # The organization layer exists only when a test writes this file.
  export AGENT_READY_SETUP_ORGANIZATION_CONFIG="$test_root/organization/config.json"
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  export GIT_CONFIG_GLOBAL="$test_root/gitconfig"
  git config --global user.name Test
  git config --global user.email test@example.invalid
  git config --global init.defaultBranch main
  git config --global core.autocrlf false
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_REVIEW_MODE
  unset AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES AGENT_READY_SETUP_SYNC_FOREGROUND
  unset AGENT_READY_SETUP_CI AGENT_READY_SETUP_REFRESH AGENT_READY_SETUP_DETECTION AGENT_READY_SETUP_TOOLS
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

state_script() {
  printf '%s/scripts/agent-ready-state.py' "${source_copy:-$skill_dir}"
}

# Prints the effective configuration as JSON into config.json; "env" arguments set variables.
resolve_config() {
  run env "$@" python3 "$(state_script)" config --project . --format json ${config_flags:-}
  [ "$status" -eq 0 ]
  printf '%s' "$output" > "$test_root/config.json"
}

config_value() {
  python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print(eval(sys.argv[2], {"data": data}))' \
    "$test_root/config.json" "$1" | tr -d '\r'
}

# Effective value and origin of one key, as "value origin".
value_and_origin() {
  python3 -c 'import json,sys,functools; data=json.load(open(sys.argv[1], encoding="utf-8")); key=sys.argv[2]; value=functools.reduce(lambda node, part: node[part], key.split("."), data["values"]); print(json.dumps(value), data["origins"][key])' \
    "$test_root/config.json" "$1" | tr -d '\r'
}

write_json() {
  mkdir -p "$(dirname "$1")"
  printf '%s\n' "$2" > "$1"
}

write_organization() { write_json "$AGENT_READY_SETUP_ORGANIZATION_CONFIG" "$1"; }
write_user() { write_json "$XDG_CONFIG_HOME/agent-ready-setup/config.json" "$1"; }
write_project() { write_json .agents/agent-ready.json "$1"; }

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

tree_fingerprint() {
  find . -path ./.git -prune -o -print | LC_ALL=C sort | while IFS= read -r path; do
    if [[ -f "$path" ]]; then
      printf 'F %s %s\n' "$path" "$(cksum < "$path")"
    else
      printf 'D %s\n' "$path"
    fi
  done
}

run_bootstrap() {
  run env PATH="$fake_bin:$PATH" bash "${source_copy:-$skill_dir}/scripts/bootstrap.sh" \
    --skill-dir "${source_copy:-$skill_dir}" --provider claude "$@"
}

copy_skill() {
  source_copy="$test_root/skill"
  cp -R "$skill_dir" "$source_copy"
}

@test "a repository without a manifest is configured with every default, and the apply writes none of them" {
  resolve_config
  [ "$(config_value 'sorted(set(data["origins"].values()))')" = "['defaults']" ]

  run_bootstrap --profiles node
  [ "$status" -eq 0 ]
  run python3 - "$skill_dir/scripts" <<'PY'
import json, sys
sys.path.insert(0, sys.argv[1])
import agent_ready_config
schema = agent_ready_config.load_schema()
manifest = json.load(open(".agents/agent-ready.json", encoding="utf-8"))
written_defaults = [key for key, value in schema.flatten(manifest).items() if value == schema.default(key)]
print(sorted(manifest), written_defaults)
PY
  [ "$status" -eq 0 ]
  [ "$output" = "['profiles'] []" ]
}

@test "an unknown key or an invalid value stops the apply before writing and names the key and the layer" {
  write_project '{"ci": {"mod": "warn"}}'
  before="$(tree_fingerprint)"
  run_bootstrap --profiles node
  [ "$status" -ne 0 ]
  [[ "$output" == *"project layer"*"unknown key 'ci.mod'"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  rm .agents/agent-ready.json

  write_user '{"updates": {"mode": "sometimes"}}'
  before="$(tree_fingerprint)"
  run_bootstrap --profiles node
  [ "$status" -ne 0 ]
  [[ "$output" == *"user layer"*"'updates.mode' must be one of auto, pinned"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  rm "$XDG_CONFIG_HOME/agent-ready-setup/config.json"

  write_organization '{"detection": {"enabled": "yes"}}'
  run_bootstrap --profiles node
  [ "$status" -ne 0 ]
  [[ "$output" == *"organization layer"*"'detection.enabled' must be true or false"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  rm "$AGENT_READY_SETUP_ORGANIZATION_CONFIG"

  run env AGENT_READY_SETUP_TOOLS=maybe PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" \
    --skill-dir "$skill_dir" --provider claude --profiles node
  [ "$status" -ne 0 ]
  [[ "$output" == *"environment layer (AGENT_READY_SETUP_TOOLS)"*"'tools.enabled'"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "a key can only come from the layers its schema allows" {
  write_project '{"security": {"trustedProjects": ["/anywhere"]}}'
  run python3 "$(state_script)" config --project .
  [ "$status" -ne 0 ]
  [[ "$output" == *"project layer"*"'security.trustedProjects' cannot be set in the project layer; only in: organization, user"* ]]
  rm .agents/agent-ready.json

  write_user '{"profiles": ["node"]}'
  run python3 "$(state_script)" config --project .
  [ "$status" -ne 0 ]
  [[ "$output" == *"user layer"*"'profiles' cannot be set in the user layer"* ]]
  rm "$XDG_CONFIG_HOME/agent-ready-setup/config.json"

  write_user '{"locked": ["ci"]}'
  run python3 "$(state_script)" config --project .
  [ "$status" -ne 0 ]
  [[ "$output" == *"'locked' can only come from the organization layer"* ]]
}

@test "the organization layer overrides the defaults" {
  write_organization '{"ci": {"mode": "warn"}}'
  resolve_config
  [ "$(value_and_origin ci.mode)" = '"warn" organization' ]
}

@test "the user layer overrides the organization" {
  write_organization '{"ci": {"mode": "warn"}}'
  write_user '{"ci": {"mode": "fail"}}'
  resolve_config
  [ "$(value_and_origin ci.mode)" = '"fail" user' ]
}

@test "the project layer overrides the user" {
  write_organization '{"ci": {"mode": "fail"}}'
  write_user '{"ci": {"mode": "fail"}}'
  write_project '{"ci": {"mode": "warn"}}'
  resolve_config
  [ "$(value_and_origin ci.mode)" = '"warn" project' ]
}

@test "the environment overrides the project for one run" {
  write_project '{"ci": {"mode": "warn"}}'
  resolve_config AGENT_READY_SETUP_CI=fail
  [ "$(value_and_origin ci.mode)" = '"fail" environment' ]
  resolve_config
  [ "$(value_and_origin ci.mode)" = '"warn" project' ]
}

@test "a flag overrides the environment for one run" {
  write_project '{"updates": {"refresh": true}}'
  config_flags="--offline" resolve_config AGENT_READY_SETUP_REFRESH=on
  [ "$(value_and_origin updates.refresh)" = 'false flags' ]
}

@test "lists marked as a union join across layers, and scalars are replaced" {
  write_organization "{\"security\": {\"trustedProjects\": [\"$(native_path "$test_root")/elsewhere\"]}, \"updates\": {\"mode\": \"pinned\"}}"
  write_user "{\"security\": {\"trustedProjects\": [\"$(native_path "$project_dir")\"]}, \"updates\": {\"mode\": \"auto\"}}"
  resolve_config
  [ "$(config_value 'len(data["values"]["security"]["trustedProjects"])')" = "2" ]
  [ "$(config_value 'data["origins"]["security.trustedProjects"]')" = "organization+user" ]
  [ "$(value_and_origin updates.mode)" = '"auto" user' ]
  [ "$(config_value 'data["projectApproved"]')" = "True" ]
}

@test "plan shows every effective value with the layer it comes from" {
  write_project '{"profiles": ["node"], "ci": {"mode": "warn"}}'
  write_user '{"detection": {"enabled": false}}'
  run_bootstrap --plan --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"Configuration (effective value and the layer it comes from)"* ]]
  [[ "$output" =~ ci\.mode\ +warn\ +\(project\) ]]
  [[ "$output" =~ detection\.enabled\ +false\ +\(user\) ]]
  [[ "$output" =~ updates\.refresh\ +false\ +\(flags\) ]]
  [[ "$output" =~ updates\.mode\ +auto\ +\(defaults\) ]]

  run_bootstrap --config
  [ "$status" -eq 0 ]
  [[ "$output" =~ ci\.mode\ +warn\ +\(project\) ]]
  [[ "$output" == *"user: "*"(present)"* ]]
}

@test "a sensitive key that loosens from an unapproved project is ignored and reported, and hardening applies" {
  write_user '{"tools": {"enabled": false}}'
  write_project '{"tools": {"enabled": true}, "updates": {"mode": "pinned"}, "sources": {"enabled": false}}'
  resolve_config
  [ "$(value_and_origin tools.enabled)" = 'false user' ]
  [ "$(value_and_origin updates.mode)" = '"pinned" project' ]
  [ "$(value_and_origin sources.enabled)" = 'false project' ]
  [ "$(config_value '[(item["key"], item["reason"]) for item in data["ignored"]]')" = "[('tools.enabled', 'loosens')]" ]

  run python3 "$(state_script)" config --project .
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING: tools.enabled=true from the project layer was ignored: it loosens security"* ]]
  [[ "$output" == *"approve it with: python3 "*"agent-ready-state.py\" trust --project "* ]]

  before="$(tree_fingerprint)"
  run python3 "$(state_script)" trust --project .
  [ "$status" -eq 0 ]
  [ "$(tree_fingerprint)" = "$before" ]
  resolve_config
  [ "$(value_and_origin tools.enabled)" = 'true project' ]
  [ "$(config_value 'data["ignored"]')" = "[]" ]

  run python3 "$(state_script)" trust --revoke --project .
  [ "$status" -eq 0 ]
  resolve_config
  [ "$(value_and_origin tools.enabled)" = 'false user' ]
}

@test "the update mode of one source cannot loosen what the user pinned on this machine" {
  mkdir -p agent-packs
  cp -R "$example_pack" agent-packs/acme
  write_user '{"updates": {"mode": "pinned"}}'
  write_project '{"sources": {"packs": [{"name": "acme", "source": "path:./agent-packs/acme", "updates": "auto"}]}}'
  run python3 "$(state_script)" config --project . --format tsv
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING: sources.packs[acme].updates=auto from the project layer was ignored: it loosens security"* ]]
  [[ "$output" == *$'auto_sources\t'* ]]
  [[ "$output" != *$'auto_sources\tacme'* ]]
}

@test "a key locked by the organization cannot change from the user, the project or the environment" {
  write_organization '{"ci": {"mode": "warn"}, "locked": ["ci"]}'
  write_user '{"ci": {"mode": "fail"}}'
  write_project '{"ci": {"enabled": false}}'
  resolve_config AGENT_READY_SETUP_CI=fail
  [ "$(value_and_origin ci.mode)" = '"warn" organization' ]
  [ "$(value_and_origin ci.enabled)" = 'true defaults' ]
  [ "$(config_value 'sorted((item["layer"], item["key"], item["reason"]) for item in data["ignored"])')" = \
    "[('environment', 'ci.mode', 'locked'), ('project', 'ci.enabled', 'locked'), ('user', 'ci.mode', 'locked')]" ]

  write_organization '{"locked": ["nothing.here"]}'
  run python3 "$(state_script)" config --project .
  [ "$status" -ne 0 ]
  [[ "$output" == *"organization layer"*"'locked' names the unknown key 'nothing.here'"* ]]
}

@test "each feature turns off with its own enabled: false without touching the others" {
  run python3 - "$skill_dir/scripts" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import agent_ready_config
for module in agent_ready_config.load_schema().modules:
    if module["mount"]:
        print(module["mount"])
PY
  [ "$status" -eq 0 ]
  modules="$(printf '%s' "$output" | tr -d '\r')"
  [ -n "$modules" ]
  for module in $modules; do
    write_user "{\"$module\": {\"enabled\": false}}"
    resolve_config
    [ "$(value_and_origin "$module.enabled")" = 'false user' ]
    [ "$(config_value "sorted(key for key, origin in data['origins'].items() if origin != 'defaults')")" = "['$module.enabled']" ]
  done
}

@test "updates.enabled false: SessionStart checks and syncs nothing, an explicit sync still runs" {
  run_bootstrap --profiles node
  [ "$status" -eq 0 ]
  write_project '{"profiles": ["node"], "updates": {"enabled": false}}'
  rm -f "$cli_calls"
  before="$(tree_fingerprint)"

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *"Automatic updates are off (updates.enabled: false)"* ]]
  [ ! -e "$cli_calls" ]
  [ ! -d "$XDG_CACHE_HOME/agent-ready-setup/updates" ]
  [ "$(tree_fingerprint)" = "$before" ]

  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_SYNC_FOREGROUND=1 \
    AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" != *"Automatic updates are off"* ]]
}

@test "sources.enabled false: a pack profile fails before writing and nothing is read from the pack" {
  mkdir -p agent-packs
  cp -R "$example_pack" agent-packs/acme
  write_project '{"profiles": ["node", "acme/kafka-interno"], "sources": {"enabled": false, "packs": [{"name": "acme", "source": "path:./agent-packs/acme"}]}}'
  before="$(tree_fingerprint)"
  run_bootstrap
  [ "$status" -ne 0 ]
  [[ "$output" == *"profile sources are off (sources.enabled: false)"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "tools.enabled false projects the assets without installing tools" {
  write_project '{"tools": {"enabled": false}}'
  run_bootstrap --profiles node,browser
  [ "$status" -eq 0 ]
  [[ "$output" == *"Browser installation skipped by tools.enabled: false"* ]]
  [ -f .agents/rules/node-security.md ]
}

@test "security.enabled false on the machine lets every project loosen without an approval" {
  write_user '{"tools": {"enabled": false}, "security": {"enabled": false}}'
  write_project '{"tools": {"enabled": true}}'
  resolve_config
  [ "$(value_and_origin tools.enabled)" = 'true project' ]
  [ "$(config_value 'data["ignored"]')" = "[]" ]
}

@test "security.preset off counts as loosening from the project, but works from the user" {
  write_project '{"security": {"preset": "off"}}'
  resolve_config
  [ "$(value_and_origin security.preset)" = '"standard" defaults' ]
  [ "$(value_and_origin security.enabled)" = 'true defaults' ]
  [ "$(config_value '[(item["key"], item["reason"]) for item in data["ignored"]]')" = "[('security.preset', 'loosens')]" ]

  rm .agents/agent-ready.json
  write_user '{"security": {"preset": "off"}}'
  resolve_config
  [ "$(value_and_origin security.preset)" = '"off" user' ]
  [ "$(value_and_origin security.enabled)" = 'false user (preset security.preset=off)' ]
}

@test "a preset sets several keys at once, and any of them can be overridden above it" {
  write_project '{"security": {"preset": "strict"}}'
  resolve_config
  [ "$(value_and_origin updates.mode)" = '"pinned" project (preset security.preset=strict)' ]

  write_user '{"security": {"preset": "strict"}}'
  write_project '{"updates": {"mode": "auto"}}'
  resolve_config
  [ "$(value_and_origin updates.mode)" = '"pinned" user (preset security.preset=strict)' ]
  [ "$(config_value '[item["key"] for item in data["ignored"]]')" = "['updates.mode']" ]
  resolve_config AGENT_READY_SETUP_UPDATES=auto
  [ "$(value_and_origin updates.mode)" = '"auto" environment' ]
}

@test "a new feature only needs its schema: the resolver loads a fixture module unchanged" {
  copy_skill
  cat > "$source_copy/assets/config/audit.schema.json" <<'EOF'
{
  "title": "Audit fixture",
  "description": "A module that exists only in this test.",
  "x-module": "audit",
  "x-mount": "audit",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "enabled": { "description": "Turns the fixture off.", "type": "boolean", "default": true },
    "level": { "description": "How much it records.", "type": "string", "enum": ["none", "basic", "full"], "default": "basic",
               "x-env": "AGENT_READY_SETUP_FIXTURE_AUDIT_LEVEL", "x-security": { "strictness": ["none", "basic", "full"] } },
    "allow": { "description": "Allowed items.", "type": "array", "items": { "type": "string" }, "default": [], "x-merge": "union" },
    "deny": { "description": "Denied items.", "type": "array", "items": { "type": "string" }, "default": [], "x-merge": "union" },
    "label": { "description": "A replaced scalar.", "type": "string", "default": "none" }
  }
}
EOF
  write_organization '{"audit": {"allow": ["git"], "deny": ["curl"], "label": "organization"}}'
  write_user '{"audit": {"allow": ["node"], "label": "user"}}'
  write_project '{"audit": {"deny": ["wget"], "level": "none", "label": "project"}}'
  resolve_config
  [ "$(value_and_origin audit.allow)" = '["git", "node"] organization+user' ]
  [ "$(value_and_origin audit.deny)" = '["curl", "wget"] organization+project' ]
  [ "$(value_and_origin audit.label)" = '"project" project' ]
  [ "$(value_and_origin audit.level)" = '"basic" defaults' ]
  [ "$(config_value '[item["key"] for item in data["ignored"]]')" = "['audit.level']" ]
  resolve_config AGENT_READY_SETUP_FIXTURE_AUDIT_LEVEL=full
  [ "$(value_and_origin audit.level)" = '"full" environment' ]

  run python3 "$(state_script)" config-reference
  [ "$status" -eq 0 ]
  [[ "$output" == *'`audit.level`'* ]]

  # A module without its own switch is rejected, naming it.
  python3 - "$source_copy/assets/config/audit.schema.json" <<'PY'
import json, sys
schema = json.load(open(sys.argv[1], encoding="utf-8"))
del schema["properties"]["enabled"]
json.dump(schema, open(sys.argv[1], "w", encoding="utf-8"))
PY
  run python3 "$(state_script)" config --project .
  [ "$status" -ne 0 ]
  [[ "$output" == *"the module 'audit' must declare 'enabled'"* ]]
}

@test "the reference of every key is generated from the schemas" {
  run python3 "$skill_dir/scripts/agent-ready-state.py" config-reference
  [ "$status" -eq 0 ]
  printf '%s\n' "$output" > "$test_root/generated.md"
  diff --strip-trailing-cr "$skill_dir/references/configuration-keys.md" "$test_root/generated.md"
}
