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
  [[ "$stderr" == *"unknown profile source other; the sources are: golfo-kit, acme"* ]]

  before="$(tree_fingerprint)"
  run_cli update acme --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme-new.md"* ]]
  [ "$(tree_fingerprint)" = "$before" ]

  run_cli update
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-new.md ]
}

@test "update follows the effective configuration: with sources off it only updates golfo-kit" {
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
  run_cli profiles remove node
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"select at least one stack profile"* ]]
  run_cli profiles add nope
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"unknown profile 'nope'"* ]]
  run_cli profiles remove browser
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"not selected: browser"* ]]
  [ "$(cksum < .agents/agent-ready.json)" = "$before" ]

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
  [ "$(json_value "$output" '[(row["name"], row["state"], len(row["profiles"])) for row in data["sources"]]')" = "[('acme', 'available', 2)]" ]

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
  [[ "$stderr" == *"checked against golfo-kit's catalog only"* ]]
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
