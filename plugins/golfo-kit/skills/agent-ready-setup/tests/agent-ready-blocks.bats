#!/usr/bin/env bats
# Managed blocks inside files shared with the project (agent_ready_blocks.py): the pull request
# template of the common profile, a block a path pack adds to the same file, the markers that stop
# every change, how status, plan and remove see each block, and the nested targets of a pack.

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
  head -1 "$template" | grep -qx '<!-- BEGIN AGENT-READY MANAGED: software-development -->'
  grep -qx '<!-- END AGENT-READY MANAGED: software-development -->' "$template"
  [ "$(lock_value 'lock["blocks"][".github/pull_request_template.md"]["software-development"]["state"]')" = "applied" ]
  [ "$(lock_value '".github/pull_request_template.md" in lock["assets"]')" = "False" ]

  printf '\n## Deploy notes\n\nSay which environment you tested.\n' >> "$template"
  run_cli apply
  [ "$status" -eq 0 ]
  grep -q '^## Deploy notes$' "$template"
  run_cli plan
  [[ "$output" != *"(block software-development)"* ]]

  # Inside the block the template wins; the project's section stays.
  sed -i.bak 's/^## /## Edited /' "$template" && rm -f "$template.bak"
  run_cli plan
  [[ "$output" == *"~ update          .github/pull_request_template.md (block software-development)  overwrites local changes inside the block"* ]]
  run_cli status
  [[ "$output" == *".github/pull_request_template.md (block software-development)"* ]]
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
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: software-development -->' "$template"
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: acme/review -->' "$template"
  grep -q '^- \[ \] Contract tests pass$' "$template"

  write_manifest '{"profiles": ["node"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'acme/review' "$template"
  ! grep -q 'Contract tests pass' "$template"
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: software-development -->' "$template"
}

@test "markers that repeat or come out of order stop every change to that file" {
  run_cli apply
  printf '<!-- BEGIN AGENT-READY MANAGED: software-development -->\nstray\n' >> "$template"
  cp "$template" "$test_root/before"
  run_cli plan
  [[ "$output" == *"! conflict        .github/pull_request_template.md (block software-development)  its markers do not pair up"* ]]
  run_cli apply
  cmp -s "$template" "$test_root/before"
  [[ "$output$stderr" == *"managed block kept: .github/pull_request_template.md (block software-development): its markers do not pair up"* ]]
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
  cp "$skill_dir/assets/profiles/software-development/blocks/.github/pull_request_template.md" "$template"
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
  head -1 "$template" | grep -qx '<!-- BEGIN AGENT-READY MANAGED: software-development -->'
  [ "$(grep -c '^## ' "$template")" -eq "$(grep -c '^## ' "$skill_dir/assets/profiles/software-development/blocks/.github/pull_request_template.md")" ]
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
lock["blocks"][".github/pull_request_template.md"]["software-development"]["sha256"] = "0" * 64
json.dump(lock, open(path, "w", encoding="utf-8"), indent=2)
PY
  cp "$template" "$test_root/before"
  run_cli apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"the block software-development of .github/pull_request_template.md does not match the sha256 of the lock"* ]]
  cmp -s "$template" "$test_root/before"
}

