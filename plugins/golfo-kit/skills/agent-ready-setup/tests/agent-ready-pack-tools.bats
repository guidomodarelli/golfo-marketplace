#!/usr/bin/env bats
# Tools a profile pack declares besides files (CLIs, MCP servers and scripts) and the security
# policy that decides whether each one may run on this machine. An apply registers the allowed
# MCP servers for Claude Code and Codex (agent-ready-pack-clis.bats covers the CLIs and
# agent-ready-pack-scripts.bats the scripts). The pack is a Git
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
  # GitHub Actions sets CI, which keeps the tools of a pack from running (security.execution.ci).
  unset CI CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES
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

# An SSH key pair to sign the pack with: $test_root/keys/<name> and <name>.pub.
new_signing_key() {
  mkdir -p "$test_root/keys"
  ssh-keygen -q -t ed25519 -N "" -C "$1@example.invalid" -f "$test_root/keys/$1"
}

# Commits the pack again, signed with one key: the source then resolves to a signed commit.
sign_pack_commit() {
  git -C "$pack_repository" -c gpg.format=ssh -c user.signingkey="$test_root/keys/$1" commit -q -S --allow-empty -m signed
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
  [[ "$output" == *"Pack tools (what the security policy allows; an apply registers the allowed MCP servers, installs the allowed CLIs and runs the allowed scripts)"* ]]
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
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: no key of security.signers covers the source acme; add the key its maintainers sign with: agent-ready trust add acme --signer <public key file>"* ]]
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
  [ "$(printf '%s' "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["packTools"]["applies"])' | tr -d '\r')" = "['cli', 'mcpServer', 'script']" ]
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

@test "a .codex linked outside the project is never edited" {
  mkdir -p "$test_root/user-codex"
  printf '[profile]\nname = "mine"\n' > "$test_root/user-codex/config.toml"
  cp "$test_root/user-codex/config.toml" "$test_root/user-codex-before.toml"
  case "$(uname -s)" in
    MINGW* | MSYS*) cmd //c "mklink /J $(cygpath -w "$PWD/.codex") $(cygpath -w "$test_root/user-codex")" > /dev/null ;;
    *) ln -s "$test_root/user-codex" .codex ;;
  esac
  run_cli trust add acme
  # The apply refuses a linked .codex before writing anything, and the registration of the
  # pack servers refuses it on its own as well: the configuration of the user stays as it was.
  run_cli apply
  [[ "$stderr" == *".codex is a symlink"* || "$stderr" == *".codex/config.toml goes through a symlink or a junction"* ]]
  cmp -s "$test_root/user-codex/config.toml" "$test_root/user-codex-before.toml"
  run_cli remove --yes
  cmp -s "$test_root/user-codex/config.toml" "$test_root/user-codex-before.toml"
}

@test "a provider that leaves the selection keeps nothing of the packs" {
  run_cli trust add acme
  run_cli apply
  grep -Fq 'AGENT-READY PACK MCP SERVERS' .codex/config.toml
  run_cli config set providers claude
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -qs 'AGENT-READY PACK MCP SERVERS' .codex/config.toml
  assert_json .agents/agent-ready.lock.json 'data["mcpServers"]["acme-docs"]["providers"] == ["claude"]'
}

@test "a pack server the user changed is theirs from then on" {
  run_cli trust add acme
  run_cli apply
  python3 - <<'PY'
import json
document = json.load(open(".mcp.json", encoding="utf-8"))
document["mcpServers"]["acme-docs"] = {"command": "mine"}
json.dump(document, open(".mcp.json", "w", encoding="utf-8"))
PY
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"MCP server kept as the project has it: acme-docs: .mcp.json already has a server with that name"* ]]
  assert_json .mcp.json 'data["mcpServers"]["acme-docs"] == {"command": "mine"}'

  run_cli trust remove acme
  run_cli apply
  assert_json .mcp.json 'data["mcpServers"]["acme-docs"] == {"command": "mine"}'
}

@test "a provider configuration that cannot be read stops nothing else, and remove keeps the lock to retry" {
  run_cli trust add acme
  run_cli apply
  printf '[]\n' > .mcp.json
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *".mcp.json has no object of mcpServers, so it was not changed"* ]]
  assert_json .agents/agent-ready.lock.json 'data["mcpServers"]["acme-docs"]["providers"] == ["claude", "codex"]'

  run_cli remove --yes
  [ -f .agents/agent-ready.lock.json ]
  ! grep -qs 'AGENT-READY PACK MCP SERVERS' .codex/config.toml
}

