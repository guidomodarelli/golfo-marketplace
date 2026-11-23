#!/usr/bin/env bats
# The agent-ready command line: one subcommand per flow over the engine of the same
# installation. Covers the contract without a terminal (help, version, usage errors, exit
# statuses, data on stdout and the rest on stderr) and that each subcommand gives the same
# result as the engine it delegates to.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-agent-ready/skills/agent-ready-setup"
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
  source "$BATS_TEST_DIRNAME/content-pack.bash"
  use_content_pack
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

# The document goes through stdin: a plan with its blocks outgrows the 32 KiB command line of Windows.
json_value() {
  printf '%s' "$1" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(eval(sys.argv[1], {"data": data}))' "$2" | tr -d '\r'
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

  for subcommand in plan status check apply update doctor remove config "config explain" "config get" "config set" "config unset"; do
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
  [ -f .agents/rules/node-security.md ]
  [ -f .agents/agent-ready.lock.json ]
  [ "$(grep -cx '<!-- BEGIN AGENT-READY MANAGED -->' AGENTS.md)" -eq 1 ]
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
      printf 'edited\n' >> .agents/rules/node-security.md
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
  [[ "$stderr" == *"unknown profile source other; the sources are: golfo, acme"* ]]

  before="$(tree_fingerprint)"
  run_cli update acme --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme-new.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run_cli update
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-new.md ]
}

@test "update follows the effective configuration: with sources off it only updates the golfo content" {
  mkdir -p .agents "$XDG_CONFIG_HOME/agent-ready-setup"
  printf '%s\n' '{"profiles": ["node"], "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme", "ref": "main"}]}}' > .agents/agent-ready.json
  printf '%s\n' '{"sources": {"enabled": false}}' > "$XDG_CONFIG_HOME/agent-ready-setup/config.json"

  run_cli update --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"Agent Ready plan"* ]]

  run_cli update acme
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"profile sources are off (sources.enabled: false)"* ]]
}

@test "init without a terminal names every missing flag, writes nothing, and with its flags applies" {
  printf '%s\n' '{"dependencies": {"react": "19.0.0"}}' > package.json
  before="$(tree_fingerprint)"
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$cli" init < /dev/null
  [ "$status" -eq 2 ]
  [ -z "$output" ]
  [[ "$stderr" == *"missing --profiles <a,b> (or --stack <s>) and --yes; there is no terminal to ask"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$cli" init --profiles nope --yes < /dev/null
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"--profiles: unknown profile 'nope'; available profiles:"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run --separate-stderr env PATH="$fake_bin:$PATH" CI=1 python3 "$cli" init --stack react < /dev/null
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"missing --yes"* ]]

  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$cli" init --stack react --yes < /dev/null
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ "$(json_value "$(cat .agents/agent-ready.json)" 'data["profiles"]')" = "['react']" ]
  [ "$(grep -cx '<!-- BEGIN AGENT-READY MANAGED -->' AGENTS.md)" -eq 1 ]

  run_cli init --profiles node --yes
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"this repository is already set up"* ]]
}

@test "profiles list, add and remove validate the selection against the catalog before writing" {
  run_cli profiles add browser
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"no selection yet; start it with agent-ready init"* ]]

  run_cli init --profiles node --yes < /dev/null
  [ "$status" -eq 0 ]
  run_cli profiles list --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[row["name"] for row in data if row["selected"]]')" = "['node']" ]

  run_cli profiles add business-flows
  [ "$status" -eq 0 ]
  [ "$(json_value "$(cat .agents/agent-ready.json)" 'data["profiles"]')" = "['node', 'business-flows']" ]
  [[ "$stderr" == *"Run agent-ready apply to project them"* ]]

  before="$(cksum < .agents/agent-ready.json)"
  run_cli profiles add nope
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"unknown profile 'nope'"* ]]
  run_cli profiles remove browser
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"not selected: browser"* ]]
  [[ "$stderr" == *"agent-ready config set excludedDefaults browser"* ]]
  [ "$(cksum < .agents/agent-ready.json)" = "$before" ]

  # The selection is checked with the excludedDefaults of the repository, as every apply does.
  run_cli config set excludedDefaults browser
  [ "$status" -eq 0 ]
  before="$(cksum < .agents/agent-ready.json)"
  run_cli profiles add browser
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"excludedDefaults lists 'browser', but the selection needs it"* ]]
  [ "$(cksum < .agents/agent-ready.json)" = "$before" ]
  run_cli config unset excludedDefaults
  [ "$status" -eq 0 ]

  run_cli profiles remove business-flows
  [ "$status" -eq 0 ]
  [ "$(json_value "$(cat .agents/agent-ready.json)" 'data["profiles"]')" = "['node']" ]
}

@test "sources add, list and remove keep the manifest valid and protect the profiles in use" {
  run_cli init --profiles node --yes < /dev/null
  [ "$status" -eq 0 ]
  mkdir -p agent-packs
  cp -R "$example_pack" agent-packs/acme

  run_cli sources add acme path:./agent-packs/acme
  [ "$status" -eq 0 ]
  run_cli sources list --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[(row["name"], row["state"], len(row["profiles"])) for row in data["sources"]]')" = "[('acme', 'available', 3)]" ]

  run_cli sources add acme path:./agent-packs/acme
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"already declares the source 'acme'"* ]]
  run_cli sources add Bad path:./agent-packs/acme
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"invalid name 'Bad'"* ]]

  run_cli profiles add acme/kafka-interno
  [ "$status" -eq 0 ]
  run_cli sources remove acme
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"the selection still uses acme/base, acme/kafka-interno; remove what brings them in first with agent-ready profiles remove acme/kafka-interno"* ]]

  run_cli profiles remove acme/kafka-interno
  [ "$status" -eq 0 ]
  run_cli sources remove acme
  [ "$status" -eq 0 ]
  [ "$(json_value "$(cat .agents/agent-ready.json)" '"sources" in data')" = "False" ]
}

@test "sources add fails with exit 5 and leaves the manifest as it was when the source cannot be fetched" {
  run_cli init --profiles node --yes < /dev/null
  [ "$status" -eq 0 ]
  before="$(cksum < .agents/agent-ready.json)"
  run_cli sources add missing path:./not-here
  [ "$status" -eq 5 ]
  [[ "$stderr" == *"could not bring the source 'missing' into the cache; the manifest was left as it was"* ]]
  [ "$(cksum < .agents/agent-ready.json)" = "$before" ]
}

@test "sources remove refuses a source that a selected profile requires through another pack" {
  run_cli init --profiles node --yes < /dev/null
  [ "$status" -eq 0 ]
  mkdir -p agent-packs/beta/profiles/base/rules agent-packs/alpha/profiles/base/rules
  printf '%s\n' '{"schemaVersion": 1, "name": "beta", "profiles": {"base": {"kind": "capability", "assets": "profiles/base"}}}' > agent-packs/beta/agent-ready-pack.json
  printf '# beta\n' > agent-packs/beta/profiles/base/rules/beta-base.md
  printf '%s\n' '{"schemaVersion": 1, "name": "alpha", "profiles": {"base": {"kind": "capability", "assets": "profiles/base", "requires": ["beta/base"]}}}' > agent-packs/alpha/agent-ready-pack.json
  printf '# alpha\n' > agent-packs/alpha/profiles/base/rules/alpha-base.md
  run_cli sources add beta path:./agent-packs/beta
  [ "$status" -eq 0 ]
  run_cli sources add alpha path:./agent-packs/alpha
  [ "$status" -eq 0 ]
  run_cli profiles add alpha/base
  [ "$status" -eq 0 ]

  run_cli sources remove beta
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"the selection still uses beta/base; remove what brings them in first with agent-ready profiles remove alpha/base"* ]]
}

