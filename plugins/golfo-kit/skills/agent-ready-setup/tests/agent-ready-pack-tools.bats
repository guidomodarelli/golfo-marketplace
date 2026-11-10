#!/usr/bin/env bats
# Tools a profile pack declares besides files (CLIs, MCP servers and scripts) and the security
# policy that decides whether each one may run on this machine. An apply registers the allowed
# MCP servers for Claude Code and Codex; CLIs and scripts are only reported yet. The pack is a Git
# repository reached through url.insteadOf, so the manifest keeps its real URL.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
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
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES
  for provider_cli in claude codex; do
    printf '#!/bin/bash\nexit 0\n' > "$fake_bin/$provider_cli"
    chmod +x "$fake_bin/$provider_cli"
  done
  publish_tools_pack
  git -C "$project_dir" init -q
  cd "$project_dir"
  printf '{}\n' > package.json
  write_manifest '{"profiles": ["acme/kafka-interno"], "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme#main"}]}}'
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

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

# The example pack with tools on kafka-interno: a CLI from a release file, one from an npm
# package without sha256, an MCP server, an install script that pipes curl to sh and a
# session-start script.
publish_tools_pack() {
  pack_repository="$test_root/repositories/acme"
  mkdir -p "$(dirname "$pack_repository")"
  cp -R "$example_pack" "$pack_repository"
  mkdir -p "$pack_repository/scripts"
  printf '#!/bin/bash\ncurl -fsSL https://downloads.example.invalid/install | sh\n' > "$pack_repository/scripts/setup.sh"
  printf '#!/bin/bash\necho refresh\n' > "$pack_repository/scripts/refresh.sh"
  set_tool_declarations "$pack_repository/agent-ready-pack.json"
  git -C "$pack_repository" init -q
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm initial
  git config --global "url.file:///$(native_path "$pack_repository" | sed 's#^/##').insteadOf" "https://packs.example.invalid/acme"
}

set_tool_declarations() {
  python3 - "$1" <<'PY'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path, encoding="utf-8"))
catalog["profiles"]["kafka-interno"].update({
    "clis": [
        {"name": "acme", "version": "1.4.2", "artifacts": [
            {"platform": "linux-x64", "url": "https://downloads.example.invalid/acme-linux-x64.tar.gz",
             "sha256": "0" * 64, "binary": "acme"}]},
        {"name": "acme-helper", "version": "2.0.0", "package": {"manager": "npm", "name": "@acme/helper"}},
    ],
    "mcpServers": {"acme-docs": {"command": "acme", "args": ["mcp"], "env": {"ACME_TOKEN": "${ACME_TOKEN}"}}},
    "scripts": [
        {"event": "install", "path": "scripts/setup.sh", "interpreter": "bash", "timeoutSeconds": 60},
        {"event": "session-start", "path": "scripts/refresh.sh", "interpreter": "bash", "timeoutSeconds": 30},
    ],
})
json.dump(catalog, open(path, "w", encoding="utf-8"), indent=2)
PY
}

write_manifest() {
  mkdir -p .agents
  printf '%s\n' "$1" > .agents/agent-ready.json
}

run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready" "$@"
}

# One line per declared tool from plan --json: "<type> <name> <decision> <reason>".
plan_tools() {
  run_cli plan --json
  [ "$status" -eq 0 ]
  printf '%s' "$output" | python3 -c '
import json, sys
report = json.load(sys.stdin).get("packTools") or {"tools": []}
for tool in report["tools"]:
    print(tool["type"], tool["name"], tool["decision"], tool["reason"] or "")' | tr -d '\r' > "$test_root/tools.txt"
}

decision_of() {
  grep -F "$1 $2 " "$test_root/tools.txt"
}

# Asserts a Python expression about the parsed JSON file ($1), given as data.
assert_json() {
  python3 -c 'import json, sys; data = json.load(open(sys.argv[1], encoding="utf-8")); assert eval(sys.argv[2]), data' "$1" "$2"
}

# Adds a remote MCP server to kafka-interno and commits it to the pack.
add_remote_server() {
  python3 - "$pack_repository/agent-ready-pack.json" <<'PY'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path, encoding="utf-8"))
catalog["profiles"]["kafka-interno"]["mcpServers"]["acme-remote"] = {
    "url": "https://mcp.example.invalid/acme",
    "headers": {"Authorization": "Bearer ${ACME_TOKEN}", "X-Api-Key": "${ACME_KEY}"},
}
json.dump(catalog, open(path, "w", encoding="utf-8"), indent=2)
PY
  git -C "$pack_repository" commit -qam "remote server"
}

