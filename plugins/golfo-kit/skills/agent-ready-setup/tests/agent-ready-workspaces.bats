#!/usr/bin/env bats
# Workspaces of a monorepo (agent_ready_workspaces.py): the selection of each folder, resolved against
# the root selection, shown by plan and status, recorded in the lock, the paths that cannot be one, the
# rules a workspace adds (scoped with paths: and listed by its own AGENTS.md), and the rest of its assets:
# skills, subagents and commands once for the repository, blocks and nested targets where they belong; the
# workspaces detection suggests and agent-ready workspaces list|add|remove.

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

manifest_value() {
  python3 -c 'import json, sys; data = json.load(open(".agents/agent-ready.json", encoding="utf-8")); print(eval(sys.argv[1]))' "$1"
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

@test "the rules a workspace adds go to its folder with paths:, its AGENTS.md lists them and the root one does not" {
  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "apps/web", "profiles": ["react"]}]}'
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"rule(s) in .agents/rules/workspaces/apps/web/, listed in apps/web/AGENTS.md"* ]]
  [[ "$output" == *"skill, subagent and command file(s) of its profiles in .agents/, for the whole repository"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  rule=.agents/rules/workspaces/apps/web/react-style.md
  [ -f "$rule" ]
  [ "$(sed -n '1,3p' "$rule" | tr '\n' '|')" = '---|paths:|  - "apps/web/**"|' ]
  [ -e .claude/rules/workspaces/apps/web/react-style.md ]
  # A rule with a frontmatter keeps it and gains paths:.
  grep -qx '  testRunner: vitest' .agents/rules/workspaces/apps/web/react-testing.md
  grep -qx '  - "apps/web/\*\*"' .agents/rules/workspaces/apps/web/react-testing.md
  ! grep -q 'rules/workspaces' AGENTS.md
  ! grep -q '`.agents/rules/react-style.md`' AGENTS.md
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: agent-ready:workspace -->' apps/web/AGENTS.md
  grep -qxF -- '- Read and follow `.agents/rules/workspaces/apps/web/react-style.md`.' apps/web/AGENTS.md
  # The section of the stack names the rules of the workspace, and its commands and skills are in .agents/.
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: react -->' apps/web/AGENTS.md
  grep -qF '`.agents/rules/workspaces/apps/web/react-style.md`' apps/web/AGENTS.md
  ! grep -qF '`.agents/rules/react-style.md`' apps/web/AGENTS.md
  [ -f .agents/commands/react-review-pr.md ]
  [ -f .agents/skills/react-review-pr/SKILL.md ]
  # The subagents go to .agents/ once and name the rules where the workspace has them.
  grep -qF '`.agents/rules/workspaces/apps/web/react-security.md`' .agents/agents/react-security-scanner.md
  missing="$(grep -o '`\.agents/rules/[^`]*`' apps/web/AGENTS.md .agents/agents/*.md .agents/commands/*.md | cut -d: -f2- |
    tr -d '`' | sort -u | while read -r reference; do
    [ -e "$reference" ] || printf '%s\n' "$reference"
  done)"
  [ -z "$missing" ]
  [ "$(cat apps/web/CLAUDE.md)" = '@AGENTS.md' ]
  grep -qxF -- '- `apps/web/AGENTS.md`' AGENTS.md
  [ "$(lock_value 'lock["assets"][".agents/rules/workspaces/apps/web/react-style.md"]["workspace"]')" = "apps/web" ]

  run_cli apply
  run_cli plan
  [[ "$output" != *"+ create"* ]]
  [[ "$output" != *"~ update"* ]]
}

@test "two workspaces with different stacks do not collide, and one that leaves takes its rules, views and blocks" {
  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "apps/web", "profiles": ["react"]}, {"path": "services/api", "profiles": ["go"]}]}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ -f .agents/rules/workspaces/apps/web/react-style.md ]
  [ -n "$(ls .agents/rules/workspaces/services/api)" ]
  grep -q 'agent-ready:workspace' services/api/AGENTS.md

  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "services/api", "profiles": ["go"]}]}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ ! -e .agents/rules/workspaces/apps ]
  [ ! -e .claude/rules/workspaces/apps ]
  [ ! -e apps/web/AGENTS.md ]
  [ ! -e apps/web/CLAUDE.md ]
  ! grep -qF -- '- `apps/web/AGENTS.md`' AGENTS.md
  [ -n "$(ls .agents/rules/workspaces/services/api)" ]
  # Nothing else selects react: its commands leave with the workspace.
  [ ! -e .agents/commands/react-review-pr.md ]
}