@test "status reports a block the first apply could not write" {
  mkdir -p .github
  printf '<!-- END AGENT-READY MANAGED: software-development -->\n' > "$template"
  run_cli apply
  run_cli check
  [ "$status" -ne 0 ]
  [[ "$output" == *".github/pull_request_template.md (block software-development): preserved conflict"* ]]
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
  [[ "$output$stderr" == *".github/pull_request_template.md (block software-development): a directory on its path is a symlink"* ]]
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
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: software-development -->' "$template"
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
  [ "$(lock_value 'lock["blocks"][".github/pull_request_template.md"]["software-development"]["state"]')" = "failed" ]
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
  write_manifest '{"profiles": ["react", "node"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '# \[Project Name\]' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED -->' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: react -->' AGENTS.md
  grep -qx '## React' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: node -->' AGENTS.md
  grep -qx '## Node.js' AGENTS.md
  [ "$(lock_value 'sorted(lock["blocks"]["AGENTS.md"])')" = "['node', 'react']" ]
  [ "$(lock_value 'lock["merged"]["AGENTS.md"]["template"]')" = "assets/common/agents-template.md" ]

  printf '
## Ownership

Team Astra owns this service.
' >> AGENTS.md
  write_manifest '{"profiles": ["node"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'AGENT-READY MANAGED: react' AGENTS.md
  ! grep -qx '## React' AGENTS.md
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
  write_manifest '{"profiles": ["react", "node"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  # The provider of this suite answers nothing: the review falls back to the verbatim managed block.
  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/merge-instructions.sh" --provider claude --stack react \
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
    '<!-- BEGIN AGENT-READY MANAGED: react -->' '<!-- END AGENT-READY MANAGED: react -->' \
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

@test "while CLAUDE.md conflicts with AGENTS.md, the apply adds, updates and removes no stack section" {
  run_cli apply
  [ "$status" -eq 0 ]
  printf '%s\n' '# Claude notes' '' 'Use the staging database for manual tests.' > CLAUDE.md
  node_section() {
    awk '/^<!-- BEGIN AGENT-READY MANAGED: node -->$/,/^<!-- END AGENT-READY MANAGED: node -->$/' AGENTS.md
  }
  node_section > "$test_root/node-before"
  write_manifest '{"profiles": ["node", "go"]}'
  run_cli apply
  # The rules block may follow the selection; the sections stay as they were.
  ! grep -q 'AGENT-READY MANAGED: go' AGENTS.md
  node_section | cmp -s - "$test_root/node-before"
  # The lock still knows the section it applied.
  [ "$(lock_value 'sorted(lock["blocks"]["AGENTS.md"])')" = "['node']" ]

  # Once the agent merged the two files, the next apply catches up.
  cp "$skill_dir/assets/claude-proxy.md" CLAUDE.md
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: go -->' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: node -->' AGENTS.md
}

@test "remove keeps the lock while a stack section stays in AGENTS.md, so a second remove takes it out" {
  run_cli apply
  # A second start of the node section: the markers no longer pair up.
  printf '%s\n' '<!-- BEGIN AGENT-READY MANAGED: node -->' >> AGENTS.md
  run_cli remove --yes
  [ -f .agents/agent-ready.lock.json ]
  grep -q 'AGENT-READY MANAGED: node' AGENTS.md

  # Repaired by hand, the next remove still knows the section.
  sed -i.bak '$d' AGENTS.md && rm -f AGENTS.md.bak
  run_cli remove --yes
  [ "$status" -eq 0 ]
  ! grep -q 'AGENT-READY MANAGED' AGENTS.md 2>/dev/null
}

@test "a section whose first write was a conflict still retires when its stack leaves the selection" {
  run_cli apply
  # The lock of a section that never got an applied base, as a first write that conflicted leaves it.
  python3 - <<'PY'
import json
path = ".agents/agent-ready.lock.json"
lock = json.load(open(path, encoding="utf-8"))
lock["blocks"]["AGENTS.md"]["node"].update(sha256=None, state="conflict")
json.dump(lock, open(path, "w", encoding="utf-8"), indent=2)
PY
  write_manifest '{"profiles": ["go"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'AGENT-READY MANAGED: node' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: go -->' AGENTS.md
  [ "$(lock_value 'sorted(lock["blocks"]["AGENTS.md"])')" = "['go']" ]
}

@test "the section of each layer follows the section of the layer it extends" {
  write_manifest '{"profiles": ["nextjs-app-router"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(grep -o 'BEGIN AGENT-READY MANAGED: [a-z-]*' AGENTS.md | tr '\n' ' ')" = \
    "BEGIN AGENT-READY MANAGED: react BEGIN AGENT-READY MANAGED: nextjs BEGIN AGENT-READY MANAGED: nextjs-app-router " ]
  [ "$(lock_value 'lock["primaryStack"]')" = "nextjs-app-router" ]

  # Dropping to the nextjs layer takes out only the App Router section and rule.
  write_manifest '{"profiles": ["nextjs"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'AGENT-READY MANAGED: nextjs-app-router' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: nextjs -->' AGENTS.md
  [ ! -e .agents/rules/nextjs-app-router.md ]
  [ -f .agents/rules/server-first-data-flow.md ]
}

@test "a selection without a stack gets the core with the neutral AGENTS.md and none of software-development" {
  write_manifest '{"profiles": ["business-flows"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '## Purpose' AGENTS.md
  ! grep -qx '## Stack' AGENTS.md
  # The core rules stand alone: none points to a rule only software-development publishes.
  ! grep -q 'lint-gate.md\|patterns-we-do-not-use.md' .agents/rules/verify-changes.md .agents/rules/speculative-complexity-approval.md || \
    grep -q 'When the project has `lint-gate.md`' .agents/rules/verify-changes.md
  ! grep -q 'AGENT-READY MANAGED: ' AGENTS.md
  [ -f .agents/rules/verify-changes.md ]
  [ -f .agents/rules/business-flows.md ]
  [ ! -e .agents/rules/lint-gate.md ]
  [ ! -e .agents/skills/pr-review-workflow ]
  [ ! -e .github/pull_request_template.md ]
  grep -qx '# BEGIN AGENT-READY MANAGED: common' .gitignore
  [ "$(lock_value 'lock["primaryStack"]')" = "None" ]
  [ "$(lock_value 'lock["merged"]["AGENTS.md"]["template"]')" = "assets/common/agents-template.md" ]

  # A stack brings software-development, which it requires: its rules, PR template and skeleton.
  write_manifest '{"profiles": ["node"]}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ -f .agents/rules/lint-gate.md ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: software-development -->' .github/pull_request_template.md
  # A new AGENTS.md with a stack takes the software skeleton; the managed block is the same one.
  rm AGENTS.md
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '## Stack' AGENTS.md
  ! grep -qx '## Purpose' AGENTS.md
  [ "$(lock_value 'lock["profileOrder"][:2]')" = "['software-development', 'node']" ]
}

# A path pack whose profile publishes a nested target: a block for the AGENTS.md of the App Router folder.
# $1 is the rest of the manifest after the selection and the source.
add_nested_pack() {
  mkdir -p packs/acme/profiles/web/nested
  printf '## App Router\n\n- Each route exports a default component.\n' > packs/acme/profiles/web/nested/app-router.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"web": {"kind": "capability", "description": "Acme web.", "assets": "profiles/web", "nested": {"app-router": {"candidates": ["app", "src/app"]}}}}}' \
    > packs/acme/agent-ready-pack.json
  write_nested_manifest "${1:-}"
}

