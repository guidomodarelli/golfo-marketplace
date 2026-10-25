#!/usr/bin/env bats

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  test_root="$(mktemp -d)"
  # Native Windows symlinks under Git Bash (needs Developer Mode); ignored elsewhere.
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  test_root="$(cd "$test_root" && pwd -P)"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  # Keeps the SessionStart upgrade window stamp out of the user's real cache.
  export XDG_CACHE_HOME="$test_root/cache"
  # Asset-projection tests use the documented offline bootstrap option. Browser
  # installation and real MCP registration are exercised in their own suite.
  export AGENT_READY_SETUP_BROWSER_INSTALL=0
  # Tests choose the Codex home explicitly; an inherited CODEX_HOME would
  # redirect config, snapshot and cache lookups away from the fixture HOME.
  unset CODEX_HOME
  # Fake provider CLIs keep the marketplace upgrade offline and never start a real provider.
  for provider_cli in claude codex; do
    cat > "$fake_bin/$provider_cli" <<'EOF'
#!/bin/bash
exit 0
EOF
    chmod +x "$fake_bin/$provider_cli"
  done
  git -C "$project_dir" -c init.defaultBranch=main init -q
  cd "$project_dir"
}

# Background tasks run detached from the hook; wait for their observable effect.
wait_for_file_containing() {
  local path="$1"
  local expected="$2"
  local attempt

  for attempt in $(seq 1 100); do
    if [[ -f "$path" ]] && grep -Fq -- "$expected" "$path"; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

teardown() {
  cd "$repository_root"
  # Windows cannot delete files that a detached background review still has open;
  # retry for a few seconds so it can finish before failing the test.
  local removal_attempt
  for removal_attempt in $(seq 1 50); do
    rm -rf "$test_root" 2>/dev/null && return 0
    sleep 0.2
  done
  rm -rf "$test_root"
}

run_bootstrap() {
  local stack="$1"
  shift

  run env PATH="$test_root/bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" \
    --stack "$stack" \
    --skill-dir "$skill_dir" \
    --provider claude \
    "$@"
}

run_marketplace_sync() {
  local hook_path="$1"
  local source_skill_dir="$2"
  shift 2

  run env \
    PATH="$test_root/bin:$PATH" \
    AGENT_READY_SETUP_SKILL_DIR="$source_skill_dir" \
    bash "$hook_path" \
    --provider claude \
    --stack frontend \
    "$@"
}

# Git Bash without native symlinks copies instead of linking; these tests check real symlinks.
# A Claude view is a symlink to the shared asset, or a hard link to it where the platform
# cannot create symlinks without privileges (Windows without Developer Mode).
# Simulates a platform without the symlink privilege: `ln -s` fails, plain `ln` works.
# Native Windows jq writes CRLF; fixtures and comparisons expect LF. Keeps jq's exit status.
jq() {
  command jq "$@" | tr -d '\r'
  return "${PIPESTATUS[0]}"
}

disable_symlinks() {
  local real_ln
  real_ln="$(command -v ln)"
  cat > "$fake_bin/ln" <<EOF
#!/bin/bash
for argument in "\$@"; do
  if [[ "\$argument" == "-s" ]]; then
    echo "ln: symbolic links are disabled for this test" >&2
    exit 1
  fi
done
exec "$real_ln" "\$@"
EOF
  chmod +x "$fake_bin/ln"
}

assert_claude_view() {
  local view="$1"
  local expected_target="${2:-}"
  local shared_asset=".agents/${view#.claude/}"

  if [[ -L "$view" ]]; then
    [[ -z "$expected_target" || "$(readlink "$view")" == "$expected_target" ]]
  else
    [[ -f "$view" && "$view" -ef "$shared_asset" ]]
  fi
}

skip_without_symlinks() {
  local probe_target="$test_root/symlink-probe-target"
  local probe_link="$test_root/symlink-probe-link"
  : > "$probe_target"
  ln -s "$probe_target" "$probe_link" 2>/dev/null || true
  if [[ ! -L "$probe_link" ]]; then
    rm -f "$probe_target" "$probe_link"
    skip "requiere symlinks reales (en Windows: Modo de desarrollador o una shell elevada)"
  fi
  rm -f "$probe_target" "$probe_link"
}

@test "normalize-instructions entry point normalizes instructions without projecting assets" {
  printf '%s\n' '# Project instructions' > CLAUDE.md
  mkdir -p docs
  printf '%s\n' '# Docs instructions' > docs/CLAUDE.md

  run bash "$skill_dir/scripts/normalize-instructions.sh" --stack node

  [ "$status" -eq 0 ]
  [ "$(cat AGENTS.md)" = '# Project instructions' ]
  cmp -s CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  [ "$(cat docs/AGENTS.md)" = '# Docs instructions' ]
  cmp -s docs/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  [[ "$output" == *"Instruction normalization completed"* ]]
  [ ! -e .agents ]
  [ ! -e .claude ]
  [ ! -e .codex ]

  run bash "$skill_dir/scripts/bootstrap.sh" --stack node --skill-dir "$skill_dir" --normalize-only
  [ "$status" -ne 0 ]
  [[ "$output" == *"Unknown argument: --normalize-only"* ]]
}

@test "SessionStart sync migrates browser MCP registrations from the existing installation" {
  source_dir="$test_root/browser-skill"
  cp -R "$skill_dir" "$source_dir"
  # Isolate the provider-backed instruction review so no real provider CLI writes into HOME,
  # and keep the background installer from detaching a real setup run during the test.
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
printf '%s\n' '[instruction-merge] Review completed'
EOF
  printf '%s\n' 'import sys' > "$source_dir/scripts/start-browser-install.py"
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  browser_home="$test_root/home"
  tools_root="$browser_home/.local/share/agent-ready-setup/browser-tools"
  mkdir -p "$tools_root/bin" "$tools_root/current/node_modules/.bin" "$browser_home/.codex"
  for executable in "$tools_root/bin/chrome-devtools" "$tools_root/bin/playwright" "$tools_root/bin/agent-browser" \
    "$tools_root/current/node_modules/.bin/agent-browser" "$test_root/chromium"; do
    printf '#!/bin/sh\n' > "$executable"
    chmod +x "$executable"
  done
  jq -n --arg tools "$tools_root" --arg chromium "$test_root/chromium" \
    '{agent_browser: ($tools + "/current/node_modules/.bin/agent-browser"), browser_executable: $chromium}' \
    > "$tools_root/installation.json"
  legacy="/Users/someone/.local/share/agent-ready-setup/browser-tools/1.9.0-0.0.81-0.38.0/node_modules/.bin"
  jq -n --arg command "$legacy/playwright-mcp" '{mcpServers: {playwright: {command: $command}, custom: {command: "custom"}}}' > .mcp.json

  run env HOME="$browser_home" CODEX_HOME="$browser_home/.codex" CLAUDE_CONFIG_DIR="$browser_home" \
    AGENT_READY_SETUP_BROWSER_INSTALL=1 PATH="$test_root/bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_dir" \
    bash .agents/hooks/sync-marketplace.sh --provider claude --stack frontend

  [ "$status" -eq 0 ]
  jq -e --arg launcher '${HOME}/.local/share/agent-ready-setup/browser-tools/bin/playwright' \
    '.mcpServers.playwright == {command: $launcher} and .mcpServers.custom == {command: "custom"}' .mcp.json >/dev/null
  ! grep -Fq '/Users/someone' .mcp.json
  [ ! -e "$browser_home/.claude.json" ]
  [ ! -e "$browser_home/.codex/config.toml" ]
  [[ "$output" != *"install pinned browser packages"* ]]
}

@test "SessionStart sync starts the background browser install when no installation exists" {
  source_dir="$test_root/background-skill"
  cp -R "$skill_dir" "$source_dir"
  # Isolate the provider-backed review and record the background installer call instead of installing.
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
printf '%s\n' '[instruction-merge] Review completed'
EOF
  # Native Windows Python cannot open POSIX paths such as /tmp; cygpath translates them.
  invocation_log_path="$test_root/background-install.log"
  if command -v cygpath >/dev/null 2>&1; then
    invocation_log_path="$(cygpath -m "$invocation_log_path")"
  fi
  cat > "$source_dir/scripts/start-browser-install.py" <<EOF
import sys
with open("$invocation_log_path", "w") as invocation_log:
    invocation_log.write(" ".join(sys.argv[1:]))
EOF
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  browser_home="$test_root/empty-home"
  mkdir -p "$browser_home"

  run env HOME="$browser_home" CODEX_HOME="$browser_home/.codex" CLAUDE_CONFIG_DIR="$browser_home" \
    AGENT_READY_SETUP_BROWSER_INSTALL=1 PATH="$test_root/bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_dir" \
    bash .agents/hooks/sync-marketplace.sh --provider claude --stack frontend

  [ "$status" -eq 0 ]
  # The installer starts detached; give it time to record its invocation.
  local wait_attempt
  for wait_attempt in $(seq 1 100); do
    [ -s "$test_root/background-install.log" ] && break
    sleep 0.1
  done
  expected_project_dir="$project_dir"
  # Git Bash translates paths passed to native Windows Python into C:/ form.
  if command -v cygpath >/dev/null 2>&1; then
    expected_project_dir="$(cygpath -m "$project_dir")"
  fi
  [ "$(cat "$test_root/background-install.log")" = "--project $expected_project_dir" ]
  [[ "$output" == *"no complete browser installation"* ]]
}

@test "SessionStart sync skips browser registration when browser setup is disabled" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  printf '%s\n' '{"mcpServers": {}}' > .mcp.json

  run_marketplace_sync .agents/hooks/sync-marketplace.sh "$skill_dir"

  [ "$status" -eq 0 ]
  [ "$(cat .mcp.json)" = '{"mcpServers": {}}' ]
  [[ "$output" != *"Browser registration"* ]]
}

@test "SessionStart sync keeps stdout empty and reports progress on stderr for both providers" {
  bats_require_minimum_version 1.5.0
  source_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$source_dir"
  # Isolate the provider-backed instruction review at the project's own boundary.
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
printf '%s\n' '[instruction-merge] Review completed'
EOF
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf '%s\n' 'Marketplace command progress'
EOF
  chmod +x "$fake_bin/claude"
  cp -p "$fake_bin/claude" "$fake_bin/codex"

  for provider in claude codex; do
    run --separate-stderr env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$source_dir" \
      bash "$source_dir/assets/common/hooks/sync-marketplace.sh" --provider "$provider" --stack node

    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [[ "$stderr" == *'Marketplace command progress'* ]]
    [[ "$stderr" != *'[instruction-merge] Review completed'* ]]
    [[ "$stderr" == *'Local managed asset projection completed for node.'* ]]
    [ -f .codex/hooks.json ]
    [ -f .agents/hooks/sync-marketplace.sh ]
    review_log="$(find "$XDG_CACHE_HOME/agent-ready-setup" -name 'instruction-review-*.log' | head -n 1)"
    wait_for_file_containing "$review_log" '[instruction-merge] Review completed'
    rm -f -- "$review_log"
  done
}

@test "SessionStart sync preserves upgrade failures without writing stdout" {
  bats_require_minimum_version 1.5.0
  cat > "$fake_bin/codex" <<'EOF'
#!/bin/bash
printf '%s\n' 'Marketplace upgrade failed'
exit 17
EOF
  chmod +x "$fake_bin/codex"

  run --separate-stderr env PATH="$fake_bin:$PATH" \
    bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" --provider codex --stack node

  [ "$status" -eq 17 ]
  [ -z "$output" ]
  [[ "$stderr" == *'Marketplace upgrade failed'* ]]
  [ ! -f "$XDG_CACHE_HOME/agent-ready-setup/marketplace-upgrade-codex.stamp" ]
}

@test "bootstrap keeps stdout empty and reports installed assets on stderr for both providers" {
  bats_require_minimum_version 1.5.0
  for provider in claude codex; do
    run --separate-stderr env PATH="$fake_bin:$PATH" \
      bash "$skill_dir/scripts/bootstrap.sh" --stack node --skill-dir "$skill_dir" --provider "$provider"

    [ "$status" -eq 0 ]
    [ -z "$output" ]
    [[ "$stderr" == *'Done.'* ]]
    [ -f .codex/hooks.json ]
    [ -f .agents/hooks/sync-marketplace.sh ]
  done
}

@test "bootstrap reports invalid arguments on stderr without writing stdout" {
  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "$skill_dir/scripts/bootstrap.sh" --stack

  [ "$status" -eq 1 ]
  [ -z "$output" ]
  [[ "$stderr" == *'ERROR: --stack requires a value'* ]]
}

@test "bootstrap installs shared GitHub PR template for every stack" {
  for stack in frontend node java go; do
    run_bootstrap "$stack"
    [ "$status" -eq 0 ]
    cmp -s .github/pull_request_template.md "$skill_dir/assets/common/github/pull_request_template.md"
    [ ! -e .agents/github ]
    [ ! -e .claude/github ]
    rm .github/pull_request_template.md
  done
}

@test "bootstrap refreshes existing PR template and preserves other GitHub files" {
  mkdir -p .github
  printf '%s\n' 'Existing template' > .github/pull_request_template.md
  printf '%s\n' 'Project owners' > .github/CODEOWNERS
  cp .github/CODEOWNERS "$test_root/expected-owners"

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  cmp -s .github/pull_request_template.md "$skill_dir/assets/common/github/pull_request_template.md"
  cmp -s .github/CODEOWNERS "$test_root/expected-owners"
}

@test "marketplace sync restores PR template and hook progress for both providers" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  for provider in claude codex; do
    printf '%s\n' 'Stale template' > .github/pull_request_template.md
    jq 'del(.hooks.SessionStart[].hooks[].statusMessage, .hooks.PostToolUse[].hooks[].statusMessage)' \
      .claude/settings.json > "$test_root/settings.json"
    cp "$test_root/settings.json" .claude/settings.json
    jq 'del(.hooks.SessionStart[].hooks[].statusMessage, .hooks.PostToolUse[].hooks[].statusMessage)' \
      .codex/hooks.json > "$test_root/hooks.json"
    cp "$test_root/hooks.json" .codex/hooks.json

    run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" \
      bash .agents/hooks/sync-marketplace.sh --provider "$provider" --stack frontend

    [ "$status" -eq 0 ]
    cmp -s .github/pull_request_template.md "$skill_dir/assets/common/github/pull_request_template.md"
    for settings_file in .claude/settings.json .codex/hooks.json; do
      jq -e '[.hooks[][] | .hooks[] | select(.type == "command")] | length >= 2 and all(.[]; (.statusMessage | type) == "string" and (.statusMessage | length) > 0)' \
        "$settings_file" >/dev/null
    done
  done
}

@test "PR template projection preserves symlinked GitHub directory" {
  skip_without_symlinks
  mkdir "$test_root/external-github"
  printf '%s\n' 'External template' > "$test_root/external-github/pull_request_template.md"
  cp "$test_root/external-github/pull_request_template.md" "$test_root/expected-template"
  ln -s "$test_root/external-github" .github

  run_bootstrap frontend
  [ "$status" -eq 0 ]
  cmp -s .github/pull_request_template.md "$test_root/expected-template"
  [[ "$output" == *'.github'*'symlink'* ]]

  run_marketplace_sync .agents/hooks/sync-marketplace.sh "$skill_dir"
  [ "$status" -eq 0 ]
  cmp -s .github/pull_request_template.md "$test_root/expected-template"
}

@test "PR template projection replaces file symlink without changing its target" {
  skip_without_symlinks
  mkdir .github
  printf '%s\n' 'External template' > "$test_root/external-template"
  cp "$test_root/external-template" "$test_root/expected-template"
  for operation in bootstrap sync; do
    ln -s "$test_root/external-template" .github/pull_request_template.md
    if [[ "$operation" == bootstrap ]]; then
      run_bootstrap frontend
    else
      run_marketplace_sync .agents/hooks/sync-marketplace.sh "$skill_dir"
    fi
    [ "$status" -eq 0 ]
    [ ! -L .github/pull_request_template.md ]
    cmp -s .github/pull_request_template.md "$skill_dir/assets/common/github/pull_request_template.md"
    cmp -s "$test_root/external-template" "$test_root/expected-template"
    rm .github/pull_request_template.md
  done
}

