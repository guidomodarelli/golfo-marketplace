#!/usr/bin/env bats

bats_require_minimum_version 1.13.0

load 'test_helper/eval-runner'

setup() {
    unset GOLFO_MARKETPLACE_EVAL_MODEL
    unset GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT
    setup_eval_runner_fixture
}

@test "uses the default model" {
    run_eval_runner

    [ "$status" -eq 0 ]
    [ "$(wc -l < "$CLAUDE_ARGS_LOG" | tr -d ' ')" -ge 1 ]
    grep -q -- '--model claude-sonnet-5-5' "$CLAUDE_ARGS_LOG"
}

@test "uses the model override" {
    GOLFO_MARKETPLACE_EVAL_MODEL='prefixed-model'

    run_eval_runner

    [ "$status" -eq 0 ]
    [ "$(wc -l < "$CLAUDE_ARGS_LOG" | tr -d ' ')" -ge 1 ]
    grep -q -- '--model prefixed-model' "$CLAUDE_ARGS_LOG"
}

@test "uses the default Claude reasoning effort" {
    run_eval_runner

    [ "$status" -eq 0 ]
    grep -q -- '--effort medium' "$CLAUDE_ARGS_LOG"
}

@test "uses the reasoning effort override" {
    GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT='high'

    run_eval_runner

    [ "$status" -eq 0 ]
    grep -q -- '--effort high' "$CLAUDE_ARGS_LOG"
}

@test "resolves a relative skill path before building the contract prompt" {
    run --separate-stderr env \
        "PATH=${STUB_BIN}:${PATH}" \
        "CLAUDE_ARGS_LOG=${CLAUDE_ARGS_LOG}" \
        "GOLFO_MARKETPLACE_EVAL_PROVIDER=claude" \
        bash -c 'cd "$1" && "$2" --jobs 1 "$3"' \
        _ "$TEST_ROOT" "$EVAL_RUNNER" "$SKILL_NAME"

    [ "$status" -eq 0 ]
    grep -Eq -- "Read and apply /[^ ]*/${SKILL_NAME}/SKILL\.md" "$CLAUDE_ARGS_LOG"
}

@test "removed provider is rejected before invoking Claude" {
    local removed_provider="co""pilot"

    run --separate-stderr env \
        "PATH=${STUB_BIN}:${PATH}" \
        "CLAUDE_ARGS_LOG=${CLAUDE_ARGS_LOG}" \
        "GOLFO_MARKETPLACE_EVAL_PROVIDER=${removed_provider}" \
        "${EVAL_RUNNER}" --jobs 1 "${SKILL_DIR}"

    [ "$status" -eq 1 ]
    [[ "$stderr" == *"Invalid provider '${removed_provider}'"* ]]
    [[ ! -s "$CLAUDE_ARGS_LOG" ]]
}

@test "rejects null assertions before invoking Claude" {
    local config_file="${SKILL_DIR}/evals/eval-config.json"
    jq '.test_cases[0].assertions = null' "$config_file" > "${config_file}.tmp"
    mv "${config_file}.tmp" "$config_file"

    run_eval_runner

    [ "$status" -eq 1 ]
    [[ "$stderr" == *"Invalid eval-config.json"* ]]
    [[ ! -s "$CLAUDE_ARGS_LOG" ]]
}

@test "rejects missing assertions before invoking Claude" {
    local config_file="${SKILL_DIR}/evals/eval-config.json"
    jq 'del(.test_cases[0].assertions)' "$config_file" > "${config_file}.tmp"
    mv "${config_file}.tmp" "$config_file"

    run_eval_runner

    [ "$status" -eq 1 ]
    [[ "$stderr" == *"Invalid eval-config.json"* ]]
    [[ ! -s "$CLAUDE_ARGS_LOG" ]]
}

@test "reports infrastructure failure as JSONL" {
    install_failures_touch_stub

    run_eval_runner

    [ "$status" -eq 1 ]
    [[ ! -s "$CLAUDE_ARGS_LOG" ]]

    local jsonl_output="$output"
    run jq -e 'select(
        .event == "case"
        and .id == "contract"
        and .status == "failed"
        and .failed_assertions[0].type == "infrastructure"
    )' <<< "$jsonl_output"
    [ "$status" -eq 0 ]

    run jq -e 'select(
        .event == "summary"
        and .total == 1
        and .passed == 0
        and .failed == 1
    )' <<< "$jsonl_output"
    [ "$status" -eq 0 ]
}

@test "reports infrastructure failure in pretty output" {
    install_failures_touch_stub

    run_eval_runner --pretty

    [ "$status" -eq 1 ]
    [[ ! -s "$CLAUDE_ARGS_LOG" ]]
    [[ "$output" == *"INFRASTRUCTURE FAILURE"* ]]
    [[ "$output" == *"FAILED"* ]]
}

@test "skips the no-skill baseline by default" {
    run_eval_runner

    [ "$status" -eq 0 ]
    [ "$(grep -c -- '--model ' "$CLAUDE_ARGS_LOG")" -eq 1 ]
    grep -Eq -- "Read and apply /[^ ]*/${SKILL_NAME}/SKILL\.md" "$CLAUDE_ARGS_LOG"

    run jq -e 'select(.event == "case" and .artifacts.baseline == null)' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "runs the no-skill baseline when requested" {
    run_eval_runner --baseline

    [ "$status" -eq 0 ]
    [ "$(grep -c -- '--model ' "$CLAUDE_ARGS_LOG")" -eq 2 ]
    [ "$(grep -Ec -- "Read and apply /[^ ]*/${SKILL_NAME}/SKILL\.md" "$CLAUDE_ARGS_LOG")" -eq 1 ]

    run jq -e 'select(.event == "case" and (.artifacts.baseline | endswith("/without-skill/contract.txt")))' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "limits Claude eval calls to read-only tools without user MCP servers" {
    run_eval_runner

    [ "$status" -eq 0 ]
    grep -q -- '--tools Read,Glob,Grep' "$CLAUDE_ARGS_LOG"
    grep -q -- '--strict-mcp-config' "$CLAUDE_ARGS_LOG"
    grep -q -- '--no-session-persistence' "$CLAUDE_ARGS_LOG"
}

@test "reports Claude usage per case in JSONL" {
    run_eval_runner

    [ "$status" -eq 0 ]
    run jq -e 'select(
        .event == "case"
        and .status == "passed"
        and .usage.cost_usd == 0.0123
        and .usage.num_turns == 2
        and .usage.cache_read_input_tokens == 3000
        and .usage.output_tokens == 40
    )' <<< "$output"
    [ "$status" -eq 0 ]
}
