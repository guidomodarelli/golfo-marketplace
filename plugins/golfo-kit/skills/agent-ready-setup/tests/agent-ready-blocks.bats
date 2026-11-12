#!/usr/bin/env bats
# Managed blocks inside files shared with the project (agent_ready_blocks.py): the pull request
# template of the common profile, a block a path pack adds to the same file, the markers that stop
# every change, and how status, plan and remove see each block.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
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
  unset CI CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES
  for provider_cli in claude codex; do
    printf '#!/bin/bash\nexit 0\n' > "$fake_bin/$provider_cli"
    chmod +x "$fake_bin/$provider_cli"
  done
  git -C "$project_dir" init -q
  cd "$project_dir"
  printf '{}\n' > package.json
  write_manifest '{"profiles": ["node"]}'
  template=.github/pull_request_template.md
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

write_manifest() {
  mkdir -p .agents
  printf '%s\n' "$1" > .agents/agent-ready.json
}

run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready" "$@"
}

lock_value() {
  python3 -c 'import json, sys; lock = json.load(open(".agents/agent-ready.lock.json", encoding="utf-8")); print(eval(sys.argv[1]))' "$1"
}

# A path pack whose profile adds a block of its own to the pull request template.
add_block_pack() {
  mkdir -p packs/acme/profiles/review/blocks/.github
  printf '## Acme checklist\n\n- [ ] Contract tests pass\n' > packs/acme/profiles/review/blocks/.github/pull_request_template.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"review": {"kind": "capability", "description": "Acme review checklist.", "assets": "profiles/review"}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node", "acme/review"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
}

@test "the pull request template is a managed block: a section of the project outside it survives every apply" {
  run_cli apply
  [ "$status" -eq 0 ]
  head -1 "$template" | grep -qx '<!-- BEGIN AGENT-READY MANAGED: common -->'
  grep -qx '<!-- END AGENT-READY MANAGED: common -->' "$template"
  [ "$(lock_value 'lock["blocks"][".github/pull_request_template.md"]["common"]["state"]')" = "applied" ]
  [ "$(lock_value '".github/pull_request_template.md" in lock["assets"]')" = "False" ]

  printf '\n## Deploy notes\n\nSay which environment you tested.\n' >> "$template"
  run_cli apply
  [ "$status" -eq 0 ]
  grep -q '^## Deploy notes$' "$template"
  run_cli plan
  [[ "$output" != *"(block common)"* ]]

  # Inside the block the template wins; the project's section stays.
  sed -i.bak 's/^## /## Edited /' "$template" && rm -f "$template.bak"
  run_cli plan
  [[ "$output" == *"~ update          .github/pull_request_template.md (block common)  overwrites local changes inside the block"* ]]
  run_cli status
  [[ "$output" == *".github/pull_request_template.md (block common)"* ]]
  run_cli apply
  ! grep -q '^## Edited Descr' "$template"
  grep -q '^## Edited Deploy notes$' "$template"
}

@test "two profiles keep blocks of their own in one file, and leaving the selection takes only its block out" {
  run_cli apply
  add_block_pack
  run_cli trust add --project .
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: common -->' "$template"
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: acme/review -->' "$template"
  grep -q '^- \[ \] Contract tests pass$' "$template"

  write_manifest '{"profiles": ["node"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'acme/review' "$template"
  ! grep -q 'Contract tests pass' "$template"
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: common -->' "$template"
}

@test "markers that repeat or come out of order stop every change to that file" {
  run_cli apply
  printf '<!-- BEGIN AGENT-READY MANAGED: common -->\nstray\n' >> "$template"
  cp "$template" "$test_root/before"
  run_cli plan
  [[ "$output" == *"! conflict        .github/pull_request_template.md (block common)  its markers do not pair up"* ]]
  run_cli apply
  cmp -s "$template" "$test_root/before"
  [[ "$output$stderr" == *"managed block kept: .github/pull_request_template.md (block common): its markers do not pair up"* ]]
}

@test "a block of a pack can only go to a file with a known comment syntax, never to the instructions" {
  mkdir -p packs/acme/profiles/review/blocks
  printf 'x\n' > packs/acme/profiles/review/blocks/AGENTS.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"review": {"kind": "capability", "description": "Acme.", "assets": "profiles/review"}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node", "acme/review"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  run_cli plan
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"profile 'acme/review': only a stack profile adds a section to AGENTS.md"* ]]

  rm packs/acme/profiles/review/blocks/AGENTS.md
  printf 'x\n' > packs/acme/profiles/review/blocks/notes.json
  run_cli plan
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"the block notes.json has no known comment syntax"* ]]
}