@test "bootstrap projects Claude, shared, and Codex trees" {
  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ -f AGENTS.md ]
  [ -f CLAUDE.md ]
  cmp -s CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  [ -f .claude/settings.json ]
  assert_claude_view .claude/rules/security.md "../../.agents/rules/security.md"
  [ -f .agents/rules/security.md ]
  assert_claude_view .claude/rules/lint-gate.md "../../.agents/rules/lint-gate.md"
  cmp -s .agents/rules/lint-gate.md "$skill_dir/assets/common/rules/lint-gate.md"
  assert_claude_view .claude/skills/component-creation/SKILL.md "../../../.agents/skills/component-creation/SKILL.md"
  [ -f .agents/skills/component-creation/SKILL.md ]
  [ -f .agents/skills/react-act-test-fixes/SKILL.md ]
  assert_claude_view .claude/skills/react-act-test-fixes/SKILL.md "../../../.agents/skills/react-act-test-fixes/SKILL.md"
  [ -f .agents/skills/react-act-test-fixes/evals/eval-config.json ]
  assert_claude_view .claude/agents/security-scanner.md
  assert_claude_view .claude/commands/review-pr.md
  [ -f .agents/agents/security-scanner.md ]
  [ -f .agents/commands/review-pr.md ]
  [ -f .agents/skills/security-scanner/SKILL.md ]
  [ -f .agents/skills/review-pr/SKILL.md ]
  [ ! -e .claude/mcp.json ]
  [ ! -e .codex/.mcp.json ]
  [ ! -e .claude/hooks ]
  [ ! -L .claude/hooks ]
  [ -f .agents/hooks/sync-marketplace.sh ]
  [ -f .agents/hooks/check-harness-consistency.sh ]
  [ ! -e .agents/hooks/pre-tool-use.md ]
  [ -f .codex/hooks.json ]
  cmp -s .agents/hooks/sync-marketplace.sh "$skill_dir/assets/common/hooks/sync-marketplace.sh"
  cmp -s .codex/hooks.json "$skill_dir/assets/codex/hooks.json"
  cmp -s .agents/hooks/check-harness-consistency.sh "$skill_dir/assets/common/hooks/check-harness-consistency.sh"
  [ ! -f .claude/CLAUDE.md ]
  [ ! -d .codex/agents ]
  for rule_file in api-configuration.md frontend-style.md language-consistency.md lint-gate.md lodash.md no-unnecessary-mocks.md security.md testing.md user-facing-feedback.md; do
    grep -Fq -- "- Read and follow \`.agents/rules/$rule_file\`." AGENTS.md
  done
  grep -Fxq '## Centralización recursiva de instrucciones' AGENTS.md
  printf '\n# Canonical shared asset\n' >> .agents/rules/security.md
  grep -Fq '# Canonical shared asset' .claude/rules/security.md
  jq -e '.hooks.SessionStart[0].matcher == "startup|clear|resume"' .codex/hooks.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/sync-marketplace.sh --provider claude)")' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/check-harness-consistency.sh)")' .claude/settings.json >/dev/null
  jq -e '.hooks.SessionStart[0].hooks[0].command == "bash .agents/hooks/sync-marketplace.sh --provider claude"' .claude/settings.json >/dev/null
  jq -e '.hooks.PostToolUse[0].hooks[0].command == "bash .agents/hooks/check-harness-consistency.sh"' .claude/settings.json >/dev/null
  jq -e '.hooks.SessionStart[0].hooks[0].command == "bash .agents/hooks/sync-marketplace.sh --provider codex"' .codex/hooks.json >/dev/null
  [[ "$output" == *"Providers: Claude Code + Codex-compatible shared tree"* ]]
}

@test "sync removes stale Claude symlink views" {
  skip_without_symlinks
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  mkdir -p .claude/rules
  ln -s ../../.agents/rules/removed-rule.md .claude/rules/removed-rule.md

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ ! -e .claude/rules/removed-rule.md ]
  [ ! -L .claude/rules/removed-rule.md ]
  [[ "$output" == *"Removed stale managed assets:"* ]]
}

@test "sync preserves custom Claude settings" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  jq '.customSetting = "preserve-me" | .permissions.allow += ["Bash(custom-project-command)"] | .hooks.PostToolUse[0].hooks += [{"type":"command","command":"bash .agents/hooks/custom-project-hook.sh"}]' .claude/settings.json > "$test_root/settings.json"
  mv "$test_root/settings.json" .claude/settings.json

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  jq -e '.customSetting == "preserve-me"' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(custom-project-command)")' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/sync-marketplace.sh --provider claude)")' .claude/settings.json >/dev/null
  jq -e '.hooks.SessionStart[0].hooks[0].command == "bash .agents/hooks/sync-marketplace.sh --provider claude"' .claude/settings.json >/dev/null
  jq -e '.hooks.PostToolUse[0].hooks | index({"type":"command","command":"bash .agents/hooks/custom-project-hook.sh"})' .claude/settings.json >/dev/null
}

@test "sync preserves custom settings array entries without other custom keys" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  jq '.permissions.allow += ["Bash(custom-project-command)"] | .hooks.PostToolUse[0].hooks += [{"type":"command","command":"bash .agents/hooks/custom-project-hook.sh"}]' .claude/settings.json > "$test_root/settings.json"
  mv "$test_root/settings.json" .claude/settings.json

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  jq -e '.permissions.allow | index("Bash(custom-project-command)")' .claude/settings.json >/dev/null
  jq -e '.hooks.PostToolUse[0].hooks | index({"type":"command","command":"bash .agents/hooks/custom-project-hook.sh"})' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/sync-marketplace.sh --provider claude)")' .claude/settings.json >/dev/null
}

@test "sync preserves custom settings array entries inserted before managed entries" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  jq '
    .permissions.allow = ["Bash(custom-before-managed)"] + .permissions.allow
    | .hooks.PostToolUse[0].hooks = [{"type":"command","command":"bash .agents/hooks/custom-before-managed.sh"}] + .hooks.PostToolUse[0].hooks
  ' .claude/settings.json > "$test_root/settings.json"
  mv "$test_root/settings.json" .claude/settings.json

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  jq -e '.permissions.allow[0] == "Bash(custom-before-managed)"' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/sync-marketplace.sh --provider claude)")' .claude/settings.json >/dev/null
  jq -e '.hooks.PostToolUse[0].hooks[0] == {"type":"command","command":"bash .agents/hooks/custom-before-managed.sh"}' .claude/settings.json >/dev/null
  jq -e '.hooks.PostToolUse[0].hooks | map(select(.type == "command" and .command == "bash .agents/hooks/check-harness-consistency.sh")) | length == 1' .claude/settings.json >/dev/null
}

@test "sync preserves replaced custom settings entries with equal length" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  jq '
    .permissions.allow[0] = "Bash(custom-replaced-permission)"
    | .hooks.PostToolUse[0].hooks[0] = {"type":"command","command":"bash .agents/hooks/custom-replaced-hook.sh"}
  ' .claude/settings.json > "$test_root/settings.json"
  mv "$test_root/settings.json" .claude/settings.json

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  jq -e '.permissions.allow | length == 3' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(custom-replaced-permission)") != null' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/sync-marketplace.sh --provider claude)") != null' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/check-harness-consistency.sh)") != null' .claude/settings.json >/dev/null
  jq -e '.hooks.PostToolUse | length == 2' .claude/settings.json >/dev/null
  jq -e '[.hooks.PostToolUse[].hooks[]] | index({"type":"command","command":"bash .agents/hooks/custom-replaced-hook.sh"}) != null' .claude/settings.json >/dev/null
  jq -e '[.hooks.PostToolUse[].hooks[]] | map(select(.type == "command" and .command == "bash .agents/hooks/check-harness-consistency.sh")) | length == 1' .claude/settings.json >/dev/null
}

@test "autonomous sync merges custom Claude settings before instruction merge" {
  dynamic_skill_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$dynamic_skill_dir"

  run_marketplace_sync "$skill_dir/assets/common/hooks/sync-marketplace.sh" "$dynamic_skill_dir" \

  [ "$status" -eq 0 ]
  [ -f .claude/settings.json ]

  jq '
    .customSetting = "preserve-me"
    | .permissions.allow = ["Bash(custom-before-managed)"] + .permissions.allow
    | .hooks.PostToolUse[0].hooks = [{"type":"command","command":"bash .agents/hooks/custom-project-hook.sh"}] + .hooks.PostToolUse[0].hooks
  ' .claude/settings.json > "$test_root/settings.json"
  mv "$test_root/settings.json" .claude/settings.json

  jq '.newManagedSetting = "new-value"' \
    "$dynamic_skill_dir/assets/common/settings.json" > "$test_root/template.json"
  mv "$test_root/template.json" "$dynamic_skill_dir/assets/common/settings.json"

  run_marketplace_sync ".agents/hooks/sync-marketplace.sh" "$dynamic_skill_dir" \

  [ "$status" -eq 0 ]
  jq -e '.customSetting == "preserve-me"' .claude/settings.json >/dev/null
  jq -e '.newManagedSetting == "new-value"' .claude/settings.json >/dev/null
  jq -e '.permissions.allow[0] == "Bash(custom-before-managed)"' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/sync-marketplace.sh --provider claude)")' .claude/settings.json >/dev/null
  jq -e '.hooks.PostToolUse[0].hooks[0] == {"type":"command","command":"bash .agents/hooks/custom-project-hook.sh"}' .claude/settings.json >/dev/null
  jq -e '.hooks.PostToolUse[0].hooks | map(select(.type == "command" and .command == "bash .agents/hooks/check-harness-consistency.sh")) | length == 1' .claude/settings.json >/dev/null
}

@test "autonomous sync replaces identical and edited Claude copies with managed views" {
  dynamic_skill_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$dynamic_skill_dir"

  run_marketplace_sync "$skill_dir/assets/common/hooks/sync-marketplace.sh" "$dynamic_skill_dir" \

  [ "$status" -eq 0 ]
  rm .claude/rules/security.md
  cp .agents/rules/security.md .claude/rules/security.md

  run_marketplace_sync ".agents/hooks/sync-marketplace.sh" "$dynamic_skill_dir" \

  [ "$status" -eq 0 ]
  assert_claude_view .claude/rules/security.md "../../.agents/rules/security.md"
  [[ "$output" != *".claude/rules/security.md differs from canonical shared asset"* ]]

  rm .claude/rules/security.md
  printf '%s\n' '# Claude-only security override' > .claude/rules/security.md

  run_marketplace_sync ".agents/hooks/sync-marketplace.sh" "$dynamic_skill_dir" \

  [ "$status" -eq 0 ]
  assert_claude_view .claude/rules/security.md "../../.agents/rules/security.md"
  ! grep -Fq '# Claude-only security override' .agents/rules/security.md
  [[ "$output" == *".claude/rules/security.md -> managed view"* ]]
}

@test "autonomous sync normalizes CLAUDE.md under .claude and is idempotent" {
  dynamic_skill_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$dynamic_skill_dir"

  run_marketplace_sync "$skill_dir/assets/common/hooks/sync-marketplace.sh" "$dynamic_skill_dir"
  [ "$status" -eq 0 ]

  cat > .claude/CLAUDE.md <<'EOF'
## Team SDD Kit

This project uses Team SDD Kit.
EOF
  rm -f .claude/AGENTS.md

  run_marketplace_sync ".agents/hooks/sync-marketplace.sh" "$dynamic_skill_dir"

  [ "$status" -eq 0 ]
  [ -f .claude/AGENTS.md ]
  grep -Fxq '## Team SDD Kit' .claude/AGENTS.md
  cmp -s .claude/CLAUDE.md "$dynamic_skill_dir/assets/claude-proxy.md"

  claude_hash_before="$(shasum .claude/CLAUDE.md | cut -d ' ' -f 1)"
  agents_hash_before="$(shasum .claude/AGENTS.md | cut -d ' ' -f 1)"

  run_marketplace_sync ".agents/hooks/sync-marketplace.sh" "$dynamic_skill_dir"

  [ "$status" -eq 0 ]
  [ "$(shasum .claude/CLAUDE.md | cut -d ' ' -f 1)" = "$claude_hash_before" ]
  [ "$(shasum .claude/AGENTS.md | cut -d ' ' -f 1)" = "$agents_hash_before" ]
}

@test "sync hook discovers provider CLAUDE.md from nested cwd" {
  dynamic_skill_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$dynamic_skill_dir"

  run_marketplace_sync "$skill_dir/assets/common/hooks/sync-marketplace.sh" "$dynamic_skill_dir"
  [ "$status" -eq 0 ]

  cat > .claude/CLAUDE.md <<'EOF'
# Nested hook instructions
EOF
  rm -f .claude/AGENTS.md

  run env \
    PATH="$test_root/bin:$PATH" \
    AGENT_READY_SETUP_SKILL_DIR="$dynamic_skill_dir" \
    bash -c 'cd .claude && bash ../.agents/hooks/sync-marketplace.sh --provider claude --stack frontend'

  [ "$status" -eq 0 ]
  [ -f .claude/AGENTS.md ]
  grep -Fxq '# Nested hook instructions' .claude/AGENTS.md
  cmp -s .claude/CLAUDE.md "$dynamic_skill_dir/assets/claude-proxy.md"
}

@test "identical legacy Claude copies become canonical symlinks" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  rm .claude/rules/security.md
  cp .agents/rules/security.md .claude/rules/security.md

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  assert_claude_view .claude/rules/security.md
  [[ "$output" == *"Updated from templates:"* ]]
  [[ "$output" == *".claude/rules/security.md -> managed view"* ]]
}

@test "edited Claude copies of managed rules are replaced with managed views" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  rm .claude/rules/security.md
  printf '%s\n' '# Claude-only security override' > .claude/rules/security.md

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  assert_claude_view .claude/rules/security.md "../../.agents/rules/security.md"
  cmp -s .agents/rules/security.md "$skill_dir/assets/stacks/frontend/rules/security.md"
  [[ "$output" == *".claude/rules/security.md -> managed view"* ]]
}

@test "nested skills receive valid Codex adapters with their directory names" {
  run_bootstrap frontend

  [ "$status" -eq 0 ]
  for skill_name in api-endpoint component-creation karpathy-guidelines logger service; do
    skill_path=".agents/skills/$skill_name/SKILL.md"
    [ -f "$skill_path" ]
    [ "$(sed -n '1p' "$skill_path")" = '---' ]
    grep -Fxq "name: $skill_name" <(sed -n '2p' "$skill_path")
    cmp -s "$skill_path" "$skill_dir/assets/stacks/frontend/skills/$skill_name/SKILL.md"
  done
  for skill_name in logger service; do
    eval_config=".agents/skills/$skill_name/evals/eval-config.json"
    [ -f "$eval_config" ]
    cmp -s "$eval_config" "$skill_dir/assets/stacks/frontend/skills/$skill_name/evals/eval-config.json"
  done
  [ ! -e .agents/skills/evals/SKILL.md ]
  [ -f .agents/skills/karpathy-guidelines/EXAMPLES.md ]
  [ ! -e .agents/skills/SKILL/SKILL.md ]
  [ ! -e .agents/skills/EXAMPLES/SKILL.md ]
}

@test "browser rule is discoverable through both providers for every stack" {
  for provider in claude codex; do
    for stack in frontend go java node; do
      stack_project="$test_root/$provider-$stack-browser"
      mkdir -p "$stack_project"
      git -C "$stack_project" -c init.defaultBranch=main init -q
      cd "$stack_project"

      run_bootstrap "$stack" --provider "$provider"

      [ "$status" -eq 0 ]
      rule_path=".agents/rules/browser-before-user-questions.md"
      [ -f "$rule_path" ]
      cmp -s "$rule_path" "$skill_dir/assets/common/rules/browser-before-user-questions.md"
      assert_claude_view .claude/rules/browser-before-user-questions.md
      cmp -s .claude/rules/browser-before-user-questions.md "$rule_path"
      grep -Fq -- "- Read and follow \`$rule_path\`." AGENTS.md
    done
  done
}

