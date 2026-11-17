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
  [[ "$output" == "learn-"*"  learn: learn it now as a rule of the project: agent-ready learn apply learn-"* ]]
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

days_ago() {
  python3 -c 'import datetime, sys; print(datetime.date.today() - datetime.timedelta(days=int(sys.argv[1])))' "$1" | tr -d '\r'
}

@test "repetitions that each arrive before the candidate expires all count, however long the series" {
  write_manifest '{"learning": {"threshold": 3, "candidateTtlDays": 90}}'
  header_rule --quote "número arriba" --session s1 --date "$(days_ago 120)"
  header_rule --quote "número arriba" --session s2 --date "$(days_ago 60)"
  header_rule --quote "número arriba" --session s3
  [[ "$output" == *"  learn: "* ]]
}

@test "an explicit request that expired does not skip the threshold when the instruction comes back" {
  write_manifest '{"learning": {"candidateTtlDays": 30}}'
  header_rule --quote "de ahora en más, número arriba" --explicit --session s1 --date "$(days_ago 40)"
  header_rule --quote "número arriba" --session s2
  [[ "$output" == *"wait: keep it as a candidate until another episode repeats it (1 of 2)"* ]]
  agent_ready learn list --json
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; print(json.load(sys.stdin)["entries"][0]["explicit"])')" = "False" ]
}

@test "two sessions recording at the same time keep both instructions" {
  writer_pids=()
  for index in 1 2 3 4; do
    python3 -B "$cli" learn record --kind rule --statement "Rule number $index." --quote "regla $index" \
      --session "s$index" > /dev/null &
    writer_pids+=("$!")
  done
  # Only the writers: a bare wait would also wait for the timer of BATS_TEST_TIMEOUT.
  wait "${writer_pids[@]}"
  [ "$(registry_value 'len(data["candidates"])')" -eq 4 ]
}

# 156b: writing what was learned.

commit_identity() {
  git config user.name Test
  git config user.email test@example.invalid
  git commit -q --allow-empty -m init
}

id_of() {
  agent_ready learn list --json
  printf '%s' "$output" | python3 -c 'import json, sys; print([entry["id"] for entry in json.load(sys.stdin)["entries"] if sys.argv[1] in entry["statement"]][0])' "$1" | tr -d '\r'
}

# A managed rule an apply wrote: the lock names its profile, so it is golfo's.
managed_rule() {
  mkdir -p .agents/rules
  printf '%s\n' '# Testing' '' "<!-- rule id=testing/runner key=testing.unit-runner $1 -->" '- Use Vitest.' \
    > .agents/rules/testing.md
  printf '%s\n' '{"assets": {".agents/rules/testing.md": {"profile": "software-development", "sha256": "x", "state": "applied"}}}' \
    > .agents/agent-ready.lock.json
}

@test "apply writes an explicit instruction as a rule of the project, in one commit with its trailers and log line" {
  commit_identity
  printf 'work in progress\n' > notes.txt
  git add notes.txt
  header_rule --quote "de ahora en más, número arriba" --explicit --session s1
  [[ "$output" == *"agent-ready learn apply learn-"* ]]
  candidate="$(id_of 'header')"

  agent_ready learn apply "$candidate"
  [ "$status" -eq 0 ]
  [[ "$output" == "$candidate  create: learned/records-header in .agents/rules/learned.md (commit "* ]]
  grep -Fxq '<!-- rule id=learned/records-header key=records.header -->' .agents/rules/learned.md
  grep -Fxq -- '- Records carry the case number in the header.' .agents/rules/learned.md
  agent_ready rules lint
  [ "$status" -eq 0 ]
  grep -Fq "create $candidate (learned/records-header): Records carry the case number in the header." .agents/learning/log.md
  [ "$(registry_value 'data["candidates"][0]["status"]')" = "learned" ]
  # One commit with the rule, the registry and the log; what the user had staged stays out of it.
  [ "$(git log -1 --format=%B | grep -c "^Learning-Id: $candidate$")" -eq 1 ]
  git log -1 --format=%B | grep -q '^Learned-from: s1:'
  [ "$(git show --name-only --format= HEAD | sort | tr '\n' ' ')" = \
    ".agents/learning/candidates.json .agents/learning/log.md .agents/rules/learned.md " ]
  git diff --cached --name-only | grep -Fxq notes.txt

  agent_ready learn apply "$candidate"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"is not learned: it is already learned"* ]]
}

