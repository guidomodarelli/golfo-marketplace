#!/usr/bin/env bats
# Learning (#156, 156g): agent-ready learn reorganize consolidates, splits or turns into skills the rules
# the agent learned. Fixed triggers decide when, a fake provider proposes and checks the operations, and
# only an equivalent structural change is applied on its own.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-agent-ready/skills/agent-ready-setup"
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
  export AGENT_READY_LEARNING_SCHEDULER=none
  git -C "$project_dir" -c init.defaultBranch=main init -q
  cd "$project_dir"
  git config user.name Test
  git config user.email test@example.invalid
  git commit -q --allow-empty -m init
  fake_provider
}

teardown() {
  cd /
  rm -rf "$test_root"
}

agent_ready() {
  run --separate-stderr python3 -B "$cli" "$@"
}

registry_value() {
  PYTHONIOENCODING=utf-8 python3 -c 'import json, sys; data = json.load(open(".agents/learning/candidates.json", encoding="utf-8")); print(eval(sys.argv[1]))' "$1" | tr -d '\r'
}

write_manifest() {
  mkdir -p .agents
  printf '%s\n' "$1" > .agents/agent-ready.json
}

# A fake claude and codex on PATH: call N saves its stdin in $FAKE_INPUTS/N.txt and answers
# $FAKE_RESPONSES/N.json as its structured output; a call without a response fails.
fake_provider() {
  fake_bin="$test_root/bin"
  export FAKE_INPUTS="$test_root/inputs"
  export FAKE_RESPONSES="$test_root/responses"
  mkdir -p "$fake_bin" "$FAKE_INPUTS" "$FAKE_RESPONSES"
  cat > "$fake_bin/fake-provider.py" <<'PY'
import json, os, sys
number = len(os.listdir(os.environ["FAKE_INPUTS"])) + 1
# The team edits the rules while the provider answers: it locks this rule.
if os.environ.get("FAKE_LOCK_RULE") and number == 1:
    # The provider runs in a directory of its own: the test gives the file by its full path.
    path = os.environ["FAKE_LOCK_FILE"]
    rule = os.environ["FAKE_LOCK_RULE"]
    text = open(path, encoding="utf-8").read().replace(f"<!-- rule id={rule} -->", f"<!-- rule id={rule} locked -->")
    open(path, "w", encoding="utf-8", newline="\n").write(text)
with open(os.path.join(os.environ["FAKE_INPUTS"], f"{number}.txt"), "wb") as saved:
    saved.write(sys.stdin.buffer.read())
response = os.path.join(os.environ["FAKE_RESPONSES"], f"{number}.json")
if not os.path.exists(response):
    sys.exit(1)
print(json.dumps({"structured_output": json.load(open(response, encoding="utf-8"))}))
PY
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
[[ "\$1" == -p ]] || exit 0
python3 "$fake_bin/fake-provider.py"
EOF
  chmod +x "$fake_bin/claude"
  export PATH="$fake_bin:$PATH"
  export AGENT_READY_LEARNING_SWEEP_FOREGROUND=1
  unset CI
}

# respond N JSON: what call N of the provider answers.
respond() {
  printf '%s\n' "$2" > "$FAKE_RESPONSES/$1.json"
}

# learn "statement" [record options]: record an explicit instruction and write it as a rule.
learn() {
  agent_ready learn record --kind rule --statement "$1" --quote "siempre: $1" --explicit --session s1 "${@:2}"
  [ "$status" -eq 0 ]
  agent_ready learn apply "$(id_of "$1")"
  [ "$status" -eq 0 ]
}

id_of() {
  agent_ready learn list --json
  printf '%s' "$output" | python3 -c 'import json, sys; print([entry["id"] for entry in json.load(sys.stdin)["entries"] if entry["statement"] == sys.argv[1]][0])' "$1" | tr -d '\r'
}

rule_id_of() {
  registry_value "[entry['learned']['ruleId'] for entry in data['candidates'] if entry['statement'] == '$1'][0]"
}

# Over conflicts.contextBudget.rulesBytes (its minimum is 1024): the rules loaded at the start trigger it.
over_budget() {
  write_manifest '{"conflicts": {"contextBudget": {"rulesBytes": 1024}}}'
  mkdir -p .agents/rules
  python3 -c 'print("# Notes\n\n" + "Context of the team. " * 60)' > .agents/rules/notes.md
  git add .agents && git commit -q -m notes
}

