#!/usr/bin/env bats

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
  test_root="$(mktemp -d)"
  repo_dir="$test_root/repo"
  mkdir -p "$repo_dir/scripts/lib"
  cp "$repository_root/scripts/validate-portable-plugins.js" "$repo_dir/scripts/"
  cp "$repository_root/scripts/lib/plugin-manifests.js" "$repo_dir/scripts/lib/"
  ln -s "$repository_root/node_modules" "$repo_dir/node_modules"

  plugin_dir="$repo_dir/plugins/golfo-kit"
  mkdir -p "$plugin_dir/.claude-plugin" "$plugin_dir/.codex-plugin"
  printf '{\n  "name": "golfo-kit",\n  "version": "1.2.0"\n}\n' > "$plugin_dir/.claude-plugin/plugin.json"
  printf '{\n  "name": "golfo-kit",\n  "version": "1.2.0"\n}\n' > "$plugin_dir/.codex-plugin/plugin.json"
  write_portable_manifest golfo-kit 1.2.0
  write_skill demo "Demo skill used by the portable package tests."
  unset GITHUB_ACTIONS
  cd "$repo_dir"
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

# write_portable_manifest <name> <version>
write_portable_manifest() {
  cat > "$plugin_dir/plugin.json" <<JSON
{
  "\$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "$1",
  "version": "$2"
}
JSON
}

# write_skill <directory> <description> [frontmatter-name]
write_skill() {
  mkdir -p "$plugin_dir/skills/$1"
  printf -- '---\nname: %s\ndescription: >-\n  %s\n---\n\n# Body\n' "${3:-$1}" "$2" > "$plugin_dir/skills/$1/SKILL.md"
}

run_validation() {
  run node scripts/validate-portable-plugins.js
}

@test "passes for a valid portable package" {
  run_validation
  [ "$status" -eq 0 ]
  [[ "$output" == *"golfo-kit: portable package is valid."* ]]
}

@test "fails when the portable root manifest is missing" {
  rm "$plugin_dir/plugin.json"

  run_validation
  [ "$status" -eq 1 ]
  [[ "$output" == *"Missing portable root plugin.json"* ]]
}

@test "fails when the portable manifest version drifts from the Claude manifest" {
  write_portable_manifest golfo-kit 1.1.0

  run_validation
  [ "$status" -eq 1 ]
  [[ "$output" == *"Portable plugin.json version 1.1.0 differs from the Claude manifest version 1.2.0."* ]]
}

@test "fails when the portable manifest has another name or fields outside the spec" {
  node -e "
    const fs = require('fs');
    const manifestPath = 'plugins/golfo-kit/plugin.json';
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    fs.writeFileSync(manifestPath, JSON.stringify({ ...manifest, name: 'other-kit', category: 'productivity' }));
  "

  run_validation
  [ "$status" -eq 1 ]
  [[ "$output" == *'Portable plugin.json name must be "golfo-kit"'* ]]
  [[ "$output" == *"fields outside Agent Plugins v1: category"* ]]
}

@test "fails when a skill description exceeds 1024 characters" {
  write_skill long-description "$(printf 'a%.0s' {1..1025})"

  run_validation
  [ "$status" -eq 1 ]
  [[ "$output" == *"skill long-description: description has 1025 characters; the limit is 1024."* ]]
}

@test "counts multibyte characters as single characters" {
  write_skill accented "$(printf 'á%.0s' {1..1024})"

  run_validation
  [ "$status" -eq 0 ]
}

@test "fails when a skill name does not match its directory" {
  write_skill renamed "Skill whose frontmatter name differs." other-name

  run_validation
  [ "$status" -eq 1 ]
  [[ "$output" == *"skill renamed: frontmatter name must equal the directory name"* ]]
}

@test "emits a GitHub Actions error annotation in CI" {
  rm "$plugin_dir/plugin.json"

  GITHUB_ACTIONS=true run_validation
  [ "$status" -eq 1 ]
  [[ "$output" == *"::error file=plugins/golfo-kit/.claude-plugin/plugin.json::golfo-kit: Missing portable root plugin.json"* ]]
}

# write_nested_skill_file <path under skills/demo>
write_nested_skill_file() {
  mkdir -p "$plugin_dir/skills/demo/$1"
  printf -- '---\nname: %s\ndescription: Nested file.\n---\n' "$(basename "$1")" > "$plugin_dir/skills/demo/$1/SKILL.md"
}

@test "fails when a SKILL.md outside the support directories would install as another skill in Hermes" {
  write_nested_skill_file examples/pack/profiles/kafka/skills/consumer

  run_validation
  [ "$status" -eq 1 ]
  [[ "$output" == *"nested demo/examples/pack/profiles/kafka/skills/consumer/SKILL.md would install as a separate skill in Hermes"* ]]
}

@test "accepts nested SKILL.md templates inside the support directories of a skill" {
  write_nested_skill_file assets/stacks/node/skills/service
  write_nested_skill_file references/examples/pack
  write_nested_skill_file templates/skill
  write_nested_skill_file scripts/fixtures/skill

  run_validation
  [ "$status" -eq 0 ]
  [[ "$output" == *"golfo-kit: portable package is valid."* ]]
}

@test "a support directory only hides a SKILL.md when its parent holds a skill" {
  write_nested_skill_file examples/assets/skill

  run_validation
  [ "$status" -eq 1 ]
  [[ "$output" == *"nested demo/examples/assets/skill/SKILL.md"* ]]
}