@test "common rules and skill adapters are projected verbatim for every stack" {
  for stack in frontend go java node; do
    stack_project="$test_root/$stack-adapters"
    mkdir -p "$stack_project"
    git -C "$stack_project" -c init.defaultBranch=main init -q
    cd "$stack_project"

    run_bootstrap "$stack"

    [ "$status" -eq 0 ]
    for common_rule in "$skill_dir/assets/common/rules/"*.md; do
      rule_name="${common_rule##*/}"
      cmp -s ".agents/rules/$rule_name" "$common_rule"
      cmp -s ".claude/rules/$rule_name" "$common_rule"
    done
    while IFS= read -r template; do
      relative="${template#"$skill_dir/assets/stacks/$stack/"}"
      case "$relative" in
        skills/*/SKILL.md)
          skill_name="${relative#skills/}"
          skill_name="${skill_name%/SKILL.md}"
          cmp -s ".claude/skills/$skill_name/SKILL.md" "$template"
          ;;
        *)
          skill_name="${relative##*/}"
          skill_name="${skill_name%.md}"
          cmp -s ".agents/$relative" "$template"
          cmp -s ".claude/$relative" "$template"
          ;;
      esac
      cmp -s ".agents/skills/$skill_name/SKILL.md" "$template"
    done < <(find "$skill_dir/assets/stacks/$stack" -type f \( -path '*/skills/*/SKILL.md' -o -path '*/agents/*.md' -o -path '*/commands/*.md' \))
    cd "$project_dir"
  done
}

@test "skill, agent, and command templates declare provider frontmatter" {
  while IFS= read -r template; do
    case "$template" in
      */skills/*/SKILL.md) expected_name="$(basename "$(dirname "$template")")" ;;
      *) expected_name="$(basename "$template" .md)" ;;
    esac
    [ "$(sed -n '1p' "$template")" = '---' ] || { echo "missing frontmatter: $template"; false; }
    frontmatter="$(sed -n '2,/^---$/p' "$template")"
    grep -Fxq "name: $expected_name" <<< "$frontmatter" || { echo "missing name: $template"; false; }
    grep -Eq '^description: .+' <<< "$frontmatter" || { echo "missing description: $template"; false; }
  done < <(find "$skill_dir/assets/stacks" -type f \( -path '*/skills/*/SKILL.md' -o -path '*/agents/*.md' -o -path '*/commands/*.md' \))
}

@test "Claude registers each agent and command once while Codex keeps its adapter" {
  source_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$source_dir"
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF

  run_bootstrap frontend
  [ "$status" -eq 0 ]
  run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"
  [ "$status" -eq 0 ]

  for workflow in agents/a11y-reviewer agents/lint-reviewer agents/perf-analyzer agents/security-scanner agents/test-reviewer commands/review-pr; do
    workflow_name="${workflow#*/}"
    assert_claude_view ".claude/$workflow.md"
    [ -f ".agents/skills/$workflow_name/SKILL.md" ]
    [ ! -e ".claude/skills/$workflow_name" ]
  done
  assert_claude_view .claude/skills/component-creation/SKILL.md
}

@test "sync removes duplicate Claude skill views of agents and commands, even when edited" {
  skip_without_symlinks
  source_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$source_dir"
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  mkdir -p .claude/skills/a11y-reviewer .claude/skills/lint-reviewer
  ln -s ../../../.agents/skills/a11y-reviewer/SKILL.md .claude/skills/a11y-reviewer/SKILL.md
  printf '%s\n' '# Custom lint skill' > .claude/skills/lint-reviewer/SKILL.md

  run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"

  [ "$status" -eq 0 ]
  [ ! -e .claude/skills/a11y-reviewer ]
  [[ "$output" == *"Removed duplicate Claude views:"* ]]
  [ ! -e .claude/skills/lint-reviewer ]
  [[ "$output" == *"  - .claude/skills/lint-reviewer/SKILL.md"* ]]
}

@test "sync links project rules for Claude and prunes views of deleted ones" {
  source_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$source_dir"
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  mkdir -p .agents/rules/area
  printf '%s\n' '# Team conventions' > .agents/rules/team-conventions.md
  printf '%s\n' '# Area rule' > .agents/rules/area/payments.md

  run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"

  [ "$status" -eq 0 ]
  assert_claude_view .claude/rules/team-conventions.md "../../.agents/rules/team-conventions.md"
  assert_claude_view .claude/rules/area/payments.md "../../../.agents/rules/area/payments.md"
  [ -f .agents/rules/team-conventions.md ]

  rm .agents/rules/team-conventions.md
  run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"

  [ "$status" -eq 0 ]
  [ ! -L .claude/rules/team-conventions.md ]
  assert_claude_view .claude/rules/area/payments.md
  assert_claude_view .claude/rules/security.md
}

@test "sync hook replaces placeholder adapter descriptions from older projections" {
  source_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$source_dir"
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  template="$skill_dir/assets/stacks/frontend/skills/karpathy-guidelines/SKILL.md"
  {
    printf '%s\n' '---' 'name: karpathy-guidelines' \
      'description: Provider-neutral reusable workflow for karpathy-guidelines.' '---' ''
    sed '1,/^---$/d' "$template"
  } > .agents/skills/karpathy-guidelines/SKILL.md

  run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"

  [ "$status" -eq 0 ]
  cmp -s .agents/skills/karpathy-guidelines/SKILL.md "$template"
  [[ "$output" == *"↻ .agents/skills/karpathy-guidelines/SKILL.md"* ]]
}

@test "backend stacks project common rules, hooks, and settings for every provider" {
  for stack in go java node; do
    stack_project="$test_root/$stack-project"
    mkdir -p "$stack_project"
    git -C "$stack_project" -c init.defaultBranch=main init -q
    cd "$stack_project"

    run_bootstrap "$stack"

    [ "$status" -eq 0 ]
    cmp -s CLAUDE.md "$skill_dir/assets/claude-proxy.md"
    grep -Fq -- '- Read and follow `.agents/rules/coding-style.md`.' AGENTS.md
    grep -Fq -- '- Read and follow `.agents/rules/security.md`.' AGENTS.md
    grep -Fq -- '- Read and follow `.agents/rules/testing.md`.' AGENTS.md
    for common_rule in established-libraries.md language-consistency.md lint-gate.md patterns-we-do-not-use.md speculative-complexity-approval.md user-actions-first.md verify-changes.md; do
      grep -Fq -- "- Read and follow \`.agents/rules/$common_rule\`." AGENTS.md
      cmp -s ".agents/rules/$common_rule" "$skill_dir/assets/common/rules/$common_rule"
      assert_claude_view ".claude/rules/$common_rule"
    done
    ! grep -Fxq '### Project rules' AGENTS.md
    cmp -s .claude/settings.json "$skill_dir/assets/common/settings.json"
    cmp -s .agents/hooks/sync-marketplace.sh "$skill_dir/assets/common/hooks/sync-marketplace.sh"
    cmp -s .codex/hooks.json "$skill_dir/assets/codex/hooks.json"
    cmp -s .agents/hooks/check-harness-consistency.sh "$skill_dir/assets/common/hooks/check-harness-consistency.sh"
    jq -e '.hooks.SessionStart[0].hooks[0].command == "bash .agents/hooks/sync-marketplace.sh --provider claude"' .claude/settings.json >/dev/null
    jq -e '.hooks.PostToolUse[0].hooks[0].command == "bash .agents/hooks/check-harness-consistency.sh"' .claude/settings.json >/dev/null
    jq -e '.hooks.SessionStart[0].hooks[0].command == "bash .agents/hooks/sync-marketplace.sh --provider codex"' .codex/hooks.json >/dev/null
  done
}

@test "second bootstrap is idempotent and preserves generated files" {
  run_bootstrap node
  [ "$status" -eq 0 ]

  agents_hash_before="$(shasum AGENTS.md | cut -d ' ' -f 1)"
  claude_hash_before="$(shasum CLAUDE.md | cut -d ' ' -f 1)"

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ "$(shasum AGENTS.md | cut -d ' ' -f 1)" = "$agents_hash_before" ]
  [ "$(shasum CLAUDE.md | cut -d ' ' -f 1)" = "$claude_hash_before" ]
  [[ "$output" == *"Already existed (skipped):"* ]]
}

@test "existing CLAUDE instructions migrate to AGENTS and become proxy" {
  cat > CLAUDE.md <<'EOF'
# Existing project instructions

Run the project test command before merging.
EOF

  run_bootstrap go

  [ "$status" -eq 0 ]
  [ "$(cat AGENTS.md)" = $'# Existing project instructions\n\nRun the project test command before merging.' ]
  cmp -s CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  [[ "$output" == *"Normalized instructions:"* ]]
}

@test "proxy CLAUDE leaves existing AGENTS unchanged" {
  cat > AGENTS.md <<'EOF'
# Canonical instructions

Keep changes backwards compatible.
EOF
  printf '%s\n' '@AGENTS.md' > CLAUDE.md

  run_bootstrap java

  [ "$status" -eq 0 ]
  [ "$(cat AGENTS.md)" = $'# Canonical instructions\n\nKeep changes backwards compatible.' ]
  cmp -s CLAUDE.md "$skill_dir/assets/claude-proxy.md"
}

@test "normalized root CLAUDE proxy and existing AGENTS are preserved" {
  cat > AGENTS.md <<'EOF'
# Canonical instructions
EOF
  cp "$skill_dir/assets/claude-proxy.md" CLAUDE.md
  claude_hash_before="$(shasum CLAUDE.md | cut -d ' ' -f 1)"

  run_bootstrap java

  [ "$status" -eq 0 ]
  [ "$(shasum CLAUDE.md | cut -d ' ' -f 1)" = "$claude_hash_before" ]
  [ "$(cat AGENTS.md)" = '# Canonical instructions' ]
}

@test "orphaned normalized root CLAUDE proxy recreates canonical AGENTS" {
  cp "$skill_dir/assets/claude-proxy.md" CLAUDE.md

  run_bootstrap java

  [ "$status" -eq 0 ]
  [ -f AGENTS.md ]
  grep -Fq '# [Project Name]' AGENTS.md
  grep -Fxq '## Centralización recursiva de instrucciones' AGENTS.md
  cmp -s CLAUDE.md "$skill_dir/assets/claude-proxy.md"
}

@test "nested instruction pairs normalize recursively" {
  mkdir -p service packages/api
  cat > service/CLAUDE.md <<'EOF'
# Service instructions

Run service checks before merging.
EOF
  cat > packages/api/AGENTS.md <<'EOF'
# API instructions

Keep API changes backwards compatible.
EOF

  run_bootstrap node

  [ "$status" -eq 0 ]
  grep -Fq '# Service instructions' service/AGENTS.md
  grep -Fq 'Run service checks before merging.' service/AGENTS.md
  cmp -s service/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  cmp -s packages/api/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  grep -Fq '# API instructions' packages/api/AGENTS.md
  grep -Fq 'Keep API changes backwards compatible.' packages/api/AGENTS.md
}

@test "nested legacy CLAUDE proxy upgrades to root template" {
  mkdir -p service
  printf '%s\n' '@AGENTS.md' > service/CLAUDE.md
  printf '%s\n' '# Canonical service instructions' > service/AGENTS.md

  run_bootstrap node

  [ "$status" -eq 0 ]
  cmp -s service/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  grep -Fq '# Canonical service instructions' service/AGENTS.md
}

@test "nested exact CLAUDE proxy creates an empty canonical sibling" {
  mkdir -p service
  cp "$skill_dir/assets/claude-proxy.md" service/CLAUDE.md

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ -f service/AGENTS.md ]
  [ ! -s service/AGENTS.md ]
  cmp -s service/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
}

@test "provider configuration CLAUDE.md gets a sibling AGENTS.md and exact proxy" {
  mkdir -p .claude
  cat > .claude/CLAUDE.md <<'EOF'
## Team SDD Kit

This project uses Team SDD Kit.
EOF

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ -f .claude/AGENTS.md ]
  grep -Fxq '## Team SDD Kit' .claude/AGENTS.md
  grep -Fxq 'This project uses Team SDD Kit.' .claude/AGENTS.md
  cmp -s .claude/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  [[ "$output" == *".claude/CLAUDE.md -> .claude/AGENTS.md"* ]]
}

@test "instruction normalization uses Git root when invoked from nested directory" {
  mkdir -p .claude
  cat > .claude/CLAUDE.md <<'EOF'
# Claude instructions

Run checks from project root.
EOF

  run bash -c "cd .claude && env PATH=\"$test_root/bin:\$PATH\" bash \"$skill_dir/scripts/bootstrap.sh\" --stack node --skill-dir \"$skill_dir\" --provider claude"

  [ "$status" -eq 0 ]
  [ -f .claude/AGENTS.md ]
  grep -Fxq '# Claude instructions' .claude/AGENTS.md
  cmp -s .claude/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
}

@test "case-variant instruction filenames normalize recursively" {
  cat > Claude.md <<'EOF'
# Root instructions

Run root checks before merging.
EOF
  mkdir -p services/api/v1
  cat > services/api/v1/claude.MD <<'EOF'
# API instructions

Run API checks before merging.
EOF

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ "$(find . -maxdepth 1 -type f -name 'Claude.md' -print)" = "" ]
  [ "$(find services/api/v1 -maxdepth 1 -type f -name 'claude.MD' -print)" = "" ]
  [ -f CLAUDE.md ]
  [ -f services/api/v1/CLAUDE.md ]
  grep -Fq '# Root instructions' AGENTS.md
  grep -Fq 'Run root checks before merging.' AGENTS.md
  grep -Fq '# API instructions' services/api/v1/AGENTS.md
  grep -Fq 'Run API checks before merging.' services/api/v1/AGENTS.md
  cmp -s CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  cmp -s services/api/v1/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  [[ "$output" == *"Renamed instruction files:"* ]]
  [[ "$output" == *"Claude.md -> ./CLAUDE.md"* ]]
  [[ "$output" == *"services/api/v1/claude.MD -> services/api/v1/CLAUDE.md"* ]]
}

@test "case-variant rename preserves a concurrent canonical destination" {
  mkdir -p service
  printf '%s\n' '# Original instructions' > service/Claude.md
  printf '%s\n' '# Existing canonical instructions' > service/AGENTS.md
  cat > "$fake_bin/mv" <<'EOF'
#!/bin/bash
/bin/mv "$@"
for argument in "$@"; do
  if [[ "$argument" == *agent-ready-name.* ]]; then
    printf '%s\n' '# Concurrent instructions' > service/CLAUDE.md
    break
  fi
done
EOF
  chmod +x "$fake_bin/mv"

  run env PATH="$test_root/bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" \
    --stack node \
    --skill-dir "$skill_dir" \
    --provider claude

  [ "$status" -eq 0 ]
  [ "$(cat service/CLAUDE.md)" = '# Concurrent instructions' ]
  [[ "$output" == *"destination changed concurrently and was preserved"* ]]
  if [ -n "$(find service -maxdepth 1 -type f -name 'Claude.md' -print)" ]; then
    [ "$(cat service/Claude.md)" = '# Original instructions' ]
  else
    staged_files=(service/.CLAUDE.md.agent-ready-name.*)
    [ -f "${staged_files[0]}" ]
    [ "$(cat "${staged_files[0]}")" = '# Original instructions' ]
  fi
}

@test "ignored case-variant instruction filenames remain untouched" {
  printf '%s\n' 'node_modules/' > .gitignore
  mkdir -p node_modules/example-package
  cat > node_modules/example-package/Claude.md <<'EOF'
# Dependency instructions
EOF

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ -f node_modules/example-package/Claude.md ]
  [ "$(find node_modules/example-package -maxdepth 1 -type f -name 'CLAUDE.md' -print)" = "" ]
  [ ! -e node_modules/example-package/AGENTS.md ]
}

