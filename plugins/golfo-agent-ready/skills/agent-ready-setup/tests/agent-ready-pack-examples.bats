#!/usr/bin/env bats
# The two example packs of references/publishing-packs-with-tools.md, used the way the guide says:
# a personal pack without signatures that its owner adds, and a corporate pack whose signed release
# the organization configuration trusts, verifies and locks. Each pack is a Git repository reached
# through url.insteadOf, so the manifest keeps the URL a real project would write.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-agent-ready/skills/agent-ready-setup"
  examples="$skill_dir/assets/examples"
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
  # The legal example brings the learning profile, whose apply registers the scheduled sweep.
  export AGENT_READY_LEARNING_SCHEDULER=none
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

# A copy of the elixir example as a path source; the Python expression edits its catalog as `catalog`.
add_elixir_pack() {
  mkdir -p agent-packs .agents
  cp -R "$examples/elixir-stack-pack" agent-packs/beam
  if [[ -n "${1:-}" ]]; then
    python3 - agent-packs/beam/agent-ready-pack.json "$1" <<'PY'
import json, sys
path, expression = sys.argv[1:]
catalog = json.load(open(path, encoding="utf-8"))
exec(expression, {"catalog": catalog})
json.dump(catalog, open(path, "w", encoding="utf-8"))
PY
  fi
  write_manifest '{"sources": {"packs": [{"name": "beam", "source": "path:./agent-packs/beam"}]}}'
}

@test "the stack example pack: detection picks its stack, and the apply brings its rules and its section" {
  rm package.json
  printf '%s\n' 'defmodule Shop.MixProject do end' > mix.exs
  add_elixir_pack

  run python3 "$skill_dir/scripts/agent-ready-state.py" detect --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: beam/elixir" ]]

  run_cli apply
  [ "$status" -eq 0 ]
  [ -f .agents/rules/elixir-coding-style.md ]
  [ -f .agents/rules/elixir-testing.md ]
  # business-flows comes by the defaults of the pack stack.
  [ -f .agents/rules/business-flows.md ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: beam/elixir -->' AGENTS.md
  grep -qx '## Elixir' AGENTS.md
  python3 - <<'PY'
import json
manifest = json.load(open(".agents/agent-ready.json", encoding="utf-8"))
lock = json.load(open(".agents/agent-ready.lock.json", encoding="utf-8"))
assert manifest["profiles"] == ["beam/elixir"], manifest["profiles"]
assert lock["primaryStack"] == "beam/elixir", lock["primaryStack"]
assert lock["profileOrder"] == ["software-development", "beam/elixir", "business-flows"], lock["profileOrder"]
PY
}

@test "a pack stack and a Golfo stack that match together need an explicit selection" {
  printf '%s\n' 'defmodule Shop.MixProject do end' > mix.exs
  add_elixir_pack

  run python3 "$skill_dir/scripts/agent-ready-state.py" detect --project . --skill-dir "$skill_dir"
  [ "$status" -eq 3 ]
  [[ "$output" == *"beam/elixir"* && "$output" == *"node"* ]]
  run_cli apply
  [ "$status" -ne 0 ]
  [ ! -e AGENTS.md ]

  run_cli apply --profiles beam/elixir,node
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: beam/elixir -->' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: node -->' AGENTS.md
}

@test "a pack stack can supersede a Golfo stack, never a stack of another source" {
  printf '%s\n' 'defmodule Shop.MixProject do end' > mix.exs
  add_elixir_pack 'catalog["profiles"]["elixir"]["detect"]["supersedes"] = ["node"]'
  run python3 "$skill_dir/scripts/agent-ready-state.py" detect --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: beam/elixir" ]]
  [[ "$output" == *"node: package.json exists (superseded by beam/elixir)"* ]]

  rm -rf agent-packs
  add_elixir_pack 'catalog["profiles"]["elixir"]["detect"]["supersedes"] = ["other/cobol"]'
  run python3 "$skill_dir/scripts/agent-ready-state.py" detect --project . --skill-dir "$skill_dir"
  [ "$status" -ne 0 ]
  [[ "$output" == *"cannot supersede 'other/cobol'"* ]]
}

@test "only a stack of a pack adds a section to AGENTS.md" {
  printf '%s\n' 'defmodule Shop.MixProject do end' > mix.exs
  add_elixir_pack 'catalog["profiles"]["elixir"]["kind"] = "capability"; del catalog["profiles"]["elixir"]["detect"]'
  write_manifest '{"profiles": ["node", "beam/elixir"], "sources": {"packs": [{"name": "beam", "source": "path:./agent-packs/beam"}]}}'
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"profile 'beam/elixir': only a stack profile adds a section to AGENTS.md"* ]]
  [ ! -e AGENTS.md ]
}