@test "sources add refuses a directory that is not a valid pack, and a broken pack can still be removed" {
  run_cli init --profiles node --yes < /dev/null
  [ "$status" -eq 0 ]
  before="$(cksum < .agents/agent-ready.json)"
  mkdir not-a-pack
  run_cli sources add bad path:./not-a-pack
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"the source 'bad' is not a valid profile pack:"*"the manifest was left as it was"* ]]
  [ "$(cksum < .agents/agent-ready.json)" = "$before" ]

  run_cli sources add bad path:./not-a-pack --offline
  [ "$status" -eq 0 ]
  run_cli sources remove bad
  [ "$status" -eq 0 ]
  [ "$(json_value "$(cat .agents/agent-ready.json)" '"sources" in data')" = "False" ]
}

@test "a selected pack that became invalid can still be removed with profiles remove and sources remove" {
  run_cli init --profiles node --yes < /dev/null
  [ "$status" -eq 0 ]
  mkdir -p agent-packs
  cp -R "$example_pack" agent-packs/acme
  run_cli sources add acme path:./agent-packs/acme
  [ "$status" -eq 0 ]
  run_cli profiles add acme/kafka-interno
  [ "$status" -eq 0 ]
  printf 'not json\n' > agent-packs/acme/agent-ready-pack.json

  run_cli profiles remove acme/kafka-interno
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"checked against the golfo catalog only"* ]]
  [ "$(json_value "$(cat .agents/agent-ready.json)" 'data["profiles"]')" = "['node']" ]
  run_cli sources remove acme
  [ "$status" -eq 0 ]
}

@test "apply and then remove --yes leave the repository as it was" {
  git add -A && git commit -qm initial
  before="$(tree_fingerprint)"
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  [ -f .claude/settings.json ]

  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [[ "$stderr" == *"Removed "*" paths; kept 0."* ]]
  [ "$(tree_fingerprint)" = "$before" ]
  [ -z "$(git status --porcelain)" ]

  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"there is nothing to remove"* ]]
}

@test "remove --dry-run lists every change and writes nothing; without a terminal it needs --yes" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  before="$(tree_fingerprint)"

  run_cli remove --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"agent-ready remove would change these paths:"* ]]
  [[ "$output" == *"remove .agents/rules/node-security.md"* ]]
  [[ "$output" == *"remove .agents/agent-ready.lock.json"* ]]
  [[ "$output" == *"AGENTS.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run_cli remove --dry-run --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[entry["action"] for entry in data["entries"] if entry["path"] == ".agents/agent-ready.json"]')" = "['remove']" ]

  run_cli remove < /dev/null
  [ "$status" -eq 2 ]
  [ -z "$output" ]
  [[ "$stderr" == *"missing --yes"*"there is no terminal to ask"* ]]
  [ "$(tree_fingerprint)" = "$before" ]
}

@test "remove keeps the project's rules, its AGENTS.md content, its settings and the managed files it edited" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  printf '# Own rule\n\nKeep it.\n' > .agents/rules/own-rule.md
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  [ -e .claude/rules/own-rule.md ]
  printf '\n## Project notes\n\nKeep me.\n' >> AGENTS.md
  printf 'local edit\n' >> .agents/rules/node-security.md
  python3 - <<'PY'
import json
settings = json.load(open(".claude/settings.json", encoding="utf-8"))
settings["permissions"]["allow"].append("Bash(make test)")
settings["hooks"]["PostToolUse"][0]["hooks"].append({"type": "command", "command": "make lint"})
json.dump(settings, open(".claude/settings.json", "w", encoding="utf-8"), indent=2)
PY

  run_cli remove --yes --json < /dev/null
  [ "$status" -eq 0 ]
  [[ "$(json_value "$output" 'data["kept"]')" == *".agents/rules/node-security.md: changed since the last apply"* ]]
  [ ! -e .agents/agent-ready.json ]
  [ ! -e .agents/agent-ready.lock.json ]
  [ ! -e .agents/hooks/sync-marketplace.sh ]
  [ -f .agents/rules/own-rule.md ]
  [ ! -e .claude/rules/own-rule.md ]
  [ ! -e .claude/rules/node-security.md ]
  grep -q 'local edit' .agents/rules/node-security.md
  grep -q 'Keep me.' AGENTS.md
  ! grep -q 'AGENT-READY MANAGED' AGENTS.md
  [ -f CLAUDE.md ]
  [ "$(json_value "$(cat .claude/settings.json)" 'data')" = "{'permissions': {'allow': ['Bash(make test)']}, 'hooks': {'PostToolUse': [{'matcher': 'Write|Edit', 'hooks': [{'type': 'command', 'command': 'make lint'}]}]}}" ]
}

@test "remove unregisters the browser servers it added and keeps the project's own servers" {
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || skip "unregistering the browser servers needs Python 3.11+"
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  printf '%s\n' '{"mcpServers": {"playwright": {"command": "${HOME}/.local/share/agent-ready-setup/browser-tools/bin/playwright"}, "own": {"command": "own-server"}}}' > .mcp.json
  printf '{}\n' > .agents/browser-tools.json
  printf 'node_modules/\n\n' | cat - .gitignore > .gitignore.new && mv .gitignore.new .gitignore

  run_cli remove --dry-run
  [[ "$output" == *"edit   .mcp.json"* ]]
  [[ "$output" == *"edit   .gitignore"* ]]

  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  [ "$(json_value "$(cat .mcp.json)" 'data')" = "{'mcpServers': {'own': {'command': 'own-server'}}}" ]
  [ ! -e .agents/browser-tools.json ]
  [ "$(cat .gitignore)" = "node_modules/" ]
}

@test "doctor reports each requirement, and the fix of what is missing, on stdout" {
  run_cli doctor --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"git"*"bash"*"python"*"provider"*"engine"*"configuration"*"sources"*"hooks"* ]]
  [[ "$output" == *"agent-ready-setup is not applied in this repository"* ]]
  [[ "$stderr" == *"Everything agent-ready-setup needs is in place."* ]]

  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  run_cli doctor --offline --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[check["status"] for check in data["checks"] if check["name"].startswith("hooks")]')" = "['ok', 'ok']" ]

  python3 - <<'PY'
import json
settings = json.load(open(".claude/settings.json", encoding="utf-8"))
del settings["hooks"]["SessionStart"]
json.dump(settings, open(".claude/settings.json", "w", encoding="utf-8"), indent=2)
PY
  printf '%s\n' '{"profiles": ["node"], "sources": {"packs": [{"name": "local-pack", "source": "path:packs/missing"}]}}' > .agents/agent-ready.json
  run_cli doctor --offline
  [ "$status" -eq 1 ]
  [[ "$output" == *"hooks claude"*"missing: SessionStart: bash .agents/hooks/sync-marketplace.sh --provider claude"* ]]
  [[ "$output" == *"fix: agent-ready apply"* ]]
  [[ "$output" == *"source local-pack"*"path packs/missing does not exist"* ]]
  [[ "$output" == *"fix: restore it, or agent-ready sources remove local-pack"* ]]
  [[ "$stderr" == *"2 problems"* ]]

  printf '{"updates": {"mode": "sometimes"}}\n' > .agents/agent-ready.json
  run_cli doctor --offline --json
  [ "$status" -eq 1 ]
  [ "$(json_value "$output" '[check["status"] for check in data["checks"] if check["name"] == "configuration"]')" = "['missing']" ]
}