@test "rejects bootstrap outside a Git worktree" {
  non_git_project="$test_root/non-git-project"
  mkdir -p "$non_git_project"
  cd "$non_git_project"

  run bash "$skill_dir/scripts/bootstrap.sh" --stack node --skill-dir "$skill_dir" --provider claude

  [ "$status" -ne 0 ]
  [[ "$output" == *"bootstrap must run inside a Git worktree"* ]]
}

@test "ignored node_modules instructions remain untouched" {
  printf '%s\n' 'node_modules/' > .gitignore
  mkdir -p node_modules/example-package
  printf '%s\n' '# Dependency instructions' > node_modules/example-package/CLAUDE.md

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ ! -e node_modules/example-package/AGENTS.md ]
  [ "$(cat node_modules/example-package/CLAUDE.md)" = '# Dependency instructions' ]
}

@test "gitignored nested instruction pairs remain untouched" {
  mkdir -p generated/api
  printf '%s\n' 'generated/' > .gitignore
  git -c init.defaultBranch=main init -q .
  printf '%s\n' '# Generated instructions' > generated/api/CLAUDE.md

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ ! -e generated/api/AGENTS.md ]
  [ "$(cat generated/api/CLAUDE.md)" = '# Generated instructions' ]
}

@test "tracked instructions under ignored directories remain normalizable" {
  mkdir -p node_modules/tracked-package
  printf '%s\n' 'node_modules/' > .gitignore
  printf '%s\n' '# Tracked instructions' > node_modules/tracked-package/CLAUDE.md
  git add -f node_modules/tracked-package/CLAUDE.md

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ -f node_modules/tracked-package/AGENTS.md ]
  cmp -s node_modules/tracked-package/CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  [ "$(cat node_modules/tracked-package/AGENTS.md)" = '# Tracked instructions' ]
}

@test "provider destinations are created when ignored by Git" {
  printf '%s\n' '.claude/' '.agents/' '.codex/' > .gitignore
  git -c init.defaultBranch=main init -q .

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ -f .claude/settings.json ]
  [ -f .agents/rules/security.md ]
  [ -f .codex/hooks.json ]
}

@test "identical instruction files collapse to canonical AGENTS" {
  cat > AGENTS.md <<'EOF'
# Shared instructions

Run checks before merging.
EOF
  cp AGENTS.md CLAUDE.md

  run_bootstrap java

  [ "$status" -eq 0 ]
  grep -Fq '# Shared instructions' AGENTS.md
  grep -Fq 'Run checks before merging.' AGENTS.md
  cmp -s CLAUDE.md "$skill_dir/assets/claude-proxy.md"
  [[ "$output" == *"Normalized instructions:"* ]]
}

@test "different instruction files report conflict without overwriting" {
  cat > AGENTS.md <<'EOF'
# Canonical instructions
EOF
  cat > CLAUDE.md <<'EOF'
# Claude-only instructions
EOF

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ "$(cat AGENTS.md)" = "# Canonical instructions" ]
  [ "$(cat CLAUDE.md)" = "# Claude-only instructions" ]
  [[ "$output" == *"Instruction conflicts or differences (agent resolution may be required):"* ]]
  [[ "$output" == *"agent must merge compatible instructions before normalizing"* ]]
}

@test "rejects symlinked provider roots before writing assets" {
  skip_without_symlinks
  for provider_root in .claude .agents .codex; do
    outside_root="$test_root/$provider_root"
    mkdir -p "$outside_root"
    ln -s "$outside_root" "$provider_root"

    run_bootstrap frontend

    [ "$status" -ne 0 ]
    [[ "$output" == *"Provider root conflicts (manual resolution required):"* ]]
    [ -z "$(find "$outside_root" -mindepth 1 -print -quit)" ]
    [ -L "$provider_root" ]

    rm "$provider_root"
  done
}

@test "rejects symlinked provider subdirectories before writing assets" {
  skip_without_symlinks
  outside_root="$test_root/outside-rules"
  mkdir -p "$outside_root" .claude
  printf '%s\n' 'sentinel' > "$outside_root/sentinel.txt"
  ln -s "$outside_root" .claude/rules

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ -L .claude/rules ]
  [ "$(cat "$outside_root/sentinel.txt")" = "sentinel" ]
  [ "$(find "$outside_root" -mindepth 1 -maxdepth 1 -type f | wc -l | tr -d ' ')" -eq 1 ]
  [[ "$output" == *"parent directory contains symlink"* ]]
  [[ "$output" == *".claude/rules"* ]]
}

@test "harness hooks inspect Claude and shared-agent paths" {
  fake_bin="$test_root/bin"
  invocation_log="$test_root/claude-invocation.log"
  mkdir -p "$fake_bin"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf 'PWD=%s\nARGS=%s\n' "$PWD" "$*" > "$CLAUDE_INVOCATION_LOG"
EOF
  chmod +x "$fake_bin/claude"
  mkdir -p .claude .agents

  for stack in frontend node java go; do
    hook="$skill_dir/assets/common/hooks/check-harness-consistency.sh"
    for provider_root in .claude .agents; do
      : > "$invocation_log"
      CLAUDE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
        bash "$hook" <<< "{\"tool_input\":{\"file_path\":\"$provider_root/rules/security.md\"}}"
      grep -Fq "PWD=$project_dir/$provider_root" "$invocation_log"
      grep -Fq "ARGS=--print Read all .md files in rules/" "$invocation_log"
      grep -Fq "all SKILL.md files in skills/*/" "$invocation_log"
    done
  done
}

@test "harness hooks keep prompt independent from payload paths" {
  fake_bin="$test_root/bin"
  invocation_log="$test_root/claude-invocation.log"
  mkdir -p "$fake_bin"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf 'PWD=%s\nARGS=%s\n' "$PWD" "$*" > "$CLAUDE_INVOCATION_LOG"
EOF
  chmod +x "$fake_bin/claude"
  mkdir -p .claude .agents

  for stack in frontend node java go; do
    hook="$skill_dir/assets/common/hooks/check-harness-consistency.sh"
    for provider_root in .claude .agents; do
      : > "$invocation_log"
      malicious_file_path="$provider_root/rules/security.md; echo INJECTED"
      CLAUDE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
        bash "$hook" <<< "{\"tool_input\":{\"file_path\":\"$malicious_file_path\"}}"
      grep -Fq "PWD=$project_dir/$provider_root" "$invocation_log"
      grep -Fq 'ARGS=--print Read all .md files in rules/ and all SKILL.md files in skills/*/.' "$invocation_log"
      ! grep -Fq 'INJECTED' "$invocation_log"
    done
  done
}

@test "harness hooks ignore unrelated paths" {
  fake_bin="$test_root/bin"
  invocation_log="$test_root/claude-invocation.log"
  mkdir -p "$fake_bin"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" > "$CLAUDE_INVOCATION_LOG"
EOF
  chmod +x "$fake_bin/claude"

  CLAUDE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
    bash "$skill_dir/assets/common/hooks/check-harness-consistency.sh" \
    <<< '{"tool_input":{"file_path":"README.md"}}'
  [ ! -e "$invocation_log" ]
}


@test "Codex hooks install at discoverable project path on bootstrap and sync" {
  for stack in frontend node java go; do
    rm -f .codex/hooks.json
    run_bootstrap "$stack"
    [ "$status" -eq 0 ]
    cmp -s .codex/hooks.json "$skill_dir/assets/codex/hooks.json"
    rm .codex/hooks.json

    run env PATH="$fake_bin:$PATH" AGENT_READY_SETUP_SKILL_DIR="$skill_dir" \
      bash .agents/hooks/sync-marketplace.sh --provider codex --stack "$stack"
    [ "$status" -eq 0 ]
    cmp -s .codex/hooks.json "$skill_dir/assets/codex/hooks.json"
  done
}

@test "Codex patches trigger harness checks once per affected root" {
  invocation_log="$test_root/claude-invocation.log"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
[[ "$1" != plugin ]] || exit 0
printf '%s\n' "$PWD" >> "$CLAUDE_INVOCATION_LOG"
EOF
  chmod +x "$fake_bin/claude"
  patch='*** Begin Patch
*** Update File: .agents/rules/testing.md
@@
-old
+new
*** Add File: .agents/skills/new/SKILL.md
+content
*** Delete File: .claude/rules/old.md
*** Update File: README.md
@@
-old
+new
*** End Patch'
  payload="$(jq -n --arg command "$patch" '{tool_name:"apply_patch",tool_input:{command:$command}}')"

  for stack in frontend node java go; do
    run_bootstrap "$stack"
    [ "$status" -eq 0 ]
    : > "$invocation_log"
    run env CLAUDE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
      bash .agents/hooks/check-harness-consistency.sh <<< "$payload"
    [ "$status" -eq 0 ]
    [ "$(wc -l < "$invocation_log" | tr -d ' ')" -eq 2 ]
    grep -Fxq "$project_dir/.agents" "$invocation_log"
    grep -Fxq "$project_dir/.claude" "$invocation_log"
  done
}

@test "Codex patches detect move destinations without reading hunk content as paths" {
  run_bootstrap node
  [ "$status" -eq 0 ]
  invocation_log="$test_root/claude-invocation.log"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf '%s\n' "$PWD" >> "$CLAUDE_INVOCATION_LOG"
EOF
  chmod +x "$fake_bin/claude"
  patch='*** Begin Patch
*** Update File: README.md
*** Move to: .agents/rules/moved.md
@@
-old
+new
+*** Add File: .claude/rules/not-a-file.md
*** End Patch'
  payload="$(jq -n --arg command "$patch" '{tool_name:"apply_patch",tool_input:{command:$command}}')"
  run env CLAUDE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
    bash .agents/hooks/check-harness-consistency.sh <<< "$payload"
  [ "$status" -eq 0 ]
  [ "$(cat "$invocation_log")" = "$project_dir/.agents" ]
}

@test "harness hooks ignore malformed payloads and unrelated Codex patches" {
  run_bootstrap go
  [ "$status" -eq 0 ]
  invocation_log="$test_root/claude-invocation.log"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf '%s\n' "$PWD" >> "$CLAUDE_INVOCATION_LOG"
EOF
  chmod +x "$fake_bin/claude"
  for payload in 'invalid json' 'null' '[]' '{"tool_input":null}' \
    '{"tool_input":{"command":42}}' \
    '{"tool_name":"Bash","tool_input":{"command":"*** Add File: .agents/rules/testing.md"}}' \
    '{"tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch"}}'; do
    run env CLAUDE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
      bash .agents/hooks/check-harness-consistency.sh <<< "$payload"
    [ "$status" -eq 0 ]
    [ ! -e "$invocation_log" ]
  done
}

@test "rejects unsupported stack and missing arguments" {
  run bash "$skill_dir/scripts/bootstrap.sh" --stack rust --skill-dir "$skill_dir" --provider claude
  [ "$status" -ne 0 ]
  [[ "$output" == *"Unsupported stack"* ]]

  run bash "$skill_dir/scripts/bootstrap.sh" --stack frontend
  [ "$status" -ne 0 ]
  [[ "$output" == *"--stack and --skill-dir are required"* ]]
}

@test "bootstrap infers Codex from installed skill path without provider override" {
  codex_home="$test_root/codex-home"
  codex_skill_dir="$codex_home/.codex/skills/agent-ready-setup"
  invocation_log="$test_root/codex-marketplace-invocation.log"
  mkdir -p "$codex_skill_dir"
  cp -R "$skill_dir/." "$codex_skill_dir/"
  cat > "$test_root/bin/codex" <<'EOF'
#!/bin/bash
printf '%s %s\n' "${0##*/}" "$*" > "$MARKETPLACE_INVOCATION_LOG"
EOF
  chmod +x "$test_root/bin/codex"

  MARKETPLACE_INVOCATION_LOG="$invocation_log" \
    run env -u AGENT_READY_SETUP_ACTIVE_PROVIDER \
      HOME="$codex_home" PATH="$test_root/bin:$PATH" \
      bash "$codex_skill_dir/scripts/bootstrap.sh" \
      --stack node --skill-dir "$codex_skill_dir"

  [ "$status" -eq 0 ]
  grep -Fxq 'codex plugin marketplace upgrade golfo-marketplace' "$invocation_log"
  [ -f .codex/hooks.json ]
}

@test "bootstrap rejects ambiguous skill path without provider override" {
  run env -u AGENT_READY_SETUP_ACTIVE_PROVIDER PATH="$test_root/bin:$PATH" \
    bash "$skill_dir/scripts/bootstrap.sh" \
    --stack node --skill-dir "$skill_dir"

  [ "$status" -ne 0 ]
  [[ "$output" == *"could not infer provider from skill directory"* ]]
  [ ! -e AGENTS.md ]
}

@test "bootstrap upgrades marketplace before projecting all provider trees" {
  invocation_log="$test_root/marketplace-invocation.log"
  cat > "$test_root/bin/claude" <<'EOF'
#!/bin/bash
if [[ -e AGENTS.md || -e CLAUDE.md || -e .claude || -e .agents || -e .codex ]]; then
  exit 43
fi
printf '%s %s\n' "${0##*/}" "$*" > "$MARKETPLACE_INVOCATION_LOG"
EOF
  chmod +x "$test_root/bin/claude"

  MARKETPLACE_INVOCATION_LOG="$invocation_log" run_bootstrap frontend

  [ "$status" -eq 0 ]
  grep -Fxq 'claude plugin marketplace update golfo-marketplace' "$invocation_log"
  [ -f AGENTS.md ]
  [ -f .agents/hooks/sync-marketplace.sh ]
  [ -f .claude/settings.json ]
  [ -f .codex/hooks.json ]
  [[ "$output" == *"[marketplace-bootstrap] Upgrade del marketplace completado."* ]]
}

@test "bootstrap upgrades marketplace for Codex when provider is explicit" {
  invocation_log="$test_root/marketplace-invocation.log"
  cat > "$test_root/bin/codex" <<'EOF'
#!/bin/bash
printf '%s %s\n' "${0##*/}" "$*" > "$MARKETPLACE_INVOCATION_LOG"
EOF
  chmod +x "$test_root/bin/codex"

  MARKETPLACE_INVOCATION_LOG="$invocation_log" \
    run env PATH="$test_root/bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" \
      --stack node --skill-dir "$skill_dir" --provider codex

  [ "$status" -eq 0 ]
  grep -Fxq 'codex plugin marketplace upgrade golfo-marketplace' "$invocation_log"
  [ -f .claude/settings.json ]
  [ -f .codex/hooks.json ]
}

@test "sync hook reuses a marketplace upgrade from the last hour unless forced" {
  source_dir="$test_root/dynamic-skill"
  cp -R "$skill_dir" "$source_dir"
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  upgrade_log="$test_root/marketplace.log"
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
printf '%s\\n' upgrade >> "$upgrade_log"
EOF
  chmod +x "$fake_bin/claude"
  stamp="$XDG_CACHE_HOME/agent-ready-setup/marketplace-upgrade-claude.stamp"

  run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"
  [ "$status" -eq 0 ]
  [ -f "$stamp" ]
  [ "$(wc -l < "$upgrade_log" | tr -d ' ')" -eq 1 ]

  run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$upgrade_log" | tr -d ' ')" -eq 1 ]
  [[ "$output" == *"El marketplace se actualizó hace menos de 60 minutos; se omite el upgrade."* ]]

  AGENT_READY_SETUP_FORCE_UPGRADE=1 run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$upgrade_log" | tr -d ' ')" -eq 2 ]

  touch -t 202001010000 "$stamp"
  run_marketplace_sync "$source_dir/assets/common/hooks/sync-marketplace.sh" "$source_dir"
  [ "$status" -eq 0 ]
  [ "$(wc -l < "$upgrade_log" | tr -d ' ')" -eq 3 ]
}