consolidation() {
  printf '{"findings": [{"type": "consolidate", "ruleIds": ["%s", "%s"], "statements": ["%s"], "skill": {"name": "", "description": "", "body": ""}, "reason": "Two halves of one instruction."}]}' "$1" "$2" "$3"
}

proposal_id() {
  PYTHONIOENCODING=utf-8 python3 -c 'import json; print(json.load(open(".agents/learning/reorganize.json", encoding="utf-8"))["proposals"][0]["id"])' | tr -d '\r'
}

@test "without a trigger nothing is reviewed, and --plan says so without a model" {
  learn "Records carry the case number in the header."
  agent_ready learn reorganize --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"no trigger holds"* ]]
  agent_ready learn reorganize
  [ "$status" -eq 0 ]
  [[ "$output" == *"Reorganization: nothing to do"* ]]
  [ -z "$(ls "$FAKE_INPUTS")" ]
}

@test "an equivalent consolidation is applied in one commit, and learn revert brings the rules back" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number in the header and the date at the end.")"
  respond 2 '{"findings": [{"equivalent": true, "reason": "Both instructions stay."}]}'

  agent_ready learn reorganize
  [ "$status" -eq 0 ]
  [[ "$output" == *"trigger context-budget"* ]]
  [[ "$output" == *"applied  consolidate $header, $footer -> Records carry the case number in the header and the date at the end."* ]]
  # The rules are data for the provider, and the check sees them before and after.
  grep -q "Records carry the date at the end." "$FAKE_INPUTS/1.txt"
  grep -q "<before>" "$FAKE_INPUTS/2.txt"
  grep -Fq -- "- Records carry the case number in the header and the date at the end." .agents/rules/learned.md
  ! grep -q "$header -->" .agents/rules/learned.md
  ! grep -q "$footer -->" .agents/rules/learned.md
  agent_ready rules lint
  [ "$status" -eq 0 ]
  [ -z "$(git status --porcelain .agents)" ]
  git log -1 --format=%B | grep -q "^Reorganizes: "
  git log -1 --format=%B | grep -q "^Learned-from: s1:"
  grep -q " reorganize learn-.* (consolidate of " .agents/learning/log.md
  merged="$(id_of 'Records carry the case number in the header and the date at the end.')"
  [ "$(registry_value "[e['status'] for e in data['candidates'] if e['id'] == '$merged'][0]")" = "learned" ]
  [ "$(registry_value "sorted(e['status'] for e in data['candidates'] if e['id'] != '$merged')")" = "['superseded', 'superseded']" ]
  # The new rule keeps the evidence of both instructions.
  [ "$(registry_value "len([e for e in data['candidates'] if e['id'] == '$merged'][0]['evidence'])")" -eq 2 ]

  agent_ready learn revert "$merged"
  [ "$status" -eq 0 ]
  grep -Fq -- "- Records carry the case number in the header." .agents/rules/learned.md
  grep -Fq -- "- Records carry the date at the end." .agents/rules/learned.md
  grep -q "id=$header" .agents/rules/learned.md
  ! grep -q "and the date at the end" .agents/rules/learned.md
  [ "$(registry_value "sorted(e['status'] for e in data['candidates'])")" = "['learned', 'learned', 'reverted']" ]
  [ -z "$(git status --porcelain .agents)" ]
  git log -1 --format=%B | grep -q "^Reverts: "
}

@test "an operation the review finds not equivalent waits for the developer, who accepts it" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number.")"
  respond 2 '{"findings": [{"equivalent": false, "reason": "The date at the end is lost."}]}'

  agent_ready learn reorganize
  [ "$status" -eq 0 ]
  [[ "$output" == *"proposed reorg-"*"the review found that it changes the behavior"* ]]
  grep -Fq -- "- Records carry the date at the end." .agents/rules/learned.md
  [ -z "$(git status --porcelain .agents)" ]
  proposal="$(proposal_id)"

  agent_ready learn reorganize --plan
  [ "$status" -eq 0 ]
  [[ "$output" == *"$proposal  consolidate $header, $footer -> Records carry the case number."* ]]
  [[ "$output" == *"waits: the review found that it changes the behavior (The date at the end is lost.)"* ]]
  agent_ready learn status
  [[ "$output" == *"1 reorganizations wait for the developer"* ]]

  agent_ready learn reorganize --accept "$proposal"
  [ "$status" -eq 0 ]
  [[ "$output" == "$proposal  accepted: consolidate"* ]]
  ! grep -Fq -- "- Records carry the date at the end." .agents/rules/learned.md
  grep -q " reorganize (accepted) " .agents/learning/log.md
  [ -z "$(git status --porcelain .agents)" ]
  agent_ready learn reorganize --plan
  [[ "$output" != *"$proposal"* ]]
  # The developer decided: no second call reviewed it.
  [ ! -e "$FAKE_INPUTS/3.txt" ]
}

