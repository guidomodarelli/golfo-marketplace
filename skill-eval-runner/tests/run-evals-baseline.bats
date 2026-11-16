#!/usr/bin/env bats

bats_require_minimum_version 1.13.0

load 'test_helper/eval-runner'

# The fixture case asserts that the response contains "ok"; the with-skill call answers "ok".
setup() {
    unset GOLFO_MARKETPLACE_EVAL_MODEL
    unset CLAUDE_RESPONSE_FILE
    unset CLAUDE_BASELINE_RESPONSE_FILE
    unset CLAUDE_BASELINE_FAIL
    setup_eval_runner_fixture
    CLAUDE_BASELINE_RESPONSE_FILE="${TEST_ROOT}/baseline-response.txt"
}

# The no-skill call answers with this text, or with one text per call when given several.
answer_without_skill() {
    if [[ $# -eq 1 ]]; then
        printf '%s\n' "$1" > "$CLAUDE_BASELINE_RESPONSE_FILE"
        return
    fi
    local call_number=0 response
    for response in "$@"; do
        call_number=$((call_number + 1))
        printf '%s\n' "$response" > "${CLAUDE_BASELINE_RESPONSE_FILE}.${call_number}"
    done
    printf '%s\n' "$1" > "$CLAUDE_BASELINE_RESPONSE_FILE"
}

case_line() {
    jq -c 'select(.event == "case")' <<< "$output"
}

summary_line() {
    jq -c 'select(.event == "summary")' <<< "$output"
}

@test "grades the no-skill response with the case's own assertions" {
    answer_without_skill "nope"

    run_eval_runner --baseline

    [ "$status" -eq 0 ]
    jq -e '.status == "passed" and .baseline.status == "failed" and .baseline.graded == 1 and .baseline.passes == 0' <<< "$(case_line)"
    jq -e '.baseline.failed_assertions | length == 1 and .[0].type == "contains"' <<< "$(case_line)"
    jq -e '.baseline_passed == 0 and .baseline_flaky == 0' <<< "$(summary_line)"
}

@test "a case that passes without the skill is reported as not discriminating and still passes" {
    answer_without_skill "ok"

    run_eval_runner --baseline

    [ "$status" -eq 0 ]
    jq -e '.status == "passed" and .baseline.status == "passed" and .baseline.passes == 1' <<< "$(case_line)"
    jq -e '.passed == 1 and .baseline_passed == 1' <<< "$(summary_line)"
}

# Marks the fixture case as a control case with this reason.
mark_as_control() {
    local config_file="${SKILL_DIR}/evals/eval-config.json"
    jq --arg reason "$1" '.test_cases[0].control = $reason' "$config_file" > "$config_file.tmp" && mv "$config_file.tmp" "$config_file"
}

@test "a control case that passes without the skill is reported apart, with its reason" {
    mark_as_control "the model already does this by default"
    answer_without_skill "ok"

    run_eval_runner --baseline

    [ "$status" -eq 0 ]
    jq -e '.baseline.status == "passed" and .baseline.control == "the model already does this by default"' <<< "$(case_line)"
    jq -e '.baseline_passed == 0 and .baseline_control == 1' <<< "$(summary_line)"
}

@test "the pretty report lists control cases apart from the ones that do not discriminate" {
    mark_as_control "the model already does this by default"
    answer_without_skill "ok"

    run_eval_runner --baseline --pretty

    [ "$status" -eq 0 ]
    plain_output=$(sed 's/\x1b\[[0-9;]*m//g' <<< "$output")
    [[ "$plain_output" == *"BASELINE: passes without the skill, as a control case: the model already does this by default"* ]]
    [[ "$plain_output" == *"Without the skill: 0 pass, so they do not discriminate"* ]]
    [[ "$plain_output" == *"    - contract: the model already does this by default"* ]]
}

@test "a control field must name its reason" {
    mark_as_control ""

    run_eval_runner --baseline

    [ "$status" -ne 0 ]
    [[ "$stderr" == *"Invalid eval-config.json"* ]]
}

@test "the pretty report says which cases pass without the skill" {
    answer_without_skill "ok"

    run_eval_runner --baseline --pretty

    [ "$status" -eq 0 ]
    [[ "$output" == *"BASELINE: passes without the skill (the case does not discriminate)"* ]]
    plain_output=$(sed 's/\x1b\[[0-9;]*m//g' <<< "$output")
    [[ "$plain_output" == *"Without the skill: 1 pass, so they do not discriminate"* ]]
    [[ "$plain_output" == *"    - contract"* ]]
}

@test "with --repeat, a case that passes without the skill in some runs only is flaky" {
    answer_without_skill "ok" "nope"

    run_eval_runner --baseline --repeat 2

    [ "$status" -eq 0 ]
    jq -e '.baseline.status == "flaky" and .baseline.runs == 2 and .baseline.graded == 2 and .baseline.passes == 1' <<< "$(case_line)"
    jq -e '[.run_results[].baseline.status] == ["passed", "failed"]' <<< "$(case_line)"
    jq -e '.baseline_passed == 0 and .baseline_flaky == 1' <<< "$(summary_line)"
}

@test "a no-skill call whose provider fails is not graded and does not fail the run" {
    answer_without_skill "ok"
    CLAUDE_BASELINE_FAIL=1

    run_eval_runner --baseline

    [ "$status" -eq 0 ]
    jq -e '.status == "passed" and .baseline.status == "infrastructure" and .baseline.graded == 0' <<< "$(case_line)"
    jq -e '.baseline.failed_assertions[0].type == "infrastructure"' <<< "$(case_line)"
    jq -e '.baseline_passed == 0' <<< "$(summary_line)"
}

# A codex that answers the preflight and the with-skill prompt, and fails the no-skill prompt after
# printing an error event, the way `codex exec --json` reports a failed request.
install_codex_stub_failing_without_skill() {
    cat > "${STUB_BIN}/codex" <<'CODEX_STUB'
#!/bin/bash
prompt="${*: -1}"
agent_message() {
  jq -nc --arg text "$1" '{type: "item.completed", item: {type: "agent_message", text: $text}}'
}
case "$prompt" in
  *eval-provider-ready*) agent_message "eval-provider-ready" ;;
  *"This is a contract evaluation."*) agent_message "fine" ;;
  *)
    jq -nc '{type: "error", message: "stream disconnected before completion"}'
    exit 1
    ;;
