#!/usr/bin/env bats

bats_require_minimum_version 1.13.0

load 'test_helper/eval-runner'

# --triggers measures the description: each request runs against a copy of the frontmatter under a
# unique name, and passes when the first tool call picks that copy exactly when it should.

setup() {
    unset EVAL_CONFIG
    setup_eval_runner_fixture
    printf 'Body that the trigger run must not see.\n' >> "${SKILL_DIR}/SKILL.md"
    STUB_LOG="${TEST_ROOT}/stub.log"
    : > "${STUB_LOG}"
    install_trigger_stub
}

# A claude that answers the provider check like the real one and, for a trigger run (stream-json),
# emits the init event and one tool call: the copy of the skill for a query with TRIGGER, Bash for one
# with IGNORE, and an init without the copy for one with NOLOAD. FLIP alternates between both.
install_trigger_stub() {
    cat > "${STUB_BIN}/claude" <<'CLAUDE_STUB'
#!/bin/bash
if [[ "$*" != *"stream-json"* ]]; then
  jq -n '{type: "result", is_error: false, result: "eval-provider-ready", total_cost_usd: 0, num_turns: 1, usage: {}}'
  exit 0
fi
stub_dir=$(ls -d .claude/skills/*/ 2>/dev/null | head -1)
name=$(basename "$stub_dir")
{
  echo "args=$*"
  echo "skill_md_name=$(grep -m1 '^name:' "$stub_dir/SKILL.md")"
  grep -q 'Contract skill for eval runner environment tests.' "$stub_dir/SKILL.md" && echo "description=kept"
  grep -q 'Body that the trigger run must not see.' "$stub_dir/SKILL.md" && echo "body=leaked"
} >> "$STUB_LOG"
query="$*"
case "$query" in
  *FLIPLOAD*)
    calls_file="${STUB_LOG}.calls"; call=$(( $(cat "$calls_file" 2>/dev/null || echo 0) + 1 )); echo "$call" > "$calls_file"
    [ $((call % 2)) -eq 1 ] && query="TRIGGER" || query="NOLOAD TRIGGER" ;;
  *FLIP*)
    calls_file="${STUB_LOG}.calls"; call=$(( $(cat "$calls_file" 2>/dev/null || echo 0) + 1 )); echo "$call" > "$calls_file"
    [ $((call % 2)) -eq 1 ] && query="TRIGGER" || query="IGNORE" ;;
esac
case "$query" in
  *NOLOAD*) jq -nc '{type: "system", subtype: "init", skills: ["other-skill"]}' ;;
  *) jq -nc --arg name "$name" '{type: "system", subtype: "init", skills: [$name, "other-skill"]}' ;;
esac
case "$query" in
  # The provider fails after loading the skill, before any tool call.
  *ERROR*) jq -nc '{type: "result", subtype: "error_during_execution", is_error: true}'; exit 1 ;;
  # The model answers in text, without a tool call, and the run ends normally.
  *TEXT*)
    jq -nc '{type: "assistant", message: {content: [{type: "text", text: "Use a sort function."}]}}'
    jq -nc '{type: "result", subtype: "success", is_error: false}'
    exit 0 ;;
  *TRIGGER*) jq -nc --arg name "$name" '{type: "assistant", message: {content: [{type: "tool_use", name: "Skill", input: {skill: $name}}]}}' ;;
  *) jq -nc '{type: "assistant", message: {content: [{type: "tool_use", name: "Bash", input: {command: "ls"}}]}}' ;;
esac
jq -nc '{type: "result", subtype: "error_max_turns", is_error: true}'
exit 1
CLAUDE_STUB
    chmod +x "${STUB_BIN}/claude"
}

write_triggers() {
    printf '%s\n' "$1" > "${SKILL_DIR}/evals/trigger-evals.json"
}

run_triggers() {
    run --separate-stderr env "PATH=${STUB_BIN}:${PATH}" "STUB_LOG=${STUB_LOG}" "GOLFO_MARKETPLACE_EVAL_PROVIDER=claude" \
        "${EVAL_RUNNER}" --jobs 2 --triggers "$@" "${SKILL_DIR}"
}

@test "a request triggers the skill when it should and not when it should not" {
    write_triggers '[{"query": "TRIGGER please", "should_trigger": true}, {"query": "IGNORE this", "should_trigger": false}]'

    run_triggers
    report="$output"

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "trigger" and .index == 1 and .triggered == 1 and .status == "passed")' <<< "$report"
    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "trigger" and .index == 2 and .triggered == 0 and .status == "passed")' <<< "$report"
    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "trigger_summary" and .passed == 2 and .trigger_rate == 1 and .false_trigger_rate == 0)' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "a skill that triggers where it should not, or misses where it should, fails" {
    write_triggers '[{"query": "IGNORE this", "should_trigger": true}, {"query": "TRIGGER please", "should_trigger": false}]'

    run_triggers
    report="$output"

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "trigger_summary" and .failed == 2 and .trigger_rate == 0 and .false_trigger_rate == 1)' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "the agent sees only the frontmatter, under a unique name, without the user's settings" {
    write_triggers '[{"query": "TRIGGER please", "should_trigger": true}]'

    run_triggers
    report="$output"

    [ "$status" -eq 0 ]
    grep -q -- '--setting-sources project' "${STUB_LOG}"
    grep -q -- '--strict-mcp-config' "${STUB_LOG}"
    grep -Eq "^skill_md_name=name: ${SKILL_NAME}-trigger-" "${STUB_LOG}"
    grep -q '^description=kept$' "${STUB_LOG}"
    ! grep -q '^body=leaked$' "${STUB_LOG}"
}

@test "a run where the session did not load the copy is not graded" {
    write_triggers '[{"query": "NOLOAD", "should_trigger": true}]'

    run_triggers
    report="$output"

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "trigger" and .graded == 0 and .status == "infrastructure")' <<< "$report"
    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "trigger_summary" and .infrastructure == 1 and .trigger_rate == null)' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "with --repeat, a request that triggers in some runs only is flaky" {
    write_triggers '[{"query": "FLIP", "should_trigger": true}]'

    run_triggers --repeat 2
    report="$output"

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "trigger" and .runs == 2 and .graded == 2 and .triggered == 1 and .status == "flaky")' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "--config names a trigger evals file kept outside the skill" {
    printf '%s\n' '[{"query": "TRIGGER please", "should_trigger": true}]' > "${TEST_ROOT}/held-out-triggers.json"

    run_triggers --config "${TEST_ROOT}/held-out-triggers.json"
    report="$output"

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "trigger_summary" and .total == 1 and .passed == 1)' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "missing or malformed trigger evals stop before calling the agent" {
    run_triggers
    report="$output"
    [ "$status" -ne 0 ]
    [[ "$stderr" == *"trigger evals not found"* ]]

    write_triggers '[{"query": "TRIGGER please"}]'
    run_triggers
    report="$output"
    [ "$status" -ne 0 ]
    [[ "$stderr" == *"Invalid trigger evals"* ]]
    ! grep -q '^args=' "${STUB_LOG}"
}

@test "--triggers cannot be combined with --baseline, --all or the codex provider" {
    write_triggers '[{"query": "TRIGGER please", "should_trigger": true}]'

    run_triggers --baseline
    report="$output"
    [ "$status" -eq 2 ]
    [[ "$stderr" == *"cannot be combined"* ]]

    run --separate-stderr env "PATH=${STUB_BIN}:${PATH}" "GOLFO_MARKETPLACE_EVAL_PROVIDER=claude" "${EVAL_RUNNER}" --triggers --all
    [ "$status" -eq 2 ]
}

@test "a run that fails before any tool call is not graded, even for a request that should not trigger" {
    write_triggers '[{"query": "ERROR now", "should_trigger": false}]'

    run_triggers
    report="$output"

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "trigger" and .graded == 0 and .status == "infrastructure")' <<< "$report"
    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "trigger_summary" and .false_trigger_rate == null)' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "an answer in text that ends normally counts as not triggered" {
    write_triggers '[{"query": "TEXT only", "should_trigger": false}]'

    run_triggers
    report="$output"

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "trigger" and .graded == 1 and .triggered == 0 and .status == "passed")' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "with --repeat, a request with an ungraded run does not pass" {
    write_triggers '[{"query": "FLIPLOAD", "should_trigger": true}]'

    run_triggers --repeat 2
    report="$output"

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "trigger" and .runs == 2 and .graded == 1 and .triggered == 1 and .status == "infrastructure")' <<< "$report"
    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "trigger_summary" and .infrastructure == 1 and .passed == 0)' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "a quoted name in the frontmatter still gives a valid copy" {
    sed -i "s/^name: .*/name: \"${SKILL_NAME}\"/" "${SKILL_DIR}/SKILL.md"
    write_triggers '[{"query": "TRIGGER please", "should_trigger": true}]'

    run_triggers
    report="$output"

    [ "$status" -eq 0 ]
    grep -Eq "^skill_md_name=name: ${SKILL_NAME}-trigger-q0-r1$" "${STUB_LOG}"
}

@test "a 64-character skill name still gives a copy name within the limit" {
    long_name="contract-skill-with-a-very-long-name-that-uses-all-of-the-limit"
    long_name="${long_name}$(printf 'x%.0s' $(seq 1 $((64 - ${#long_name}))))"
    [ "${#long_name}" -eq 64 ]
    sed -i "s/^name: .*/name: ${long_name}/" "${SKILL_DIR}/SKILL.md"
    write_triggers '[{"query": "TRIGGER please", "should_trigger": true}]'

    run_triggers
    report="$output"

    [ "$status" -eq 0 ]
    copy_name=$(sed -n 's/^skill_md_name=name: //p' "${STUB_LOG}" | head -1)
    [ "${#copy_name}" -le 64 ]
    [[ "$copy_name" == *-trigger-q0-r1 ]]
    [[ "$copy_name" != *--trigger-* ]]
}
