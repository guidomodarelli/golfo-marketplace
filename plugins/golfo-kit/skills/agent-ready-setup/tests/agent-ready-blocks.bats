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
  [[ "$output$stderr" == *"AGENTS.md is not a file a block can go to"* ]]

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
