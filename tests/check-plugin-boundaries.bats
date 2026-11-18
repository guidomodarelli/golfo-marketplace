#!/usr/bin/env bats

# Exercises scripts/check-plugin-boundaries.js against temporary plugins: links must stay
# inside their plugin and a skill that names a skill of another plugin declares it in
# metadata.plugin-dependencies.

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
  test_root="$(mktemp -d)"
  repo_dir="$test_root/repo"
  mkdir -p "$repo_dir/scripts/lib"
  cp "$repository_root/scripts/check-plugin-boundaries.js" "$repo_dir/scripts/"
  cp "$repository_root/scripts/lib/terminal-output.js" "$repo_dir/scripts/lib/"
  ln -s "$repository_root/node_modules" "$repo_dir/node_modules"
  write_skill golfo-core error-helpers "Error helpers."
  write_skill golfo-ui flow-states "Flow states."
  export NO_COLOR=1
  unset GITHUB_ACTIONS
  cd "$repo_dir"
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

# write_skill <plugin> <skill> <body> [metadata-line]
write_skill() {
  local skill_dir="$repo_dir/plugins/$1/skills/$2"
  mkdir -p "$skill_dir/references"
  {
    printf -- '---\nname: %s\ndescription: Demo skill.\nmetadata:\n  version: "1.0.0"\n' "$2"
    [ -n "${4:-}" ] && printf '  %s\n' "$4"
    printf -- '---\n\n%s\n' "$3"
  } > "$skill_dir/SKILL.md"
}

check_boundaries() {
  run node scripts/check-plugin-boundaries.js "$repo_dir/plugins"
}

@test "plugins that only link inside themselves and name no other plugin pass" {
  printf '%s\n' '# Rules' > plugins/golfo-ui/skills/flow-states/references/rules.md
  write_skill golfo-ui flow-states "See [rules](references/rules.md)."
  check_boundaries
  [ "$status" -eq 0 ]
  [[ "$output" == *"every plugin links only inside itself"* ]]
}

@test "a link to a skill of a sibling plugin fails and names that plugin" {
  write_skill golfo-ui flow-states "See [errors](../error-helpers/SKILL.md)." 'plugin-dependencies: "golfo-core"'
  check_boundaries
  [ "$status" -eq 1 ]
  [[ "$output" == *"plugins/golfo-ui/skills/flow-states/SKILL.md: link to ../error-helpers/SKILL.md points to a skill of golfo-core"* ]]
}

@test "a link that leaves the plugin directory fails" {
  write_skill golfo-ui flow-states "See [guide](../../../golfo-core/skills/error-helpers/SKILL.md)." 'plugin-dependencies: "golfo-core"'
  check_boundaries
  [ "$status" -eq 1 ]
  [[ "$output" == *"leaves plugin golfo-ui"* ]]
}

@test "a link to a missing file inside the plugin fails" {
  write_skill golfo-ui flow-states "See [rules](references/missing.md)."
  check_boundaries
  [ "$status" -eq 1 ]
  [[ "$output" == *"link to references/missing.md does not exist"* ]]
}

@test "placeholders, external links and links inside code are not checked" {
  body=$'Template: [run]({{run_url}}) and [docs](https://example.com) and [more](...).\n\n```md\n[x](../error-helpers/SKILL.md)\n```\n\nInline `[y](../error-helpers/SKILL.md)`.'
  write_skill golfo-ui flow-states "$body" 'plugin-dependencies: "golfo-core"'
  check_boundaries
  [ "$status" -eq 0 ]
}

@test "naming a skill of another plugin without declaring the plugin fails" {
  write_skill golfo-ui flow-states 'Load `error-helpers` for partial failures.'
  check_boundaries
  [ "$status" -eq 1 ]
  [[ "$output" == *"names error-helpers of golfo-core; add golfo-core to metadata.plugin-dependencies"* ]]
}

@test "a declared dependency on the named plugin passes" {
  write_skill golfo-ui flow-states 'Load `error-helpers` for partial failures.' 'plugin-dependencies: "golfo-core"'
  check_boundaries
  [ "$status" -eq 0 ]
}

@test "a declared dependency on a plugin that does not exist fails" {
  write_skill golfo-ui flow-states 'No mentions.' 'plugin-dependencies: "golfo-missing"'
  check_boundaries
  [ "$status" -eq 1 ]
  [[ "$output" == *"metadata.plugin-dependencies names golfo-missing, which is not a plugin"* ]]
}

@test "mentions inside evals are not dependencies" {
  mkdir -p plugins/golfo-ui/skills/flow-states/evals
  printf '%s\n' 'Uses `error-helpers` in a test prompt.' > plugins/golfo-ui/skills/flow-states/evals/notes.md
  check_boundaries
  [ "$status" -eq 0 ]
}
