#!/usr/bin/env bats
# The two example packs of references/publishing-packs-with-tools.md, used the way the guide says:
# a personal pack without signatures that its owner adds, and a corporate pack whose signed release
# the organization configuration trusts, verifies and locks. Each pack is a Git repository reached
# through url.insteadOf, so the manifest keeps the URL a real project would write.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  examples="$skill_dir/assets/examples"
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

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

# Publishes an example pack as a Git repository that answers at the URL given.
publish_example() {
  local example="$1" url="$2"
  pack_repository="$test_root/repositories/$example"
  mkdir -p "$(dirname "$pack_repository")"
  cp -R "$examples/$example" "$pack_repository"
  git -C "$pack_repository" init -q
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm release
  git config --global "url.file:///$(native_path "$pack_repository" | sed 's#^/##').insteadOf" "$url"
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

@test "the personal example pack: its owner adds it, its tools pass unsigned, and the README restrictions hold" {
  publish_example personal-tools-pack https://github.example.invalid/me/mytools
  write_manifest '{"profiles": ["node"]}'
  run_cli sources add mytools "git+https://github.example.invalid/me/mytools#main"
  [ "$status" -eq 0 ]
  run_cli profiles add mytools/dev
  [ "$status" -eq 0 ]
  plan_tools
  [ "$(decision_of cli mytool)" = "cli mytool allowed " ]
  [ "$(decision_of script mytools/scripts/write-local-config.sh)" = "script mytools/scripts/write-local-config.sh allowed " ]

  # The restrictions of its README: only mytool may be installed, and no script pipes to sh.
  run_cli config set security.allow.clis mytool --layer user
  run_cli config set security.rules '[{"match": {"type": "script", "contains": "| sh"}, "action": "deny"}]' --layer user
  plan_tools
  [ "$(decision_of cli mytool)" = "cli mytool allowed " ]
  [ "$(decision_of script mytools/scripts/write-local-config.sh)" = "script mytools/scripts/write-local-config.sh allowed " ]

  # Its releases are not signed: requiring a signature stops every tool.
  run_cli config set security.checks.signature true --layer user
  plan_tools
  [[ "$(decision_of cli mytool)" == *"blocked security.checks.signature: no key of security.signers covers the source mytools"* ]]
  run_cli config unset security.checks.signature --layer user

  # Its download URLs are placeholders, so the CLI stays out; the script writes the local config once.
  run_cli config set security.deny.commands mytool --layer user
  run_cli apply
  [ "$status" -eq 0 ]
  [ -f .agents/rules/mytools.md ]
  grep -q '"strict": true' .mytool/config.json
}

@test "the corporate example pack: the organization trusts and verifies its signed release, and nobody loosens it" {
  publish_example corporate-signed-pack https://git.acme.example/platform/agent-ready-pack
  mkdir -p "$test_root/keys"
  ssh-keygen -q -t ed25519 -N "" -C platform-release@acme.example -f "$test_root/keys/platform-release"
  git -C "$pack_repository" -c gpg.format=ssh -c user.signingkey="$test_root/keys/platform-release" tag -s -m "acme-platform 2.4.0" v2.4.0
  # The organization configuration of the example, with the release key of this test.
  mkdir -p "$(dirname "$AGENT_READY_SETUP_ORGANIZATION_CONFIG")"
  python3 - "$examples/corporate-signed-pack/organization-config.json" "$test_root/keys/platform-release.pub" "$AGENT_READY_SETUP_ORGANIZATION_CONFIG" <<'PY'
import json, sys
configuration = json.load(open(sys.argv[1], encoding="utf-8"))
configuration["security"]["signers"][0]["key"] = open(sys.argv[2], encoding="utf-8").read().strip()
json.dump(configuration, open(sys.argv[3], "w", encoding="utf-8"), indent=2)
PY
  write_manifest '{"profiles": ["node", "acme-platform/platform"], "sources": {"packs": [{"name": "acme-platform", "source": "git+https://git.acme.example/platform/agent-ready-pack#v2.4.0"}]}}'

  # Nobody ran trust add: the organization trusts the origin and the signed tag passes.
  plan_tools
  [ "$(decision_of cli acme)" = "cli acme allowed " ]
  [ "$(decision_of mcpServer acme-docs)" = "mcpServer acme-docs allowed " ]
  [ "$(decision_of script acme-platform/scripts/check-login.sh)" = "script acme-platform/scripts/check-login.sh allowed " ]

  # A source that follows main runs nothing once main moves past the signed release.
  git -C "$pack_repository" commit -q --allow-empty -m "unreleased"
  write_manifest '{"profiles": ["node", "acme-platform/platform"], "sources": {"packs": [{"name": "acme-platform", "source": "git+https://git.acme.example/platform/agent-ready-pack#main"}]}}'
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: neither commit"* ]]

  # The organization locks the checks and the keys: a user can neither turn the check off nor add a key.
  ssh-keygen -q -t ed25519 -N "" -C someone@example.invalid -f "$test_root/keys/someone"
  git -C "$pack_repository" -c gpg.format=ssh -c user.signingkey="$test_root/keys/someone" commit -q -S --allow-empty -m "signed by someone"
  run_cli config set security.checks.signature false --layer user
  run_cli trust add acme-platform --signer "$test_root/keys/someone.pub"
  plan_tools
  [[ "$(decision_of cli acme)" == *"blocked security.checks.signature: neither commit"* ]]

  # The rules and skills of the pack are projected whatever happens to its tools.
  run_cli apply
  [ -f .agents/rules/acme-platform.md ]
}