@test "a rule that becomes a skill always waits, and the developer can dismiss it" {
  learn "Records carry the case number in the header."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  respond 1 "{\"findings\": [{\"type\": \"to-skill\", \"ruleIds\": [\"$header\"], \"statements\": [], \"skill\": {\"name\": \"record-header\", \"description\": \"Put the case number in the header of a record.\", \"body\": \"1. Find the number.\\n2. Write it.\"}, \"reason\": \"A procedure.\"}]}"

  agent_ready learn reorganize
  [ "$status" -eq 0 ]
  [[ "$output" == *"proposed reorg-"*"a rule that becomes a skill always waits for the developer"* ]]
  # Without a check: nothing would be applied anyway.
  [ ! -e "$FAKE_INPUTS/2.txt" ]
  [ ! -e .agents/skills/record-header ]
  proposal="$(proposal_id)"

  agent_ready learn reorganize --dismiss "$proposal"
  [ "$status" -eq 0 ]
  [[ "$output" == "$proposal  dismissed: to-skill $header -> skill record-header"* ]]
  agent_ready learn reorganize --plan
  [[ "$output" != *"$proposal"* ]]
  [ -z "$(git status --porcelain .agents)" ]
}

@test "the developer accepts a rule that becomes a skill, and learn revert brings the rule back" {
  learn "Records carry the case number in the header."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  respond 1 "{\"findings\": [{\"type\": \"to-skill\", \"ruleIds\": [\"$header\"], \"statements\": [], \"skill\": {\"name\": \"record-header\", \"description\": \"Put the case number in the header of a record.\", \"body\": \"1. Find the number.\\n2. Write it.\"}, \"reason\": \"A procedure.\"}]}"
  agent_ready learn reorganize
  proposal="$(proposal_id)"

  agent_ready learn reorganize --accept "$proposal"
  [ "$status" -eq 0 ]
  grep -Fxq "name: record-header" .agents/skills/record-header/SKILL.md
  grep -Fxq "2. Write it." .agents/skills/record-header/SKILL.md
  # The learned file had only that rule: it goes with it.
  [ ! -e .agents/rules/learned.md ]
  skill="$(id_of 'Put the case number in the header of a record.')"

  agent_ready learn revert "$skill"
  [ "$status" -eq 0 ]
  [ ! -e .agents/skills/record-header ]
  grep -Fq -- "- Records carry the case number in the header." .agents/rules/learned.md
  [ -z "$(git status --porcelain .agents)" ]
}

@test "under developer-review, or with learning.reorganize.auto off, nothing is applied on its own" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number in the header and the date at the end.")"
  write_manifest '{"conflicts": {"contextBudget": {"rulesBytes": 1024}}, "learning": {"reorganize": {"auto": false}}}'

  agent_ready learn reorganize
  [ "$status" -eq 0 ]
  [[ "$output" == *"proposed reorg-"*"learning.reorganize.auto is off"* ]]
  [ ! -e "$FAKE_INPUTS/2.txt" ]
  grep -Fq -- "- Records carry the date at the end." .agents/rules/learned.md
}