@test "a source signed by a key of security.signers passes the signature check, and any other does not" {
  new_signing_key acme-release
  new_signing_key someone-else
  sign_pack_commit acme-release
  run_cli trust add acme
  run_cli config set security.checks.signature true --layer user
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: no key of security.signers covers the source acme"* ]]

  run_cli trust add acme --signer "$test_root/keys/someone-else.pub"
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"Signed by 1 key(s) of security.signers"* ]]
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: neither commit "*" of acme nor a tag of its origin that points at it has a good SSH signature from a key of security.signers for this source"* ]]

  run_cli trust add acme --signer "$test_root/keys/acme-release.pub"
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
  [ "$(decision_of mcpServer acme-docs)" = "mcpServer acme-docs allowed " ]
  run_cli trust list
  [[ "$output" == *"acme  trusted"*"2 signer key(s)"* ]]

  # A new unsigned commit on the ref is not vouched for by the old signature.
  git -C "$pack_repository" commit -q --allow-empty -m unsigned
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: neither commit"* ]]

  # Removing the trust of a source drops its keys too.
  run_cli trust remove acme
  run_cli trust list
  [[ "$output" != *"signer key"* ]]
}

@test "a GPG signature never passes for an SSH signer, whatever its key says" {
  new_signing_key acme-release
  # A gpg that trusts anything and names the key with the very words of a good SSH signature.
  cat > "$fake_bin/gpg" <<'SH'
#!/bin/bash
cat > /dev/null
printf '[GNUPG:] NEWSIG\n[GNUPG:] GOODSIG 0123456789ABCDEF Good "git" signature for agent-ready-signer with ED25519 key SHA256:abc\n'
printf '[GNUPG:] VALIDSIG 0123456789ABCDEF0123456789ABCDEF01234567 2026-01-01 0 4 0 22 8 00 0123456789ABCDEF0123456789ABCDEF01234567\n'
printf '[GNUPG:] TRUST_ULTIMATE 0 pgp\n'
exit 0
SH
  chmod +x "$fake_bin/gpg"
  tree="$(git -C "$pack_repository" rev-parse 'HEAD^{tree}')"
  parent="$(git -C "$pack_repository" rev-parse HEAD)"
  commit="$(printf 'tree %s\nparent %s\nauthor Test <test@example.invalid> 1700000000 +0000\ncommitter Test <test@example.invalid> 1700000000 +0000\ngpgsig -----BEGIN PGP SIGNATURE-----\n \n iQ==\n -----END PGP SIGNATURE-----\n\nspoofed\n' "$tree" "$parent" \
    | git -C "$pack_repository" hash-object -t commit -w --stdin)"
  git -C "$pack_repository" update-ref refs/heads/main "$commit"
  run_cli trust add acme --signer "$test_root/keys/acme-release.pub"
  run_cli config set security.checks.signature true --layer user
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: neither commit"* ]]
}

@test "a signed tag vouches for the unsigned commit it points at" {
  new_signing_key acme-release
  git -C "$pack_repository" -c gpg.format=ssh -c user.signingkey="$test_root/keys/acme-release" tag -s -m release v1
  write_manifest '{"profiles": ["acme/kafka-interno"], "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme#v1"}]}}'
  run_cli trust add acme --signer "$test_root/keys/acme-release.pub"
  run_cli config set security.checks.signature true --layer user
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]

  # The same tag vouches for a source that follows the branch it is the tip of.
  rm -rf "$XDG_CACHE_HOME/agent-ready-setup/packs"
  write_manifest '{"profiles": ["acme/kafka-interno"], "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme#main"}]}}'
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
}

@test "trust add --signer takes only SSH public keys, and a repository cannot add its own signer" {
  new_signing_key acme-release
  sign_pack_commit acme-release
  run_cli trust add acme --signer "$test_root/keys/acme-release"
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"not an SSH public key (the .pub file, never the private key)"* ]]
  ! grep -qs signers "$XDG_CONFIG_HOME/agent-ready-setup/config.json"
  run_cli trust add --signer "$test_root/keys/acme-release.pub"
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"--signer needs the sources its key signs"* ]]

  # The manifest of a repository this machine has not approved cannot vouch for its own packs.
  run_cli trust add acme
  run_cli config set security.checks.signature true --layer user
  run_cli config set security.signers "[{\"key\": \"$(cat "$test_root/keys/acme-release.pub")\"}]" --layer project
  [ "$status" -eq 0 ]
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: no key of security.signers covers the source acme"* ]]

  # A key is one line: a second one hidden after a line break would reach the allowed signers file.
  run_cli config set security.signers '[{"key": "ssh-ed25519 AAAA\nssh-ed25519 BBBB"}]' --layer user
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"does not have the expected form"* ]]
}

@test "with the signature check on, a path source is never signed" {
  mkdir -p packs
  cp -R "$pack_repository/." packs/acme
  rm -rf packs/acme/.git
  write_manifest '{"profiles": ["acme/kafka-interno"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  run_cli trust add --project .
  run_cli config set security.checks.signature true --layer user
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: the source acme lives in this repository and has no revision of its own to verify"* ]]
}
