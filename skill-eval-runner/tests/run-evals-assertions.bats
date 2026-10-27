#!/usr/bin/env bats

bats_require_minimum_version 1.13.0

load 'test_helper/eval-runner'

setup() {
    unset GOLFO_MARKETPLACE_EVAL_MODEL
    unset CLAUDE_RESPONSE_FILE
    setup_eval_runner_fixture
}

write_mixed_action_config() {
    local config_file="${SKILL_DIR}/evals/eval-config.json"

    cat > "$config_file" <<JSON
{
  "skill": "${SKILL_NAME}",
  "test_cases": [
    {
      "id": "mixed-actions",
      "input": "Describe next steps",
      "assertions": [
        {
          "type": "not_contains_any",
          "values": [
            "[0-9][0-9]*\\\\..*\\\\[AUTO\\\\].*\\\\[MANUAL\\\\]",
            "[0-9][0-9]*\\\\..*\\\\[MANUAL\\\\].*\\\\[AUTO\\\\]",
            "- .*\\\\[AUTO\\\\].*\\\\[MANUAL\\\\]",
            "- .*\\\\[MANUAL\\\\].*\\\\[AUTO\\\\]",
            "[0-9][0-9]*\\\\..*automátic.*manual",
            "[0-9][0-9]*\\\\..*manual.*automátic",
            "- .*automátic.*manual",
            "- .*manual.*automátic",
            "\\\\[AUTO\\\\].*permis",
            "\\\\[AUTO\\\\].*permission"
          ],
          "description": "Keeps action types separate within one step"
        }
      ]
    }
  ]
}
JSON
}

run_mixed_action_assertion() {
    local response="$1"
    local response_file="${TEST_ROOT}/response.txt"

    write_mixed_action_config
    printf '%s\n' "$response" > "$response_file"
    CLAUDE_RESPONSE_FILE="$response_file"
    run_eval_runner
}

write_dash_prefixed_config() {
    local config_file="${SKILL_DIR}/evals/eval-config.json"

    cat > "$config_file" <<JSON
{
  "skill": "${SKILL_NAME}",
  "test_cases": [
    {
      "id": "dash-prefixed-values",
      "input": "Describe the merge command",
      "assertions": [
        { "type": "contains", "value": "--match-head-commit", "description": "Contains a flag" },
        { "type": "contains_any", "values": ["--rebase", "--squash"], "description": "Contains one of the flags" },
        { "type": "regex", "pattern": "--delete-branch( |$)", "description": "Matches a flag pattern" }
      ]
    }
  ]
}
JSON
}

run_dash_prefixed_assertions() {
    local response="$1"
    local response_file="${TEST_ROOT}/response.txt"

    write_dash_prefixed_config
    printf '%s\n' "$response" > "$response_file"
    CLAUDE_RESPONSE_FILE="$response_file"
    run_eval_runner
}

