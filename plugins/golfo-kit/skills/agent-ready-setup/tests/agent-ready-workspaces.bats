#!/usr/bin/env bats
# Workspaces of a monorepo (agent_ready_workspaces.py): the selection of each folder, resolved against
# the root selection, shown by plan and status, recorded in the lock, and the paths that cannot be one.

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
  mkdir -p apps/web services/api
  touch apps/web/.keep services/api/.keep
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

@test "each workspace resolves its profiles against the root selection, and plan, status and the lock show it" {
  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "apps/web", "profiles": ["nextjs-app-router"]}, {"path": "services/api", "profiles": ["node"]}]}'
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Workspace apps/web: nextjs-app-router (adds react, nextjs, nextjs-app-router to the root selection)"* ]]
  [[ "$output" == *"Workspace services/api: node (nothing of its own: the root selection already has it)"* ]]
  run_cli plan --json
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; print([(item["path"], item["own"]) for item in json.load(sys.stdin)["workspaces"]])')" = "[('apps/web', ['react', 'nextjs', 'nextjs-app-router']), ('services/api', [])]" ]

  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value 'lock["workspaces"]["apps/web"]')" = "{'own': ['react', 'nextjs', 'nextjs-app-router'], 'profiles': ['nextjs-app-router']}" ]
  run_cli status
  [[ "$output" == *"Workspace apps/web: nextjs-app-router"* ]]
  [[ "$output" != *"! workspace"* ]]

  # A selection the lock does not have yet, and a workspace that left the manifest, are drift.
  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "apps/web", "profiles": ["react"]}]}'
  run_cli status
  [[ "$output" == *"! workspace apps/web selects react, the lock nextjs-app-router: run agent-ready apply to adopt it"* ]]
  [[ "$output" == *"! workspace services/api left the manifest: run agent-ready apply to adopt it"* ]]
  run_cli check --offline
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"workspace apps/web selects react, the lock nextjs-app-router"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(lock_value 'sorted(lock["workspaces"])')" = "['apps/web']" ]
}

@test "a workspace path that cannot be one, or a selection that does not resolve, stops before writing" {
  mkdir -p ignored && touch ignored/.keep
  printf 'ignored/\n' > .gitignore
  local entries expected
  for entries in \
    '{"path": "missing", "profiles": ["node"]}' \
    '{"path": "ignored", "profiles": ["node"]}' \
    '{"path": "../outside", "profiles": ["node"]}' \
    '{"path": ".agents", "profiles": ["node"]}' \
    '{"path": "apps", "profiles": ["node"]}, {"path": "apps/web", "profiles": ["react"]}' \
    '{"path": "apps/web", "profiles": ["node"]}, {"path": "apps/web", "profiles": ["react"]}' \
    '{"path": "apps/web", "profiles": ["no-such-profile"]}' \
    '{"path": "apps/web", "profiles": ["ci-github"]}'; do
    case "$entries" in
      *missing*) expected="the workspace 'missing' does not exist in the repository; nothing was written" ;;
      *ignored*) expected="the workspace 'ignored' is ignored by Git; nothing was written" ;;
      *outside*) expected="the workspace '../outside' is not a relative folder inside the repository" ;;
      *'".agents"'*) expected="the workspace '.agents' is under .git/, .agents/, .claude/, .codex/" ;;
      *'"apps",'*) expected="the workspace 'apps/web' is inside the workspace 'apps'" ;;
      *no-such-profile*) expected="workspace apps/web: unknown profile 'no-such-profile'" ;;
      *ci-github*) expected="workspace apps/web: profile 'ci-github' comes from ci.provider, not from the selection" ;;
      *) expected="the workspace 'apps/web' is listed twice" ;;
    esac
    write_manifest "{\"profiles\": [\"node\"], \"workspaces\": [$entries]}"
    run_cli plan
    [ "$status" -eq 2 ]
    [[ "$stderr" == *"$expected"* ]]
    run_cli apply
    [ "$status" -ne 0 ]
    [ ! -e .agents/agent-ready.lock.json ]
  done
}

@test "Git ignoring one file of a workspace does not make the workspace ignored" {
  printf 'AGENTS.md\n' > .gitignore
  touch apps/web/package.json
  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "apps/web", "profiles": ["react"]}]}'
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Workspace apps/web: react (adds react to the root selection)"* ]]
}

@test "a workspace resolves with the root selection, so a profile that conflicts with one of the root fails" {
  mkdir -p packs/acme/profiles/headless/rules
  printf '# Headless\n' > packs/acme/profiles/headless/rules/acme-headless.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"headless": {"kind": "capability", "description": "No browser.", "assets": "profiles/headless", "conflicts": ["browser"]}}}' \
    > packs/acme/agent-ready-pack.json
  # node brings browser by default, so the workspace cannot take a profile that conflicts with it.
  write_manifest '{"profiles": ["node"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}, "workspaces": [{"path": "apps/web", "profiles": ["acme/headless"]}]}'
  run_cli trust add --project .
  run_cli plan
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"workspace apps/web: profiles 'acme/headless' and 'browser' are declared incompatible"* ]]
}

@test "--from-lock refuses a workspace selection that is not the one of the lock" {
  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "apps/web", "profiles": ["react"]}]}'
  run_cli apply
  [ "$status" -eq 0 ]
  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "apps/web", "profiles": ["go"]}]}'
  cp .agents/agent-ready.lock.json "$test_root/lock-before"
  run_cli apply --from-lock
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"selection: workspace apps/web selects go, the lock react"* ]]
  cmp -s .agents/agent-ready.lock.json "$test_root/lock-before"
}