@test "an operation on rules that are not learned, locked or contradicting the registry is dropped" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "{\"findings\": [
    {\"type\": \"consolidate\", \"ruleIds\": [\"$header\", \"team/other\"], \"statements\": [\"One.\"], \"skill\": {\"name\": \"\", \"description\": \"\", \"body\": \"\"}, \"reason\": \"\"},
    {\"type\": \"consolidate\", \"ruleIds\": [\"$header\", \"$footer\"], \"statements\": [\"Records carry the date at the end.\"], \"skill\": {\"name\": \"\", \"description\": \"\", \"body\": \"\"}, \"reason\": \"\"},
    {\"type\": \"split\", \"ruleIds\": [\"$header\"], \"statements\": [\"Only one.\"], \"skill\": {\"name\": \"\", \"description\": \"\", \"body\": \"\"}, \"reason\": \"\"}]}"

  agent_ready learn reorganize --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; report = json.load(sys.stdin); print(report["dropped"], len(report["applied"]), len(report["proposed"]))' | tr -d '\r')" = "3 0 0" ]
  [ ! -e "$FAKE_INPUTS/2.txt" ]
}

@test "a proposal whose rules changed after it was made is not written" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number.")"
  respond 2 '{"findings": [{"equivalent": false, "reason": "A rule is lost."}]}'
  agent_ready learn reorganize
  proposal="$(proposal_id)"
  python3 - <<'PY'
path = ".agents/rules/learned.md"
text = open(path, encoding="utf-8").read().replace("- Records carry the date at the end.", "- Records carry the date at the end.\n  - Details the team added.")
open(path, "w", encoding="utf-8", newline="\n").write(text)
PY

  agent_ready learn reorganize --accept "$proposal"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"changed after it was proposed"* ]]
  grep -q "Details the team added." .agents/rules/learned.md
}

@test "in CI the review calls no provider" {
  learn "Records carry the case number in the header."
  over_budget
  CI=true agent_ready learn reorganize
  [ "$status" -eq 0 ]
  [[ "$output" == *"no review under CI"* ]]
  [ -z "$(ls "$FAKE_INPUTS")" ]
}

@test "the end of a chat reorganizes in the background, at most once every learning.reorganize.minIntervalDays" {
  mkdir -p .agents
  printf '%s\n' '{"assets": {}, "profileOrder": ["software-development", "learning"]}' > .agents/agent-ready.lock.json
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number.")"
  respond 2 '{"findings": [{"equivalent": false, "reason": "A rule is lost."}]}'
  export AGENT_READY_LEARNING_NOW=2026-03-10T09:00:00+0000
  agent_ready learn episode --session chat --touch --provider claude
  agent_ready learn episode --session chat --end
  [ "$status" -eq 0 ]
  [[ "$output" == *"reorganize: 0 applied, 1 proposed for the developer, 0 dropped"* ]]
  [ -e "$FAKE_INPUTS/2.txt" ]

  # A day later the interval of 7 days has not passed: no provider is called again.
  export AGENT_READY_LEARNING_NOW=2026-03-11T09:00:00+0000
  agent_ready learn episode --session chat --touch --provider claude
  agent_ready learn episode --session chat --end
  [ "$status" -eq 0 ]
  [ ! -e "$FAKE_INPUTS/3.txt" ]
  # An explicit run does not wait for the interval.
  agent_ready learn reorganize
  [ -e "$FAKE_INPUTS/3.txt" ]
}

@test "a rule another rule requires is never reorganized away" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  printf '%s\n' '# Team' '' "<!-- rule id=team/header-format requires=$header -->" '- Write the case number in bold.' \
    > .agents/rules/team.md
  git add .agents && git commit -q -m team
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number in the header and the date at the end.")"

  agent_ready learn reorganize --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; report = json.load(sys.stdin); print(report["dropped"], len(report["applied"]))' | tr -d '\r')" = "1 0" ]
  [ ! -e "$FAKE_INPUTS/2.txt" ]
  grep -q "id=$header" .agents/rules/learned.md
}

@test "learn revert leaves a reorganized rule whose marker the team changed" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number in the header and the date at the end.")"
  respond 2 '{"findings": [{"equivalent": true, "reason": "Both instructions stay."}]}'
  agent_ready learn reorganize
  merged="$(id_of 'Records carry the case number in the header and the date at the end.')"
  merged_rule="$(rule_id_of 'Records carry the case number in the header and the date at the end.')"
  # Python, not sed -i: the sed of macOS takes a suffix after -i.
  python3 - "$merged_rule" <<'PY'