@test "doctor names the content or the pack that needs a newer engine, with the plugin to install" {
  run_cli doctor --offline --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[check["name"] + ":" + check["status"] for check in data["checks"] if check["name"].startswith(("content", "pack"))]')" = "['content golfo:ok']" ]

  # The content and a pack that ask for engines newer than this one: an apply would stop on both.
  copy_content_pack
  python3 - "$content_dir/agent-ready-pack.json" <<'PY'
import json, sys
catalog = json.load(open(sys.argv[1], encoding="utf-8"))
catalog["minEngine"] = "99.0.0"
json.dump(catalog, open(sys.argv[1], "w", encoding="utf-8"), indent=2)
PY
  mkdir -p packs/acme/profiles/team/rules
  printf '# Team\n' > packs/acme/profiles/team/rules/acme-team.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "version": "2.0.0", "minEngine": "98.0.0", "profiles": {"team": {"kind": "capability", "assets": "profiles/team"}}}' > packs/acme/agent-ready-pack.json
  mkdir -p .agents
  printf '%s\n' '{"sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}' > .agents/agent-ready.json
  run_cli doctor --offline
  [ "$status" -eq 1 ]
  grep -Fq -- "(AGENT_READY_SETUP_CONTENT_DIR) needs the agent-ready-setup engine 99.0.0 or newer" <<< "$output"
  grep -Fq -- "pack 'acme' needs the agent-ready-setup engine 98.0.0 or newer" <<< "$output"
  grep -Fq -- "fix: install the golfo-agent-ready plugin 98.0.0 or newer: claude plugin update golfo-agent-ready@golfo-marketplace" <<< "$output"
  grep -Fq -- "2 problems" <<< "$stderr"
  run_cli doctor --offline --json
  [ "$(json_value "$output" '[check["name"] + ":" + check["status"] for check in data["checks"] if check["name"].startswith(("content", "pack"))]')" = "['content golfo:missing', 'pack acme:missing']" ]

  # Offline and without the content on this machine, the packs that are here are still checked.
  unset AGENT_READY_SETUP_CONTENT_DIR
  run_cli doctor --offline --json
  [ "$status" -eq 1 ]
  [ "$(json_value "$output" '[check["name"] + ":" + check["status"] for check in data["checks"] if check["name"].startswith(("content", "pack"))]')" = "['content:skipped', 'pack acme:missing']" ]

  # A catalog newer than this engine reads asks for the newest plugin; a malformed one, a fix of the catalog.
  export AGENT_READY_SETUP_CONTENT_DIR="$content_pack"
  printf '%s\n' '{"schemaVersion": 9, "name": "acme", "profiles": {"team": {"kind": "capability", "assets": "profiles/team"}}}' > packs/acme/agent-ready-pack.json
  run_cli doctor --offline
  [ "$status" -eq 1 ]
  grep -Fq -- "fix: install the newest golfo-agent-ready plugin: claude plugin update golfo-agent-ready@golfo-marketplace" <<< "$output"
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "minEngine": "soon", "profiles": {}}' > packs/acme/agent-ready-pack.json
  run_cli doctor --offline
  [ "$status" -eq 1 ]
  grep -Fq -- "minEngine must be a semantic version" <<< "$output"
  grep -Fq -- "fix: fix the catalog it names" <<< "$output"

  # Content written for a newer catalog format cannot even be composed: doctor and the apply both ask for the newest plugin.
  python3 - "$content_dir/agent-ready-pack.json" <<'PY'
import json, sys
catalog = json.load(open(sys.argv[1], encoding="utf-8"))
catalog.update(schemaVersion=9, fieldOfANewerFormat=True)
json.dump(catalog, open(sys.argv[1], "w", encoding="utf-8"), indent=2)
PY
  export AGENT_READY_SETUP_CONTENT_DIR="$content_dir"
  run_cli doctor --offline --json
  [ "$status" -eq 1 ]
  [ "$(json_value "$output" '[check["fix"] for check in data["checks"] if check["name"] == "content golfo"][0].split(":")[0]')" = "install the newest golfo-agent-ready plugin" ]
  run_cli apply --stack node
  [ "$status" -ne 0 ]
  grep -Fq -- "uses catalog schemaVersion 9, and this engine" <<< "$stderr"
  export AGENT_READY_SETUP_CONTENT_DIR="$content_pack"

  # A source the manifest declares wrong keeps the report: the sources check names it.
  printf '%s\n' '{"sources": {"packs": [{"name": "acme", "source": "path:/absolute"}]}}' > .agents/agent-ready.json
  run_cli doctor --offline --json
  [ "$status" -eq 1 ]
  [ "$(json_value "$output" '[check["name"] + ":" + check["status"] for check in data["checks"] if check["name"].startswith(("content", "pack", "sources"))]')" = "['sources:missing', 'content golfo:ok']" ]
}

@test "doctor runs outside a repository and names the missing worktree; a missing agent CLI says how to fix it" {
  mkdir "$test_root/plain"
  cd "$test_root/plain"
  run_cli doctor --offline
  [ "$status" -eq 1 ]
  [[ "$output" == *"is not inside a Git worktree"* ]]
  [[ "$output" == *"fix: run it from a repository, or pass --project <path>"* ]]

  if PATH="$(getconf PATH 2>/dev/null || printf '/usr/bin:/bin')" command -v claude >/dev/null; then
    skip "a real agent CLI is installed in the system PATH"
  fi
  cd "$project_dir"
  run --separate-stderr env PATH="$(dirname "$(command -v git)"):$(dirname "$(command -v python3)"):$(dirname "$(command -v bash)")" python3 "$cli" doctor --offline
  [ "$status" -eq 1 ]
  [[ "$output" == *"claude and codex are not on PATH"* ]]
  [[ "$output" == *"fix: install Claude Code (claude) or Codex (codex)"* ]]
}

@test "doctor reads the repository root from a subdirectory and checks each hook in its own event" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  mkdir src
  cd src
  run_cli doctor --offline --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" '[check["status"] for check in data["checks"] if check["name"].startswith("hooks")]')" = "['ok', 'ok']" ]

  cd "$project_dir"
  python3 - <<'PY'
import json
settings = json.load(open(".claude/settings.json", encoding="utf-8"))
settings["hooks"]["PostToolUse"] += settings["hooks"].pop("SessionStart")
json.dump(settings, open(".claude/settings.json", "w", encoding="utf-8"), indent=2)
PY
  run_cli doctor --offline
  [ "$status" -eq 1 ]
  [[ "$output" == *"missing: SessionStart: bash .agents/hooks/sync-marketplace.sh --provider claude"* ]]
}

@test "remove never changes files through a linked directory and waits for a running apply" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  mv .claude "$test_root/shared-claude"
  ln -s "$test_root/shared-claude" .claude 2>/dev/null || true
  [ -L .claude ] || skip "this system cannot create symlinks"
  shared_settings="$(cksum < "$test_root/shared-claude/settings.json")"

  mkdir .agents/.agent-ready-assets.lock
  run_cli remove --yes < /dev/null
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"an apply or a session sync is running"* ]]
  [ -f .agents/agent-ready.lock.json ]
  [ -f .agents/rules/node-security.md ]
  rmdir .agents/.agent-ready-assets.lock

  run_cli remove --dry-run --json
  [ "$(json_value "$output" '[entry["action"] for entry in data["entries"] if entry["path"] == ".claude/settings.json"]')" = "['keep']" ]
  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  [ "$(cksum < "$test_root/shared-claude/settings.json")" = "$shared_settings" ]
  [ ! -e .agents/agent-ready.lock.json ]
}

@test "remove keeps the lockfile while a managed asset cannot be deleted, so it can run again" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  chmod a-w .agents/rules
  if touch .agents/rules/.probe 2>/dev/null; then
    rm -f .agents/rules/.probe
    chmod u+w .agents/rules
    skip "this system lets a read-only directory lose its files"
  fi
  run_cli remove --yes --json < /dev/null
  chmod u+w .agents/rules
  [ "$status" -eq 1 ]
  [[ "$(json_value "$output" 'data["failed"]')" == *".agents/rules/"* ]]
  [ -f .agents/agent-ready.lock.json ]

  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  [ ! -e .agents/agent-ready.lock.json ]
  [ ! -e .agents/rules/node-security.md ]
}

@test "doctor checks the version of the python3 that the session hooks run" {
  real_python="$(command -v python3)"
  printf '#!/bin/sh\necho "Python 3.6.9"\n' > "$fake_bin/python3"
  chmod +x "$fake_bin/python3"
  run --separate-stderr env PATH="$fake_bin:$PATH" "$real_python" "$cli" doctor --offline
  [ "$status" -eq 1 ]
  [[ "$output" == *"reports 'Python 3.6.9'"* ]]
  [[ "$output" == *"fix: install Python 3.8 or newer and put it first on PATH as python3"* ]]
}