esac
CODEX_STUB
    chmod +x "${STUB_BIN}/codex"
}

@test "with --all and Codex, a failed no-skill request is not graded as an answer" {
    # --all runs each skill inside an `if`, where a failed command does not stop the runner: the
    # runner must still tell the failed request apart from a response.
    local repository="${TEST_ROOT}/repository"
    mkdir -p "$repository/skill-eval-runner" "$repository/skills" "${TEST_ROOT}/home"
    cp "$EVAL_RUNNER" "$repository/skill-eval-runner/run-evals.sh"
    cp -R "$SKILL_DIR" "$repository/skills/$SKILL_NAME"
    # Only a negative assertion: the error event stream would pass it.
    jq '.test_cases[0].assertions = [{type: "not_contains_any", values: ["forbidden"], description: "Avoids the forbidden word"}]' \
        "$SKILL_DIR/evals/eval-config.json" > "$repository/skills/$SKILL_NAME/evals/eval-config.json"
    install_codex_stub_failing_without_skill

    run --separate-stderr env -u CODEX_HOME "PATH=${STUB_BIN}:${PATH}" "HOME=${TEST_ROOT}/home" \
        "GOLFO_MARKETPLACE_EVAL_PROVIDER=codex" \
        "$repository/skill-eval-runner/run-evals.sh" --jobs 1 --baseline --all

    [ "$status" -eq 0 ]
    jq -e '.status == "passed" and .baseline.status == "infrastructure" and .baseline.graded == 0' <<< "$(case_line)"
    jq -e '.baseline_passed == 0' <<< "$(summary_line)"
}

@test "without --baseline nothing is graded without the skill" {
    answer_without_skill "ok"

    run_eval_runner

    [ "$status" -eq 0 ]
    jq -e '.baseline == null' <<< "$(case_line)"
    jq -e 'has("baseline_passed") | not' <<< "$(summary_line)"
    [ "$(grep -c -- '--model ' "$CLAUDE_ARGS_LOG")" -eq 1 ]
}
