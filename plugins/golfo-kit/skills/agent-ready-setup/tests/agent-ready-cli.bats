#!/usr/bin/env bats
# The agent-ready command line: one subcommand per flow over the engine of the same
# installation. Covers the contract without a terminal (help, version, usage errors, exit
# statuses, data on stdout and the rest on stderr) and that each subcommand gives the same
# result as the engine it delegates to.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  cli="$skill_dir/scripts/agent-ready"
  example_pack="$skill_dir/assets/examples/acme-profile-pack"
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

# Runs the CLI keeping stdout and stderr apart: $output is stdout only, $test_root/stderr the rest.
run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$cli" "$@"
}

json_value() {
  python3 -c 'import json,sys; data=json.loads(sys.argv[1]); print(eval(sys.argv[2], {"data": data}))' "$1" "$2" | tr -d '\r'
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

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

publish_pack_repository() {
  pack_repository="$test_root/repositories/acme"
  mkdir -p "$(dirname "$pack_repository")"
  cp -R "$example_pack" "$pack_repository"
  git -C "$pack_repository" init -q
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm initial
  git config --global "url.file:///$(native_path "$pack_repository" | sed 's#^/##').insteadOf" "https://packs.example.invalid/acme"
}

@test "--help and --version answer on stdout for the CLI and every subcommand, without acting" {
  run_cli --help
  [ "$status" -eq 0 ]
  [[ "$output" == *"exit status:"* ]]
  [[ "$output" == *"plan"*"status"*"check"*"apply"*"update"*"config"* ]]
  run_cli --version
  [ "$status" -eq 0 ]
  [[ "$output" == "agent-ready "* ]]

  for subcommand in plan status check apply update config "config explain" "config get" "config set" "config unset"; do
    # shellcheck disable=SC2086
    run_cli $subcommand --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"usage: agent-ready $subcommand"* ]]
    [[ "$output" == *"examples:"* ]]
    # shellcheck disable=SC2086
    run_cli $subcommand --version
    [ "$status" -eq 0 ]
    [[ "$output" == "agent-ready "* ]]
  done
  [ ! -e .agents ]
}

@test "a usage error exits 2 with nothing on stdout and names the valid values" {
  run_cli nope
  [ "$status" -eq 2 ]
  [ -z "$output" ]
  [[ "$stderr" == *"invalid choice: 'nope'"*"plan"* ]]

  run_cli plan --nope
  [ "$status" -eq 2 ]
  [ -z "$output" ]
  [[ "$stderr" == *"unrecognized arguments: --nope"* ]]

  run_cli
  [ "$status" -eq 2 ]
  [ -z "$output" ]
  [[ "$stderr" == *"usage: agent-ready"* ]]

  run_cli config set ci.mode sometimes
  [ "$status" -eq 2 ]
  [ -z "$output" ]
  [[ "$stderr" == *"'ci.mode' must be one of fail, warn"* ]]
  [ ! -e .agents/agent-ready.json ]
}

@test "a repository outside Git and a provider that cannot be inferred are usage errors" {
  mkdir "$test_root/plain"
  cd "$test_root/plain"
  run_cli check
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"is not inside a Git repository"* ]]

  cd "$project_dir"
  run --separate-stderr env -u AGENT_READY_SETUP_ACTIVE_PROVIDER PATH="$fake_bin:$PATH" python3 "$cli" plan --offline
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"pass --provider claude|codex"* ]]
}

@test "apply projects the assets and aligns AGENTS.md, with nothing on stdout" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [[ "$stderr" == *"Resolved agent-ready-setup source:"* ]]
  [ -f .agents/rules/security.md ]
  [ -f .agents/agent-ready.lock.json ]
  [ "$(grep -c 'BEGIN AGENT-READY MANAGED' AGENTS.md)" -eq 1 ]
  [ "$(json_value "$(cat .agents/agent-ready.json)" 'data["profiles"]')" = "['node']" ]
}

@test "apply --dry-run shows the plan and writes nothing" {
  before="$(tree_fingerprint)"
  run_cli apply --profiles node --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"Agent Ready plan (read-only: nothing was written)"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "plan --json and status --json print only JSON on stdout and write nothing" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  before="$(tree_fingerprint)"

  run_cli plan --offline --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[data["complete"], data["primaryStack"], data["configuration"]["origins"]["ci.mode"]]')" = "[True, 'node', 'defaults']" ]
  [[ "$stderr" == *"[marketplace-bootstrap]"* ]]

  run_cli status --offline --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[data["hasLock"], data["drift"]]')" = "[True, False]" ]
  [ "$(tree_fingerprint)" = "$before" ]

  run_cli plan --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"Agent Ready plan"* ]]
  [[ "$output" != *"[marketplace-bootstrap]"* ]]
}

@test "check gives the same exit status and the same JSON as agent-ready-state.py check" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  for scenario in up-to-date outdated; do
    if [[ "$scenario" == outdated ]]; then
      printf 'edited\n' >> .agents/rules/security.md
    fi
    run_cli check --offline --json
    cli_status="$status"
    cli_output="$output"
    run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready-state.py" check \
      --project . --skill-dir "$skill_dir" --offline --format json
    [ "$cli_status" -eq "$status" ]
    [ "$cli_output" = "$output" ]
  done
  [ "$cli_status" -eq 4 ]
  [ "$(json_value "$cli_output" 'data["status"]')" = "outdated" ]
}

@test "config set, get, explain and unset work on the project and the user layers" {
  run_cli config set ci.mode warn
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [[ "$stderr" == *"Effective now: ci.mode=warn (project)"* ]]
  [ "$(json_value "$(cat .agents/agent-ready.json)" 'data')" = "{'ci': {'mode': 'warn'}}" ]

  run_cli config get ci.mode
  [ "$status" -eq 0 ]
  [ "$output" = "warn" ]

  run_cli config explain ci.mode --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[data["value"], data["origin"]]')" = "['warn', 'project']" ]

  run_cli config set updates.mode pinned --layer user
  [ "$status" -eq 0 ]
  [ "$(json_value "$(cat "$XDG_CONFIG_HOME/agent-ready-setup/config.json")" 'data')" = "{'updates': {'mode': 'pinned'}}" ]
  run_cli config explain updates.mode
  [ "$status" -eq 0 ]
  [[ "$output" == *"updates.mode  pinned  (user)"* ]]

  run_cli config unset ci.mode
  [ "$status" -eq 0 ]
  [ "$(json_value "$(cat .agents/agent-ready.json)" 'data')" = "{}" ]
  run_cli config get ci.mode
  [ "$output" = "fail" ]

  run_cli config set nope.key 1
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"unknown configuration key 'nope.key'; valid keys:"*"ci.mode"* ]]
}

@test "config set says when the effective value ignores what was written" {
  run_cli config set sources.enabled false --layer user
  [ "$status" -eq 0 ]
  run_cli config set sources.enabled true
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"Effective now: sources.enabled=false (user)"* ]]
  [[ "$stderr" == *"ignored from the project layer: true (loosens)"* ]]
}

@test "update adopts a source, refuses one the manifest does not declare and previews with --dry-run" {
  publish_pack_repository
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["acme/kafka-interno"], "updates": {"mode": "pinned"}, "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}' > .agents/agent-ready.json
  run_cli apply
  [ "$status" -eq 0 ]
  printf 'new rule\n' > "$pack_repository/profiles/kafka-interno/rules/acme-new.md"
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm advance

  run_cli update other
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"unknown profile source other; the manifest declares: acme"* ]]

  before="$(tree_fingerprint)"
  run_cli update acme --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme-new.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run_cli update
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-new.md ]
}