import sys
path = ".agents/rules/learned.md"
rule = sys.argv[1]
text = open(path, encoding="utf-8").read().replace(f"<!-- rule id={rule} -->", f"<!-- rule id={rule} locked -->")
open(path, "w", encoding="utf-8", newline="\n").write(text)
PY
  grep -q "id=$merged_rule locked" .agents/rules/learned.md

  agent_ready learn revert "$merged"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"changed after the reorganization"* ]]
  grep -q "id=$merged_rule locked" .agents/rules/learned.md
  ! grep -q "id=$header -->" .agents/rules/learned.md
}

@test "a background run without a trigger does not start the interval" {
  mkdir -p .agents
  printf '%s\n' '{"assets": {}, "profileOrder": ["software-development", "learning"]}' > .agents/agent-ready.lock.json
  learn "Records carry the case number in the header."
  export AGENT_READY_LEARNING_NOW=2026-03-10T09:00:00+0000
  agent_ready learn sweep --reorganize
  [ "$status" -eq 0 ]
  [ ! -e .git/info/agent-ready/reorganize.json ]

  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number.")"
  respond 2 '{"findings": [{"equivalent": false, "reason": "A rule is lost."}]}'
  agent_ready learn sweep --reorganize
  [ "$status" -eq 0 ]
  [ -e "$FAKE_INPUTS/1.txt" ]
  [ -e .git/info/agent-ready/reorganize.json ]
}

@test "the same operation proposed again on rules that changed replaces the stale proposal" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number.")"
  respond 2 '{"findings": [{"equivalent": false, "reason": "A rule is lost."}]}'
  agent_ready learn reorganize
  proposal="$(proposal_id)"
  python3 - <<'PY'
path = ".agents/rules/learned.md"
text = open(path, encoding="utf-8").read().replace("- Records carry the date at the end.", "- Records carry the date at the end.\n  - Details the team added.")
open(path, "w", encoding="utf-8", newline="\n").write(text)
PY
  git add .agents && git commit -q -m details
  agent_ready learn reorganize --plan
  [[ "$output" != *"$proposal"* ]]

  respond 3 "$(consolidation "$header" "$footer" "Records carry the case number.")"
  agent_ready learn reorganize
  [ "$status" -eq 0 ]
  agent_ready learn reorganize --plan
  [[ "$output" == *"$proposal  consolidate"* ]]
  [ "$(PYTHONIOENCODING=utf-8 python3 -c 'import json; print(len(json.load(open(".agents/learning/reorganize.json", encoding="utf-8"))["proposals"]))' | tr -d '\r')" -eq 1 ]
  agent_ready learn reorganize --accept "$proposal"
  [ "$status" -eq 0 ]
}

@test "a rule locked while the provider answers is not reorganized" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number in the header and the date at the end.")"
  respond 2 '{"findings": [{"equivalent": true, "reason": "Both instructions stay."}]}'
  # The team locks a rule while the first call runs.
  export FAKE_LOCK_RULE="$header" FAKE_LOCK_FILE="$PWD/.agents/rules/learned.md"
  agent_ready learn reorganize --json
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; report = json.load(sys.stdin); print(report["dropped"], len(report["applied"]))' | tr -d '\r')" = "1 0" ]
  grep -q "id=$header locked" .agents/rules/learned.md
  grep -Fq -- "- Records carry the date at the end." .agents/rules/learned.md
}

@test "learn revert puts the rules back in the file the team had moved them to" {
  learn "Records carry the case number in the header."
  learn "Records carry the date at the end."
  over_budget
  mv .agents/rules/learned.md .agents/rules/policies.md
  git add -A .agents && git commit -q -m move
  header="$(rule_id_of 'Records carry the case number in the header.')"
  footer="$(rule_id_of 'Records carry the date at the end.')"
  respond 1 "$(consolidation "$header" "$footer" "Records carry the case number in the header and the date at the end.")"
  respond 2 '{"findings": [{"equivalent": true, "reason": "Both instructions stay."}]}'
  agent_ready learn reorganize
  [[ "$output" == *"applied  consolidate"* ]]
  merged="$(id_of 'Records carry the case number in the header and the date at the end.')"

  agent_ready learn revert "$merged"
  [ "$status" -eq 0 ]
  grep -Fq -- "- Records carry the case number in the header." .agents/rules/policies.md
  grep -Fq -- "- Records carry the date at the end." .agents/rules/policies.md
  [ ! -e .agents/rules/learned.md ]
}