@test "without configuration a pack with tools projects its rules and skills and runs nothing" {
  run_cli apply
  [ "$status" -eq 0 ]
  [ -f .agents/rules/acme-kafka.md ]
  ! grep -qs acme-docs .mcp.json

  plan_tools
  [ "$(wc -l < "$test_root/tools.txt" | tr -d ' ')" -eq 5 ]
  [[ "$(decision_of cli acme)" == *"blocked the source acme is not trusted on this machine; trust it with agent-ready trust add acme"* ]]
  [[ "$(decision_of mcpServer acme-docs)" == *"blocked the source acme is not trusted"* ]]
  [[ "$(decision_of script acme/scripts/setup.sh)" == *"blocked the source acme is not trusted"* ]]

  run_cli status
  [ "$status" -eq 0 ]
  [[ "$output" == *"Pack tools (what the security policy allows; an apply registers the allowed MCP servers, and does not install CLIs or run scripts yet)"* ]]
  [[ "$output" == *"- blocked: cli acme 1.4.2 (artifacts) [acme/kafka-interno]"* ]]
}

@test "trusting a source lets its tools pass the policy, except what the checks and events still stop" {
  run_cli trust add acme
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"Trusted on this machine: acme (https://packs.example.invalid/acme)"* ]]
  grep -Fq 'https://packs.example.invalid/acme' "$XDG_CONFIG_HOME/agent-ready-setup/config.json"

  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
  [ "$(decision_of mcpServer acme-docs)" = "mcpServer acme-docs allowed " ]
  [ "$(decision_of script acme/scripts/setup.sh)" = "script acme/scripts/setup.sh allowed " ]
  [[ "$(decision_of cli acme-helper)" == *"blocked security.checks.artifactSha256: the npm package of acme-helper declares no sha256"* ]]
  [[ "$(decision_of script acme/scripts/refresh.sh)" == *"blocked security.execution.events does not include session-start"* ]]

  run_cli trust list
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme  trusted"* ]]
  run_cli trust remove acme
  [ "$status" -eq 0 ]
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked the source acme is not trusted"* ]]
}

@test "whoever adds a source with sources add trusts it on their machine" {
  write_manifest '{"profiles": ["node"]}'
  run_cli sources add acme "git+https://packs.example.invalid/acme#main"
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"Trusted on this machine, because you added it: https://packs.example.invalid/acme"* ]]
  run_cli trust list
  [[ "$output" == *"acme  trusted"* ]]
}

@test "deny wins over allow, rules decide between them, and allow lists restrict only when they list something" {
  run_cli trust add acme
  run_cli config set security.allow.clis mytool
  [ "$status" -eq 0 ]
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.allow.clis does not include acme"* ]]

  run_cli config set security.allow.clis acme,mytool
  run_cli config set security.deny.commands acme
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.deny.commands matches acme"* ]]
  # The MCP server launches the same command, so the same deny stops it.
  [[ "$(decision_of mcpServer acme-docs)" == *"blocked security.deny.commands matches acme"* ]]

  run_cli config set security.rules '[{"match": {"type": "script", "contains": "| sh"}, "action": "deny"}]'
  [ "$status" -eq 0 ]
  plan_tools
  [[ "$(decision_of script acme/scripts/setup.sh)" == *"blocked security.rules: deny contains | sh, type script"* ]]

  # A rule that allows lets a tool outside an allow list through, never past a deny.
  run_cli config unset security.deny.commands
  run_cli config set security.allow.clis mytool
  run_cli config set security.rules '[{"match": {"type": "cli", "pattern": "acme"}, "action": "allow"}]' --layer user
  [ "$status" -eq 0 ]
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
}

@test "each mechanism of the policy turns off on its own" {
  run_cli trust add acme
  run_cli config set security.execution.enabled false --layer user
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.execution.enabled is false"* ]]
  [[ "$(decision_of script acme/scripts/setup.sh)" == *"blocked security.execution.enabled is false"* ]]
  run_cli config unset security.execution.enabled --layer user

  run_cli config set security.checks.artifactSha256 false --layer user
  plan_tools
  [ "$(decision_of cli acme-helper)" = "cli acme-helper allowed " ]

  run_cli config set security.execution.events install,post-apply,session-start --layer user
  plan_tools
  [ "$(decision_of script acme/scripts/refresh.sh)" = "script acme/scripts/refresh.sh allowed " ]

  run_cli config set security.checks.signature true --layer user
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: the signature of acme is not verified"* ]]
  run_cli config unset security.checks.signature --layer user

  run_cli trust remove acme
  run_cli config set security.checks.trustedSource false --layer user
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
}