@test "remove waits for a running AGENTS.md review and keeps project lines that only mention the markers" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  printf 'Do not edit the block starting with <!-- BEGIN AGENT-READY MANAGED --> by hand.\n\nRelease policy: keep me.\n\n%s' "$(cat AGENTS.md)" > AGENTS.md

  mkdir .agents/.agent-ready-instructions.lock
  run_cli remove --yes < /dev/null
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"an AGENTS.md review is running"* ]]
  [ -f .agents/agent-ready.lock.json ]
  rmdir .agents/.agent-ready-instructions.lock

  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  grep -q 'Release policy: keep me.' AGENTS.md
  grep -q 'Do not edit the block starting with' AGENTS.md
  ! grep -q '^<!-- END AGENT-READY MANAGED -->$' AGENTS.md
}

@test "remove keeps the Git hook that another worktree of the repository still needs" {
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  git add -A && git commit -qm "agent ready"
  git config hook.agent-ready-relink.event post-index-change
  git config hook.agent-ready-relink.command "sh .agents/hooks/relink-hard-link-views.sh"
  git worktree add -q "$test_root/linked"

  cd "$test_root/linked"
  run_cli remove --dry-run --json
  [[ "$(json_value "$output" '[entry["reason"] for entry in data["entries"] if entry["kind"] == "git-config"]')" == *"shared with the worktree"* ]]
  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  [ "$(git config --get hook.agent-ready-relink.command)" = "sh .agents/hooks/relink-hard-link-views.sh" ]

  cd "$project_dir"
  run_cli remove --yes < /dev/null
  [ "$status" -eq 0 ]
  [ -z "$(git config --get hook.agent-ready-relink.command)" ]
}

@test "an apply that leaves the learning profile takes the repository out of the scheduled sweep" {
  source "$BATS_TEST_DIRNAME/fake-scheduler.bash"
  fake_scheduler crontab
  mkdir -p .agents
  printf '%s\n' '{"assets": {}, "profileOrder": ["node", "learning"]}' > .agents/agent-ready.lock.json
  run_cli learn schedule
  [ "$status" -eq 0 ]
  grep -q "# agent-ready learning sweep" "$FAKE_SCHEDULER_STATE/crontab.txt"

  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  [[ "$output$stderr" == *"Scheduled learning sweep removed: this repository no longer asks for the scheduled sweep"* ]]
  ! grep -q "# agent-ready learning sweep" "$FAKE_SCHEDULER_STATE/crontab.txt"

  # Without learning, later applies never touch the scheduler.
  : > "$FAKE_SCHEDULER_STATE/calls.log"
  run_cli apply --profiles node
  [ "$status" -eq 0 ]
  [ ! -s "$FAKE_SCHEDULER_STATE/calls.log" ]
}

# 169a: the identity of the user of the system, apart from the Git account, and the collaboration preset.
@test "identity defaults to user@machine, and set and link store it for this user of the system only" {
  run_cli identity show --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" 'data["source"]')" = "default" ]
  [[ "$(json_value "$output" 'data["id"]')" =~ ^[a-z0-9][a-z0-9._-]*@[a-z0-9._-]+$ ]]
  [ ! -e "$XDG_CONFIG_HOME/agent-ready-setup/identity.json" ]

  run_cli identity set --name "Ana Pérez" --id ana
  [ "$status" -eq 0 ]
  [[ "$output" == *"Identity: ana (Ana Pérez), set on this machine."* ]]
  [ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' \
    "$XDG_CONFIG_HOME/agent-ready-setup/identity.json" | tr -d '\r')" = "ana" ]

  # The same person on a second machine adopts the id and keeps the name of this one.
  run_cli identity link ana-perez
  [ "$status" -eq 0 ]
  run_cli identity show --json
  [ "$(json_value "$output" 'data["id"]')" = "ana-perez" ]
  [ "$(json_value "$output" 'data["name"]')" = "Ana Pérez" ]
  # It lives outside the repository: nothing to commit.
  [ -z "$(git status --porcelain --untracked-files=all -- .agents)" ]

  run_cli identity set --id "Ana Pérez"
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"identity id 'Ana Pérez' must be 1 to 64 lowercase letters"* ]]

  # A broken file is replaced when both fields are given, as its error says.
  printf '%s\n' '{"id": "Ana Pérez"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  run_cli identity show
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"fix it with agent-ready identity set"* ]]
  run_cli identity set --id ana --name Ana
  [ "$status" -eq 0 ]
  [[ "$output" == *"Identity: ana (Ana), set on this machine."* ]]
}

@test "collaboration auto is software with software-development in the selection and business without it" {
  mkdir -p .agents
  printf '%s\n' '{"assets": {}, "profileOrder": ["node", "software-development"]}' > .agents/agent-ready.lock.json
  run_cli identity show --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" 'data["collaboration"]["effective"]')" = "software" ]

  printf '%s\n' '{"assets": {}, "profileOrder": ["learning"]}' > .agents/agent-ready.lock.json
  run_cli identity show
  [[ "$output" == *"Collaboration: business, chosen by the selection."* ]]

  # A monorepo that selects its code stacks only in a workspace.
  printf '%s\n' '{"assets": {}, "profileOrder": [], "workspaces": {"apps/web": {"profiles": ["react"], "own": ["react", "software-development"]}}}' \
    > .agents/agent-ready.lock.json
  run_cli identity show --json
  [ "$(json_value "$output" 'data["collaboration"]["effective"]')" = "software" ]

  printf '%s\n' '{"collaboration": "software"}' > .agents/agent-ready.json
  run_cli identity show --json
  [ "$(json_value "$output" 'data["collaboration"]')" = "{'configured': 'software', 'effective': 'software'}" ]
}

# 169c: agent-ready sync between two machines of an office, against a local bare remote.
# Each machine is a clone with its own configuration (its identity) whose apply registered the drivers.
setup_office_remote() {
  export AGENT_READY_LEARNING_SCHEDULER=none
  export AGENT_READY_TEAM_SYNC_FOREGROUND=1
  remote="$test_root/remote.git"
  other="$test_root/other"
  # The two applies are the slow part: the first test builds the office, the others copy it.
  local office="$BATS_FILE_TMPDIR/office"
  if [ ! -d "$office" ]; then
    build_office
    mkdir -p "$office"
    cp -a "$project_dir" "$office/project"
    cp -a "$remote" "$office/remote.git"
    cp -a "$other" "$office/other"
    return
  fi
  rm -rf "$project_dir"
  cp -a "$office/project" "$project_dir"
  cp -a "$office/remote.git" "$remote"
  cp -a "$office/other" "$other"
  git -C "$project_dir" remote set-url origin "$remote"
  git -C "$other" remote set-url origin "$remote"
  # The drivers of each copy still name the engine of the test that built it; every sync points them to its own.
  cd "$project_dir"
}

build_office() {
  run_cli apply --profiles learning
  [ "$status" -eq 0 ]
  git add -A
  git commit -qm "agent-ready"
  git init -q --bare "$remote"
  git -C "$remote" symbolic-ref HEAD refs/heads/main
  git remote add origin "$remote"
  git push -q origin HEAD:main
  git branch -q --set-upstream-to=origin/main
  git clone -q "$remote" "$other"
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli apply
  [ "$status" -eq 0 ]
  cd "$project_dir"
}

# A learned rule as learn apply leaves it, written by hand so the test controls the content.
# RULE_FILE names another file of .agents/rules/, and RULE_ATTRIBUTES adds attributes to the marker.
learn_rule() {
  local file="${RULE_FILE:-.agents/rules/learned.md}"
  mkdir -p "$(dirname "$file")"
  [ -f "$file" ] || printf '%s\n' '# Learned rules' > "$file"
  printf '%s\n' '' "<!-- rule id=learned/$1${RULE_ATTRIBUTES:+ $RULE_ATTRIBUTES} -->" "- $2" >> "$file"
}