@test "failed marketplace upgrade does not open the upgrade window" {
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
exit 7
EOF
  chmod +x "$fake_bin/claude"

  run_marketplace_sync "$skill_dir/assets/common/hooks/sync-marketplace.sh" "$skill_dir"

  [ "$status" -ne 0 ]
  [ ! -e "$XDG_CACHE_HOME/agent-ready-setup/marketplace-upgrade-claude.stamp" ]
}

@test "bootstrap stops before projection when marketplace upgrade fails" {
  cat > "$test_root/bin/claude" <<'EOF'
#!/bin/bash
exit 42
EOF
  chmod +x "$test_root/bin/claude"

  run_bootstrap node

  [ "$status" -ne 0 ]
  [ ! -e AGENTS.md ]
  [ ! -e CLAUDE.md ]
  [ ! -e .claude ]
  [ ! -e .agents ]
  [ ! -e .codex ]
  [[ "$output" == *"falló el upgrade del marketplace"* ]]
  [ -z "$(find .agents -type f -print -quit 2>/dev/null)" ]
}

@test "common sync hook passes provider and infers Codex from canonical path" {
  fake_bin="$test_root/bin"
  invocation_log="$test_root/marketplace-invocation.log"
  hook="$skill_dir/assets/common/hooks/sync-marketplace.sh"
  mkdir -p "$fake_bin"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf '%s %s\n' "${0##*/}" "$*" > "$MARKETPLACE_INVOCATION_LOG"
EOF
  chmod +x "$fake_bin/claude"
  cp -p "$fake_bin/claude" "$fake_bin/codex"

  MARKETPLACE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
    run bash "$hook" --provider claude
  [ "$status" -eq 0 ]
  grep -Fxq 'claude plugin marketplace update golfo-marketplace' "$invocation_log"

  MARKETPLACE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
    run bash "$hook" -p codex
  [ "$status" -eq 0 ]
  grep -Fxq 'codex plugin marketplace upgrade golfo-marketplace' "$invocation_log"

  mkdir -p .agents/hooks
  cp "$hook" .agents/hooks/sync-marketplace.sh

  MARKETPLACE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
    run bash .agents/hooks/sync-marketplace.sh
  [ "$status" -eq 0 ]
  grep -Fxq 'codex plugin marketplace upgrade golfo-marketplace' "$invocation_log"

  run bash "$hook" --provider unsupported
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported marketplace provider"* ]]

  run env -u AGENT_READY_SETUP_SKILL_DIR \
    MARKETPLACE_INVOCATION_LOG="$invocation_log" PATH="$fake_bin:$PATH" \
    bash "$hook" --provider claude
  [ "$status" -eq 0 ]
  [[ "$output" == *"could not detect project stack"* ]]
}

@test "sync hook rejects removed phase flags" {
  for removed_flag in --sync --update --sync-instructions --merge-instructions --yes; do
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude "$removed_flag"

    [ "$status" -ne 0 ]
    [[ "$output" == *"unsupported marketplace sync argument: $removed_flag"* ]]
  done
}

@test "sync hook rejects invalid reexecution guards" {
  for guard in AGENT_READY_SETUP_MARKETPLACE_UPGRADED AGENT_READY_SETUP_SYNC_LOCK_HELD; do
    run env "$guard=invalid" PATH="$test_root/bin:$PATH" \
      bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" --provider claude

    [ "$status" -ne 0 ]
    [[ "$output" == *"$guard must be 0 or 1"* ]]
  done
}

@test "bootstrap shows diffs and updates changed managed assets without prompting" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  printf '%s\n' '# Local change' >> .agents/rules/security.md

  run_bootstrap frontend < /dev/null

  [ "$status" -eq 0 ]
  cmp -s .agents/rules/security.md "$skill_dir/assets/stacks/frontend/rules/security.md"
  [[ "$output" == *"Diff for .agents/rules/security.md"* ]]
  [[ "$output" != *"Pending confirmation"* ]]
  [[ "$output" != *"Replace .agents/rules/security.md with the template?"* ]]
}

@test "bootstrap updates managed assets and preserves root instructions" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  printf '%s\n' '# Local change' >> .agents/rules/security.md
  printf '%s\n' '# Project instructions' > AGENTS.md
  cp "$skill_dir/assets/claude-proxy.md" CLAUDE.md
  root_hash_before="$(shasum AGENTS.md CLAUDE.md | shasum | cut -d ' ' -f 1)"

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  cmp -s .agents/rules/security.md "$skill_dir/assets/stacks/frontend/rules/security.md"
  [ "$(shasum AGENTS.md CLAUDE.md | shasum | cut -d ' ' -f 1)" = "$root_hash_before" ]
  [[ "$output" == *"Updated from templates:"* ]]
}

@test "sync updates managed provider assets" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  [ ! -e .claude/hooks ]

  source_dir="$test_root/updated-agent-ready"
  cp -R "$skill_dir"/. "$source_dir"/
  jq '.hooks.SessionStart[0].matcher = "changed"' \
    "$source_dir/assets/common/settings.json" > "$test_root/settings.json"
  mv "$test_root/settings.json" "$source_dir/assets/common/settings.json"
  printf '%s\n' '# updated common hook' >> "$source_dir/assets/common/hooks/sync-marketplace.sh"
  jq '.hooks.SessionStart[0].hooks[0].command = "bash .agents/hooks/updated-sync.sh"' \
    "$source_dir/assets/codex/hooks.json" > "$test_root/hooks.json"
  mv "$test_root/hooks.json" "$source_dir/assets/codex/hooks.json"

  run env \
    AGENT_READY_SETUP_SKILL_DIR="$source_dir" \
    PATH="$test_root/bin:$PATH" \
    bash "$source_dir/scripts/bootstrap.sh" \
      --stack frontend \
      --skill-dir "$source_dir" \
      --provider claude
  [ "$status" -eq 0 ]
  cmp -s .agents/hooks/sync-marketplace.sh "$source_dir/assets/common/hooks/sync-marketplace.sh"
  jq -en --slurpfile actual .claude/settings.json \
    --slurpfile expected "$source_dir/assets/common/settings.json" \
    '$actual[0] == $expected[0]' >/dev/null
  jq -e '[.hooks.SessionStart[].hooks[].command] | index("bash .agents/hooks/updated-sync.sh") != null' .codex/hooks.json >/dev/null
}

@test "bootstrap detects managed destination changes before atomic rename" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  printf '%s\n' '# Local change' >> .agents/rules/security.md
  fake_bin="$test_root/bin"
  mkdir -p "$fake_bin"
  cat > "$fake_bin/cp" <<'EOF'
#!/bin/bash
/bin/cp "$@"
for argument in "$@"; do
  if [[ "$argument" == *agent-ready-sync.* ]]; then
    printf '%s\n' '# Newer destination change' > .agents/rules/security.md
    break
  fi
done
EOF
  chmod +x "$fake_bin/cp"

  run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" \
    --stack frontend --skill-dir "$skill_dir" --provider claude

  [ "$status" -eq 0 ]
  [ "$(cat .agents/rules/security.md)" = '# Newer destination change' ]
  [[ "$output" == *".agents/rules/security.md changed during synchronization; neither was changed"* ]]
}

@test "bootstrap rejects removed sync and confirmation flags" {
  for removed_flag in --sync --update --yes; do
    run bash "$skill_dir/scripts/bootstrap.sh" --stack node --skill-dir "$skill_dir" --provider claude "$removed_flag"

    [ "$status" -ne 0 ]
    [[ "$output" == *"Unknown argument: $removed_flag"* ]]
  done
}

@test "symlinked managed assets are replaced without touching their target" {
  skip_without_symlinks
  outside_file="$test_root/outside-security.md"
  printf '%s\n' '# Outside asset' > "$outside_file"
  run_bootstrap node
  [ "$status" -eq 0 ]

  rm .agents/rules/security.md
  ln -s "$outside_file" .agents/rules/security.md

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ ! -L .agents/rules/security.md ]
  cmp -s .agents/rules/security.md "$skill_dir/assets/stacks/node/rules/security.md"
  [ "$(cat "$outside_file")" = '# Outside asset' ]
  [[ "$output" == *".agents/rules/security.md (symlink replaced with template)"* ]]
}

@test "a symlink to a directory at a managed path cannot redirect the write" {
  skip_without_symlinks
  outside_directory="$test_root/outside-directory"
  mkdir -p "$outside_directory"
  run_bootstrap node
  [ "$status" -eq 0 ]

  rm .agents/rules/security.md
  ln -s "$outside_directory" .agents/rules/security.md

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ -f .agents/rules/security.md ]
  [ ! -L .agents/rules/security.md ]
  [ -z "$(ls -A "$outside_directory")" ]
}

@test "a directory at a managed path is preserved and reported" {
  run_bootstrap node
  [ "$status" -eq 0 ]

  rm .agents/rules/security.md
  mkdir .agents/rules/security.md

  run_bootstrap node

  [ "$status" -eq 0 ]
  [ -d .agents/rules/security.md ]
  [[ "$output" == *".agents/rules/security.md is not a regular file"* ]]
}

@test "bootstrap re-resolves replaced versioned marketplace cache after upgrade" {
  fake_bin="$test_root/bin"
  cache_root="$test_root/.claude/plugins/cache/golfo-marketplace/golfo-kit"
  old_source="$cache_root/1.0.0/skills/agent-ready-setup"
  updated_source="$cache_root/2.0.0/skills/agent-ready-setup"
  mkdir -p "$old_source" "$updated_source"
  cp -R "$skill_dir"/. "$old_source"/
  cp -R "$skill_dir"/. "$updated_source"/
  printf '%s\n' '# Updated marketplace template' >> "$updated_source/assets/stacks/node/rules/security.md"
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
rm -rf "$old_source"
EOF
  chmod +x "$fake_bin/claude"

  run env HOME="$test_root" PATH="$fake_bin:$PATH" bash "$old_source/scripts/bootstrap.sh" \
    --stack node \
    --skill-dir "$old_source" \
    --provider claude

  [ "$status" -eq 0 ]
  [ ! -e "$old_source" ]
  grep -Fq '# Updated marketplace template' .agents/rules/security.md
}

@test "bootstrap ignores higher versions from another plugin cache" {
  cache_root="$test_root/.claude/plugins/cache/golfo-marketplace"
  target_source="$cache_root/golfo-kit/1.9.0/skills/agent-ready-setup"
  unrelated_source="$cache_root/other-plugin/99.0.0/skills/agent-ready-setup"
  mkdir -p "$target_source" "$unrelated_source"
  cp -R "$skill_dir"/. "$target_source"/
  cp -R "$skill_dir"/. "$unrelated_source"/
  printf '%s\n' '# golfo-kit template' > "$target_source/assets/stacks/node/rules/security.md"
  printf '%s\n' '# unrelated template' > "$unrelated_source/assets/stacks/node/rules/security.md"
  cat > "$target_source/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  chmod +x "$target_source/scripts/merge-instructions.sh"

  run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
    bash "$target_source/scripts/bootstrap.sh" \
      --stack node \
      --skill-dir "$target_source" \
      --provider claude

  [ "$status" -eq 0 ]
  grep -Fxq '# golfo-kit template' .agents/rules/security.md
  ! grep -Fxq '# unrelated template' .agents/rules/security.md
}

@test "resolvers select highest semantic cache version for Claude and Codex" {
  for provider in claude codex; do
    cache_root="$test_root/.$provider/plugins/cache/golfo-marketplace/golfo-kit"
    old_source="$cache_root/1.9.0/skills/agent-ready-setup"
    new_source="$cache_root/1.10.2/skills/agent-ready-setup"
    mkdir -p "$old_source" "$new_source"
    cp -R "$skill_dir"/. "$old_source"/
    cp -R "$skill_dir"/. "$new_source"/
    printf '%s\n' "# old $provider template" > "$old_source/assets/stacks/node/rules/security.md"
    printf '%s\n' "# newest $provider template" > "$new_source/assets/stacks/node/rules/security.md"
    cat > "$new_source/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
    chmod +x "$new_source/scripts/merge-instructions.sh"

    rm -rf .agents .claude .codex AGENTS.md CLAUDE.md
    mkdir -p .agents/rules
    printf '%s\n' "# existing $provider rule" > .agents/rules/security.md

    run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
      bash "$old_source/scripts/bootstrap.sh" \
        --stack node \
        --skill-dir "$old_source" \
        --provider "$provider"

    [ "$status" -eq 0 ]
    grep -Fxq "# newest $provider template" .agents/rules/security.md

    rm -rf .agents .claude .codex AGENTS.md CLAUDE.md
    mkdir -p .agents/rules
    printf '%s\n' "# existing hook $provider rule" > .agents/rules/security.md

    run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
      bash "$old_source/assets/common/hooks/sync-marketplace.sh" \
        --provider "$provider" \
        --stack node

    [ "$status" -eq 0 ]
    grep -Fxq "# newest $provider template" .agents/rules/security.md
  done
}

@test "sync hook prefers newest semantic cache over active old source" {
  for provider in claude codex; do
    provider_root="$test_root/.$provider"
    cache_root="$provider_root/plugins/cache/golfo-marketplace/golfo-kit"
    old_source="$cache_root/1.9.0/skills/agent-ready-setup"
    new_source="$cache_root/1.10.2/skills/agent-ready-setup"
    mkdir -p "$old_source" "$new_source"
    cp -R "$skill_dir"/. "$old_source"/
    cp -R "$skill_dir"/. "$new_source"/
    printf '%s\n' "# old $provider template" > "$old_source/assets/stacks/node/rules/security.md"
    printf '%s\n' "# newest $provider template" > "$new_source/assets/stacks/node/rules/security.md"
    cat > "$new_source/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
    chmod +x "$new_source/scripts/merge-instructions.sh"

    rm -rf .agents .claude .codex AGENTS.md CLAUDE.md
    mkdir -p .agents/rules
    printf '%s\n' "# existing $provider rule" > .agents/rules/security.md

    run env \
      HOME="$test_root" \
      PATH="$test_root/bin:$PATH" \
      CLAUDE_PLUGIN_ROOT="$old_source" \
      bash "$old_source/assets/common/hooks/sync-marketplace.sh" \
        --provider "$provider" \
        --stack node

    [ "$status" -eq 0 ]
    grep -Fxq "# newest $provider template" .agents/rules/security.md
    [[ "$output" == *"[marketplace-sync] Using agent-ready-setup cache version 1.10.2."* ]]
  done
}

create_marketplace_snapshot() {
  local snapshot_root="$1"
  local version="$2"
  local template="$3"
  local plugin_root="$snapshot_root/plugins/golfo-kit"
  local snapshot_skill="$plugin_root/skills/agent-ready-setup"

  mkdir -p "$snapshot_skill" "$plugin_root/.claude-plugin" "$plugin_root/.codex-plugin"
  cp -R "$skill_dir"/. "$snapshot_skill"/
  printf '{\n  "name": "golfo-kit",\n  "version": "%s"\n}\n' "$version" \
    | tee "$plugin_root/.claude-plugin/plugin.json" > "$plugin_root/.codex-plugin/plugin.json"
  printf '%s\n' "$template" > "$snapshot_skill/assets/stacks/node/rules/security.md"
  cat > "$snapshot_skill/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  chmod +x "$snapshot_skill/scripts/merge-instructions.sh"
}

create_cache_source() {
  local provider_root="$1"
  local version="$2"
  local template="$3"
  local cache_source="$provider_root/plugins/cache/golfo-marketplace/golfo-kit/$version/skills/agent-ready-setup"

  mkdir -p "$cache_source"
  cp -R "$skill_dir"/. "$cache_source"/
  printf '%s\n' "$template" > "$cache_source/assets/stacks/node/rules/security.md"
  cat > "$cache_source/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  chmod +x "$cache_source/scripts/merge-instructions.sh"
  printf '%s\n' "$cache_source"
}

