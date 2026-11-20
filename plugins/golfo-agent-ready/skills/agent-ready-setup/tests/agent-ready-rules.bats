#!/usr/bin/env bats
# Atomic rules (#168): agent-ready rules list|show|lint read the rule entries of a repository or of
# a pack, hash each rule apart from its formatting and its neighbours, and lint atomicity, length
# and the consistency of the set without calling any provider.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-agent-ready/skills/agent-ready-setup"
  cli="$skill_dir/scripts/agent-ready"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  project_dir="$test_root/project"
  mkdir -p "$project_dir/.agents/rules" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CONFIG_HOME="$test_root/config"
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_ORGANIZATION_CONFIG="$test_root/organization.json"
  git -C "$project_dir" -c init.defaultBranch=main init -q
  cd "$project_dir"
}

teardown() {
  cd /
  rm -rf "$test_root"
}

agent_ready() {
  python3 "$cli" "$@"
}

write_testing_rules() {
  cat > .agents/rules/testing.md <<'EOF'
---
paths:
  - "src/**"
---

# Testing

Tests describe behavior. This intro is prose, not a rule.

## Unit tests

<!-- rule id=testing/unit-runner key=testing.unit-runner -->
- Use Vitest for unit tests.
  - Except: keep the runner the project already uses if it is not Vitest.
  - Run them with `pnpm test`.

<!-- rule id=testing/behavior-only requires=testing/unit-runner -->
- Assert observable behavior, not implementation details.

```markdown
- A bullet inside a code fence is an example, not a rule.
```
EOF
}

@test "rules show reads the metadata, statement, exceptions and details of a rule" {
  write_testing_rules

  run agent_ready rules show testing/unit-runner --json
  [ "$status" -eq 0 ]
  report="$output"
  [ "$(jq -r '.rules[0].key' <<<"$report")" = "testing.unit-runner" ]
  [ "$(jq -r '.rules[0].statement' <<<"$report")" = "Use Vitest for unit tests." ]
  [ "$(jq -r '.rules[0].exceptions[0]' <<<"$report")" = "keep the runner the project already uses if it is not Vitest." ]
  [ "$(jq -r '.rules[0].details[0]' <<<"$report")" = 'Run them with `pnpm test`.' ]
  [ "$(jq -r '.rules[0].path' <<<"$report")" = ".agents/rules/testing.md" ]
  [ "$(jq -r '.rules[0].line' <<<"$report")" = "13" ]
  [[ "$(jq -r '.rules[0].hash' <<<"$report")" == sha256:* ]]

  run agent_ready rules show testing/behavior-only
  [ "$status" -eq 0 ]
  [[ "$output" == *"requires: testing/unit-runner"* ]]
  [[ "$output" == *"statement: Assert observable behavior, not implementation details."* ]]
}

@test "rules list prints every rule of .agents/rules with its key and place" {
  write_testing_rules

  run agent_ready rules list
  [ "$status" -eq 0 ]
  [[ "$output" == *"testing/unit-runner  key=testing.unit-runner  .agents/rules/testing.md:13"* ]]
  [[ "$output" == *"testing/behavior-only  .agents/rules/testing.md:18"* ]]
  [[ "$output" != *"code fence"* ]]

  run agent_ready rules show testing/missing
  [ "$status" -eq 1 ]
  [[ "$output" == *"no rule has the id testing/missing"* ]]
}

@test "the hash of a rule ignores line endings, spacing, wrapping and the order of the metadata" {
  write_testing_rules
  run agent_ready rules show testing/unit-runner --json
  original="$(jq -r '.rules[0].hash' <<<"$output")"

  cat > .agents/rules/testing.md <<'EOF'
<!-- rule   key=testing.unit-runner   id=testing/unit-runner -->
- Use   Vitest
  for unit tests.
    - Except:   keep the runner the project already
      uses if it is not Vitest.
    - Run them with `pnpm test`.
EOF
  # perl -pi edits in place the same way with GNU and BSD tools; sed -i does not.
  perl -pi -e 's/\n/\r\n/' .agents/rules/testing.md
  run agent_ready rules show testing/unit-runner --json
  [ "$status" -eq 0 ]
  [ "$(jq -r '.rules[0].hash' <<<"$output")" = "$original" ]

  perl -pi -e 's/Use   Vitest/Use   Jest/' .agents/rules/testing.md
  run agent_ready rules show testing/unit-runner --json
  [ "$(jq -r '.rules[0].hash' <<<"$output")" != "$original" ]
}

