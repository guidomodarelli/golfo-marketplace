#!/usr/bin/env bats
# Learning (#156): agent-ready learn record|status|list keep the instructions of the user in
# .agents/learning/candidates.json, count distinct episodes and decide from fixed rules of evidence
# whether one is learned now. No provider is called.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  cli="$skill_dir/scripts/agent-ready"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  project_dir="$test_root/project"
  mkdir -p "$project_dir" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CONFIG_HOME="$test_root/config"
  export XDG_CACHE_HOME="$test_root/cache"
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
  run --separate-stderr python3 -B "$cli" "$@"
}

header_rule() {
  agent_ready learn record --kind rule --key records.header \
    --statement "Records carry the case number in the header." "$@"
}

registry_value() {
  PYTHONIOENCODING=utf-8 python3 -c 'import json, sys; data = json.load(open(".agents/learning/candidates.json", encoding="utf-8")); print(eval(sys.argv[1]))' "$1" | tr -d '\r'
}

write_manifest() {
  mkdir -p .agents
  printf '%s\n' "$1" > .agents/agent-ready.json
}

@test "an explicit instruction is learned at once, and only the registry keeps the quote" {
  header_rule --quote "de ahora en más, el número de expediente va en el encabezado de las actas" \
    --explicit --session s1
  [ "$status" -eq 0 ]
  [[ "$output" == "learn-"*"  learn: learn it now: write it as a rule of the project"* ]]
  [ "$(registry_value 'data["candidates"][0]["evidence"][0]["quote"]')" = \
    "de ahora en más, el número de expediente va en el encabezado de las actas" ]
  [ "$(registry_value 'data["candidates"][0]["evidence"][0]["source"]')" = "in-session" ]

  agent_ready learn list
  [ "$status" -eq 0 ]
  [[ "$output" == *"candidate  rule  1 episodes  key=records.header"* ]]
  agent_ready learn list --json
  [[ "$output" != *"expediente"* ]]
  agent_ready learn status --json
  [[ "$output" != *"expediente"* ]]
}

@test "an implicit instruction waits for a second episode: repeating it in the same one counts once" {
  header_rule --quote "poné el número de expediente arriba" --session s1
  [ "$status" -eq 0 ]
  [[ "$output" == *"wait: keep it as a candidate until another episode repeats it (1 of 2)"* ]]
  # Same session and day: the same episode, even reworded in case and punctuation.
  agent_ready learn record --kind rule --statement "records carry the case number in the header" \
    --quote "otra vez, el número arriba" --session s1
  [[ "$output" == *"(1 of 2)"* ]]
  [ "$(registry_value 'len(data["candidates"])')" -eq 1 ]
  [ "$(registry_value 'len(data["candidates"][0]["evidence"])')" -eq 2 ]

  # Another session is another episode.
  header_rule --quote "el número de expediente, arriba" --session s2
  [[ "$output" == *"  learn: "* ]]

  # The episode a hook reports splits one long session in two.
  agent_ready learn record --kind rule --statement "Reports end with the sources." --quote "cerrá con las fuentes" \
    --session long --episode long-1
  [[ "$output" == *"(1 of 2)"* ]]
  agent_ready learn record --kind rule --statement "Reports end with the sources." --quote "las fuentes al final" \
    --session long --episode long-2
  [[ "$output" == *"  learn: "* ]]
}

@test "the threshold and developer-review mode change the decision" {
  write_manifest '{"learning": {"threshold": 1}}'
  header_rule --quote "número arriba" --session s1
  [[ "$output" == *"  learn: "* ]]

  write_manifest '{"learning": {"mode": "developer-review"}}'
  header_rule --quote "número arriba" --explicit --session s2
  [ "$status" -eq 0 ]
  [[ "$output" == *"  propose: learning.mode is developer-review: leave it for the developer, write nothing"* ]]
  agent_ready learn status
  [[ "$output" == "Learning: developer-review, 2 episodes to learn"* ]]
}

@test "a candidate without evidence for candidateTtlDays expires, and old evidence never counts again" {
  write_manifest '{"learning": {"candidateTtlDays": 30}}'
  old_date="$(python3 -c 'import datetime; print(datetime.date.today() - datetime.timedelta(days=40))')"
  header_rule --quote "número arriba" --session s1 --date "$old_date"
  [[ "$output" == *"  wait: "* ]]
  agent_ready learn list --status expired
  [[ "$output" == *"expired  rule"* ]]
  agent_ready learn status
  [[ "$output" == *"0 candidate, 0 learned, 0 superseded, 1 expired"* ]]

  # It comes back with today's evidence, but the expired episode does not add up to the threshold.
  header_rule --quote "número arriba otra vez" --session s2
  [[ "$output" == *"(1 of 2)"* ]]
  [ "$(registry_value 'data["candidates"][0]["status"]')" = "candidate" ]
}

@test "another statement on the same key is reported, so the agent can replace it" {
  header_rule --quote "número arriba" --explicit --session s1
  agent_ready learn record --kind rule --key records.header --statement "Records carry the case number in the footer." \
    --quote "no, el número va al pie" --explicit --session s1
  [ "$status" -eq 0 ]
  [[ "$output" == *"same key records.header: learn-"*"(candidate) Records carry the case number in the header."* ]]
  agent_ready learn record --kind rule --key records.header --statement "Records carry the case number in the footer." \
    --quote "al pie" --session s2 --json
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; print(len(json.load(sys.stdin)["sameKey"]))')" -eq 1 ]
}

@test "record refuses an instruction that cannot become one atomic rule, or evidence that is not real" {
  agent_ready learn record --kind rule --statement $'First line.\nSecond line.' --quote "x"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"--statement has several lines"* ]]
  write_manifest '{"rules": {"maxStatementChars": 20, "statementWarnChars": 10}}'
  header_rule --quote "x"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"over rules.maxStatementChars (20)"* ]]
  rm .agents/agent-ready.json
  agent_ready learn record --kind rule --key Records.Header --statement "A rule." --quote "x"
  [[ "$stderr" == *"--key 'Records.Header' must be lowercase segments joined by dots"* ]]
  header_rule --quote "   "
  [[ "$stderr" == *"--quote is empty"* ]]
  header_rule --quote "x" --date 2999-01-01
  [[ "$stderr" == *"--date 2999-01-01 is in the future"* ]]
  [ ! -e .agents/learning/candidates.json ]
}

@test "learning.enabled false records nothing, and status still reads the registry" {
  header_rule --quote "número arriba" --session s1
  write_manifest '{"learning": {"enabled": false}}'
  header_rule --quote "número arriba" --session s2
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"learning.enabled is off: nothing was recorded."* ]]
  [ "$(registry_value 'len(data["candidates"][0]["evidence"])')" -eq 1 ]
  agent_ready learn status
  [[ "$output" == "Learning: off,"* ]]
}

@test "two sessions recording at the same time keep both instructions" {
  for index in 1 2 3 4; do
    python3 -B "$cli" learn record --kind rule --statement "Rule number $index." --quote "regla $index" \
      --session "s$index" > /dev/null &
  done
  wait
  [ "$(registry_value 'len(data["candidates"])')" -eq 4 ]
}