@test "sync brings to the other machine what one learned, and both rules of one file stay, without Git commands" {
  setup_office_remote
  learn_rule dates 'Dates go first.'
  run_cli sync --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" 'data["result"]')" = "synced" ]
  [ "$(json_value "$output" 'data["committed"]')" = "True" ]
  git log -1 --format=%B | grep -q '^Learned-by: '

  cd "$other"
  learn_rule signature 'Sign at the end.'
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  [[ "$output" == "Sync: up to date with the remote."* ]]
  grep -Fxq -- '- Dates go first.' .agents/rules/learned.md
  grep -Fxq -- '- Sign at the end.' .agents/rules/learned.md

  cd "$project_dir"
  run_cli sync
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Sign at the end.' .agents/rules/learned.md
  [ "$(git rev-parse HEAD)" = "$(git -C "$remote" rev-parse main)" ]
  run_cli status
  [[ "$output" == *"Sync: up to date"* ]]
}

@test "without network the commit waits, and the first sync that reaches the remote pushes it" {
  setup_office_remote
  mv "$remote" "$test_root/away.git"
  learn_rule dates 'Dates go first.'
  run_cli sync --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" 'data["result"]')" = "offline" ]
  [ "$(json_value "$output" 'data["toPush"]')" = "1" ]
  [ -z "$(git status --porcelain -- .agents/rules)" ]
  run_cli status
  [[ "$output" == *"Sync: offline, 1 commit waiting to go out"* ]]

  mv "$test_root/away.git" "$remote"
  run_cli sync
  [ "$status" -eq 0 ]
  [ "$(git rev-parse HEAD)" = "$(git -C "$remote" rev-parse main)" ]
}

@test "sync off, or the software preset, makes no commit, fetch nor push" {
  setup_office_remote
  before="$(git -C "$remote" rev-parse main)"
  learn_rule dates 'Dates go first.'
  AGENT_READY_SETUP_TEAM_SYNC=0 run_cli sync
  [ "$status" -eq 0 ]
  [[ "$output" == "Sync: off"* ]]
  [ -n "$(git status --porcelain -- .agents/rules)" ]

  python3 - <<'PY'
import json
path = ".agents/agent-ready.json"
manifest = json.load(open(path, encoding="utf-8"))
manifest["collaboration"] = "software"
json.dump(manifest, open(path, "w", encoding="utf-8"), indent=2)
PY
  run_cli sync
  [ "$status" -eq 0 ]
  [[ "$output" == "Sync: nothing to do in the software preset"* ]]
  [ -n "$(git status --porcelain -- .agents/rules)" ]
  [ "$(git -C "$remote" rev-parse main)" = "$before" ]
}

@test "a rule changed two ways is aborted: the checkout is never left half merged, and nothing is forced" {
  setup_office_remote
  learn_rule header 'Put the date in the header.'
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  sed -i.bak 's/Put the date in the header./Put the case in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  theirs="$(git -C "$remote" rev-parse main)"

  cd "$project_dir"
  sed -i.bak 's/Put the date in the header./Put the date and the case in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync --json
  [ "$status" -eq 1 ]
  [ "$(json_value "$output" 'data["result"]')" = "conflict" ]
  [[ "$(json_value "$output" 'data["message"]')" == *".agents/rules/learned.md"* ]]
  [ ! -e "$(git rev-parse --git-path MERGE_HEAD)" ]
  grep -Fxq -- '- Put the date and the case in the header.' .agents/rules/learned.md
  [ "$(git -C "$remote" rev-parse main)" = "$theirs" ]
}

@test "sync waits for the learning: while learn holds the registry, it merges and commits nothing" {
  setup_office_remote
  learn_rule dates 'Dates go first.'
  lock_path="$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import agent_ready_learning as learning; print(learning.RegistryLock(sys.argv[2]).path)' \
    "$skill_dir/scripts" "$project_dir" | tr -d '\r')"
  mkdir -p "$lock_path"
  run_cli sync --json
  rmdir "$lock_path"
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" 'data["result"]')" = "busy" ]
  [ -n "$(git status --porcelain -- .agents/rules)" ]
  run_cli sync
  [ "$status" -eq 0 ]
  [ -z "$(git status --porcelain -- .agents/rules)" ]
}

# 169e: what two people taught alike as personal rules goes to the team in the next sync.
teach_personal() {
  local config="$1" statement="$2"
  XDG_CONFIG_HOME="$config" run_cli learn record --kind rule --key reports.summary --scope personal --explicit \
    --session "s-$RANDOM" --statement "$statement" --quote "a mí me gusta así" --json
  [ "$status" -eq 0 ]
  local entry
  entry="$(json_value "$output" 'data["candidate"]["id"]')"
  XDG_CONFIG_HOME="$config" run_cli learn apply "$entry"
  [ "$status" -eq 0 ]
}

be_person_at() {
  mkdir -p "$1/agent-ready-setup"
  printf '{"id": "%s", "name": "%s"}\n' "$2" "$2" > "$1/agent-ready-setup/identity.json"
}

@test "two people who taught the same personal rule get it as a rule of the team, and their personal ones go" {
  setup_office_remote
  be_person_at "$XDG_CONFIG_HOME" ana
  be_person_at "$test_root/config-other" juan
  teach_personal "$XDG_CONFIG_HOME" "Reports end with a one-line summary."
  run_cli sync
  [ "$status" -eq 0 ]

  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  teach_personal "$test_root/config-other" "Reports end with a one-line summary."
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  grep -Fxq '<!-- rule id=learned/reports-summary key=reports.summary -->' .agents/rules/learned.md
  ! grep -q 'one-line summary' .agents/rules/learned/users/ana/learned.md
  ! grep -q 'one-line summary' .agents/rules/learned/users/juan/learned.md
  grep -q ' promote learn-.* (learned/reports-summary, from the personal rules of ana, juan): ' .agents/learning/log.md

  cd "$project_dir"
  run_cli sync
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Reports end with a one-line summary.' .agents/rules/learned.md
  [ "$(python3 -c 'import json; print(sorted(entry["status"] for entry in json.load(open(".agents/learning/candidates.json"))["candidates"] if entry.get("scope") == "personal"))' | tr -d '\r')" = \
    "['superseded', 'superseded']" ]
  run_cli rules lint
  [ "$status" -eq 0 ]
}

@test "two machines that promote the same rule at once end with it once" {
  setup_office_remote
  be_person_at "$XDG_CONFIG_HOME" ana
  be_person_at "$test_root/config-other" juan
  # No promotion while both personal rules travel; each machine turns it on by itself afterwards.
  printf '%s\n' '{"profiles": ["learning"], "sync": {"promoteAfterUsers": 0}}' > .agents/agent-ready.json
  git commit -qm "no promotion yet" -- .agents/agent-ready.json
  git push -q origin HEAD:main
  teach_personal "$XDG_CONFIG_HOME" "Reports end with a one-line summary."
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  teach_personal "$test_root/config-other" "Reports end with a one-line summary."
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ] || { printf '%s\n%s\n' "$output" "$stderr"; git status --short; false; }
  cd "$project_dir"
  run_cli sync
  [ "$status" -eq 0 ]

  # Both machines promote before either has seen the other's promotion.
  for checkout in "$project_dir" "$other"; do
    sed -i.bak 's/"promoteAfterUsers": 0/"promoteAfterUsers": 2/' "$checkout/.agents/agent-ready.json"
    rm -f "$checkout/.agents/agent-ready.json.bak"
  done
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync --json
  [ "$status" -eq 0 ]
  [ "$(json_value "$output" 'data["result"]')" = "synced" ]
  [ "$(grep -c '^<!-- rule id=learned/reports-summary ' .agents/rules/learned.md)" -eq 1 ]
  [ "$(python3 -c 'import json; print(sum(1 for entry in json.load(open(".agents/learning/candidates.json"))["candidates"] if entry.get("learned", {}).get("action") == "promote"))' | tr -d '\r')" = 1 ]
}