@test "a newer instruction on the same key replaces the learned one in place, and the old one is superseded" {
  commit_identity
  header_rule --quote "número arriba" --explicit --session s1
  agent_ready learn apply "$(id_of 'header')"
  agent_ready learn record --kind rule --key records.header --statement "Records carry the case number in the footer." \
    --quote "no, al pie" --explicit --session s2
  footer="$(id_of 'footer')"
  agent_ready learn apply "$footer"
  [ "$status" -eq 0 ]
  [[ "$output" == *"supersede: learned/records-header in .agents/rules/learned.md, replaces learn-"* ]]
  [ "$(grep -c '^<!-- rule' .agents/rules/learned.md)" -eq 1 ]
  grep -Fxq -- '- Records carry the case number in the footer.' .agents/rules/learned.md
  agent_ready learn list --status superseded
  [[ "$output" == *"Records carry the case number in the header."* ]]
  [ "$(git log --format=%s | grep -c '^learn: ')" -eq 2 ]
}

@test "a rule the team wrote on the same key is edited in place and keeps its exceptions" {
  commit_identity
  mkdir -p .agents/rules
  printf '%s\n' '# Records' '' '<!-- rule id=records/header key=records.header -->' '- Records carry the date in the header.' \
    '  - Except: drafts.' > .agents/rules/records.md
  header_rule --quote "de ahora en más, el número arriba" --explicit --session s1
  agent_ready learn apply "$(id_of 'case number')"
  [ "$status" -eq 0 ]
  [[ "$output" == *"update: records/header in .agents/rules/records.md"* ]]
  grep -Fxq -- '- Records carry the case number in the header.' .agents/rules/records.md
  grep -Fxq -- '  - Except: drafts.' .agents/rules/records.md
  [ ! -e .agents/rules/learned.md ]
}

@test "a managed rule on the same key is replaced with overrides and never edited; a locked one stops the learning" {
  commit_identity
  managed_rule ""
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use the test runner of the project." \
    --quote "de ahora en más, usá el runner del proyecto" --explicit --session s1
  candidate="$(id_of 'runner of the project')"
  agent_ready learn apply "$candidate"
  [ "$status" -eq 0 ]
  [[ "$output" == *"create: learned/testing-unit-runner in .agents/rules/learned.md, overrides golfo:testing/runner"* ]]
  grep -Fxq '<!-- rule id=learned/testing-unit-runner key=testing.unit-runner overrides=golfo:testing/runner -->' \
    .agents/rules/learned.md
  grep -Fxq -- '- Use Vitest.' .agents/rules/testing.md

  # Locked: nothing is written or committed, and the message says why.
  rm -rf .agents/learning .agents/rules/learned.md
  managed_rule locked
  commits="$(git rev-list --count HEAD)"
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use the test runner of the project." \
    --quote "de ahora en más, usá el runner del proyecto" --explicit --session s1
  agent_ready learn apply "$(id_of 'runner of the project')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"golfo:testing/runner decides testing.unit-runner and is locked: it cannot change, so nothing was saved"* ]]
  [ ! -e .agents/rules/learned.md ]
  [ "$(git rev-list --count HEAD)" -eq "$commits" ]
  [ "$(registry_value 'data["candidates"][0]["status"]')" = "candidate" ]
}