@test "remove takes every managed block out, keeps the project's content and deletes a file that only held blocks" {
  run_cli apply
  printf '\n## Deploy notes\n' >> "$template"
  run_cli remove --yes
  [ "$status" -eq 0 ]
  [ -f "$template" ]
  ! grep -q 'AGENT-READY MANAGED' "$template"
  grep -qx '## Deploy notes' "$template"

  git init -q "$test_root/other" && cd "$test_root/other"
  printf '{}\n' > package.json
  write_manifest '{"profiles": ["node"]}'
  run_cli apply
  [ -f "$template" ]
  run_cli remove --yes
  [ "$status" -eq 0 ]
  [ ! -e "$template" ]
}

@test "a whole-file template the lock still records is retired and the file holds only the block" {
  run_cli apply
  # The previous format: the template as a whole managed asset, without blocks in the lock.
  cp "$skill_dir/assets/common/blocks/.github/pull_request_template.md" "$template"
  python3 - <<'PY'
import hashlib, json
path = ".agents/agent-ready.lock.json"
lock = json.load(open(path, encoding="utf-8"))
content = open(".github/pull_request_template.md", "rb").read()
lock.pop("blocks", None)
lock["assets"][".github/pull_request_template.md"] = {"profile": "common", "source": "assets/common/github/pull_request_template.md",
                                                       "sha256": hashlib.sha256(content).hexdigest(), "state": "applied"}
json.dump(lock, open(path, "w", encoding="utf-8"), indent=2)
PY
  run_cli apply
  [ "$status" -eq 0 ]
  head -1 "$template" | grep -qx '<!-- BEGIN AGENT-READY MANAGED: common -->'
  [ "$(grep -c '^## ' "$template")" -eq "$(grep -c '^## ' "$skill_dir/assets/common/blocks/.github/pull_request_template.md")" ]
  [ "$(lock_value '".github/pull_request_template.md" in lock["assets"]')" = "False" ]
}

@test "a block keeps a file executable and a template ending in a blank line stays current" {
  mkdir -p packs/acme/profiles/review/blocks
  printf 'echo acme\n\n' > packs/acme/profiles/review/blocks/deploy.sh
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"review": {"kind": "capability", "description": "Acme.", "assets": "profiles/review"}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node", "acme/review"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  printf '#!/bin/sh\necho project\n' > deploy.sh
  chmod 0755 deploy.sh
  run_cli trust add --project .
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '# BEGIN AGENT-READY MANAGED: acme/review' deploy.sh
  run_cli plan
  [[ "$output" != *"(block acme/review)"* ]]
  run_cli check
  [ "$status" -eq 0 ]
  if [[ "$OSTYPE" != msys* && "$OSTYPE" != cygwin* ]]; then
    [ -x deploy.sh ]
    run_cli remove --yes
    [ -x deploy.sh ]
  fi
}

@test "a pack cannot publish a block to AGENTS.md or CLAUDE.md in any directory or case" {
  mkdir -p packs/acme/profiles/review/blocks/src
  printf 'x\n' > packs/acme/profiles/review/blocks/src/Agents.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"review": {"kind": "capability", "description": "Acme.", "assets": "profiles/review"}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node", "acme/review"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  run_cli plan
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"src/Agents.md is not a file a block can go to"* ]]
}

@test "--from-lock refuses a block that does not match the lock" {
  run_cli apply
  python3 - <<'PY'
import json
path = ".agents/agent-ready.lock.json"
lock = json.load(open(path, encoding="utf-8"))
lock["blocks"][".github/pull_request_template.md"]["common"]["sha256"] = "0" * 64
json.dump(lock, open(path, "w", encoding="utf-8"), indent=2)
PY
  cp "$template" "$test_root/before"
  run_cli apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"the block common of .github/pull_request_template.md does not match the sha256 of the lock"* ]]
  cmp -s "$template" "$test_root/before"
}

@test "status reports a block the first apply could not write" {
  mkdir -p .github
  printf '<!-- END AGENT-READY MANAGED: common -->\n' > "$template"
  run_cli apply
  run_cli check
  [ "$status" -ne 0 ]
  [[ "$output" == *".github/pull_request_template.md (block common): preserved conflict"* ]]
}

@test "a junction or symlinked directory on the path keeps the block out of a file outside the repository" {
  mkdir -p "$test_root/shared"
  if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
    cmd //c mklink //J "$(cygpath -w "$project_dir/.github")" "$(cygpath -w "$test_root/shared")" > /dev/null
  else
    ln -s "$test_root/shared" .github
  fi
  run_cli apply
  [ ! -e "$test_root/shared/pull_request_template.md" ]
  [[ "$output$stderr" == *".github/pull_request_template.md (block common): a directory on its path is a symlink"* ]]
}

@test "remove keeps the lock when a block cannot be taken out, so it can run again" {
  if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* || "$(id -u)" = 0 ]]; then
    skip "needs POSIX directory permissions"
  fi
  run_cli apply
  chmod 0555 .github
  run_cli remove --yes
  chmod 0755 .github
  [ "$status" -ne 0 ]
  [ -f .agents/agent-ready.lock.json ]
  [ "$(lock_value '".github/pull_request_template.md" in lock["blocks"]')" = "True" ]
}