@test "promoteAfterUsers 1 promotes the personal rule of one person, and 0 none" {
  setup_office_remote
  be_person_at "$XDG_CONFIG_HOME" ana
  python3 -c 'import json; json.dump({"profiles": ["learning"], "sync": {"promoteAfterUsers": 0}}, open(".agents/agent-ready.json", "w"))'
  teach_personal "$XDG_CONFIG_HOME" "Reports end with a one-line summary."
  run_cli sync
  [ "$status" -eq 0 ]
  ! grep -q 'learned/reports-summary' .agents/rules/learned.md 2>/dev/null

  python3 -c 'import json; json.dump({"profiles": ["learning"], "sync": {"promoteAfterUsers": 1}}, open(".agents/agent-ready.json", "w"))'
  run_cli sync
  [ "$status" -eq 0 ]
  grep -Fxq '<!-- rule id=learned/reports-summary key=reports.summary -->' .agents/rules/learned.md
}

# 169f: a rule two people changed in two ways waits for a person, who decides it once.
make_rule_conflict() {
  setup_office_remote
  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup" "$test_root/config-other/agent-ready-setup"
  printf '%s\n' '{"id": "ana", "name": "Ana"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  printf '%s\n' "{\"id\": \"${1:-juan}\", \"name\": \"Other\"}" > "$test_root/config-other/agent-ready-setup/identity.json"
  learn_rule header 'Put the date in the header.'
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  sed -i.bak 's/Put the date in the header./Put the case in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  cd "$project_dir"
  sed -i.bak 's/Put the date in the header./Put the date at the top of the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync
  [ "$status" -eq 1 ]
  conflict_id='.agents/rules/learned.md#learned/header'
}

@test "a rule changed two ways is explained at the next session, and keeping theirs merges, pushes and logs it" {
  make_rule_conflict
  run_cli sync --conflicts
  [ "$status" -eq 0 ]
  [[ "$output" == *"Two people changed the same rule in different ways"* ]]
  [[ "$output" == *"$conflict_id"* ]]
  [[ "$output" == *"this machine, ana at "*": Put the date at the top of the header."* ]]
  [[ "$output" == *"the other, juan at "*": Put the case in the header."* ]]

  run_cli sync --resolve "$conflict_id" --keep theirs
  [ "$status" -eq 0 ]
  [[ "$output" == *"Sync: up to date with the remote."* ]]
  grep -Fxq -- '- Put the case in the header.' .agents/rules/learned.md
  ! grep -q '^<<<<<<<' .agents/rules/learned.md
  ! grep -q 'top of the header' .agents/rules/learned.md
  grep -q ' resolve learned/header (theirs, decided by ana): ' .agents/learning/log.md
  [ "$(git rev-parse HEAD)" = "$(git -C "$remote" rev-parse main)" ]
  run_cli sync --conflicts
  [ -z "$output" ]
}

@test "a combined statement replaces both versions of the rule" {
  make_rule_conflict
  run_cli sync --resolve "$conflict_id" --merged "Put the date and the case at the top of the header."
  [ "$status" -eq 0 ]
  grep -Fxq '<!-- rule id=learned/header -->' .agents/rules/learned.md
  grep -Fxq -- '- Put the date and the case at the top of the header.' .agents/rules/learned.md
  run_cli rules lint
  [ "$status" -eq 0 ]
}

@test "each one keeps their own: the rule of the team leaves, and each version is personal for who taught it" {
  make_rule_conflict
  run_cli sync --resolve "$conflict_id"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"--resolve needs exactly one of"* ]]
  run_cli sync --resolve "$conflict_id" --each-their-own
  [ "$status" -eq 0 ]
  ! grep -q 'learned/header -->' .agents/rules/learned.md
  grep -Fxq -- '- Put the date at the top of the header.' .agents/rules/learned/users/ana/learned.md
  grep -Fxq -- '- Put the case in the header.' .agents/rules/learned/users/juan/learned.md
  run_cli rules lint
  [ "$status" -eq 0 ]
}

# The other machine edits $1 with sed $2 and syncs.
other_edits() {
  cd "$other"
  sed -i.bak "$2" "$1"
  rm -f "$1.bak"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  cd "$project_dir"
}

@test "a decision waits for the rest: two rule files in conflict are decided one by one and merged once" {
  setup_office_remote
  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup" "$test_root/config-other/agent-ready-setup"
  printf '%s\n' '{"id": "ana", "name": "Ana"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  printf '%s\n' '{"id": "juan", "name": "Juan"}' > "$test_root/config-other/agent-ready-setup/identity.json"
  learn_rule header 'Put the date in the header.'
  RULE_FILE=.agents/rules/learned/reports.md learn_rule reports 'Reports start with a summary.'
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  sed -i.bak 's/Put the date in the header./Put the case in the header./' .agents/rules/learned.md
  sed -i.bak 's/Reports start with a summary./Reports start with the client./' .agents/rules/learned/reports.md
  rm -f .agents/rules/learned.md.bak .agents/rules/learned/reports.md.bak
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  cd "$project_dir"
  sed -i.bak 's/Put the date in the header./Put the date at the top of the header./' .agents/rules/learned.md
  sed -i.bak 's/Reports start with a summary./Reports start with the date./' .agents/rules/learned/reports.md
  rm -f .agents/rules/learned.md.bak .agents/rules/learned/reports.md.bak
  run_cli sync
  [ "$status" -eq 1 ]
  conflict_id='.agents/rules/learned.md#learned/header'
  run_cli sync --resolve "$conflict_id" --keep theirs
  [ "$status" -eq 1 ]
  # The decision of learned.md is kept although its file merged in the aborted attempt.
  run_cli sync --conflicts
  [[ "$output" == *".agents/rules/learned/reports.md#learned/reports"* ]]
  [[ "$output" != *"$conflict_id"* ]]
  run_cli sync --resolve '.agents/rules/learned/reports.md#learned/reports' --keep mine
  [ "$status" -eq 0 ]
  [[ "$output" == *"Sync: up to date with the remote."* ]]
  grep -Fxq -- '- Put the case in the header.' .agents/rules/learned.md
  grep -Fxq -- '- Reports start with the date.' .agents/rules/learned/reports.md
  grep -q ' resolve learned/header (theirs, decided by ana): ' .agents/learning/log.md
  grep -q ' resolve learned/reports (mine, decided by ana): ' .agents/learning/log.md
}

@test "a decision holds only for the versions the person saw: a newer change of the other asks again" {
  make_rule_conflict
  # The person saw "the case"; before the sync with the decision, the other machine changed it again.
  other_edits .agents/rules/learned.md 's/Put the case in the header./Put the case number in the header./'
  run_cli sync --resolve "$conflict_id" --keep theirs
  [ "$status" -eq 1 ]
  ! grep -q 'Put the case in the header.' .agents/rules/learned.md
  run_cli sync --conflicts
  [[ "$output" == *"the other, juan at "*": Put the case number in the header."* ]]
}

@test "each version is told by who changed that rule, not by the last one who changed its file" {
  make_rule_conflict
  # Carla, on the other machine, teaches another rule of the same file after Juan changed the header.
  mkdir -p "$test_root/config-carla/agent-ready-setup"
  printf '%s\n' '{"id": "carla", "name": "Carla"}' > "$test_root/config-carla/agent-ready-setup/identity.json"
  cd "$other"
  learn_rule closing 'Sign at the end.'
  XDG_CONFIG_HOME="$test_root/config-carla" run_cli sync
  [ "$status" -eq 0 ]
  cd "$project_dir"
  run_cli sync
  [ "$status" -eq 1 ]
  run_cli sync --conflicts
  [[ "$output" == *"the other, juan at "*": Put the case in the header."* ]]
  [[ "$output" != *"the other, carla"* ]]
}

@test "each one keeps their own needs two people and a rule for the whole repository" {
  make_rule_conflict ana
  run_cli sync --resolve "$conflict_id" --each-their-own
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"both versions are from the same person"* ]]

  rm -rf "$test_root/remote.git" "$other"
  RULE_ATTRIBUTES='paths=docs/**' make_rule_conflict
  run_cli sync --resolve "$conflict_id" --each-their-own
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"this rule applies to some files only"* ]]
}