@test "apply refuses what record did not decide to learn, and asks for the folder or the skill it needs" {
  commit_identity
  header_rule --quote "número arriba" --session s1
  agent_ready learn apply "$(id_of 'header')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"it waits for another episode, or it expired"* ]]
  write_manifest '{"learning": {"mode": "developer-review"}}'
  header_rule --quote "de ahora en más, número arriba" --explicit --session s2
  agent_ready learn apply "$(id_of 'header')"
  [[ "$stderr" == *"learning.mode is developer-review: the developer decides"* ]]
  rm .agents/agent-ready.json
  agent_ready learn apply learn-0000000000
  [[ "$stderr" == *"no entry has the id learn-0000000000"* ]]

  agent_ready learn record --kind nested --statement "Invoices round to two decimals." --quote "siempre dos decimales" \
    --explicit --session s1
  agent_ready learn apply "$(id_of 'Invoices')"
  [[ "$stderr" == *"is only for one folder: record it with --paths"* ]]
  agent_ready learn record --kind nested --statement "Invoices round to two decimals." --quote "siempre dos decimales" \
    --paths "billing/**" --explicit --session s1
  agent_ready learn apply "$(id_of 'Invoices')"
  [ "$status" -eq 0 ]
  # A rule for some folders goes to a file whose frontmatter keeps the scope Claude reads.
  grep -Fq 'paths=billing/** -->' .agents/rules/learned-billing.md
  [ "$(sed -n 1,4p .agents/rules/learned-billing.md | tr '\n' '|')" = '---|paths:|  - "billing/**"|---|' ]
  [ ! -e .agents/rules/learned.md ]
  agent_ready rules lint
  [ "$status" -eq 0 ]

  agent_ready learn record --kind skill --statement "Draft a record in four steps." --quote "siempre así: paso 1..." \
    --explicit --session s1
  skill="$(id_of 'four steps')"
  agent_ready learn apply "$skill"
  [[ "$stderr" == *"is a skill: write it under .agents/skills/<name>/ and pass --skill"* ]]
  agent_ready learn apply "$skill" --skill notes
  [[ "$stderr" == *"must be a directory directly under .agents/skills/"* ]]
  mkdir -p .agents/skills/draft-record
  printf -- '---\nname: draft-record\ndescription: Draft a record.\n---\n1. Header.\n' > .agents/skills/draft-record/SKILL.md
  agent_ready learn apply "$skill" --skill .agents/skills/draft-record
  [ "$status" -eq 0 ]
  [[ "$output" == *"create: .agents/skills/draft-record in .agents/skills/draft-record"* ]]
  git show --name-only --format= HEAD | grep -Fxq .agents/skills/draft-record/SKILL.md
}

@test "a locked rule stops the learning even when a rule of the project decides the same key" {
  commit_identity
  managed_rule locked
  printf '%s\n' '# Team' '' '<!-- rule id=team/runner key=testing.unit-runner overrides=golfo:testing/runner -->' \
    '- Use Jest.' > .agents/rules/team.md
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use the test runner of the project." \
    --quote "de ahora en más, el runner del proyecto" --explicit --session s1
  agent_ready learn apply "$(id_of 'runner of the project')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"golfo:testing/runner decides testing.unit-runner and is locked"* ]]
  grep -Fxq -- '- Use Jest.' .agents/rules/team.md

  printf '%s\n' '# Team' '' '<!-- rule id=team/runner key=testing.unit-runner locked -->' '- Use Jest.' > .agents/rules/team.md
  rm .agents/agent-ready.lock.json .agents/rules/testing.md
  agent_ready learn apply "$(id_of 'runner of the project')"
  [[ "$stderr" == *"project:team/runner decides testing.unit-runner and is locked"* ]]
  grep -Fxq -- '- Use Jest.' .agents/rules/team.md
}

