#!/usr/bin/env bats

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
  test_root="$(mktemp -d)"
  repo_dir="$test_root/repo"
  mkdir -p "$repo_dir/scripts" "$repo_dir/plugins/golfo-kit/.claude-plugin" "$repo_dir/plugins/golfo-kit/.codex-plugin" \
    "$repo_dir/plugins/golfo-kit/skills/agent-ready-setup/scripts" "$repo_dir/plugins/golfo-kit/skills/vivid-visual-output"
  cp "$repository_root/scripts/detect-test-areas.js" "$repo_dir/scripts/"
  for manifest in plugin.json .claude-plugin/plugin.json .codex-plugin/plugin.json; do
    write_manifest "$manifest" 1.0.0 "https://github.com/example/repo"
  done
  printf '%s\n' 'echo bootstrap' > "$repo_dir/plugins/golfo-kit/skills/agent-ready-setup/scripts/bootstrap.sh"
  printf '%s\n' 'skill' > "$repo_dir/plugins/golfo-kit/skills/vivid-visual-output/SKILL.md"
  printf '%s\n' '{}' > "$repo_dir/package.json"

  git -C "$repo_dir" -c init.defaultBranch=main init -q
  git -C "$repo_dir" config user.name "Detect Areas Test"
  git -C "$repo_dir" config user.email "detect-areas-test@example.com"
  git -C "$repo_dir" add -A
  git -C "$repo_dir" commit -qm "Initialize fixture"
  git -C "$repo_dir" switch -qc feature/change
  unset GITHUB_ACTIONS GITHUB_OUTPUT
  export GITHUB_EVENT_NAME=pull_request
  cd "$repo_dir"
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

# write_manifest <path under plugins/golfo-kit> <version> <repository>
write_manifest() {
  printf '{\n  "name": "golfo-kit",\n  "version": "%s",\n  "repository": "%s"\n}\n' "$2" "$3" \
    > "$repo_dir/plugins/golfo-kit/$1"
}

commit_all() {
  git add -A
  git commit -qm "$1"
}

run_detect() {
  run node scripts/detect-test-areas.js main
}

@test "a change outside agent-ready-setup skips the agent_ready area" {
  printf '%s\n' 'more' >> plugins/golfo-kit/skills/vivid-visual-output/SKILL.md
  commit_all "Change another skill"

  run_detect
  [ "$status" -eq 0 ]
  [[ "$output" == *"agent_ready=false"* ]]
}

@test "a change under agent-ready-setup runs the agent_ready area" {
  printf '%s\n' 'echo changed' >> plugins/golfo-kit/skills/agent-ready-setup/scripts/bootstrap.sh
  commit_all "Change agent-ready-setup"

  run_detect
  [ "$status" -eq 0 ]
  [[ "$output" == *"agent_ready=true"* ]]
  [[ "$output" == *"agent-ready-setup/scripts/bootstrap.sh changed"* ]]
}

@test "a change to package.json or the tests workflow runs the agent_ready area" {
  printf '%s\n' '{"name": "x"}' > package.json
  commit_all "Change package.json"
  run_detect
  [[ "$output" == *"agent_ready=true"* ]]

  git reset -q --hard main
  mkdir -p .github/workflows
  printf '%s\n' 'name: Tests' > .github/workflows/tests.yml
  commit_all "Change tests workflow"
  run_detect
  [[ "$output" == *"agent_ready=true"* ]]
}

@test "a pure version bump of the golfo-kit manifests skips the agent_ready area" {
  for manifest in plugin.json .claude-plugin/plugin.json .codex-plugin/plugin.json; do
    write_manifest "$manifest" 1.1.0 "https://github.com/example/repo"
  done
  printf '%s\n' 'more' >> plugins/golfo-kit/skills/vivid-visual-output/SKILL.md
  commit_all "Bump version"

  run_detect
  [ "$status" -eq 0 ]
  [[ "$output" == *"agent_ready=false"* ]]
}

@test "a manifest change beyond its version runs the agent_ready area" {
  write_manifest .claude-plugin/plugin.json 1.1.0 "https://github.com/example/other"
  commit_all "Change repository"

  run_detect
  [[ "$output" == *"agent_ready=true"* ]]
  [[ "$output" == *".claude-plugin/plugin.json changed beyond its version"* ]]
}

@test "adding a file to a manifest folder runs the agent_ready area" {
  printf '%s\n' 'readme' > plugins/golfo-kit/.codex-plugin/README.md
  commit_all "Add a file to the Codex manifest folder"

  run_detect
  [[ "$output" == *"agent_ready=true"* ]]
}

@test "a push or workflow_dispatch runs every area without comparing" {
  printf '%s\n' 'more' >> plugins/golfo-kit/skills/vivid-visual-output/SKILL.md
  commit_all "Change another skill"

  GITHUB_EVENT_NAME=push run_detect
  [[ "$output" == *"agent_ready=true"* ]]
  GITHUB_EVENT_NAME=workflow_dispatch run_detect
  [[ "$output" == *"agent_ready=true"* ]]
}

@test "a base it cannot compare against runs every area instead of failing" {
  run node scripts/detect-test-areas.js does-not-exist
  [ "$status" -eq 0 ]
  [[ "$output" == *"agent_ready=true"* ]]
  [[ "$output" == *"could not compare against does-not-exist"* ]]
}

@test "the decision goes to GITHUB_OUTPUT when it is set" {
  printf '%s\n' 'more' >> plugins/golfo-kit/skills/vivid-visual-output/SKILL.md
  commit_all "Change another skill"

  GITHUB_OUTPUT="$test_root/output" run_detect
  [ "$status" -eq 0 ]
  [ "$(cat "$test_root/output")" = "agent_ready=false" ]
}