@test "a rule file one machine deleted and the other changed is decided like any other conflict" {
  setup_office_remote
  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup" "$test_root/config-other/agent-ready-setup"
  printf '%s\n' '{"id": "ana", "name": "Ana"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  printf '%s\n' '{"id": "juan", "name": "Juan"}' > "$test_root/config-other/agent-ready-setup/identity.json"
  RULE_FILE=.agents/rules/learned/reports.md learn_rule reports 'Reports start with a summary.'
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  cd "$project_dir"
  other_edits .agents/rules/learned/reports.md 's/Reports start with a summary./Reports start with the client./'
  rm .agents/rules/learned/reports.md
  run_cli sync
  [ "$status" -eq 1 ]
  run_cli sync --conflicts
  [[ "$output" == *".agents/rules/learned/reports.md#learned/reports"* ]]
  run_cli sync --resolve '.agents/rules/learned/reports.md#learned/reports' --keep theirs
  [ "$status" -eq 0 ]
  [[ "$output" == *"Sync: up to date with the remote."* ]]
  grep -Fxq -- '- Reports start with the client.' .agents/rules/learned/reports.md
  [ ! -e "$(git rev-parse --git-path MERGE_HEAD)" ]
  [ "$(git rev-parse HEAD)" = "$(git -C "$remote" rev-parse main)" ]
}

@test "a rule written with accents keeps them in the explanation and in the personal rules of each one" {
  setup_office_remote
  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup" "$test_root/config-other/agent-ready-setup"
  printf '%s
' '{"id": "ana", "name": "Ana"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  printf '%s
' '{"id": "juan", "name": "Juan"}' > "$test_root/config-other/agent-ready-setup/identity.json"
  learn_rule header 'Poné la fecha en el encabezado.'
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  sed -i.bak 's/Poné la fecha en el encabezado./Poné el número de expediente en el encabezado./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  cd "$project_dir"
  sed -i.bak 's/Poné la fecha en el encabezado./Poné la fecha arriba de todo, en el encabezado./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync
  [ "$status" -eq 1 ]
  run_cli sync --conflicts
  [[ "$output" == *"the other, juan at "*": Poné el número de expediente en el encabezado."* ]]
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --each-their-own
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Poné la fecha arriba de todo, en el encabezado.' .agents/rules/learned/users/ana/learned.md
  grep -Fxq -- '- Poné el número de expediente en el encabezado.' .agents/rules/learned/users/juan/learned.md
}

@test "each one keeps their own is refused when a version has no known author or its personal rule already exists" {
  make_rule_conflict
  mkdir -p .agents/rules/learned/users/ana
  printf '%s\n' '# Personal rules' '' '<!-- rule id=learned/users/ana/header -->' '- Put the logo in the header.' \
    > .agents/rules/learned/users/ana/learned.md
  run_cli sync --resolve "$conflict_id" --each-their-own
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"already has a personal rule with this id"* ]]
  rm -rf .agents/rules/learned/users
  python3 - "$(git rev-parse --git-path info/agent-ready/sync-conflicts.json)" <<'PY'
import json, sys
path = sys.argv[1]
state = json.load(open(path, encoding="utf-8"))
state["conflicts"][0]["theirs"]["by"] = None
json.dump(state, open(path, "w", encoding="utf-8"))
PY
  run_cli sync --resolve "$conflict_id" --each-their-own
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"who wrote one of the versions is not known"* ]]
}

@test "a combined statement keeps the exceptions both versions share" {
  setup_office_remote
  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup" "$test_root/config-other/agent-ready-setup"
  printf '%s\n' '{"id": "ana", "name": "Ana"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  printf '%s\n' '{"id": "juan", "name": "Juan"}' > "$test_root/config-other/agent-ready-setup/identity.json"
  learn_rule header 'Put the date in the header.'
  printf '%s\n' '  - Except: leave archived records unchanged.' >> .agents/rules/learned.md
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  sed -i.bak 's/Put the date in the header./Put the case in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  [ "$status" -eq 0 ]
  cd "$project_dir"
  sed -i.bak 's/Put the date in the header./Put the date at the top of the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync
  [ "$status" -eq 1 ]
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --merged "Put the date and the case at the top of the header."
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Put the date and the case at the top of the header.' .agents/rules/learned.md
  grep -Fxq -- '  - Except: leave archived records unchanged.' .agents/rules/learned.md
}

@test "each one keeps their own keeps the exceptions of each version in its personal rule" {
  setup_office_remote
  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup" "$test_root/config-other/agent-ready-setup"
  printf '%s\n' '{"id": "ana", "name": "Ana"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  printf '%s\n' '{"id": "juan", "name": "Juan"}' > "$test_root/config-other/agent-ready-setup/identity.json"
  learn_rule header 'Put the date in the header.'
  printf '%s\n' '  - Except: leave archived records unchanged.' >> .agents/rules/learned.md
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  sed -i.bak 's/Put the date in the header./Put the case in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  cd "$project_dir"
  sed -i.bak 's/Put the date in the header./Put the date at the top of the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync
  [ "$status" -eq 1 ]
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --each-their-own
  [ "$status" -eq 0 ]
  for person in ana juan; do
    grep -Fxq -- '  - Except: leave archived records unchanged.' ".agents/rules/learned/users/$person/learned.md"
  done
  run_cli rules lint
  [ "$status" -eq 0 ]
}

@test "a decision the merge no longer needs is dropped: the other went back, and nothing personal is written" {
  make_rule_conflict
  # Juan puts the rule back as it was: the change of this machine merges by itself.
  other_edits .agents/rules/learned.md 's/Put the case in the header./Put the date in the header./'
  run_cli sync --resolve "$conflict_id" --each-their-own
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Put the date at the top of the header.' .agents/rules/learned.md
  [ ! -e .agents/rules/learned/users ]
  ! grep -q ' resolve learned/header ' .agents/learning/log.md
  run_cli sync --conflicts
  [ -z "$output" ]
}

@test "a conflict that nobody decided goes away when the other side went back, and nobody is asked about it" {
  make_rule_conflict
  other_edits .agents/rules/learned.md 's/Put the case in the header./Put the date in the header./'
  run_cli sync
  [ "$status" -eq 0 ]
  run_cli sync --conflicts
  [ -z "$output" ]
}

@test "each one keeps their own is refused while another rule requires the team rule it would remove" {
  setup_office_remote
  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup" "$test_root/config-other/agent-ready-setup"
  printf '%s\n' '{"id": "ana", "name": "Ana"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  printf '%s\n' '{"id": "juan", "name": "Juan"}' > "$test_root/config-other/agent-ready-setup/identity.json"
  learn_rule header 'Put the date in the header.'
  RULE_ATTRIBUTES='requires=learned/header' learn_rule header-format 'Write the header in bold.'
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  sed -i.bak 's/Put the date in the header./Put the case in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  cd "$project_dir"
  sed -i.bak 's/Put the date in the header./Put the date at the top of the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync
  [ "$status" -eq 1 ]
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --each-their-own
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"the rule learned/header-format requires this one"* ]]
}

@test "a combined statement that would not pass the lint is refused before anything is decided" {
  make_rule_conflict
  run_cli sync --resolve "$conflict_id" --merged "Put the date in the header. Put the case number in the header."
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"the combined statement would not be a valid rule"* ]]
  run_cli sync --conflicts
  [[ "$output" == *"$conflict_id"* ]]
}

@test "a statement that continues on the next line is replaced whole by the combined one" {
  setup_office_remote
  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup" "$test_root/config-other/agent-ready-setup"
  printf '%s\n' '{"id": "ana", "name": "Ana"}' > "$XDG_CONFIG_HOME/agent-ready-setup/identity.json"
  printf '%s\n' '{"id": "juan", "name": "Juan"}' > "$test_root/config-other/agent-ready-setup/identity.json"
  learn_rule header 'Put the date'
  printf '%s\n' '  in the header.' >> .agents/rules/learned.md
  run_cli sync
  [ "$status" -eq 0 ]
  cd "$other"
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  sed -i.bak 's/^- Put the date$/- Put the case/' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  XDG_CONFIG_HOME="$test_root/config-other" run_cli sync
  cd "$project_dir"
  sed -i.bak 's/^- Put the date$/- Put the date and the time/' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync
  [ "$status" -eq 1 ]
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --merged "Put the date and the case in the header."
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Put the date and the case in the header.' .agents/rules/learned.md
  ! grep -Fxq -- '  in the header.' .agents/rules/learned.md
}