@test "a rule of a workspace is checked against the folder of the workspace, not the root" {
  printf '{"devDependencies": {"jest": "29"}}\n' > apps/web/package.json
  write_manifest '{"profiles": ["node"], "workspaces": [{"path": "apps/web", "profiles": ["react"]}]}'
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *".agents/rules/workspaces/apps/web/react-testing.md"*"vitest"*"jest"*"apps/web/package.json"* ]]
}

@test "a pack only a workspace selects counts as selected: its rules keep their patterns and its changes are drift" {
  mkdir -p packs/acme/profiles/web/rules
  printf '%s\n' '---' 'paths: ["src/**/*.{ts,tsx}", "lib/*"]' '---' '# Acme web' > packs/acme/profiles/web/rules/acme-web.md
  printf '%s\n' '---' 'paths:' '# the docs' '- "docs/**" # markdown' '' '- "guides/**"' '---' '# Acme docs' > packs/acme/profiles/web/rules/acme-docs.md
  printf '%s\n' '---' 'paths: ["api/**"] # handlers' '---' '# Acme api' > packs/acme/profiles/web/rules/acme-api.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"web": {"kind": "capability", "description": "Acme web.", "assets": "profiles/web"}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}, "workspaces": [{"path": "apps/web", "profiles": ["acme/web"]}]}'
  run_cli trust add --project .
  run_cli apply
  [ "$status" -eq 0 ]
  grep -qxF '  - "apps/web/src/**/*.{ts,tsx}"' .agents/rules/workspaces/apps/web/acme-web.md
  grep -qxF '  - "apps/web/lib/*"' .agents/rules/workspaces/apps/web/acme-web.md
  # A YAML sequence without indentation is a list too, and a comment is not part of a pattern.
  grep -qxF '  - "apps/web/docs/**"' .agents/rules/workspaces/apps/web/acme-docs.md
  grep -qxF '  - "apps/web/guides/**"' .agents/rules/workspaces/apps/web/acme-docs.md
  [ "$(grep -c '^  - ' .agents/rules/workspaces/apps/web/acme-docs.md)" -eq 2 ]
  grep -qxF '  - "apps/web/api/**"' .agents/rules/workspaces/apps/web/acme-api.md
  [ "$(lock_value '"acme/web" in lock["profiles"]')" = "True" ]
  [ "$(lock_value 'lock["profileSources"]["acme"]["profiles"]')" = "['acme/web']" ]

  printf '# Another rule\n' > packs/acme/profiles/web/rules/acme-other.md
  run_cli status
  [[ "$output" == *"acme differs from the lock"* ]]
}

@test "a workspace cannot override an asset the root selection projects for the whole repository" {
  mkdir -p packs/acme/profiles/jest/rules
  printf '# Jest\n' > packs/acme/profiles/jest/rules/react-testing.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"jest": {"kind": "capability", "description": "Jest.", "assets": "profiles/jest", "overrides": ["react:rules/react-testing.md"]}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["react"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}, "workspaces": [{"path": "apps/web", "profiles": ["acme/jest"]}]}'
  run_cli trust add --project .
  run_cli plan
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"workspace apps/web: profile 'acme/jest' overrides an asset of 'react', which the root selection projects for the whole repository"* ]]
  [ ! -e .agents/agent-ready.lock.json ]
}

