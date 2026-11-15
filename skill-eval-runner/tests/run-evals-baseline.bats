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

@test "without --baseline nothing is graded without the skill" {
    answer_without_skill "ok"

    run_eval_runner

    [ "$status" -eq 0 ]
    jq -e '.baseline == null' <<< "$(case_line)"
    jq -e 'has("baseline_passed") | not' <<< "$(summary_line)"
    [ "$(grep -c -- '--model ' "$CLAUDE_ARGS_LOG")" -eq 1 ]
}