@test "matches contains, contains_any and regex values that start with dashes" {
    run_dash_prefixed_assertions 'gh pr merge 42 --squash --delete-branch --match-head-commit abc1234'

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "summary" and .passed == 1 and .failed == 0)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "still fails dash-prefixed values that are absent from the response" {
    run_dash_prefixed_assertions 'gh pr merge 42 --merge'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "rejects manual continuation after automatic step" {
    run_mixed_action_assertion $'1. [AUTO] Validate generated files.\n   [MANUAL] Decide project permissions.'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "rejects automatic continuation after manual step" {
    run_mixed_action_assertion $'1. [MANUAL] Decide project permissions.\n   [AUTO] Validate generated files.'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "rejects manual continuation after blank line" {
    run_mixed_action_assertion $'1. [AUTO] Validate generated files.\n\n   [MANUAL] Decide project permissions.'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "rejects automatic continuation after blank line" {
    run_mixed_action_assertion $'1. [MANUAL] Decide project permissions.\n\n   [AUTO] Validate generated files.'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "accepts commentary paragraph after the last step" {
    run_mixed_action_assertion $'1. [AUTO] Validate generated files.\n2. [MANUAL] Decide project permissions.\n\nThe [AUTO] step only validates; the [MANUAL] step needs a project decision.'

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "summary" and .passed == 1 and .failed == 0)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "rejects indented continuation of the last step after a blank line" {
    run_mixed_action_assertion $'1. [MANUAL] Decide project permissions.\n2. [AUTO] Validate generated files.\n\n   [MANUAL] Decide project scope.'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "accepts separate numbered steps" {
    run_mixed_action_assertion $'1. [AUTO] Validate generated files.\n2. [MANUAL] Decide project permissions.'

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "summary" and .passed == 1 and .failed == 0)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "rejects both action types on one step line" {
    run_mixed_action_assertion '1. [AUTO] Validate files and [MANUAL] decide permissions.'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "preserves textual automatic and manual action detection" {
    run_mixed_action_assertion $'1. Validación automática de archivos.\n   Completar manualmente permisos del proyecto.'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

write_wrapped_phrase_config() {
    local config_file="${SKILL_DIR}/evals/eval-config.json"

    cat > "$config_file" <<JSON
{
  "skill": "${SKILL_NAME}",
  "test_cases": [
    {
      "id": "wrapped-phrases",
      "input": "Explain what to keep",
      "assertions": [
        { "type": "contains_any", "values": ["conservar.*diagramas"], "description": "Phrase split across a wrapped paragraph" },
        { "type": "regex", "pattern": "no.*parent.history", "description": "Pattern split across a wrapped list item" }
      ]
    }
  ]
}
JSON
}

run_wrapped_phrase_assertions() {
    local response="$1"
    local response_file="${TEST_ROOT}/response.txt"

    write_wrapped_phrase_config
    printf '%s\n' "$response" > "$response_file"
    CLAUDE_RESPONSE_FILE="$response_file"
    run_eval_runner
}

@test "matches positive assertions split across the lines of one paragraph or list item" {
    run_wrapped_phrase_assertions $'Hay que conservar los\ndiagramas originales.\n\n- No hace falta tocar\n  parent.history en ningún caso.'

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "summary" and .passed == 1 and .failed == 0)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "does not join separate paragraphs to satisfy a positive assertion" {
    run_wrapped_phrase_assertions $'Hay que conservar.\n\nLos diagramas cambian.\n\nNo.\n\nparent.history'

    [ "$status" -eq 1 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
}

run_repeated_contract() {
    local response_file="${TEST_ROOT}/response.txt"
    printf 'ok\n' > "$response_file"
    CLAUDE_RESPONSE_FILE="$response_file"
    run_eval_runner "$@"
}

@test "--repeat passes a case only when every run passes" {
    run_repeated_contract --repeat 3

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "summary" and .passed == 1 and .failed == 0 and .flaky == 0 and .runs == 3)' <<< "$output"
    [ "$status" -eq 0 ]
    [ "$(cat "${TEST_ROOT}/response.txt.calls")" -eq 3 ]
}

@test "--repeat reports a case that passes some runs as flaky and fails the suite" {
    printf 'ok\n' > "${TEST_ROOT}/response.txt.1"
    printf 'nothing useful\n' > "${TEST_ROOT}/response.txt.2"

    run_repeated_contract --repeat 2

    [ "$status" -eq 1 ]
    local report="$output"
    run jq -e 'select(.event == "case" and .status == "flaky" and .runs == 2 and .passes == 1)' <<< "$report"
    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "summary" and .passed == 0 and .failed == 1 and .flaky == 1)' <<< "$report"
    [ "$status" -eq 0 ]
}

@test "--repeat rejects a value that is not a positive integer" {
    run_repeated_contract --repeat 0

    [ "$status" -eq 2 ]
    [[ "$stderr" == *"--repeat needs a positive integer"* ]]
}

@test "--repeat keeps the failing run's assertions and response for a flaky case" {
    printf 'nothing useful\n' > "${TEST_ROOT}/response.txt.1"
    printf 'ok\n' > "${TEST_ROOT}/response.txt.2"

    run_repeated_contract --repeat 2

    [ "$status" -eq 1 ]
    local report="$output" case_line
    case_line=$(jq -c 'select(.event == "case")' <<< "$report")
    run jq -e '.status == "flaky" and (.failed_assertions | length) > 0 and (.run_results | length) == 2 and .run_results[0].status == "failed" and .run_results[1].status == "passed"' <<< "$case_line"
    [ "$status" -eq 0 ]
    local failing_artifact passing_artifact
    failing_artifact=$(jq -r '.artifacts.with_skill' <<< "$case_line")
    passing_artifact=$(jq -r '.run_results[1].artifacts.with_skill' <<< "$case_line")
    [ "$failing_artifact" != "$passing_artifact" ]
    grep -q 'nothing useful' "$failing_artifact"
    grep -qx 'ok' "$passing_artifact"
}

@test "--repeat still reports a case whose worker died before writing the first run's result" {
    CLAUDE_KILL_CASE_ON_CALL=1 run_repeated_contract --repeat 2
    unset CLAUDE_KILL_CASE_ON_CALL

    [ "$status" -eq 1 ]
    local report="$output" case_line
    case_line=$(jq -c 'select(.event == "case")' <<< "$report")
    [ -n "$case_line" ]
    run jq -e '.status == "flaky" and .id == "contract" and .failed_assertions[0].type == "infrastructure" and .run_results[0].status == "failed" and .run_results[1].status == "passed"' <<< "$case_line"
    [ "$status" -eq 0 ]
}