@test "a pack stack with only its section of AGENTS.md and no rules of its own is applied" {
  rm package.json
  printf '%s\n' 'defmodule Shop.MixProject do end' > mix.exs
  add_elixir_pack 'del catalog["profiles"]["elixir"]["defaults"]'
  rm -rf agent-packs/beam/profiles/elixir/rules

  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: beam/elixir -->' AGENTS.md
  [ ! -e .agents/rules/elixir-coding-style.md ]
}

@test "the first apply fetches a declared Git pack before detecting, so its stack can be the one detected" {
  rm package.json
  printf '%s\n' 'defmodule Shop.MixProject do end' > mix.exs
  publish_example elixir-stack-pack https://git.example.invalid/beam
  write_manifest '{"sources": {"packs": [{"name": "beam", "source": "git+https://git.example.invalid/beam", "ref": "main"}]}}'

  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: beam/elixir -->' AGENTS.md
  [ "$(python3 -c 'import json; print(json.load(open(".agents/agent-ready.json"))["profiles"])' | tr -d '\r')" = "['beam/elixir']" ]
}

# A copy of the estudio-juridico example as a path source.
add_legal_pack() {
  mkdir -p agent-packs .agents
  cp -R "$examples/estudio-juridico-pack" agent-packs/estudio-juridico
  write_manifest '{"sources": {"packs": [{"name": "estudio-juridico", "source": "path:./agent-packs/estudio-juridico"}]}}'
}

@test "the legal example pack: its domain stack is detected by folders and brings its capabilities, without software-development" {
  rm package.json
  mkdir -p actas/2026
  printf '%s\n' '# Acta de infracción N.º 001' > actas/2026/acta-001.md
  add_legal_pack

  run python3 "$skill_dir/scripts/agent-ready-state.py" detect --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: estudio-juridico/estudio" ]]

  run_cli apply
  [ "$status" -eq 0 ]
  for rule in actas-formato actas-citas-normativas actas-datos-personales; do
    [ -f ".agents/rules/$rule.md" ]
  done
  [ -f .agents/skills/redactar-acta/SKILL.md ]
  [ -f .agents/skills/redactar-acta/templates/acta.md ]
  [ -f .agents/skills/redactar-acta/evals/eval-config.json ]
  grep -qx '## Purpose' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: estudio-juridico/estudio -->' AGENTS.md
  # A repository without code: none of software-development.
  [ ! -e .agents/rules/lint-gate.md ]
  [ ! -e .github/pull_request_template.md ]
  [ "$(python3 -c 'import json; print(json.load(open(".agents/agent-ready.lock.json"))["profileOrder"])' | tr -d '\r')" = "['estudio-juridico/estudio', 'estudio-juridico/actas-infraccion', 'learning']" ]
  # The learning capability of the content comes by default: its rules and the hook of the episodes.
  grep -q 'rule id=learning/user-messages-only' .agents/rules/learning.md
  [ -f .agents/hooks/learning-hook.sh ]
  run_cli learn status
  [ "$status" -eq 0 ]
  [[ "$output" == *"Notice to the user: on. Scope question: at most one per episode."* ]]
}

@test "the legal example pack: a repository leaves learning out with excludedDefaults" {
  rm package.json
  mkdir -p actas/2026
  printf '%s\n' '# Acta de infracción N.º 001' > actas/2026/acta-001.md
  add_legal_pack
  write_manifest '{"sources": {"packs": [{"name": "estudio-juridico", "source": "path:./agent-packs/estudio-juridico"}]}, "excludedDefaults": ["learning"]}'

  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(python3 -c 'import json; print(json.load(open(".agents/agent-ready.lock.json"))["profileOrder"])' | tr -d '\r')" = "['estudio-juridico/estudio', 'estudio-juridico/actas-infraccion']" ]
  [ ! -e .agents/rules/learning.md ]
}

@test "without its folders the legal domain stack is not detected, and its capability works alone" {
  rm package.json
  mkdir -p notas
  printf '%s\n' '# Notas' > notas/reunion.md
  add_legal_pack

  run python3 "$skill_dir/scripts/agent-ready-state.py" detect --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: none" ]]

  run_cli apply --profiles estudio-juridico/actas-infraccion
  [ "$status" -eq 0 ]
  [ -f .agents/rules/actas-formato.md ]
  ! grep -q 'AGENT-READY MANAGED: estudio-juridico' AGENTS.md
}

# A copy of the estudio-contable example as a path source, projected for the three providers.
add_accounting_pack() {
  mkdir -p agent-packs .agents
  cp -R "$examples/estudio-contable-pack" agent-packs/estudio-contable
  write_manifest '{"providers": ["claude", "codex", "antigravity"], "sources": {"packs": [{"name": "estudio-contable", "source": "path:./agent-packs/estudio-contable"}]}}'
}