@test "a workspace profile puts its nested targets inside the workspace and its blocks in the files they belong to" {
  mkdir -p apps/site/app packs/acme/profiles/web/blocks
  touch apps/site/app/page.tsx
  printf 'dist/\n' > packs/acme/profiles/web/blocks/.gitignore
  mkdir -p packs/acme/profiles/web/rules
  printf '# Acme checklist\n' > packs/acme/profiles/web/rules/acme-checklist.md
  printf '%s\n' '## Acme web' '' 'Follow `.agents/rules/acme-checklist.md`.' > packs/acme/profiles/web/blocks/CONTRIBUTING.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"web": {"kind": "capability", "description": "Acme web.", "assets": "profiles/web"}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node"], "providers": ["claude", "codex"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}, "workspaces": [{"path": "apps/web", "profiles": ["acme/web"]}, {"path": "apps/site", "profiles": ["nextjs-app-router"]}]}'
  run_cli trust add --project .
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"Nested AGENTS.md: nextjs-app-router/app-router -> apps/site/app/AGENTS.md (detected) (workspace apps/site)"* ]]
  run_cli apply
  [ "$status" -eq 0 ]
  # The nested target names the rule of the workspace, and the root index lists it.
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: nextjs-app-router/app-router -->' apps/site/app/AGENTS.md
  grep -qF '`.agents/rules/workspaces/apps/site/nextjs-app-router.md`' apps/site/app/AGENTS.md
  [ -f .agents/rules/workspaces/apps/site/nextjs-app-router.md ]
  grep -qxF -- '- `apps/site/app/AGENTS.md`' AGENTS.md
  # Git reads .gitignore by folder; any other file takes its block at the root.
  grep -qx '# BEGIN AGENT-READY MANAGED: acme/web' apps/web/.gitignore
  ! grep -q 'acme/web' .gitignore
  grep -qx '<!-- BEGIN AGENT-READY MANAGED: acme/web -->' CONTRIBUTING.md
  # The block names the rule where the workspace has it.
  grep -qF 'Follow `.agents/rules/workspaces/apps/web/acme-checklist.md`.' CONTRIBUTING.md

  run_cli plan
  [[ "$output" != *"+ create"* ]]
  [[ "$output" != *"~ update"* ]]

  write_manifest '{"profiles": ["node"], "providers": ["claude", "codex"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}}'
  run_cli apply
  [ "$status" -eq 0 ]
  [ ! -e apps/site/app/AGENTS.md ]
  [ ! -e apps/web/.gitignore ]
  [ ! -e CONTRIBUTING.md ]
}

@test "two workspaces keep their own nested folders and their own replacement of the same rule" {
  mkdir -p apps/a/app apps/b/app packs/acme/profiles/jest/rules packs/acme/profiles/vitest/rules
  touch apps/a/app/page.tsx apps/b/app/page.tsx
  printf '# Jest\n' > packs/acme/profiles/jest/rules/react-testing.md
  printf '# Vitest\n' > packs/acme/profiles/vitest/rules/react-testing.md
  printf '%s\n' '{"schemaVersion": 1, "name": "acme", "profiles": {"jest": {"kind": "capability", "description": "Jest.", "assets": "profiles/jest", "overrides": ["react:rules/react-testing.md"]}, "vitest": {"kind": "capability", "description": "Vitest.", "assets": "profiles/vitest", "overrides": ["react:rules/react-testing.md"]}}}' \
    > packs/acme/agent-ready-pack.json
  write_manifest '{"profiles": ["node"], "sources": {"packs": [{"name": "acme", "source": "path:packs/acme"}]}, "nested": {"targets": [{"id": "nextjs-app-router/app-router", "paths": ["apps/a/app", "apps/b/app"]}]}, "workspaces": [{"path": "apps/a", "profiles": ["nextjs-app-router", "acme/jest"]}, {"path": "apps/b", "profiles": ["nextjs-app-router", "acme/vitest"]}]}'
  run_cli trust add --project .
  run_cli apply
  [ "$status" -eq 0 ]
  # Each workspace replaces the rule in its own folder.
  grep -qx '# Jest' .agents/rules/workspaces/apps/a/react-testing.md
  grep -qx '# Vitest' .agents/rules/workspaces/apps/b/react-testing.md
  # A folder of nested.targets belongs to the workspace that holds it.
  grep -qF '`.agents/rules/workspaces/apps/a/nextjs-app-router.md`' apps/a/app/AGENTS.md
  grep -qF '`.agents/rules/workspaces/apps/b/nextjs-app-router.md`' apps/b/app/AGENTS.md
  ! grep -q 'workspaces/apps/b' apps/a/app/AGENTS.md
  # A subagent both workspaces share names the rule of each one.
  grep -qF '`.agents/rules/workspaces/apps/a/react-security.md` or `.agents/rules/workspaces/apps/b/react-security.md` (the one of the workspace you work in)' \
    .agents/agents/react-security-scanner.md

  run_cli plan
  [[ "$output" != *"+ create"* ]]
  [[ "$output" != *"~ update"* ]]
}