write_nested_manifest() {
  write_manifest "{\"profiles\": [\"node\", \"acme/web\"], \"sources\": {\"packs\": [{\"name\": \"acme\", \"source\": \"path:packs/acme\"}]}${1:+, $1}}"
}

@test "a nested target of a pack goes to the first candidate folder, with its CLAUDE.md proxy and the project's content kept" {
  mkdir -p src/app && printf 'export default function Page() {}\n' > src/app/page.tsx
  add_nested_pack
  run_cli trust add --project .
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Nested AGENTS.md: acme/web/app-router -> src/app/AGENTS.md (detected)"* ]]
  [[ "$output" == *"+ create          src/app/AGENTS.md (block acme/web/app-router)  creates the file"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  head -1 src/app/AGENTS.md | grep -qx '<!-- BEGIN AGENT-READY MANAGED: acme/web/app-router -->'
  grep -qx -- '- Each route exports a default component.' src/app/AGENTS.md
  [ "$(cat src/app/CLAUDE.md)" = '@AGENTS.md' ]
  [ "$(lock_value 'lock["blocks"]["src/app/AGENTS.md"]["acme/web/app-router"]["state"]')" = "applied" ]

  printf '\n## Team notes\n\nKeep server actions in actions.ts.\n' >> src/app/AGENTS.md
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx 'Keep server actions in actions.ts.' src/app/AGENTS.md
  run_cli plan
  [[ "$output" != *"(block acme/web/app-router)"* ]]

  # A Next.js repository with app/ at the root gets it there: app is the first candidate.
  git init -q "$test_root/root-app" && cd "$test_root/root-app"
  printf '{}\n' > package.json
  mkdir -p app && printf 'export default function Page() {}\n' > app/page.tsx
  add_nested_pack
  run_cli trust add --project .
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: acme/web/app-router -->' app/AGENTS.md
  [ -f app/CLAUDE.md ]
}

@test "nested.targets wins over detection, and moving a target retires its block and an AGENTS.md left empty with its proxy" {
  mkdir -p src/app apps/web/app && touch src/app/page.tsx apps/web/app/page.tsx
  add_nested_pack
  run_cli trust add --project .
  run_cli apply
  [ -f src/app/AGENTS.md ]

  write_nested_manifest '"nested": {"targets": [{"id": "acme/web/app-router", "paths": ["apps/web/app"]}]}'
  run_cli plan
  [[ "$output" == *"Nested AGENTS.md: acme/web/app-router -> apps/web/app/AGENTS.md (nested.targets)"* ]]
  [[ "$output" == *"- retire          src/app/AGENTS.md (block acme/web/app-router)"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: acme/web/app-router -->' apps/web/app/AGENTS.md
  [ -f apps/web/app/CLAUDE.md ]
  [ ! -e src/app/AGENTS.md ]
  [ ! -e src/app/CLAUDE.md ]
  [ "$(lock_value '"src/app/AGENTS.md" in lock["blocks"]')" = "False" ]

  # A folder with instructions of its own keeps them, and its CLAUDE.md, when the block leaves.
  printf '\n## Web notes\n' >> apps/web/app/AGENTS.md
  write_nested_manifest '"nested": {"targets": [{"id": "acme/web/app-router", "enabled": false}]}'
  run_cli plan
  [[ "$output" == *"Nested AGENTS.md: acme/web/app-router: off (nested.targets)"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'AGENT-READY MANAGED' apps/web/app/AGENTS.md
  head -1 apps/web/app/AGENTS.md | grep -qx '## Web notes'
  [ -f apps/web/app/CLAUDE.md ]
  [ ! -e src/app/AGENTS.md ]
}

@test "without a candidate folder or with nested off nothing is written, and plan says why" {
  add_nested_pack
  run_cli trust add --project .
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Nested AGENTS.md: acme/web/app-router: no folder, nothing is written (tried app, src/app; set one in nested.targets)"* ]]

  mkdir -p src/app && touch src/app/page.tsx
  write_nested_manifest '"nested": {"enabled": false, "targets": [{"id": "acme/web/other"}]}'
  run_cli plan
  [[ "$output" == *"Nested AGENTS.md: acme/web/app-router: off (nested.enabled)"* ]]
  [[ "$output" == *"Nested AGENTS.md: acme/web/other: in nested.targets, but no selected profile publishes it"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  [ ! -e src/app/AGENTS.md ]
  [ ! -e src/app/CLAUDE.md ]
}

@test "a folder of nested.targets outside the repository, reserved, a pattern, missing or ignored stops before writing" {
  mkdir -p src/app ignored && touch src/app/page.tsx
  printf 'ignored/\n' > .gitignore
  add_nested_pack
  run_cli trust add --project .
  local folder expected
  for folder in '../outside' '.agents/rules' 'src/*' 'missing' 'ignored'; do
    case "$folder" in
      ../outside) expected="is not a relative folder inside the repository" ;;
      .agents/rules) expected="is under .git/, .agents/, .claude/, .codex/" ;;
      'src/*') expected="is a pattern, not a folder" ;;
      missing) expected="does not exist in the repository" ;;
      ignored) expected="is ignored by Git" ;;
    esac
    write_nested_manifest "\"nested\": {\"targets\": [{\"id\": \"acme/web/app-router\", \"paths\": [\"$folder\"]}]}"
    run_cli plan
    [ "$status" -eq 2 ]
    [[ "$stderr" == *"the folder '$folder' of the nested target acme/web/app-router $expected"*"nothing was written"* ]]
    run_cli apply
    [ "$status" -ne 0 ]
    [[ "$stderr" == *"the folder '$folder' of the nested target acme/web/app-router $expected"*"nothing was written"* ]]
    [ ! -e src/app/AGENTS.md ]
    [ ! -e .agents/agent-ready.lock.json ]
  done
}

@test "a symlinked folder on the path of a nested target keeps the block out" {
  mkdir -p "$test_root/outside" && touch "$test_root/outside/page.tsx"
  ln -s "$test_root/outside" linked || skip "this filesystem cannot create a symlink"
  [ -L linked ] || skip "this filesystem cannot create a symlink"
  add_nested_pack '"nested": {"targets": [{"id": "acme/web/app-router", "paths": ["linked"]}]}'
  run_cli trust add --project .
  run_cli plan
  [[ "$output" == *"! conflict        linked/AGENTS.md (block acme/web/app-router)  a directory on its path is a symlink"* ]]
  run_cli apply
  [ ! -e "$test_root/outside/AGENTS.md" ]
  [ ! -e "$test_root/outside/CLAUDE.md" ]
}

@test "remove takes a nested block out and deletes the AGENTS.md that only held it, with its proxy" {
  mkdir -p src/app && touch src/app/page.tsx
  add_nested_pack
  run_cli trust add --project .
  run_cli apply
  [ -f src/app/CLAUDE.md ]
  run_cli remove --yes
  [ "$status" -eq 0 ]
  [ ! -e src/app/AGENTS.md ]
  [ ! -e src/app/CLAUDE.md ]
  [ -f src/app/page.tsx ]
}

@test "a pack that declares a nested target without its block, or publishes a block it does not declare, fails" {
  add_nested_pack
  rm packs/acme/profiles/web/nested/app-router.md
  run_cli plan
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"profile 'acme/web' declares the nested target 'app-router' but does not publish nested/app-router.md"* ]]

  printf 'x\n' > packs/acme/profiles/web/nested/app-router.md
  printf 'x\n' > packs/acme/profiles/web/nested/stray.md
  run_cli plan
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"profile 'acme/web': nested/stray.md is not the block of a nested target it declares in 'nested'"* ]]

  rm packs/acme/profiles/web/nested/stray.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"web": {"kind": "capability", "description": "Acme web.", "assets": "profiles/web", "nested": {"app-router": {"candidates": ["../app"]}}}}}' \
    > packs/acme/agent-ready-pack.json
  run_cli plan
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"the candidate '../app' of the nested target 'app-router' is not a relative folder inside the repository"* ]]
}