# The accounting example requires the orchestration capability of the content. A content release
# without it (the ref of the tests may predate it) gets a minimal one in a copy, so the test checks the
# pack and not the version of the content.
use_content_with_orchestration() {
  copy_content_pack
  [ -d "$content_dir/profiles/orchestration" ] && return 0
  mkdir -p "$content_dir/profiles/orchestration/skills/orchestrate-agents"
  printf '%s\n' '---' 'name: orchestrate-agents' 'description: Dispatches a task to the subagents of a roster and consolidates one report.' '---' \
    'Read the roster, dispatch each subagent, consolidate.' \
    > "$content_dir/profiles/orchestration/skills/orchestrate-agents/SKILL.md"
  python3 - "$content_dir/agent-ready-pack.json" <<'PY'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path, encoding="utf-8"))
catalog["profiles"]["orchestration"] = {"kind": "capability", "description": "Orchestrate a roster of subagents.",
                                        "assets": "profiles/orchestration"}
json.dump(catalog, open(path, "w", encoding="utf-8"), indent=2)
PY
}

@test "the accounting example pack: its subagents, skills and roster reach Claude Code, Codex and Antigravity with their metadata" {
  rm package.json
  mkdir -p liquidaciones/cliente-a/2026-03
  printf '%s\n' '# Recibos de marzo' > liquidaciones/cliente-a/2026-03/recibos.md
  use_content_with_orchestration
  add_accounting_pack

  run python3 "$skill_dir/scripts/agent-ready-state.py" detect --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "${lines[0]}" == "Stack: estudio-contable/estudio" ]]

  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Claude Code sees"*"2 subagents"*"; Codex sees"*"and 2 subagents; Antigravity sees"*"and 2 subagents"* ]]
  # Every subagent of the roster is installed: no structural conflict for it.
  [[ "$output" != *"names .agents/agents/"* ]]
  # What Codex cannot enforce for the read-only auditor only informs.
  [[ "$output" == *".agents/agents/auditor-contable.md: Codex keeps the sandbox of the session"* ]]

  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(python3 -c 'import json; print(json.load(open(".agents/agent-ready.lock.json"))["profileOrder"])' | tr -d '\r')" = "['estudio-contable/estudio', 'orchestration', 'estudio-contable/contabilidad', 'learning']" ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: estudio-contable/estudio -->' AGENTS.md
  for rule in contable-datos-personales contable-formato-reportes; do
    grep -qx 'trigger: always_on' ".agents/rules/$rule.md"
  done
  for skill in conciliar-extracto preparar-cierre-mensual revisar-cierre; do
    [ -f ".agents/skills/$skill/SKILL.md" ]
    [ -f ".agents/skills/$skill/evals/eval-config.json" ]
  done
  # The roster runs the procedure of the content's orchestration capability.
  [ -f .agents/skills/orchestrate-agents/SKILL.md ]
  grep -q '.agents/skills/orchestrate-agents/SKILL.md' .agents/skills/revisar-cierre/SKILL.md
  # A repository without code: none of software-development.
  [ ! -e .agents/rules/lint-gate.md ]

  # auditor-contable: access read-only and model-tier deep, rendered by provider.
  grep -qx 'tools: Read, Grep, Glob' .claude/agents/auditor-contable.md
  grep -qx 'model: opus' .claude/agents/auditor-contable.md
  grep -q '"view_file"' .agents/agents/auditor-contable.md
  ! grep -q 'run_command' .agents/agents/auditor-contable.md
  grep -qx 'model: pro' .agents/agents/auditor-contable.md
  grep -qx 'name = "auditor-contable"' .codex/agents/auditor-contable.toml
  grep -qx 'model_reasoning_effort = "high"' .codex/agents/auditor-contable.toml
  # investigador-normativo: only model-tier balanced, so every provider keeps all its tools.
  grep -qx 'model: sonnet' .claude/agents/investigador-normativo.md
  ! grep -q '^tools:' .claude/agents/investigador-normativo.md
  grep -qx 'model: inherit' .agents/agents/investigador-normativo.md
  ! grep -q '^tools:' .agents/agents/investigador-normativo.md
  grep -qx 'model_reasoning_effort = "medium"' .codex/agents/investigador-normativo.toml
}

@test "the accounting example pack: conflicts --pack passes, and fails once the roster names a subagent it does not publish" {
  use_content_with_orchestration
  publish_example estudio-contable-pack https://git.example.invalid/estudio-contable
  cd "$pack_repository"

  run_cli conflicts --pack . --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"estudio-contable/estudio: no conflicts"* ]]
  [[ "$output" == *"estudio-contable/contabilidad: no conflicts"* ]]

  git rm -q profiles/contabilidad/agents/auditor-contable.md
  git commit -qm "without the auditor"
  run_cli conflicts --pack . --offline
  [ "$status" -eq 6 ]
  [[ "$output" == *".agents/skills/revisar-cierre/SKILL.md (estudio-contable/contabilidad) names .agents/agents/auditor-contable.md, which no selected profile publishes and the project does not have"* ]]
}