@test "a manifest that loosens the policy counts only in a repository this machine approved" {
  run_cli config set security.checks.trustedSource false
  [ "$status" -eq 0 ]
  run_cli config set security.trustedSources https://packs.example.invalid/acme
  [ "$status" -eq 0 ]
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked the source acme is not trusted"* ]]
  run_cli plan
  [[ "$output" == *"security.checks.trustedSource=false from the project layer was ignored"* ]]
  [[ "$output" == *"security.trustedSources"*"was ignored"* ]]

  run_cli trust add --project .
  [ "$status" -eq 0 ]
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
}

@test "a key the organization locks cannot be loosened from the user or the project" {
  mkdir -p "$(dirname "$AGENT_READY_SETUP_ORGANIZATION_CONFIG")"
  printf '%s\n' '{"security": {"checks": {"trustedSource": true}}, "locked": ["security.checks"]}' > "$AGENT_READY_SETUP_ORGANIZATION_CONFIG"
  run_cli config set security.checks.trustedSource false --layer user
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked the source acme is not trusted"* ]]
  run_cli config explain security.checks.trustedSource
  [[ "$output" == *"ignored from the user layer: false (locked)"* ]]

  rm "$AGENT_READY_SETUP_ORGANIZATION_CONFIG"
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
}

@test "plan --json shows the effective policy and the layer of each value" {
  run_cli config set security.deny.scripts 'acme/*' --layer user
  run_cli plan --json
  [ "$status" -eq 0 ]
  policy() {
    printf '%s' "$output" | python3 -c 'import json,sys; item=json.load(sys.stdin)["packTools"]["policy"][sys.argv[1]]; print(item["value"], item["origin"])' "$1" | tr -d '\r'
  }
  [ "$(policy security.checks.trustedSource)" = "True defaults" ]
  [ "$(policy security.deny.scripts)" = "['acme/*'] user" ]
  [ "$(printf '%s' "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["packTools"]["applies"])' | tr -d '\r')" = "['mcpServer']" ]
}

@test "a declaration outside the schema stops the apply before writing" {
  for change in \
    'catalog["profiles"]["kafka-interno"]["mcpServers"]["acme-docs"]["env"]["ACME_TOKEN"] = "plain-secret"' \
    'catalog["profiles"]["kafka-interno"]["mcpServers"]["acme-docs"]["env"]["ACME_TOKEN"] = "${OTHER_TOKEN}"' \
    'catalog["profiles"]["kafka-interno"]["clis"][0]["version"] = "^1.4"' \
    'catalog["profiles"]["kafka-interno"]["scripts"][0]["path"] = "scripts/missing.sh"' \
    'catalog["profiles"]["kafka-interno"]["clis"][0]["artifacts"][0]["url"] = "http://downloads.example.invalid/acme"'; do
    git -C "$pack_repository" reset -q --hard HEAD
    python3 - "$pack_repository/agent-ready-pack.json" "$change" <<'PY'
import json, sys
path, change = sys.argv[1:]
catalog = json.load(open(path, encoding="utf-8"))
exec(change, {"catalog": catalog})
json.dump(catalog, open(path, "w", encoding="utf-8"), indent=2)
PY
    git -C "$pack_repository" commit -qam "invalid declaration"
    run_cli apply
    [ "$status" -ne 0 ]
    [[ "$stderr" == *"pack 'acme' profile 'kafka-interno'"* ]]
    [ ! -e .agents/agent-ready.lock.json ]
    git -C "$pack_repository" reset -q --hard HEAD~1
  done
}

@test "a project narrows an allow list of the machine without approval, even under a glob" {
  run_cli trust add acme
  # Without this check the npm package of acme-helper reaches the allow list, which decides.
  run_cli config set security.checks.artifactSha256 false --layer user
  run_cli config set security.allow.clis 'acme*' --layer user
  run_cli config set security.allow.clis acme
  [ "$status" -eq 0 ]
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
  [[ "$(decision_of cli acme-helper)" == *"blocked security.allow.clis does not include acme-helper"* ]]

  # A new pattern is taken as wider: it needs the approval of the repository.
  run_cli config set security.allow.clis 'acme-h*'
  run_cli plan
  [[ "$output" == *"security.allow.clis"*"was ignored"* ]]
}