@test "changing one rule does not change the hash of its neighbours in the same file" {
  write_testing_rules
  run agent_ready rules show testing/behavior-only --json
  neighbour="$(jq -r '.rules[0].hash' <<<"$output")"

  perl -pi -e 's/Use Vitest for unit tests\./Use Jest for unit tests./' .agents/rules/testing.md
  run agent_ready rules show testing/unit-runner --json
  [ "$(jq -r '.rules[0].statement' <<<"$output")" = "Use Jest for unit tests." ]
  run agent_ready rules show testing/behavior-only --json
  [ "$(jq -r '.rules[0].hash' <<<"$output")" = "$neighbour" ]
}

@test "a fence closes only with its own character and length, so examples inside stay out of the rules" {
  cat > .agents/rules/examples.md <<'EOF'
````markdown
```bash
pnpm test
```
<!-- rule id=example/inside-backticks -->
- An example rule inside a four-backtick fence.
````

~~~markdown
```
<!-- rule id=example/inside-tildes -->
- An example rule inside a tilde fence.
~~~

<!-- rule id=real/after-fences -->
- A real rule after the examples.
EOF

  run agent_ready rules list --json
  [ "$status" -eq 0 ]
  [ "$(jq -r '[.rules[].id] | join(",")' <<<"$output")" = "real/after-fences" ]
}

@test "rules lint --path takes the configuration of --project, not of the current directory" {
  printf -- '- Prefer early returns.\n' > .agents/rules/style.md
  printf '%s\n' '{"rules": {"enabled": false}}' > .agents/agent-ready.json
  cd "$test_root"

  run agent_ready rules lint --project "$project_dir" --path "$project_dir/.agents/rules/style.md"
  [ "$status" -eq 0 ]
  [[ "$output" == *"rules.enabled is off"* ]]
}

@test "rules lint passes a file of atomic rules and ignores prose, frontmatter and code fences" {
  write_testing_rules

  run agent_ready rules lint
  [ "$status" -eq 0 ]
  [[ "$output" == *"2 rules, 0 errors, 0 warnings."* ]]
}

@test "two rules with the same key and different content are a conflict; with the same content, a duplicate" {
  write_testing_rules
  cat > .agents/rules/team.md <<'EOF'
<!-- rule id=team/jest key=testing.unit-runner -->
- Use Jest for unit tests.
EOF

  run agent_ready rules lint --json
  [ "$status" -eq 1 ]
  report="$output"
  [ "$(jq -r '[.findings[] | select(.code == "key-conflict")] | length' <<<"$report")" = "1" ]
  # Files are read in path order, so the conflict is reported on the second rule and names the first.
  [ "$(jq -r '.findings[] | select(.code == "key-conflict") | .rule' <<<"$report")" = "testing/unit-runner" ]
  [[ "$(jq -r '.findings[] | select(.code == "key-conflict") | .message' <<<"$report")" == *"team/jest (.agents/rules/team.md:2)"* ]]

  cat > .agents/rules/team.md <<'EOF'
<!-- rule id=team/vitest key=testing.unit-runner -->
- Use Vitest for unit tests.
  - Except: keep the runner the project already uses if it is not Vitest.
EOF
  run agent_ready rules lint --json
  [ "$status" -eq 0 ]
  report="$output"
  [ "$(jq -r '[.findings[] | select(.code == "key-conflict")] | length' <<<"$report")" = "0" ]
  [ "$(jq -r '.findings[] | select(.code == "duplicate-rule") | .level' <<<"$report")" = "warning" ]
}

@test "rules lint reports a top-level bullet without a marker, with its line" {
  cat > .agents/rules/style.md <<'EOF'
# Style

<!-- rule id=style/names -->
- Name variables by their role.

- Prefer early returns.
EOF

  run agent_ready rules lint
  [ "$status" -eq 1 ]
  [[ "$output" == *".agents/rules/style.md:6: error: [untagged-rule]"* ]]
  [[ "$output" == *"1 rules, 1 errors, 0 warnings."* ]]
}

@test "a statement over statementWarnChars warns, over maxStatementChars fails, and the project sets both" {
  long_statement="Use $(printf 'very %.0s' $(seq 1 45))long names."
  printf '<!-- rule id=style/long -->\n- %s\n' "$long_statement" > .agents/rules/style.md
  [ "${#long_statement}" -gt 200 ]
  [ "${#long_statement}" -le 300 ]

  run agent_ready rules lint --json
  [ "$status" -eq 0 ]
  [ "$(jq -r '.findings[0].code' <<<"$output")" = "statement-long" ]

  mkdir -p .agents
  printf '%s\n' '{"rules": {"statementWarnChars": 100, "maxStatementChars": 150}}' > .agents/agent-ready.json
  run agent_ready rules lint --json
  [ "$status" -eq 1 ]
  report="$output"
  [ "$(jq -r '.findings[0].code' <<<"$report")" = "statement-too-long" ]
  [[ "$(jq -r '.findings[0].message' <<<"$report")" == *"rules.maxStatementChars (150)"* ]]

  printf '%s\n' '{"rules": {"statementWarnChars": 400, "maxStatementChars": 300}}' > .agents/agent-ready.json
  run agent_ready rules lint
  [ "$status" -eq 2 ]
  [[ "$output" == *"rules.statementWarnChars (400) is over rules.maxStatementChars (300)"* ]]
}

@test "a statement that chains several decisions fails; code, parentheses and abbreviations do not count" {
  cat > .agents/rules/style.md <<'EOF'
<!-- rule id=style/two-sentences -->
- Use Vitest. Write tests next to the code.

<!-- rule id=style/semicolon -->
- Use Vitest; write tests next to the code.

<!-- rule id=style/one-decision -->
- Call `config.load(); config.apply()` once at startup (e.g. In main. Not elsewhere), i.e. before any request.

<!-- rule id=style/double-backticks -->
- Document the literal syntax `` `first`; `second` `` in the guide.
EOF

  run agent_ready rules lint --json
  [ "$status" -eq 1 ]
  report="$output"
  [ "$(jq -r '[.findings[] | select(.code == "several-decisions") | .rule] | sort | join(",")' <<<"$report")" = "style/semicolon,style/two-sentences" ]
}

@test "malformed markers, a marker without a bullet and an unknown requires are errors" {
  cat > .agents/rules/broken.md <<'EOF'
<!-- rule key=style.names -->
- A rule without an id.

<!-- rule id=Style/Names -->
- An id that is not kebab-case.

<!-- rule id=style/flags color=red locked=yes -->
- Unknown attribute and a flag with a value.

<!-- rule id=style/orphan -->

Prose, not a bullet.

<!-- rule id=style/needs requires=style/absent,golfo:testing/unit-runner -->
- Requires a rule that is not in the set, and one of another source.
EOF

  run agent_ready rules lint --json
  [ "$status" -eq 1 ]
  report="$output"
  messages="$(jq -r '.findings[] | "\(.line) \(.code) \(.message)"' <<<"$report")"
  [[ "$messages" == *"1 marker-syntax the marker has no id"* ]]
  [[ "$messages" == *"4 marker-syntax the id 'Style/Names' must be kebab-case"* ]]
  [[ "$messages" == *"7 marker-syntax unknown attribute color"* ]]
  [[ "$messages" == *"7 marker-syntax locked is a flag and takes no value"* ]]
  [[ "$messages" == *"10 marker-without-rule"* ]]
  [[ "$messages" == *"15 unknown-requires requires style/absent"* ]]
  [[ "$messages" != *"golfo:testing/unit-runner, which no rule"* ]]
}

@test "a repeated id is an error that points at the first one" {
  write_testing_rules
  printf '<!-- rule id=testing/unit-runner -->\n- Keep tests fast.\n' > .agents/rules/other.md

  run agent_ready rules lint
  [ "$status" -eq 1 ]
  [[ "$output" == *".agents/rules/testing.md:13: error: [duplicate-id] testing/unit-runner: the id is already used at .agents/rules/other.md:2"* ]]
}

@test "rules lint --path reads the rules/ directories of a pack without a consumer repository" {
  pack="$test_root/pack"
  mkdir -p "$pack/base/rules" "$pack/stacks/node/rules" "$pack/stacks/node/skills/tool"
  printf '<!-- rule id=base/names -->\n- Name variables by their role.\n' > "$pack/base/rules/names.md"
  printf '<!-- rule id=node/esm -->\n- Use ES modules.\n' > "$pack/stacks/node/rules/modules.md"
  printf -- '- A skill body is not a rule file.\n' > "$pack/stacks/node/skills/tool/SKILL.md"
  printf -- '- A README is not a rule file.\n' > "$pack/README.md"
  cd "$test_root"

  run agent_ready rules list --path "$pack" --json
  [ "$status" -eq 0 ]
  [ "$(jq -r '[.rules[].id] | join(",")' <<<"$output")" = "base/names,node/esm" ]

  run agent_ready rules lint --path "$pack"
  [ "$status" -eq 0 ]
  [[ "$output" == *"2 rules, 0 errors, 0 warnings."* ]]

  run agent_ready rules lint
  [ "$status" -eq 2 ]
  [[ "$output" == *"is not inside a Git repository"* ]]
}

@test "rules.enabled off skips the lint" {
  printf -- '- Prefer early returns.\n' > .agents/rules/style.md
  printf '%s\n' '{"rules": {"enabled": false}}' > .agents/agent-ready.json

  run agent_ready rules lint
  [ "$status" -eq 0 ]
  [[ "$output" == *"rules.enabled is off: the rules were not linted."* ]]
}

write_rule_graph() {
  write_testing_rules
  printf '<!-- rule id=team/runner overrides=golfo:testing/unit-runner -->\n- Use Jest for unit tests.\n' > .agents/rules/team.md
  mkdir -p .agents/skills/add-tests
  printf -- '---\nname: add-tests\n---\nFollow rule:golfo:testing/unit-runner when you add tests; a subrule:x is not a citation.\n' \
    > .agents/skills/add-tests/SKILL.md
}

@test "rules impact lists the rules that require or replace a rule and the skills that cite it" {
  write_rule_graph

  run agent_ready rules impact testing/unit-runner
  [ "$status" -eq 0 ]
  [[ "$output" == *"testing/unit-runner  (.agents/rules/testing.md:13)"* ]]
  [[ "$output" == *"required by: testing/behavior-only (.agents/rules/testing.md:18)"* ]]
  [[ "$output" == *"replaced by: team/runner (.agents/rules/team.md:2)"* ]]
  [[ "$output" == *"cited by: .agents/skills/add-tests/SKILL.md:4"* ]]

  # The id with its source names the same rule.
  run agent_ready rules impact golfo:testing/unit-runner --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; report = json.load(sys.stdin); print(len(report["requiredBy"]), len(report["replacedBy"]), len(report["citedBy"]))')" = "1 1 1" ]

  run agent_ready rules impact team/runner
  [ "$status" -eq 0 ]
  [[ "$output" == *"nothing requires, replaces or cites it"* ]]
}

@test "rules impact of a replaced rule still shows what replaces it, and an unknown id fails" {
  write_rule_graph
  # The apply projects the file without the replaced rule: only the references to it remain.
  perl -0pi -e 's/<!-- rule id=testing\/unit-runner [^\n]*\n- Use Vitest[^\n]*\n(  [^\n]*\n)*//' .agents/rules/testing.md

  run agent_ready rules impact testing/unit-runner
  [ "$status" -eq 0 ]
  [[ "$output" == *"not in this set"* ]]
  [[ "$output" == *"replaced by: team/runner"* ]]

  run agent_ready rules impact testing/absent
  [ "$status" -eq 1 ]
  [[ "$output" == *"no rule has the id testing/absent"* ]]
}

@test "rules graph prints every requires, overrides and citation, also of a pack with --path" {
  write_rule_graph

  run agent_ready rules graph
  [ "$status" -eq 0 ]
  [[ "$output" == *"testing/behavior-only requires testing/unit-runner"* ]]
  [[ "$output" == *"team/runner overrides golfo:testing/unit-runner"* ]]
  [[ "$output" == *".agents/skills/add-tests/SKILL.md cites golfo:testing/unit-runner"* ]]
  [[ "$output" == *"3 rules, 3 edges."* ]]

  mkdir -p "$test_root/pack/profiles/base/rules" "$test_root/pack/profiles/base/skills/review"
  cp .agents/rules/testing.md "$test_root/pack/profiles/base/rules/"
  cp .agents/skills/add-tests/SKILL.md "$test_root/pack/profiles/base/skills/review/"
  cd "$test_root"
  run agent_ready rules graph --path pack --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; graph = json.load(sys.stdin); print(len(graph["nodes"]), sorted(edge["kind"] for edge in graph["edges"]))')" = "2 ['cites', 'requires']" ]
}