@test "agent-ready workspaces add, list and remove change the manifest and check it before writing" {
  write_manifest '{"profiles": ["node"]}'
  run_cli workspaces add apps/web react
  [ "$status" -eq 0 ]
  [ "$(manifest_value 'data["workspaces"]')" = "[{'path': 'apps/web', 'profiles': ['react']}]" ]
  run_cli workspaces add ./apps/web/ business-flows
  [ "$status" -eq 0 ]
  [ "$(manifest_value 'data["workspaces"][0]["profiles"]')" = "['react', 'business-flows']" ]
  run_cli workspaces list
  [ "$status" -eq 0 ]
  [[ "$output" == *"apps/web"*"react, business-flows"*"(adds react, business-flows)"* ]]
  run_cli workspaces list --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; print(json.load(sys.stdin)["workspaces"][0]["adds"])')" = "['react', 'business-flows']" ]

  before="$(cat .agents/agent-ready.json)"
  run_cli workspaces add missing react
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"the workspace 'missing' does not exist in the repository"* ]]
  run_cli workspaces add services/api no-such-profile
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"workspace services/api: unknown profile 'no-such-profile'"* ]]
  run_cli workspaces remove services/api
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"services/api is not a workspace"* ]]
  run_cli workspaces remove apps/web go
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"workspace apps/web does not select go"* ]]
  [ "$(cat .agents/agent-ready.json)" = "$before" ]

  run_cli workspaces remove apps/web business-flows
  [ "$status" -eq 0 ]
  [ "$(manifest_value 'data["workspaces"][0]["profiles"]')" = "['react']" ]
  run_cli workspaces remove apps/web
  [ "$status" -eq 0 ]
  [ "$(manifest_value '"workspaces" in data')" = "False" ]
}

@test "detection suggests a workspace for each folder with a stack the root does not have, and add takes it" {
  printf '{"dependencies": {"next": "15", "react": "19"}}\n' > apps/web/package.json
  mkdir -p apps/web/app libs/ui tools/gen packages/docs
  touch apps/web/app/layout.tsx packages/docs/README.md
  printf 'module example.invalid/api\n' > services/api/go.mod
  # Folders the package managers declare count too, besides apps/, packages/ and services/.
  printf '%s\n' 'packages:' '  - "libs/*"' > pnpm-workspace.yaml
  printf '{"dependencies": {"react": "19"}}\n' > libs/ui/package.json
  printf '%s\n' 'go 1.22' '' 'use (' '	./tools/gen' ')' > go.work
  printf 'module example.invalid/gen\n' > tools/gen/go.mod
  # A recursive pattern goes into the subfolders, but never into installed dependencies; a literal
  # folder (./tools/gen of go.work) counts as it is.
  printf '{"workspaces": ["modules/**"]}\n' > package.json
  mkdir -p modules/team/api modules/team/node_modules/lib
  printf 'module example.invalid/team\n' > modules/team/api/go.mod
  printf 'module example.invalid/lib\n' > modules/team/node_modules/lib/go.mod
  write_manifest '{"profiles": ["node"]}'
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"? apps/web: nextjs-app-router (apps/web/app/layout.tsx matches app/layout.tsx)"* ]]
  [[ "$output" == *"Add it with agent-ready workspaces add services/api"* ]]
  [[ "$output" == *"? libs/ui: react"* ]]
  [[ "$output" == *"? tools/gen: go"* ]]
  [[ "$output" == *"? modules/team/api: go"* ]]
  [[ "$output" != *"node_modules"* ]]
  [[ "$output" != *"? packages/docs"* ]]

  run_cli workspaces add apps/web
  [ "$status" -eq 0 ]
  [ "$(manifest_value 'data["workspaces"]')" = "[{'path': 'apps/web', 'profiles': ['nextjs-app-router']}]" ]
  run_cli workspaces list
  [ "$status" -eq 0 ]
  [[ "$stderr" != *"Suggested: apps/web"* ]]
  [[ "$stderr" == *"Suggested: services/api: go"* ]]

  # A folder without a stack of its own needs its profiles named.
  run_cli workspaces add packages/docs
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"no stack detected in packages/docs"* ]]

  write_manifest '{"profiles": ["node"], "detection": {"workspaces": false}}'
  run_cli plan
  [ "$status" -eq 0 ]
  [[ "$output" != *"Workspaces suggested"* ]]
}