# A path pack with two profiles that each add a block to the pull request template, one of them
# spelling the file in capitals.
add_two_block_profiles() {
  mkdir -p packs/acme/profiles/review/blocks/.github packs/acme/profiles/deploy/blocks/.github
  printf '## Acme review\n' > packs/acme/profiles/review/blocks/.github/pull_request_template.md
  printf '## Acme deploy\n' > "packs/acme/profiles/deploy/blocks/.github/$1"
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"review": {"kind": "capability", "description": "Review.", "assets": "profiles/review"}, "deploy": {"kind": "capability", "description": "Deploy.", "assets": "profiles/deploy"}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node", "acme/review", "acme/deploy"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  run_cli trust add --project .
}

@test "two pack profiles add blocks to one file through bootstrap, whatever case they spell it in" {
  add_two_block_profiles PULL_REQUEST_TEMPLATE.md
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(ls .github)" = "pull_request_template.md" ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: common -->' "$template"
  grep -qx '## Acme review' "$template"
  grep -qx '## Acme deploy' "$template"
  run_cli plan
  [[ "$output" != *"(block "* ]]
}

@test "a block the apply cannot write is a failure the lock and the background report keep" {
  if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* || "$(id -u)" = 0 ]]; then
    skip "needs POSIX directory permissions"
  fi
  mkdir -p .github
  chmod 0555 .github
  run_cli apply
  chmod 0755 .github
  [[ "$output$stderr" == *"managed blocks of .github/pull_request_template.md"* ]]
  [ "$(lock_value 'lock["blocks"][".github/pull_request_template.md"]["common"]["state"]')" = "failed" ]
  [ ! -e "$template" ]
}

@test "check reports a block whose first write failed" {
  mkdir -p packs/acme/profiles/review/blocks/blocked
  printf 'echo acme\n' > packs/acme/profiles/review/blocks/blocked/deploy.sh
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"review": {"kind": "capability", "description": "Acme.", "assets": "profiles/review"}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node", "acme/review"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  printf 'not a directory\n' > blocked
  run_cli trust add --project .
  run_cli apply
  [ "$(lock_value 'lock["blocks"]["blocked/deploy.sh"]["acme/review"]["state"]')" = "failed" ]
  run_cli check
  [ "$status" -ne 0 ]
  [[ "$output" == *"blocked/deploy.sh (block acme/review)"* ]]
}

@test "remove takes a block out of a file another step of the removal edited first" {
  run_cli apply
  # Another edit of the same file between the plan and the block, as the browser teardown does to .gitignore.
  python3 - "$skill_dir/scripts" "$skill_dir" <<'PY'
import importlib.util, sys
sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location("state", sys.argv[1] + "/agent-ready-state.py")
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)
plan = state.plan_removal(".", sys.argv[2])
with open(".github/pull_request_template.md", "a", encoding="utf-8") as template:
    template.write("\n## Added while removing\n")
report = state.apply_removal(".", sys.argv[2], {"entries": [entry for entry in plan["entries"] if entry["kind"] == "block"]})
assert report["edited"] == [".github/pull_request_template.md"], report
PY
  ! grep -q 'AGENT-READY MANAGED' "$template"
  grep -qx '## Added while removing' "$template"
}

@test "the local state of agent-ready-setup is ignored through a managed .gitignore block" {
  printf 'node_modules/\n' > .gitignore
  run_cli apply
  [ "$status" -eq 0 ]
  head -1 .gitignore | grep -qx 'node_modules/'
  grep -qx '# BEGIN AGENT-READY MANAGED: common' .gitignore
  for local_path in .agents/browser-tools.json .agents/.agent-ready-assets.lock/held .claude/.agent-ready-hard-link-views; do
    git check-ignore --quiet --no-index "$local_path"
  done
  [ "$(lock_value 'lock["blocks"][".gitignore"]["common"]["state"]')" = "applied" ]

  run_cli remove --yes
  [ "$status" -eq 0 ]
  [ "$(cat .gitignore)" = "node_modules/" ]
}

@test "each selected stack adds its section to AGENTS.md, and a stack that leaves the selection takes it out" {
  write_manifest '{"profiles": ["frontend", "node"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '# \[Project Name\]' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED -->' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: frontend -->' AGENTS.md
  grep -qx '## Frontend' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: node -->' AGENTS.md
  grep -qx '## Node.js' AGENTS.md
  [ "$(lock_value 'sorted(lock["blocks"]["AGENTS.md"])')" = "['frontend', 'node']" ]
  [ "$(lock_value 'lock["merged"]["AGENTS.md"]["template"]')" = "assets/common/agents-template.md" ]

  printf '
## Ownership

Team Astra owns this service.
' >> AGENTS.md
  write_manifest '{"profiles": ["node"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'AGENT-READY MANAGED: frontend' AGENTS.md
  ! grep -qx '## Frontend' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: node -->' AGENTS.md
  grep -qx 'Team Astra owns this service.' AGENTS.md
  [ "$(lock_value 'sorted(lock["blocks"]["AGENTS.md"])')" = "['node']" ]
}