@test "a file whose title also changed two ways is named after its rule is decided" {
  make_rule_conflict
  other_edits .agents/rules/learned.md 's/^# Learned rules$/# Rules of the office/'
  sed -i.bak 's/^# Learned rules$/# What we learned/' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync
  run_cli sync --resolve "$conflict_id" --keep theirs
  [ "$status" -eq 1 ]
  [[ "$output" == *"the same part changed on two machines: .agents/rules/learned.md"* ]]
}

# 169g: in the software preset, the rules of the merge the developer does; nothing syncs by itself.
setup_code_repository() {
  run_cli apply --profiles learning
  [ "$status" -eq 0 ]
  python3 - <<'PY'
import json
path = ".agents/agent-ready.json"
manifest = json.load(open(path, encoding="utf-8"))
manifest["collaboration"] = "software"
json.dump(manifest, open(path, "w", encoding="utf-8"))
PY
  learn_rule header 'Put the date in the header.'
  git add -A
  git commit -qm "agent-ready and a learned rule"
  base_branch="$(git symbolic-ref --short HEAD)"
  git checkout -qb other-work
}

@test "software: two branches that learned different rules merge with the drivers, without a conflict" {
  setup_code_repository
  learn_rule closing 'Sign at the end.'
  git commit -qam "learn: closing"
  git checkout -q "$base_branch"
  learn_rule summary 'Start with a summary.'
  git commit -qam "learn: summary"
  git merge -q --no-edit other-work
  grep -Fxq -- '- Sign at the end.' .agents/rules/learned.md
  grep -Fxq -- '- Start with a summary.' .agents/rules/learned.md
}

@test "software: the same rule changed on two branches is explained and written into the merge, which stays the developer's" {
  setup_code_repository
  sed -i.bak 's/Put the date in the header./Put the case in the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  git commit -qam "learn: the case in the header"
  git checkout -q "$base_branch"
  sed -i.bak 's/Put the date in the header./Put the date at the top of the header./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  git commit -qam "learn: the date at the top"
  ! git merge -q --no-edit other-work
  run_cli sync --conflicts
  [ "$status" -eq 0 ]
  [[ "$output" == *"the two branches changed in different ways"* ]]
  [[ "$output" == *"this branch, "*": Put the date at the top of the header."* ]]
  [[ "$output" == *"the other branch, "*": Put the case in the header."* ]]
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --each-their-own
  [ "$status" -ne 0 ]
  # A combined statement that would not pass the lint writes nothing.
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --merged "Put the date in the header. Put the case in it."
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"the combined statement would not be a valid rule"* ]]
  [ -n "$(git diff --name-only --diff-filter=U)" ]
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --merged "Put the date and the case at the top of the header."
  [ "$status" -eq 0 ]
  [[ "$output" == *"staged; finish the merge with git commit"* ]]
  grep -Fxq -- '- Put the date and the case at the top of the header.' .agents/rules/learned.md
  [ -z "$(git diff --name-only --diff-filter=U)" ]
  # Nothing was committed nor pushed: the merge is still the developer's.
  [ -e "$(git rev-parse --git-path MERGE_HEAD)" ]
  git commit -q --no-edit
  run_cli sync --conflicts
  [ -z "$output" ]
}

# Both branches change the rule $1 of $2: this one with sed $3, other-work with sed $4; the merge conflicts.
branches_change_rule() {
  git checkout -q other-work
  sed -i.bak "$4" "$2"
  rm -f "$2.bak"
  git commit -qam "other-work changes $1"
  git checkout -q "$base_branch"
  sed -i.bak "$3" "$2"
  rm -f "$2.bak"
  git commit -qam "this branch changes $1"
  ! git merge -q --no-edit other-work
}

@test "software: a rule file with accents in its name is found and resolved" {
  setup_code_repository
  RULE_FILE=.agents/rules/política.md learn_rule firma 'Firmá al final.'
  git add -A
  git commit -qm "learn: firma"
  git checkout -q "$base_branch"
  git merge -q --no-edit other-work
  branches_change_rule firma .agents/rules/política.md 's/Firmá al final./Firmá al pie./' 's/Firmá al final./Firmá con aclaración./'
  run_cli sync --conflicts
  [[ "$output" == *".agents/rules/política.md#learned/firma"* ]]
  run_cli sync --resolve '.agents/rules/política.md#learned/firma' --keep theirs
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Firmá con aclaración.' .agents/rules/política.md
}

@test "software: a file that also conflicts in its title is left to the developer, never rewritten" {
  setup_code_repository
  git checkout -q "$base_branch"
  branches_change_rule header .agents/rules/learned.md \
    's/Put the date in the header./Put the date at the top./; s/^# Learned rules$/# Our rules/' \
    's/Put the date in the header./Put the case in the header./; s/^# Learned rules$/# Team rules/'
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --keep mine
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"also conflicts outside its rules"* ]]
  grep -q '^<<<<<<<' .agents/rules/learned.md
}

@test "software: a decision of an aborted merge does not hide a rule that changed since" {
  setup_code_repository
  git checkout -q "$base_branch"
  branches_change_rule header .agents/rules/learned.md \
    's/Put the date in the header./Put the date at the top./' 's/Put the date in the header./Put the case in the header./'
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --keep mine
  [ "$status" -eq 0 ]
  git merge --abort
  sed -i.bak 's/Put the date at the top./Put the date at the very top./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  git commit -qam "this branch changes header again"
  ! git merge -q --no-edit other-work
  run_cli sync --conflicts
  [[ "$output" == *"this branch, "*": Put the date at the very top."* ]]
}

@test "software: a file edited by hand after a --resolve is not rewritten by the next one" {
  setup_code_repository
  learn_rule closing 'Sign at the end.'
  git commit -qam "learn: closing"
  git checkout -q "$base_branch"
  git merge -q --no-edit other-work
  branches_change_rule header .agents/rules/learned.md \
    's/Put the date in the header./Put the date at the top./; s/Sign at the end./Sign at the foot./' \
    's/Put the date in the header./Put the case in the header./; s/Sign at the end./Sign with a stamp./'
  run_cli sync --resolve '.agents/rules/learned.md#learned/header' --keep mine
  [ "$status" -eq 0 ]
  sed -i.bak 's/Put the date at the top./Put the date at the very top./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  run_cli sync --resolve '.agents/rules/learned.md#learned/closing' --keep theirs
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"changed after agent-ready sync --resolve wrote it"* ]]
  grep -Fxq -- '- Put the date at the very top.' .agents/rules/learned.md
}

@test "software: a rule file the other branch renamed is found at its new name" {
  setup_code_repository
  mkdir -p .agents/rules/learned
  git mv .agents/rules/learned.md .agents/rules/learned/office.md
  sed -i.bak 's/Put the date in the header./Put the case in the header./' .agents/rules/learned/office.md
  rm -f .agents/rules/learned/office.md.bak
  git commit -qam "other-work renames the rules and changes header"
  git checkout -q "$base_branch"
  sed -i.bak 's/Put the date in the header./Put the date at the top./' .agents/rules/learned.md
  rm -f .agents/rules/learned.md.bak
  git commit -qam "this branch changes header"
  ! git merge -q --no-edit other-work
  run_cli sync --conflicts
  [[ "$output" == *".agents/rules/learned/office.md#learned/header"* ]]
  run_cli sync --resolve '.agents/rules/learned/office.md#learned/header' --keep theirs
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Put the case in the header.' .agents/rules/learned/office.md
}