@test "sync hook projects upgraded marketplace snapshot before plugin cache update" {
  claude_snapshot="$test_root/claude-marketplace"
  codex_snapshot="$test_root/.codex/.tmp/marketplaces/golfo-marketplace"
  mkdir -p "$test_root/.claude/plugins"
  printf '{"golfo-marketplace": {"installLocation": "%s"}}\n' "$claude_snapshot" \
    > "$test_root/.claude/plugins/known_marketplaces.json"
  create_marketplace_snapshot "$claude_snapshot" "2.0.0" "# claude snapshot template"
  create_marketplace_snapshot "$codex_snapshot" "2.0.0" "# codex snapshot template"

  for provider in claude codex; do
    old_source="$(create_cache_source "$test_root/.$provider" "1.9.0" "# stale $provider cache template")"
    rm -rf .agents .claude .codex AGENTS.md CLAUDE.md

    run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
      bash "$old_source/assets/common/hooks/sync-marketplace.sh" \
        --provider "$provider" \
        --stack node

    [ "$status" -eq 0 ]
    grep -Fxq "# $provider snapshot template" .agents/rules/security.md
    [[ "$output" == *"[marketplace-sync] Using agent-ready-setup marketplace snapshot version 2.0.0."* ]]
  done
}

@test "sync hook reads Codex local marketplace source from config" {
  local_snapshot="$test_root/local-marketplace"
  mkdir -p "$test_root/.codex"
  cat > "$test_root/.codex/config.toml" <<EOF
[marketplaces.other-marketplace]
source_type = "local"
source = "$test_root/other"

[marketplaces.golfo-marketplace]
source_type = "local"
source = "$local_snapshot"
EOF
  create_marketplace_snapshot "$local_snapshot" "3.0.0" "# local snapshot template"
  old_source="$(create_cache_source "$test_root/.codex" "1.0.0" "# stale cache template")"

  run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
    bash "$old_source/assets/common/hooks/sync-marketplace.sh" \
      --provider codex \
      --stack node

  [ "$status" -eq 0 ]
  grep -Fxq '# local snapshot template' .agents/rules/security.md
}

# Codex rejects `marketplace upgrade` for local sources, so the fake fails the
# run if the scripts still call it for one.
write_codex_marketplace_config() {
  local source_type="$1"
  local source_line="$2"

  mkdir -p "$test_root/.codex"
  cat > "$test_root/.codex/config.toml" <<CONFIG
[marketplaces.golfo-marketplace]
source_type = "$source_type"
$source_line
CONFIG
}

write_recording_codex() {
  cat > "$test_root/bin/codex" <<'FAKE'
#!/bin/bash
printf '%s %s\n' "${0##*/}" "$*" >> "$MARKETPLACE_INVOCATION_LOG"
if [[ "$*" == "plugin marketplace upgrade golfo-marketplace" && "$FAKE_CODEX_MARKETPLACE_TYPE" == local ]]; then
  echo "Error: marketplace \`golfo-marketplace\` is not configured as a Git marketplace" >&2
  exit 1
fi
FAKE
  chmod +x "$test_root/bin/codex"
}

@test "bootstrap skips Codex upgrade for a local marketplace and projects its source" {
  invocation_log="$test_root/marketplace-invocation.log"
  local_snapshot="$test_root/local-marketplace"
  write_codex_marketplace_config local "source = \"$local_snapshot\""
  create_marketplace_snapshot "$local_snapshot" "3.0.0" "# local snapshot template"
  old_source="$(create_cache_source "$test_root/.codex" "1.0.0" "# stale cache template")"
  write_recording_codex

  MARKETPLACE_INVOCATION_LOG="$invocation_log" FAKE_CODEX_MARKETPLACE_TYPE=local \
    run env -u AGENT_READY_SETUP_SKILL_DIR HOME="$test_root" PATH="$test_root/bin:$PATH" \
      bash "$old_source/scripts/bootstrap.sh" \
        --stack node --skill-dir "$old_source" --provider codex

  [ "$status" -eq 0 ]
  [ ! -e "$invocation_log" ]
  [[ "$output" == *"[marketplace-bootstrap] golfo-marketplace es un marketplace Codex local; se omite el upgrade"* ]]
  grep -Fxq '# local snapshot template' .agents/rules/security.md
}

@test "bootstrap upgrades a Codex Git marketplace" {
  invocation_log="$test_root/marketplace-invocation.log"
  write_codex_marketplace_config git 'source = "https://example.invalid/golfo-marketplace.git"'
  write_recording_codex

  MARKETPLACE_INVOCATION_LOG="$invocation_log" FAKE_CODEX_MARKETPLACE_TYPE=git \
    run env HOME="$test_root" PATH="$test_root/bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" \
      --stack node --skill-dir "$skill_dir" --provider codex

  [ "$status" -eq 0 ]
  grep -Fxq 'codex plugin marketplace upgrade golfo-marketplace' "$invocation_log"
  [[ "$output" == *"[marketplace-bootstrap] Upgrade del marketplace completado."* ]]
}

@test "sync hook skips Codex upgrade for a local marketplace with a literal source" {
  invocation_log="$test_root/marketplace-invocation.log"
  local_snapshot="$test_root/local-marketplace"
  write_codex_marketplace_config local "source = '$local_snapshot'"
  create_marketplace_snapshot "$local_snapshot" "3.0.0" "# local snapshot template"
  old_source="$(create_cache_source "$test_root/.codex" "1.0.0" "# stale cache template")"
  write_recording_codex

  MARKETPLACE_INVOCATION_LOG="$invocation_log" FAKE_CODEX_MARKETPLACE_TYPE=local \
    run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
      bash "$old_source/assets/common/hooks/sync-marketplace.sh" \
        --provider codex \
        --stack node

  [ "$status" -eq 0 ]
  [ ! -e "$invocation_log" ]
  [[ "$output" == *"[marketplace-sync] golfo-marketplace es un marketplace Codex local; se omite el upgrade"* ]]
  grep -Fxq '# local snapshot template' .agents/rules/security.md
}

# CODEX_HOME outside $HOME/.codex is the home Codex uses; a local marketplace
# configured there must skip the Git-only upgrade.
@test "sync hook honors CODEX_HOME for a local marketplace" {
  invocation_log="$test_root/marketplace-invocation.log"
  custom_codex_home="$test_root/custom-codex-home"
  local_snapshot="$test_root/local-marketplace"
  mkdir -p "$custom_codex_home"
  cat > "$custom_codex_home/config.toml" <<CONFIG
[marketplaces.golfo-marketplace]
source_type = "local"
source = "$local_snapshot"
CONFIG
  create_marketplace_snapshot "$local_snapshot" "3.0.0" "# local snapshot template"
  old_source="$(create_cache_source "$custom_codex_home" "1.0.0" "# stale cache template")"
  write_recording_codex

  MARKETPLACE_INVOCATION_LOG="$invocation_log" FAKE_CODEX_MARKETPLACE_TYPE=local     run env HOME="$test_root" CODEX_HOME="$custom_codex_home" PATH="$test_root/bin:$PATH"       bash "$old_source/assets/common/hooks/sync-marketplace.sh"         --provider codex         --stack node

  [ "$status" -eq 0 ]
  [ ! -e "$invocation_log" ]
  [[ "$output" == *"[marketplace-sync] golfo-marketplace es un marketplace Codex local; se omite el upgrade"* ]]
  grep -Fxq '# local snapshot template' .agents/rules/security.md
}

@test "bootstrap honors CODEX_HOME for a local marketplace" {
  invocation_log="$test_root/marketplace-invocation.log"
  custom_codex_home="$test_root/custom-codex-home"
  local_snapshot="$test_root/local-marketplace"
  mkdir -p "$custom_codex_home"
  cat > "$custom_codex_home/config.toml" <<CONFIG
[marketplaces.golfo-marketplace]
source_type = "local"
source = "$local_snapshot"
CONFIG
  create_marketplace_snapshot "$local_snapshot" "3.0.0" "# local snapshot template"
  old_source="$(create_cache_source "$custom_codex_home" "1.0.0" "# stale cache template")"
  write_recording_codex

  MARKETPLACE_INVOCATION_LOG="$invocation_log" FAKE_CODEX_MARKETPLACE_TYPE=local     run env -u AGENT_READY_SETUP_SKILL_DIR HOME="$test_root" CODEX_HOME="$custom_codex_home"       PATH="$test_root/bin:$PATH"       bash "$old_source/scripts/bootstrap.sh"         --stack node --skill-dir "$old_source"

  [ "$status" -eq 0 ]
  [ ! -e "$invocation_log" ]
  [[ "$output" == *"[marketplace-bootstrap] golfo-marketplace es un marketplace Codex local; se omite el upgrade"* ]]
  grep -Fxq '# local snapshot template' .agents/rules/security.md
}

@test "sync hook upgrades a Codex Git marketplace" {
  invocation_log="$test_root/marketplace-invocation.log"
  write_codex_marketplace_config git 'source = "https://example.invalid/golfo-marketplace.git"'
  old_source="$(create_cache_source "$test_root/.codex" "1.0.0" "# cache template")"
  write_recording_codex

  MARKETPLACE_INVOCATION_LOG="$invocation_log" FAKE_CODEX_MARKETPLACE_TYPE=git \
    run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
      bash "$old_source/assets/common/hooks/sync-marketplace.sh" \
        --provider codex \
        --stack node

  [ "$status" -eq 0 ]
  grep -Fxq 'codex plugin marketplace upgrade golfo-marketplace' "$invocation_log"
  [[ "$output" == *"[marketplace-sync] Upgrade del marketplace completado."* ]]
}

@test "sync hook keeps newer plugin cache over older marketplace snapshot" {
  create_marketplace_snapshot "$test_root/.claude/plugins/marketplaces/golfo-marketplace" \
    "1.9.0" "# older snapshot template"
  new_source="$(create_cache_source "$test_root/.claude" "1.10.2" "# newer cache template")"

  run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
    bash "$new_source/assets/common/hooks/sync-marketplace.sh" \
      --provider claude \
      --stack node

  [ "$status" -eq 0 ]
  grep -Fxq '# newer cache template' .agents/rules/security.md
  [[ "$output" == *"[marketplace-sync] Using agent-ready-setup cache version 1.10.2."* ]]
}

@test "bootstrap projects upgraded marketplace snapshot before plugin cache update" {
  for provider in claude codex; do
    if [[ "$provider" == "claude" ]]; then
      snapshot_root="$test_root/.claude/plugins/marketplaces/golfo-marketplace"
    else
      snapshot_root="$test_root/.codex/.tmp/marketplaces/golfo-marketplace"
    fi
    create_marketplace_snapshot "$snapshot_root" "2.0.0" "# $provider snapshot template"
    old_source="$(create_cache_source "$test_root/.$provider" "1.9.0" "# stale $provider cache template")"
    rm -rf .agents .claude .codex AGENTS.md CLAUDE.md

    run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
      bash "$old_source/scripts/bootstrap.sh" \
        --stack node \
        --skill-dir "$old_source" \
        --provider "$provider"

    [ "$status" -eq 0 ]
    grep -Fxq "# $provider snapshot template" .agents/rules/security.md
    [[ "$output" == *"[marketplace-bootstrap] Using agent-ready-setup marketplace snapshot version 2.0.0."* ]]
    [[ "$output" == *"Resolved agent-ready-setup source: $snapshot_root/plugins/golfo-kit/skills/agent-ready-setup"* ]]
  done
}

@test "bootstrap keeps newer plugin cache over older marketplace snapshot" {
  create_marketplace_snapshot "$test_root/.claude/plugins/marketplaces/golfo-marketplace" \
    "1.9.0" "# older snapshot template"
  new_source="$(create_cache_source "$test_root/.claude" "1.10.2" "# newer cache template")"

  run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
    bash "$new_source/scripts/bootstrap.sh" \
      --stack node \
      --skill-dir "$new_source" \
      --provider claude

  [ "$status" -eq 0 ]
  grep -Fxq '# newer cache template' .agents/rules/security.md
  [[ "$output" == *"Using agent-ready-setup cache version 1.10.2."* ]]
  [[ "$output" == *"Resolved agent-ready-setup source: $new_source"* ]]
}

@test "bootstrap reports an explicit source outside the cache for local development" {
  create_marketplace_snapshot "$test_root/.claude/plugins/marketplaces/golfo-marketplace" \
    "9.0.0" "# snapshot template"

  run env -u AGENT_READY_SETUP_SKILL_DIR -u CLAUDE_PLUGIN_ROOT HOME="$test_root" PATH="$test_root/bin:$PATH" \
    bash "$skill_dir/scripts/bootstrap.sh" \
      --stack node \
      --skill-dir "$skill_dir" \
      --provider claude

  [ "$status" -eq 0 ]
  [[ "$output" == *"Resolved agent-ready-setup source: $skill_dir"* ]]
  cmp -s "$skill_dir/assets/stacks/node/rules/security.md" .agents/rules/security.md
}

@test "bootstrap keeps requested newest cache version instead of downgrading" {
  cache_root="$test_root/.claude/plugins/cache/golfo-marketplace/golfo-kit"
  old_source="$cache_root/1.9.0/skills/agent-ready-setup"
  new_source="$cache_root/1.10.2/skills/agent-ready-setup"
  mkdir -p "$old_source" "$new_source"
  cp -R "$skill_dir"/. "$old_source"/
  cp -R "$skill_dir"/. "$new_source"/
  printf '%s\n' '# old template' > "$old_source/assets/stacks/node/rules/security.md"
  printf '%s\n' '# newest template' > "$new_source/assets/stacks/node/rules/security.md"

  run env HOME="$test_root" PATH="$test_root/bin:$PATH" \
    bash "$new_source/scripts/bootstrap.sh" \
      --stack node \
      --skill-dir "$new_source" \
      --provider claude

  [ "$status" -eq 0 ]
  grep -Fxq '# newest template' .agents/rules/security.md
  [[ "$output" == *"Using agent-ready-setup cache version 1.10.2."* ]]
  [[ "$output" != *"cache version 1.9.0"* ]]
}

@test "sync hook refreshes missing shared helper before projecting assets" {
  cache_root="$test_root/.claude/plugins/cache/golfo-marketplace/golfo-kit"
  source_dir="$cache_root/1.0.0/skills/agent-ready-setup"
  upgrade_log="$test_root/marketplace.log"
  mkdir -p "$(dirname "$source_dir")"
  cp -R "$skill_dir" "$source_dir"
  rm "$source_dir/scripts/asset-sync-common.sh"
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  chmod +x "$source_dir/scripts/merge-instructions.sh"
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
printf '%s\\n' "\$*" >> "$upgrade_log"
if [[ "\$(wc -l < "$upgrade_log")" -eq 2 ]]; then
  cp "$skill_dir/scripts/asset-sync-common.sh" "$source_dir/scripts/asset-sync-common.sh"
fi
EOF
  chmod +x "$fake_bin/claude"

  run env HOME="$test_root" PATH="$fake_bin:$PATH" \
    bash "$source_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack node

  [ "$status" -eq 0 ]
  [ "$(wc -l < "$upgrade_log")" -eq 2 ]
  [ -f "$source_dir/scripts/asset-sync-common.sh" ]
  cmp -s .agents/hooks/sync-marketplace.sh \
    "$source_dir/assets/common/hooks/sync-marketplace.sh"
  [[ "$output" == *"Falta el helper compartido de sincronización; refrescando"* ]]
}

@test "sync hook preserves local hook when helper remains unavailable after refresh" {
  cache_root="$test_root/.claude/plugins/cache/golfo-marketplace/golfo-kit"
  source_dir="$cache_root/1.0.0/skills/agent-ready-setup"
  upgrade_log="$test_root/marketplace.log"
  mkdir -p "$(dirname "$source_dir")" .agents/hooks
  cp -R "$skill_dir" "$source_dir"
  rm "$source_dir/scripts/asset-sync-common.sh"
  printf '%s\n' '# local hook' > .agents/hooks/sync-marketplace.sh
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
exit 0
EOF
  chmod +x "$source_dir/scripts/merge-instructions.sh"
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
printf '%s\\n' "\$*" >> "$upgrade_log"
exit 0
EOF
  chmod +x "$fake_bin/claude"

  run env HOME="$test_root" PATH="$fake_bin:$PATH" \
    bash "$source_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack node

  [ "$status" -eq 0 ]
  [ "$(wc -l < "$upgrade_log")" -eq 2 ]
  grep -Fxq '# local hook' .agents/hooks/sync-marketplace.sh
  [[ "$output" == *"no está disponible después del refresh del marketplace; se omite la proyección local."* ]]
}