@test "a nested target waits beside a CLAUDE.md of its own that Git ignores, which the normalization never moves" {
  mkdir -p src/app && touch src/app/page.tsx
  printf 'Local notes.\n' > src/app/CLAUDE.md
  printf 'src/app/CLAUDE.md\n' > .gitignore
  add_nested_pack
  run_cli trust add --project .
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Nested AGENTS.md: acme/web/app-router -> src/app/AGENTS.md (detected); waits in src/app: its CLAUDE.md has instructions of its own"* ]]
  [[ "$output" != *"(block acme/web/app-router)"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  [ ! -e src/app/AGENTS.md ]
  grep -qx 'Local notes.' src/app/CLAUDE.md

  # The same bytes in AGENTS.md do not help: the ignored CLAUDE.md never becomes the proxy.
  cp src/app/CLAUDE.md src/app/AGENTS.md
  run_cli plan
  [[ "$output" == *"waits in src/app: its CLAUDE.md has instructions of its own"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'AGENT-READY MANAGED' src/app/AGENTS.md
}

@test "the root AGENTS.md lists the nested AGENTS.md files for Codex, and the index follows the targets and the providers" {
  mkdir -p src/app apps/web/app && touch src/app/page.tsx apps/web/app/page.tsx
  add_nested_pack
  run_cli trust add --project .
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Nested AGENTS.md index for Codex: 1 file(s) listed in AGENTS.md, ~"*" bytes of its limit"* ]]
  run_cli plan --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; index = json.load(sys.stdin)["nestedIndex"]; print(index["destinations"], index["bytes"] > 0)')" = "['src/app/AGENTS.md'] True" ]
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: agent-ready:nested-index -->' AGENTS.md
  grep -qxF -- '- `src/app/AGENTS.md`' AGENTS.md
  [ "$(lock_value 'lock["blocks"]["AGENTS.md"]["agent-ready:nested-index"]["state"]')" = "applied" ]

  # Moving the target moves its line.
  write_nested_manifest '"nested": {"targets": [{"id": "acme/web/app-router", "paths": ["apps/web/app"]}]}'
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qxF -- '- `apps/web/app/AGENTS.md`' AGENTS.md
  ! grep -qF -- '- `src/app/AGENTS.md`' AGENTS.md

  # Without Codex among the providers, or with nested.codexIndex off, there is no index.
  write_nested_manifest '"providers": ["claude"]'
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'agent-ready:nested-index' AGENTS.md
  [ -f src/app/AGENTS.md ]
  write_nested_manifest '"nested": {"codexIndex": false}'
  run_cli plan
  [[ "$output" != *"Nested AGENTS.md index for Codex"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  ! grep -q 'agent-ready:nested-index' AGENTS.md
}