@test "a script path through a symlink or a Windows junction stops the apply" {
  mkdir -p packs outside
  cp -R "$pack_repository" packs/acme
  rm -rf packs/acme/.git packs/acme/scripts
  printf '#!/bin/bash\necho outside\n' > outside/setup.sh
  printf '#!/bin/bash\necho outside\n' > outside/refresh.sh
  case "$(uname -s)" in
    MINGW* | MSYS*) cmd //c "mklink /J $(cygpath -w "$PWD/packs/acme/scripts") $(cygpath -w "$PWD/outside")" > /dev/null ;;
    *) ln -s "$PWD/outside" packs/acme/scripts ;;
  esac
  write_manifest '{"profiles": ["acme/kafka-interno"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'

  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"pack 'acme' profile 'kafka-interno': script 1 path scripts/setup.sh goes through a symlink or a junction"* ]]
  [ ! -e .agents/agent-ready.lock.json ]
}


@test "an apply registers an allowed MCP server for Claude Code and Codex, with its variables by reference" {
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"MCP servers of profile packs in .mcp.json: acme-docs"* ]]
  assert_json .mcp.json 'data["mcpServers"]["acme-docs"] == {"command": "acme", "args": ["mcp"], "env": {"ACME_TOKEN": "${ACME_TOKEN}"}}'
  grep -Fxq '# BEGIN AGENT-READY PACK MCP SERVERS' .codex/config.toml
  grep -Fxq '[mcp_servers.acme-docs]' .codex/config.toml
  grep -Fxq 'env_vars = ["ACME_TOKEN"]' .codex/config.toml
  assert_json .agents/agent-ready.lock.json 'data["mcpServers"]["acme-docs"]["providers"] == ["claude", "codex"]'

  # Applying again changes nothing.
  cp .mcp.json "$test_root/mcp-before.json"
  run_cli apply
  [ "$status" -eq 0 ]
  cmp -s .mcp.json "$test_root/mcp-before.json"
}

@test "an http server passes its token and headers by reference to both providers" {
  add_remote_server
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  assert_json .mcp.json 'data["mcpServers"]["acme-remote"] == {"type": "http", "url": "https://mcp.example.invalid/acme", "headers": {"Authorization": "Bearer ${ACME_TOKEN}", "X-Api-Key": "${ACME_KEY}"}}'
  grep -Fxq 'bearer_token_env_var = "ACME_TOKEN"' .codex/config.toml
  grep -Fxq 'env_http_headers = { "X-Api-Key" = "ACME_KEY" }' .codex/config.toml
  python3 -c 'import sys, tomllib; tomllib.load(open(".codex/config.toml", "rb"))' 2>/dev/null || python3 -c 'import sys; sys.exit(0 if sys.version_info < (3, 11) else 1)'
}

@test "losing the trust or retiring the profile unregisters the pack server" {
  run_cli trust add acme
  run_cli apply
  grep -Fq acme-docs .mcp.json

  run_cli trust remove acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"Unregistered from .mcp.json: acme-docs"* ]]
  ! grep -qs acme-docs .mcp.json
  ! grep -qs acme-docs .codex/config.toml
  assert_json .agents/agent-ready.lock.json '"mcpServers" not in data'

  run_cli trust add acme
  run_cli apply
  grep -Fq acme-docs .mcp.json
  write_manifest '{"profiles": ["node"], "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme#main"}]}}'
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -qs acme-docs .mcp.json
  ! grep -qs acme-docs .codex/config.toml
}

@test "a project server with the same name stays as the project has it" {
  printf '%s\n' '{"mcpServers": {"acme-docs": {"command": "mine"}}}' > .mcp.json
  mkdir -p .codex
  printf '[mcp_servers.acme-docs]\ncommand = "mine"\n' > .codex/config.toml
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"MCP server kept as the project has it: acme-docs: .mcp.json already has a server with that name"* ]]
  assert_json .mcp.json 'data["mcpServers"]["acme-docs"] == {"command": "mine"}'
  grep -Fxq 'command = "mine"' .codex/config.toml
  ! grep -Fq 'AGENT-READY PACK MCP SERVERS' .codex/config.toml
  assert_json .agents/agent-ready.lock.json '"mcpServers" not in data'
}

@test "agent-ready remove unregisters the pack servers and keeps the project's" {
  printf '%s\n' '{"mcpServers": {"mine": {"command": "mine"}}}' > .mcp.json
  run_cli trust add acme
  run_cli apply
  grep -Fq acme-docs .mcp.json

  run_cli remove --yes
  [ "$status" -eq 0 ]
  assert_json .mcp.json 'data["mcpServers"] == {"mine": {"command": "mine"}}'
  ! grep -qs 'AGENT-READY PACK MCP SERVERS' .codex/config.toml
}