@test "a local edit inside the section of a stack is reported, and the next apply restores the section" {
  run_cli apply
  sed -i.bak 's/^## Node.js$/## Edited Node.js/' AGENTS.md && rm -f AGENTS.md.bak
  run_cli plan
  [[ "$output" == *"~ update          AGENTS.md (block node)  overwrites local changes inside the block"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '## Node.js' AGENTS.md
  ! grep -q 'Edited Node.js' AGENTS.md
}

@test "remove takes the stack sections out with the managed block, and AGENTS.md goes when only the template is left" {
  run_cli apply
  run_cli remove --yes
  [ "$status" -eq 0 ]
  [ ! -e AGENTS.md ]

  git init -q "$test_root/other" && cd "$test_root/other"
  printf '{}
' > package.json
  write_manifest '{"profiles": ["node"]}'
  run_cli apply
  printf '
## Ownership

Team Astra owns this service.
' >> AGENTS.md
  run_cli remove --yes
  [ "$status" -eq 0 ]
  ! grep -q 'AGENT-READY MANAGED' AGENTS.md
  ! grep -qx '## Node.js' AGENTS.md
  grep -qx 'Team Astra owns this service.' AGENTS.md
}

# Number of lines of AGENTS.md that are exactly the given marker.
agents_marker_count() {
  grep -Fxc -- "$1" AGENTS.md || true
}

@test "applies, the instruction review and the session hook keep one pair of markers per stack section" {
  write_manifest '{"profiles": ["frontend", "node"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  # The provider of this suite answers nothing: the review falls back to the verbatim managed block.
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/merge-instructions.sh" --provider claude --stack frontend \
    --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  run_cli apply
  [ "$status" -eq 0 ]
  # The session hook projects the assets again and applies the managed block, in the foreground.
  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 \
    AGENT_READY_SETUP_SYNC_FOREGROUND=1 bash .agents/hooks/sync-marketplace.sh --provider claude
  [ "$status" -eq 0 ]
  run_cli apply
  [ "$status" -eq 0 ]
  for marker in '<!-- BEGIN AGENT-READY MANAGED -->' '<!-- END AGENT-READY MANAGED -->' \
    '<!-- BEGIN AGENT-READY MANAGED: frontend -->' '<!-- END AGENT-READY MANAGED: frontend -->' \
    '<!-- BEGIN AGENT-READY MANAGED: node -->' '<!-- END AGENT-READY MANAGED: node -->'; do
    [ "$(agents_marker_count "$marker")" -eq 1 ]
  done
  [ "$(grep -Fxc '## Node.js' AGENTS.md)" -eq 1 ]
  run_cli check
  [[ "$output" != *"AGENTS.md (block"* ]]
}

@test "the normalization of a root CLAUDE.md with its own instructions leaves the stack sections alone" {
  run_cli apply
  [ "$status" -eq 0 ]
  cp AGENTS.md "$test_root/agents-before"
  printf '%s\n' '# Claude notes' '' 'Use the staging database for manual tests.' > CLAUDE.md
  run_cli apply
  # The two instruction files differ: the engine reports it and changes neither of them.
  cmp -s AGENTS.md "$test_root/agents-before"
  [ "$(agents_marker_count '<!-- BEGIN AGENT-READY MANAGED: node -->')" -eq 1 ]
  grep -Fxq 'Use the staging database for manual tests.' CLAUDE.md
}

@test "the stack sections wait until a project AGENTS.md has its managed block" {
  printf '%s
' '# Canonical instructions' > AGENTS.md
  write_manifest '{"profiles": ["node"]}'
  # bootstrap alone leaves a project AGENTS.md without the block for the instruction review.
  run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1 bash "$skill_dir/scripts/bootstrap.sh"     --skill-dir "$skill_dir" --provider claude
  [ "$status" -eq 0 ]
  [ "$(cat AGENTS.md)" = '# Canonical instructions' ]
  [ "$(lock_value '"AGENTS.md" in lock.get("blocks", {})')" = "False" ]

  # The apply runs that review, which places the block after the sections were left out...
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED -->' AGENTS.md
  ! grep -q 'AGENT-READY MANAGED: node' AGENTS.md
  # ...and the next apply adds the section to the file it adopted.
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: node -->' AGENTS.md
  [ "$(head -1 AGENTS.md)" = '# Canonical instructions' ]
}