@test "a rule of the core, or of another scope, is never replaced by a learned rule" {
  commit_identity
  managed_rule ""
  sed -i.bak 's/"software-development"/"common"/' .agents/agent-ready.lock.json && rm .agents/agent-ready.lock.json.bak
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use the test runner of the project." \
    --quote "de ahora en más, el runner del proyecto" --explicit --session s1
  agent_ready learn apply "$(id_of 'runner of the project')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"belongs to the core, which a rule cannot override yet: nothing was saved"* ]]
  [ ! -e .agents/rules/learned.md ]

  rm .agents/agent-ready.lock.json .agents/rules/testing.md
  printf '%s\n' '# Team' '' '<!-- rule id=team/runner key=testing.unit-runner -->' '- Use Vitest.' > .agents/rules/team.md
  agent_ready learn record --kind nested --key testing.unit-runner --statement "Use pytest." --paths "backend/**" \
    --quote "en backend, siempre pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"project:team/runner decides testing.unit-runner for the whole repository, and the instruction is for backend/**"* ]]
  grep -Fxq -- '- Use Vitest.' .agents/rules/team.md
}

@test "a statement that is not one atomic decision is refused before anything is written" {
  commit_identity
  agent_ready learn record --kind rule --statement "Use pytest; run the tests before committing." \
    --quote "siempre pytest y correr los tests" --explicit --session s1
  commits="$(git rev-list --count HEAD)"
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"would not be a valid atomic rule, so nothing was written"*"several-decisions"* ]]
  [ ! -e .agents/rules/learned.md ]
  [ "$(git rev-list --count HEAD)" -eq "$commits" ]
}

@test "a replaced instruction is not applied again from its old evidence, but the user can bring it back" {
  commit_identity
  header_rule --quote "de ahora en más, número arriba" --explicit --session s1
  header="$(id_of 'header')"
  agent_ready learn apply "$header"
  agent_ready learn record --kind rule --key records.header --statement "Records carry the case number in the footer." \
    --quote "no, al pie" --explicit --session s2
  agent_ready learn apply "$(id_of 'footer')"

  agent_ready learn apply "$header"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"$header was replaced by learn-"* ]]

  # Said again without «always»: a fresh candidate, whose old explicit evidence does not count.
  header_rule --quote "mejor arriba" --session s3
  [[ "$output" == *"wait: keep it as a candidate until another episode repeats it (1 of 2)"* ]]
  header_rule --quote "arriba, dije" --session s4
  [[ "$output" == *"  learn: "* ]]
  agent_ready learn apply "$header"
  [ "$status" -eq 0 ]
  [[ "$output" == *"supersede: learned/records-header"*"replaces learn-"* ]]
  grep -Fxq -- '- Records carry the case number in the header.' .agents/rules/learned.md
}

@test "replacing a statement takes all of it, also an indented continuation after a blank line" {
  commit_identity
  mkdir -p .agents/rules
  printf '%s\n' '# Testing' '' '<!-- rule id=testing/runner key=testing.unit-runner -->' '- Run the tests with' '' \
    '  `vitest`.' '  - Except: the e2e suite.' > .agents/rules/team.md
  agent_ready rules lint
  [ "$status" -eq 0 ]
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Run the tests with pytest." \
    --quote "de ahora en más, pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -eq 0 ]
  ! grep -Fq 'vitest' .agents/rules/team.md
  grep -Fxq -- '- Run the tests with pytest.' .agents/rules/team.md
  grep -Fxq -- '  - Except: the e2e suite.' .agents/rules/team.md
}

@test "a rule of the project that requires another one can be updated by a learning" {
  commit_identity
  mkdir -p .agents/rules
  printf '%s\n' '# Team' '' '<!-- rule id=team/base -->' '- Keep tests next to the code.' '' \
    '<!-- rule id=team/tests key=testing.unit-runner requires=team/base -->' '- Use Vitest.' > .agents/rules/team.md
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use pytest." \
    --quote "de ahora en más, pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -eq 0 ]
  [[ "$output" == *"update: team/tests in .agents/rules/team.md"* ]]
  grep -Fxq -- '- Use pytest.' .agents/rules/team.md
}

@test "every managed rule of the key is replaced, and one that already replaces another stops the learning" {
  commit_identity
  mkdir -p .agents/rules
  printf '%s\n' '# Testing' '' '<!-- rule id=testing/runner key=testing.unit-runner -->' '- Use Vitest.' > .agents/rules/testing.md
  printf '%s\n' '# Web' '' '<!-- rule id=web/runner key=testing.unit-runner -->' '- Use Vitest.' > .agents/rules/web.md
  printf '%s\n' '{"assets": {".agents/rules/testing.md": {"profile": "software-development", "sha256": "x", "state": "applied"},' \
    '".agents/rules/web.md": {"profile": "react", "sha256": "x", "state": "applied"}}}' > .agents/agent-ready.lock.json
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use pytest." \
    --quote "de ahora en más, pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -eq 0 ]
  grep -Fq 'overrides=golfo:testing/runner,golfo:web/runner -->' .agents/rules/learned.md

  rm -rf .agents/learning .agents/rules/learned.md
  printf '%s\n' '# Web' '' '<!-- rule id=web/runner key=testing.unit-runner overrides=golfo:testing/runner -->' '- Use Jest.' \
    > .agents/rules/web.md
  rm .agents/rules/testing.md
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use pytest." \
    --quote "de ahora en más, pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"golfo:web/runner decides testing.unit-runner and already replaces golfo:testing/runner"* ]]
  [ ! -e .agents/rules/learned.md ]
}

@test "two active rules on the key make the learning ambiguous, but a managed rule the project replaces does not count" {
  commit_identity
  mkdir -p .agents/rules
  printf '%s\n' '# Team' '' '<!-- rule id=team/runner key=testing.unit-runner -->' '- Use Vitest.' > .agents/rules/team.md
  printf '%s\n' '# Web' '' '<!-- rule id=web/runner key=testing.unit-runner -->' '- Use Vitest.' > .agents/rules/web.md
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use pytest." \
    --quote "de ahora en más, pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"project:team/runner, project:web/runner all decide testing.unit-runner"* ]]
  grep -Fxq -- '- Use Vitest.' .agents/rules/team.md

  # The project rule replaces the managed one, so only the project rule is in force.
  mv .agents/rules/web.md .agents/rules/testing.md
  sed -i.bak 's#web/runner#testing/runner#' .agents/rules/testing.md && rm .agents/rules/testing.md.bak
  printf '%s\n' '{"assets": {".agents/rules/testing.md": {"profile": "software-development", "sha256": "x", "state": "applied"}}}' \
    > .agents/agent-ready.lock.json
  printf '%s\n' '# Team' '' '<!-- rule id=team/runner key=testing.unit-runner overrides=golfo:testing/runner -->' \
    '- Use Jest.' > .agents/rules/team.md
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Use pytest.' .agents/rules/team.md
  grep -Fxq -- '- Use Vitest.' .agents/rules/testing.md
}

@test "a managed rule that a rule of another key already replaces is not replaced twice" {
  commit_identity
  managed_rule ""
  printf '%s\n' '# Team' '' '<!-- rule id=team/runner overrides=golfo:testing/runner -->' '- Use Jest.' > .agents/rules/team.md
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use pytest." \
    --quote "de ahora en más, pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'pytest')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"golfo:testing/runner decides testing.unit-runner and team/runner (.agents/rules/team.md) already replaces it"* ]]
  [ ! -e .agents/rules/learned.md ]
}

@test "the paths: of the file of a rule are its scope, as Claude reads it" {
  commit_identity
  mkdir -p .agents/rules
  printf '%s\n' '---' 'paths: ["backend/**"]' '---' '# Backend' '' '<!-- rule id=backend/runner key=testing.unit-runner -->' \
    '- Use unittest.' > .agents/rules/backend.md
  agent_ready learn record --kind rule --key testing.unit-runner --statement "Use pytest everywhere." \
    --quote "de ahora en más, pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'everywhere')"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"project:backend/runner decides testing.unit-runner for backend/**, and the instruction is for the whole repository"* ]]

  agent_ready learn record --kind nested --key testing.unit-runner --statement "Use pytest." --paths "backend/**" \
    --quote "en backend, siempre pytest" --explicit --session s1
  agent_ready learn apply "$(id_of 'Use pytest.')"
  [ "$status" -eq 0 ]
  [[ "$output" == *"update: backend/runner in .agents/rules/backend.md"* ]]
  grep -Fxq -- '- Use pytest.' .agents/rules/backend.md
}

# 156c: what the developer decides.

@test "in developer-review mode status lists the proposals, and only learn accept writes them" {
  commit_identity
  write_manifest '{"learning": {"mode": "developer-review"}}'
  header_rule --quote "de ahora en más, número arriba" --explicit --session s1
  candidate="$(id_of 'header')"
  agent_ready learn status
  [[ "$output" == *"Proposals for the developer (agent-ready learn accept <id>, or reject <id>):"*"$candidate  Records carry the case number in the header."* ]]
  agent_ready learn status --json
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; print(json.load(sys.stdin)["proposals"][0])' | tr -d '\r')" = "$candidate" ]
  agent_ready learn apply "$candidate"
  [ "$status" -ne 0 ]

  agent_ready learn accept "$candidate"
  [ "$status" -eq 0 ]
  [[ "$output" == "$candidate  create: learned/records-header in .agents/rules/learned.md (commit "* ]]
  [ "$(registry_value 'data["candidates"][0]["learned"]["accepted"]')" = "True" ]
  grep -Fq "create (accepted) $candidate" .agents/learning/log.md
}

@test "a rejected entry is never learned by the agent, and learn accept brings it back" {
  commit_identity
  header_rule --quote "número arriba" --session s1
  candidate="$(id_of 'header')"
  agent_ready learn reject "$candidate"
  [ "$status" -eq 0 ]
  [[ "$output" == "$candidate  rejected (commit "* ]]
  git log -1 --format=%B | grep -Fxq "Learning-Id: $candidate"
  grep -Fq "reject $candidate: Records carry the case number in the header." .agents/learning/log.md

  # The user insists, even explicitly: the developer's decision holds.
  header_rule --quote "de ahora en más, número arriba" --explicit --session s2
  [[ "$output" == *"  rejected: the developer rejected it: write nothing (agent-ready learn accept $candidate brings it back)"* ]]
  agent_ready learn apply "$candidate"
  [[ "$stderr" == *"the developer rejected it; learn accept brings it back"* ]]
  agent_ready learn reject "$candidate"
  [[ "$stderr" == *"is already rejected"* ]]

  agent_ready learn accept "$candidate"
  [ "$status" -eq 0 ]
  grep -Fxq -- '- Records carry the case number in the header.' .agents/rules/learned.md
  agent_ready learn reject "$candidate"
  [[ "$stderr" == *"is learned: undo it with agent-ready learn revert $candidate"* ]]
}

@test "revert undoes a learning in its rule, keeps later changes, and brings back what it replaced" {
  commit_identity
  header_rule --quote "de ahora en más, número arriba" --explicit --session s1
  header="$(id_of 'header')"
  agent_ready learn apply "$header"
  agent_ready learn record --kind rule --key records.header --statement "Records carry the case number in the footer." \
    --quote "no, al pie" --explicit --session s2
  footer="$(id_of 'footer')"
  agent_ready learn apply "$footer"
  # A later learning in the same file stays when the earlier one is reverted.
  agent_ready learn record --kind rule --statement "Reports end with the sources." --quote "siempre las fuentes" \
    --explicit --session s2
  agent_ready learn apply "$(id_of 'sources')"

  agent_ready learn revert "$footer"
  [ "$status" -eq 0 ]
  [[ "$output" == "$footer  reverted: .agents/rules/learned.md as before commit "*", $header is learned again (commit "* ]]
  grep -Fxq -- '- Records carry the case number in the header.' .agents/rules/learned.md
  grep -Fxq -- '- Reports end with the sources.' .agents/rules/learned.md
  agent_ready learn list --status learned
  [[ "$output" == *"$header  learned"* ]]
  git log -1 --format=%B | grep -q "^Reverts: [0-9a-f]\{40\}$"
  grep -Fq "revert $footer (.agents/rules/learned.md, commit " .agents/learning/log.md
  agent_ready learn revert "$footer"
  [[ "$stderr" == *"$footer is reverted, not learned: there is nothing to revert"* ]]

  # Said again, a reverted instruction is a fresh candidate.
  agent_ready learn record --kind rule --key records.header --statement "Records carry the case number in the footer." \
    --quote "al pie, otra vez" --session s3
  [[ "$output" == *"wait: keep it as a candidate until another episode repeats it (1 of 2)"* ]]
}

@test "revert refuses a rule that changed after the learning, and changes nothing" {
  commit_identity
  header_rule --quote "de ahora en más, número arriba" --explicit --session s1
  header="$(id_of 'header')"
  agent_ready learn apply "$header"
  sed -i.bak 's/in the header\./in the header, in bold./' .agents/rules/learned.md && rm .agents/rules/learned.md.bak
  git commit -qam "team edit"
  commits="$(git rev-list --count HEAD)"
  agent_ready learn revert "$header"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *".agents/rules/learned.md changed after the learning: rule learned/records-header no longer says what $header wrote; nothing was reverted"* ]]
  grep -Fq 'in the header, in bold.' .agents/rules/learned.md
  [ "$(git rev-list --count HEAD)" -eq "$commits" ]
  [ "$(registry_value 'data["candidates"][0]["status"]')" = "learned" ]
}

@test "revert removes a learned skill" {
  commit_identity
  agent_ready learn record --kind skill --statement "Draft a record in four steps." --quote "siempre así" --explicit --session s1
  skill="$(id_of 'four steps')"
  mkdir -p .agents/skills/draft-record
  printf -- '---\nname: draft-record\ndescription: Draft a record.\n---\n1. Header.\n' > .agents/skills/draft-record/SKILL.md
  agent_ready learn apply "$skill" --skill .agents/skills/draft-record
  agent_ready learn revert "$skill"
  [ "$status" -eq 0 ]
  [ ! -e .agents/skills/draft-record/SKILL.md ]
  [ -z "$(git status --porcelain -- .agents/skills)" ]
}