@test "sync hook preserves custom Claude array entries with equal length" {
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  jq '.permissions.allow[0] = "Bash(custom-command)"' .claude/settings.json > "$test_root/settings.json"
  mv "$test_root/settings.json" .claude/settings.json

  cat > "$test_root/bin/claude" <<'EOF'
#!/bin/bash
awk '/^<!-- BEGIN AGENT-READY MANAGED -->$/ { print "<!-- AGENT-READY MANAGED BLOCK -->"; skip = 1; next }
  /^<!-- END AGENT-READY MANAGED -->$/ { skip = 0; next }
  !skip' AGENTS.md |
  jq -Rs '{project_content:., removed:[], inconsistencies:[], reason:"No changes"}'
EOF
  chmod +x "$test_root/bin/claude"

  AGENT_READY_SETUP_SKILL_DIR="$skill_dir" PATH="$test_root/bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack frontend

  [ "$status" -eq 0 ]
  jq -e '.permissions.allow | length == 3' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(custom-command)") != null' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/sync-marketplace.sh --provider claude)") != null' .claude/settings.json >/dev/null
  jq -e '.permissions.allow | index("Bash(.agents/hooks/check-harness-consistency.sh)") != null' .claude/settings.json >/dev/null
  [[ "$output" == *"Local backups directory:"* ]]
  backup_files=("$test_root"/tmp/agent-ready-backups.*/.claude/settings.json.agent-ready-backup.*)
  [ -f "${backup_files[0]}" ]
  grep -Fq 'Bash(custom-command)' "${backup_files[0]}"
}

@test "sync hook projects managed assets without bootstrap" {
  fake_bin="$test_root/bin"
  source_dir="$test_root/agent-ready-setup"
  event_log="$test_root/events.log"
  bootstrap_log="$test_root/bootstrap.log"
  mkdir -p \
    "$fake_bin" \
    "$source_dir/assets/common/hooks" \
    "$source_dir/assets/common/shared" \
    "$source_dir/assets/codex" \
    "$source_dir/assets/stacks/go/hooks" \
    "$source_dir/assets/stacks/go/rules" \
    "$source_dir/assets/stacks/go/agents" \
    "$source_dir/assets/stacks/go/commands" \
    "$source_dir/assets/stacks/go/skills/deploy-helper" \
    "$source_dir/scripts" \
    .agents/rules
  touch "$source_dir/SKILL.md"
  printf '%s\n' '#!/bin/bash' > "$source_dir/scripts/normalize-instructions.sh"
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
    "$source_dir/assets/common/hooks/sync-marketplace.sh"
  cp "$skill_dir/scripts/asset-sync-common.sh" "$source_dir/scripts/asset-sync-common.sh"
  cp "$skill_dir/scripts/render-instruction-template.sh" "$source_dir/scripts/render-instruction-template.sh"
  cp "$skill_dir/scripts/merge-managed-settings.py" "$source_dir/scripts/merge-managed-settings.py"
  cp "$skill_dir/scripts/run-detached.py" "$source_dir/scripts/run-detached.py"
  printf '%s\n' '{"settings":"updated"}' > "$source_dir/assets/common/settings.json"
  printf '%s\n' '# updated common asset' > "$source_dir/assets/common/shared/asset.md"
  printf '%s\n' '{"hooks":"updated"}' > "$source_dir/assets/codex/hooks.json"
  printf '%s\n' '#!/bin/bash' > "$source_dir/assets/common/hooks/check-harness-consistency.sh"
  printf '%s\n' '# updated pre-tool hook' > "$source_dir/assets/stacks/go/hooks/pre-tool-use.md"
  printf '%s\n' '# updated coding style' > "$source_dir/assets/stacks/go/rules/coding-style.md"
  printf '%s\n' '# security scanner' > "$source_dir/assets/stacks/go/agents/security-scanner.md"
  printf '%s\n' '# review command' > "$source_dir/assets/stacks/go/commands/review-pr.md"
  cat > "$source_dir/assets/stacks/go/skills/deploy-helper/SKILL.md" <<'EOF'
---
name: deploy-helper
description: Deploy applications.
---

# Deploy helper
EOF
  printf '%s\n' '{"mcp":"updated"}' > "$source_dir/assets/stacks/go/mcp.json"
  mkdir -p .agents/shared
  printf '%s\n' '# previous common asset' > .agents/shared/asset.md
  printf '%s\n' '# previous coding style' > .agents/rules/coding-style.md
  cat > "$source_dir/scripts/bootstrap.sh" <<'EOF'
#!/bin/bash
printf 'bootstrap\n' >> "$EVENT_LOG"
printf '%s\n' "$*" > "$BOOTSTRAP_INVOCATION_LOG"
EOF
  chmod +x "$source_dir/scripts/bootstrap.sh"
  cat > "$source_dir/scripts/apply-managed-block.sh" <<'EOF'
#!/bin/bash
[[ "$(cat .agents/shared/asset.md)" = '# updated common asset' ]] || exit 42
[[ -f .agents/rules/coding-style.md ]] || exit 42
[[ -f .agents/agents/security-scanner.md ]] || exit 42
[[ -f .agents/commands/review-pr.md ]] || exit 42
[[ -f .agents/skills/deploy-helper/SKILL.md ]] || exit 42
[[ -f .codex/.mcp.json ]] || exit 42
printf 'apply\n' >> "$EVENT_LOG"
EOF
  cat > "$source_dir/scripts/merge-instructions.sh" <<'EOF'
#!/bin/bash
printf 'merge\n' >> "$EVENT_LOG"
EOF
  chmod +x "$source_dir/scripts/merge-instructions.sh"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
printf 'upgrade\n' >> "$EVENT_LOG"
printf '%s %s\n' "${0##*/}" "$*" > "$MARKETPLACE_INVOCATION_LOG"
EOF
  chmod +x "$fake_bin/claude"
  EVENT_LOG="$event_log" \
    MARKETPLACE_INVOCATION_LOG="$test_root/marketplace.log" \
    BOOTSTRAP_INVOCATION_LOG="$bootstrap_log" \
    AGENT_READY_SETUP_SKILL_DIR="$source_dir" \
    PATH="$fake_bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack go

  [ "$status" -eq 0 ]
  wait_for_file_containing "$event_log" "merge"
  [ "$(sed -n '1p' "$event_log")" = "upgrade" ]
  [ "$(sed -n '2p' "$event_log")" = "apply" ]
  [ "$(sed -n '3p' "$event_log")" = "merge" ]
  [ "$(wc -l < "$event_log")" -eq 3 ]
  [ ! -e "$bootstrap_log" ]
  grep -Fxq 'claude plugin marketplace update golfo-marketplace' "$test_root/marketplace.log"
  cmp -s .agents/hooks/sync-marketplace.sh "$source_dir/assets/common/hooks/sync-marketplace.sh"
  cmp -s .agents/hooks/check-harness-consistency.sh "$source_dir/assets/common/hooks/check-harness-consistency.sh"
  cmp -s .agents/hooks/pre-tool-use.md "$source_dir/assets/stacks/go/hooks/pre-tool-use.md"
  cmp -s .agents/shared/asset.md "$source_dir/assets/common/shared/asset.md"
  assert_claude_view .claude/shared/asset.md "../../.agents/shared/asset.md"
  cmp -s .agents/rules/coding-style.md "$source_dir/assets/stacks/go/rules/coding-style.md"
  cmp -s .agents/agents/security-scanner.md "$source_dir/assets/stacks/go/agents/security-scanner.md"
  cmp -s .agents/commands/review-pr.md "$source_dir/assets/stacks/go/commands/review-pr.md"
  grep -Fq '# Deploy helper' .agents/skills/deploy-helper/SKILL.md
  adapter_mode="$(python3 -c 'import os, stat, sys; print(format(stat.S_IMODE(os.stat(sys.argv[1]).st_mode), "o"))' .agents/skills/deploy-helper/SKILL.md)"
  # NTFS has no POSIX permission bits: Windows Python always reports 666 there.
  [ "$adapter_mode" = "644" ] || [ "$adapter_mode" = "666" ]
  claude_adapter_mode="$(python3 -c 'import os, stat, sys; print(format(stat.S_IMODE(os.stat(sys.argv[1]).st_mode), "o"))' .claude/skills/deploy-helper/SKILL.md)"
  [ "$claude_adapter_mode" = "644" ] || [ "$claude_adapter_mode" = "666" ]
  cmp -s .agents/mcp.json "$source_dir/assets/stacks/go/mcp.json"
  cmp -s .claude/settings.json "$source_dir/assets/common/settings.json"
  cmp -s .codex/hooks.json "$source_dir/assets/codex/hooks.json"
  cmp -s .codex/.mcp.json "$source_dir/assets/stacks/go/mcp.json"
  assert_claude_view .claude/rules/coding-style.md "../../.agents/rules/coding-style.md"
  assert_claude_view .claude/agents/security-scanner.md
  assert_claude_view .claude/commands/review-pr.md
  assert_claude_view .claude/skills/deploy-helper/SKILL.md
}

@test "bootstrap creates new managed assets through atomic rename" {
  mv_log="$test_root/mv.log"
  cat > "$fake_bin/mv" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$MV_LOG"
exec /bin/mv "$@"
EOF
  chmod +x "$fake_bin/mv"

  MV_LOG="$mv_log" run env PATH="$fake_bin:$PATH" bash "$skill_dir/scripts/bootstrap.sh" \
    --stack frontend --skill-dir "$skill_dir" --provider claude

  [ "$status" -eq 0 ]
  grep -Eq 'agent-ready-sync\.[^ ]+ \.agents/hooks/sync-marketplace\.sh$' "$mv_log"
}

@test "sync hook creates new managed assets through atomic rename" {
  source_dir="$test_root/agent-ready-setup"
  mv_log="$test_root/mv.log"
  mkdir -p \
    "$source_dir/assets/common/hooks" \
    "$source_dir/assets/codex" \
    "$source_dir/assets/stacks/go/hooks" \
    "$source_dir/scripts"
  touch "$source_dir/SKILL.md"
  printf '%s\n' '#!/bin/bash' > "$source_dir/scripts/normalize-instructions.sh"
  printf '%s\n' '#!/bin/bash' > "$source_dir/scripts/apply-managed-block.sh"
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
    "$source_dir/assets/common/hooks/sync-marketplace.sh"
  cp "$skill_dir/scripts/asset-sync-common.sh" "$source_dir/scripts/asset-sync-common.sh"
  cp "$skill_dir/scripts/merge-managed-settings.py" "$source_dir/scripts/merge-managed-settings.py"
  printf '%s\n' '{"settings":"updated"}' > "$source_dir/assets/common/settings.json"
  printf '%s\n' '{"hooks":"updated"}' > "$source_dir/assets/codex/hooks.json"
  cat > "$fake_bin/mv" <<'EOF'
#!/bin/bash
printf '%s\n' "$*" >> "$MV_LOG"
exec /bin/mv "$@"
EOF
  chmod +x "$fake_bin/mv"

  AGENT_READY_SETUP_SKILL_DIR="$source_dir" MV_LOG="$mv_log" PATH="$fake_bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack go

  [ "$status" -eq 0 ]
  grep -Eq 'agent-ready-sync\.[^ ]+ \.agents/hooks/sync-marketplace\.sh$' "$mv_log"
}

@test "sync hook replaces its own running file atomically" {
  source_dir="$test_root/agent-ready-setup"
  mkdir -p .agents/hooks
  cp -R "$skill_dir"/. "$source_dir"/
  cp "$skill_dir/assets/common/hooks/sync-marketplace.sh" .agents/hooks/sync-marketplace.sh
  printf '%s\n' '# stale target marker' >> .agents/hooks/sync-marketplace.sh

  AGENT_READY_SETUP_SKILL_DIR="$source_dir" PATH="$test_root/bin:$PATH" \
    run bash .agents/hooks/sync-marketplace.sh \
      --provider claude --stack go

  [ "$status" -eq 0 ]
  grep -Fq -- "Sync hook updated; restarting with latest version." <<< "$output"
  grep -Fq -- "Local managed asset projection completed for go." <<< "$output"
  [ ! -e .agents/.agent-ready-assets.lock ]
  cmp -s .agents/hooks/sync-marketplace.sh "$source_dir/assets/common/hooks/sync-marketplace.sh"
}

@test "sync hook reclaims lock left by terminated process" {
  source_dir="$test_root/agent-ready-setup"
  cp -R "$skill_dir"/. "$source_dir"/
  mkdir -p .agents/.agent-ready-assets.lock
  (sleep 30) 3>&- &
  stale_pid=$!
  kill "$stale_pid"
  wait "$stale_pid" 2>/dev/null || true
  printf '%s\n' "$stale_pid" > .agents/.agent-ready-assets.lock/owner

  AGENT_READY_SETUP_SKILL_DIR="$source_dir" PATH="$test_root/bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack go

  [ "$status" -eq 0 ]
  [ ! -e .agents/.agent-ready-assets.lock ]
  cmp -s .agents/hooks/sync-marketplace.sh "$source_dir/assets/common/hooks/sync-marketplace.sh"
}

@test "sync hook preserves lock held by live process" {
  source_dir="$test_root/agent-ready-setup"
  cp -R "$skill_dir"/. "$source_dir"/
  mkdir -p .agents/.agent-ready-assets.lock
  owner_start_time="$(ps -p "$$" -o lstart= | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  printf '%s\n%s\n' "$$" "$owner_start_time" > .agents/.agent-ready-assets.lock/owner

  AGENT_READY_SETUP_SKILL_DIR="$source_dir" PATH="$test_root/bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack go

  [ "$status" -eq 0 ]
  [ -d .agents/.agent-ready-assets.lock ]
  [[ "$output" == *"active/ambiguous lock"* ]]
}

@test "sync hook preserves old lock without owner metadata" {
  source_dir="$test_root/agent-ready-setup"
  cp -R "$skill_dir"/. "$source_dir"/
  mkdir -p .agents/.agent-ready-assets.lock
  touch -t 200001010000 .agents/.agent-ready-assets.lock

  AGENT_READY_SETUP_SKILL_DIR="$source_dir" PATH="$test_root/bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude --stack go

  [ "$status" -eq 0 ]
  [ -d .agents/.agent-ready-assets.lock ]
  [[ "$output" == *"active/ambiguous lock"* ]]
}

@test "bootstrap reclaims asset lock left by terminated process" {
  mkdir -p .agents/.agent-ready-assets.lock
  (sleep 30) 3>&- &
  stale_pid=$!
  kill "$stale_pid"
  wait "$stale_pid" 2>/dev/null || true
  printf '%s\n' "$stale_pid" > .agents/.agent-ready-assets.lock/owner

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ ! -e .agents/.agent-ready-assets.lock ]
  [ -f .agents/hooks/sync-marketplace.sh ]
}

@test "sync hooks do not project content when marketplace upgrade fails" {
  fake_bin="$test_root/bin"
  source_dir="$test_root/agent-ready-setup"
  bootstrap_log="$test_root/bootstrap.log"
  mkdir -p "$fake_bin" "$source_dir/assets/stacks" "$source_dir/scripts"
  touch "$source_dir/SKILL.md"
  cat > "$source_dir/scripts/bootstrap.sh" <<'EOF'
#!/bin/bash
printf '%s\n' called > "$BOOTSTRAP_INVOCATION_LOG"
EOF
  chmod +x "$source_dir/scripts/bootstrap.sh"
  cat > "$fake_bin/claude" <<'EOF'
#!/bin/bash
exit 42
EOF
  chmod +x "$fake_bin/claude"

  MARKETPLACE_INVOCATION_LOG="$test_root/marketplace.log" \
    BOOTSTRAP_INVOCATION_LOG="$bootstrap_log" \
    AGENT_READY_SETUP_SKILL_DIR="$source_dir" \
    PATH="$fake_bin:$PATH" \
    run bash "$skill_dir/assets/common/hooks/sync-marketplace.sh" \
      --provider claude

  [ "$status" -ne 0 ]
  [ ! -e "$bootstrap_log" ]
}

@test "common marketplace assets have no stack duplicates" {
  [ -f "$skill_dir/assets/common/settings.json" ]
  [ -f "$skill_dir/assets/common/hooks/sync-marketplace.sh" ]
  for common_rule in established-libraries.md language-consistency.md lint-gate.md patterns-we-do-not-use.md speculative-complexity-approval.md user-actions-first.md verify-changes.md; do
    [ -f "$skill_dir/assets/common/rules/$common_rule" ]
  done
  [ -f "$skill_dir/scripts/asset-sync-common.sh" ]
  [ -f "$skill_dir/scripts/merge-managed-settings.py" ]

  for stack in frontend node java go; do
    [ ! -e "$skill_dir/assets/stacks/$stack/settings.json" ]
    [ ! -e "$skill_dir/assets/stacks/$stack/hooks/sync-marketplace.sh" ]
    [ ! -e "$skill_dir/assets/stacks/$stack/rules/language-consistency.md" ]
    [ ! -e "$skill_dir/assets/stacks/$stack/rules/lint-gate.md" ]
    [ ! -e "$skill_dir/assets/stacks/$stack/rules/established-libraries.md" ]
    [ ! -e "$skill_dir/assets/stacks/$stack/rules/verify-changes.md" ]
    [ ! -e "$skill_dir/assets/stacks/$stack/rules/user-actions-first.md" ]
    [ ! -e "$skill_dir/assets/stacks/$stack/rules/speculative-complexity-approval.md" ]
    [ ! -e "$skill_dir/assets/stacks/$stack/rules/patterns-we-do-not-use.md" ]
  done
}


@test "Codex hooks merge keeps custom hooks and handler options and remains idempotent" {
  mkdir -p .codex
  jq 'del(.hooks.SessionStart[].hooks[].statusMessage) | .hooks.SessionStart[0].hooks[0].timeout = 123 | .hooks.Stop = [{"hooks":[{"type":"command","command":"echo current"}]}]' \
    "$skill_dir/assets/codex/hooks.json" > .codex/hooks.json

  run_bootstrap node
  [ "$status" -eq 0 ]
  jq -e '[.hooks.Stop[].hooks[].command] == ["echo current"]' .codex/hooks.json >/dev/null
  jq -e '[.hooks.SessionStart[].hooks[]] | length == 1 and .[0].statusMessage != null' .codex/hooks.json >/dev/null
  jq -e '.hooks.SessionStart[0].hooks[0].timeout == 123' .codex/hooks.json >/dev/null
  cp .codex/hooks.json "$test_root/expected-hooks.json"

  run_marketplace_sync .agents/hooks/sync-marketplace.sh "$skill_dir"
  [ "$status" -eq 0 ]
  cmp -s .codex/hooks.json "$test_root/expected-hooks.json"
}

@test "Codex sync leaves files under .codex/hooks untouched" {
  run_bootstrap node
  [ "$status" -eq 0 ]
  mkdir -p .codex/hooks
  printf '%s\n' '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo other"}]}]}}' > .codex/hooks/hooks.json
  cp .codex/hooks/hooks.json "$test_root/expected-other-hooks.json"

  run_marketplace_sync .agents/hooks/sync-marketplace.sh "$skill_dir"
  [ "$status" -eq 0 ]
  cmp -s .codex/hooks/hooks.json "$test_root/expected-other-hooks.json"
  cmp -s .codex/hooks.json "$skill_dir/assets/codex/hooks.json"
}

@test "Codex hooks merge preserves malformed or symlinked destination" {
  skip_without_symlinks
  mkdir -p .codex
  printf '%s\n' 'invalid json' > .codex/hooks.json
  run_bootstrap go
  [ "$status" -eq 0 ]
  [ "$(cat .codex/hooks.json)" = 'invalid json' ]
  [[ "$output" == *'Codex hooks contain invalid configuration'* ]]

  rm .codex/hooks.json
  printf '%s\n' '{"hooks":{}}' > "$test_root/outside-hooks.json"
  ln -s "$test_root/outside-hooks.json" .codex/hooks.json
  run_bootstrap go
  [ "$status" -eq 0 ]
  [ -L .codex/hooks.json ]
  [ "$(cat "$test_root/outside-hooks.json")" = '{"hooks":{}}' ]
  [[ "$output" == *'Codex hooks preserved'* ]]
}


@test "Codex hooks merge preserves distinct custom handler options for the same command" {
  mkdir -p .codex
  printf '%s\n' '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo custom","timeout":10}]},{"matcher":"other","hooks":[{"type":"command","command":"echo custom","timeout":20}]}]}}' \
    > .codex/hooks.json
  run_bootstrap node
  [ "$status" -eq 0 ]
  jq -e '[.hooks.Stop[].hooks[].timeout] | sort == [10, 20]' .codex/hooks.json >/dev/null
  cp .codex/hooks.json "$test_root/expected-hooks.json"
  run_bootstrap node
  [ "$status" -eq 0 ]
  cmp -s .codex/hooks.json "$test_root/expected-hooks.json"
}

@test "Codex hooks merge keeps original snapshot through the final replacement" {
  for provider in bootstrap sync; do
    mkdir -p .codex
    printf '%s\n' '{"hooks":{},"custom":"original"}' > .codex/hooks.json
    cat > "$fake_bin/mktemp" <<'SCRIPT'
#!/bin/bash
for argument in "$@"; do
  if [[ "$argument" == .codex/hooks.json.agent-ready-expected.* ]]; then
    printf '%s\n' '{"hooks":{},"custom":"concurrent"}' > .codex/hooks.json
  fi
done
exec /usr/bin/mktemp "$@"
SCRIPT
    chmod +x "$fake_bin/mktemp"
    if [[ "$provider" == bootstrap ]]; then
      run_bootstrap node
    else
      run_marketplace_sync "$skill_dir/assets/common/hooks/sync-marketplace.sh" "$skill_dir"
    fi
    [ "$status" -eq 0 ]
    jq -e '.custom == "concurrent"' .codex/hooks.json >/dev/null
    [[ "$output" == *'.codex/hooks.json changed during synchronization'* ]]
  done
}

@test "Codex hooks sync preserves a destination created concurrently during staging" {
  for provider in bootstrap sync; do
    mkdir -p .codex
    rm -f .codex/hooks.json
    cat > "$fake_bin/cp" <<'SCRIPT'
#!/bin/bash
/bin/cp "$@"
for argument in "$@"; do
  if [[ "$argument" == .codex/hooks.json.agent-ready-sync.* ]]; then
    printf '%s\n' '{"hooks":{},"custom":"concurrent"}' > .codex/hooks.json
  fi
done
SCRIPT
    chmod +x "$fake_bin/cp"
    if [[ "$provider" == bootstrap ]]; then
      run_bootstrap node
    else
      run_marketplace_sync "$skill_dir/assets/common/hooks/sync-marketplace.sh" "$skill_dir"
    fi
    [ "$status" -eq 0 ]
    jq -e '.custom == "concurrent"' .codex/hooks.json >/dev/null
    [[ "$output" == *'.codex/hooks.json changed during synchronization'* ]]
  done
}

@test "Claude views fall back to hard links when symlinks are unavailable" {
  disable_symlinks

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ ! -L .claude/rules/security.md ]
  [ .claude/rules/security.md -ef .agents/rules/security.md ]
  grep -Fxq 'rules/security.md' .claude/.agent-ready-hard-link-views
  [[ "$output" != *"could not create Claude view"* ]]
}

@test "detached hard-link views are relinked on the next bootstrap" {
  disable_symlinks
  run_bootstrap frontend
  [ "$status" -eq 0 ]

  # Git recreates files on checkout or rebase, which detaches existing hard links.
  cp .agents/rules/security.md "$test_root/security.md"
  mv "$test_root/security.md" .agents/rules/security.md
  [ ! .claude/rules/security.md -ef .agents/rules/security.md ]

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ .claude/rules/security.md -ef .agents/rules/security.md ]
}

@test "hard-link views of deleted project rules are pruned" {
  disable_symlinks
  mkdir -p .agents/rules
  printf '%s\n' '# Team conventions' > .agents/rules/team-conventions.md
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  [ .claude/rules/team-conventions.md -ef .agents/rules/team-conventions.md ]

  rm .agents/rules/team-conventions.md
  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ ! -e .claude/rules/team-conventions.md ]
  ! grep -Fxq 'rules/team-conventions.md' .claude/.agent-ready-hard-link-views
}

@test "hard-link pruning keeps Claude files that agent-ready did not create" {
  disable_symlinks
  mkdir -p .claude/rules
  printf '%s\n' '# Personal rule' > .claude/rules/personal.md

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  grep -Fxq '# Personal rule' .claude/rules/personal.md
  ! grep -Fxq 'rules/personal.md' .claude/.agent-ready-hard-link-views
}

# Real git, except `git hook run`, which fails as on versions without config-based hooks.
disable_config_hooks() {
  local real_git
  real_git="$(command -v git)"
  cat > "$fake_bin/git" <<EOF
#!/bin/bash
for argument in "\$@"; do
  if [[ "\$argument" == "hook" ]]; then
    exit 1
  fi
done
exec "$real_git" "\$@"
EOF
  chmod +x "$fake_bin/git"
}

commit_agents_and_detach_security_rule() {
  git config user.email agent-ready-tests@example.com
  git config user.name "Agent Ready Tests"
  git add .agents
  git commit -qm "agent-ready assets"
  printf '%s\n' 'Project addition.' >> .agents/rules/security.md
  git commit -qam "edit security rule"
  # reset --hard recreates the rule, which detaches the hard-link view.
  git reset -q --hard HEAD~1
}

@test "hard-link views register a config-based git hook that relinks them after git reset" {
  disable_symlinks
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  [ "$(git config --get hook.agent-ready-relink.event)" = "post-index-change" ]
  [ "$(git config --get hook.agent-ready-relink.command)" = "sh .agents/hooks/relink-hard-link-views.sh" ]
  [ ! -e "$(git rev-parse --git-path hooks)/post-index-change" ]

  commit_agents_and_detach_security_rule

  [ .claude/rules/security.md -ef .agents/rules/security.md ]
  ! grep -Fxq 'Project addition.' .claude/rules/security.md
}

@test "config-based relink hook coexists with a project hook manager" {
  disable_symlinks
  git config core.hooksPath .husky
  mkdir -p .husky

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ "$(git config --get core.hooksPath)" = ".husky" ]
  [ -z "$(ls -A .husky)" ]
  [ "$(git config --get hook.agent-ready-relink.event)" = "post-index-change" ]
  commit_agents_and_detach_security_rule
  [ .claude/rules/security.md -ef .agents/rules/security.md ]
}

@test "relink hook falls back to a hooks-directory file when git lacks config-based hooks" {
  disable_symlinks
  disable_config_hooks

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  hook_path="$(git rev-parse --git-path hooks)/post-index-change"
  [ -x "$hook_path" ]
  grep -Fq 'agent-ready-setup: relinks .claude hard-link views' "$hook_path"
  [ -z "$(git config --get hook.agent-ready-relink.event)" ]
}

@test "relink hook fallback is not installed over a project hook manager" {
  disable_symlinks
  disable_config_hooks
  git config core.hooksPath .husky

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ ! -e .husky/post-index-change ]
  [ ! -e .git/hooks/post-index-change ]
  [[ "$output" == *"core.hooksPath is set"* ]]
}

@test "Claude prompt hook relinks views detached without any git hook" {
  disable_symlinks
  run_bootstrap frontend
  [ "$status" -eq 0 ]
  jq -e '.hooks.UserPromptSubmit[0].hooks[0].command == "sh .agents/hooks/relink-hard-link-views.sh"' .claude/settings.json >/dev/null

  # `git apply` without --index rewrites files and fires no git hook at all.
  cp .agents/rules/security.md "$test_root/security.md"
  mv "$test_root/security.md" .agents/rules/security.md
  [ ! .claude/rules/security.md -ef .agents/rules/security.md ]

  run sh .agents/hooks/relink-hard-link-views.sh

  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ .claude/rules/security.md -ef .agents/rules/security.md ]
}

@test "relink hook is not registered when views are symlinks" {
  skip_without_symlinks

  run_bootstrap frontend

  [ "$status" -eq 0 ]
  [ -z "$(git config --get hook.agent-ready-relink.event)" ]
  [ ! -e "$(git rev-parse --git-path hooks)/post-index-change" ]
}

# Builds a PATH that only exposes the given fake provider CLIs plus system tools.
provider_cli_path() {
  local isolated_bin="$test_root/isolated-bin-$1"
  local provider_cli
  mkdir -p "$isolated_bin"
  shift
  for provider_cli in "$@"; do
    cp "$fake_bin/$provider_cli" "$isolated_bin/$provider_cli"
  done
  printf '%s:/usr/bin:/bin\n' "$isolated_bin"
}

@test "resolve-provider infers the only provider CLI for a Hermes installation" {
  hermes_home="$test_root/hermes-home"
  hermes_skill_dir="$hermes_home/plugins/golfo-kit/skills/agent-ready-setup"
  mkdir -p "$hermes_skill_dir"

  run env -u AGENT_READY_SETUP_ACTIVE_PROVIDER -u LOCALAPPDATA HERMES_HOME="$hermes_home" \
    PATH="$(provider_cli_path codex-only codex)" \
    bash "$skill_dir/scripts/resolve-provider.sh" --skill-dir "$hermes_skill_dir"

  [ "$status" -eq 0 ]
  [ "$output" = "codex" ]
}

@test "resolve-provider asks for a choice when a Hermes installation sees both provider CLIs" {
  hermes_home="$test_root/hermes-home"
  hermes_skill_dir="$hermes_home/skills/agent-ready-setup"
  mkdir -p "$hermes_skill_dir"

  run env -u AGENT_READY_SETUP_ACTIVE_PROVIDER -u LOCALAPPDATA HERMES_HOME="$hermes_home" \
    PATH="$(provider_cli_path both claude codex)" \
    bash "$skill_dir/scripts/resolve-provider.sh" --skill-dir "$hermes_skill_dir"

  [ "$status" -ne 0 ]
  [[ "$output" == *"belongs to Hermes and both claude and codex are in PATH"* ]]
}

@test "resolve-provider rejects a Hermes installation without provider CLIs" {
  hermes_skill_dir="$HOME/.hermes/plugins/golfo-kit/skills/agent-ready-setup"

  run env -u AGENT_READY_SETUP_ACTIVE_PROVIDER -u LOCALAPPDATA -u HERMES_HOME \
    PATH="$(provider_cli_path none)" \
    bash "$skill_dir/scripts/resolve-provider.sh" --skill-dir "$hermes_skill_dir"

  [ "$status" -ne 0 ]
  [[ "$output" == *"belongs to Hermes, which is not a target provider, and neither claude nor codex is in PATH"* ]]
}

@test "resolve-provider matches a Windows-style HERMES_HOME" {
  command -v cygpath >/dev/null 2>&1 || skip "cygpath is only available on Windows"
  hermes_home="$test_root/hermes-home"
  hermes_skill_dir="$hermes_home/plugins/golfo-kit/skills/agent-ready-setup"
  mkdir -p "$hermes_skill_dir"

  run env -u AGENT_READY_SETUP_ACTIVE_PROVIDER -u LOCALAPPDATA HERMES_HOME="$(cygpath -w "$hermes_home")" \
    PATH="$(provider_cli_path claude-only claude)" \
    bash "$skill_dir/scripts/resolve-provider.sh" --skill-dir "$hermes_skill_dir"

  [ "$status" -eq 0 ]
  [ "$output" = "claude" ]
}
