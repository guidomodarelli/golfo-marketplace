#!/usr/bin/env bats

bats_require_minimum_version 1.13.0

load 'test_helper/eval-runner'

# The agent under evaluation must not be able to read the assertions it is graded against:
# the runner exposes a copy of the skill without its evals/ directory, keeps relative
# references working, and accepts an eval-config.json kept outside the skill tree.

setup() {
    unset EVAL_CONFIG
    setup_eval_runner_fixture
    VIEW_LOG="${TEST_ROOT}/view.log"
    : > "${VIEW_LOG}"
    install_view_inspecting_stub
}

# Replaces the claude stub with one that inspects, at call time, the skill path named in the
# contract prompt and records what the agent could read there.
install_view_inspecting_stub() {
    cat > "${STUB_BIN}/claude" <<'CLAUDE_STUB'
#!/bin/bash
prompt="$*"
case "$prompt" in
  *eval-provider-ready*) response_text='eval-provider-ready' ;;
  *)
    printf '%s\n' "$prompt" >> "$CLAUDE_ARGS_LOG"
    view=$(printf '%s\n' "$prompt" | sed -n 's/.*Read and apply \(.*\)\/SKILL\.md and every reference.*/\1/p' | head -1)
    {
      echo "view=$view"
      [ -f "$view/SKILL.md" ] && echo "skill_md=yes" || echo "skill_md=no"
      [ -e "$view/evals" ] && echo "evals=visible" || echo "evals=hidden"
      [ -f "$view/references/local.md" ] && echo "own_reference=yes" || echo "own_reference=no"
      [ -f "$view/../../shared/shared.md" ] && echo "parent_reference=yes" || echo "parent_reference=no"
      [ -f "$view/../sibling-skill/SKILL.md" ] && echo "sibling_skill=yes" || echo "sibling_skill=no"
      skill_dir_name=$(basename "$view")
      [ -e "$view/../sibling-skill/../$skill_dir_name/evals" ] && echo "sibling_traversal=visible" || echo "sibling_traversal=hidden"
      [ -e "$view/../../shared/../skills/$skill_dir_name/evals" ] && echo "parent_traversal=visible" || echo "parent_traversal=hidden"
      [ -e "$view/../held-out-eval-config.json" ] && echo "adjacent_config=visible" || echo "adjacent_config=hidden"
      [ -e "$view/../unrelated-tree" ] && echo "unrelated_tree=visible" || echo "unrelated_tree=hidden"
    } >> "$VIEW_LOG"
    response_text='ok'
    ;;
esac
jq -n --arg result "$response_text" '{type: "result", is_error: false, result: $result, total_cost_usd: 0, num_turns: 1,
  usage: {input_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, output_tokens: 1}}'
CLAUDE_STUB
    chmod +x "${STUB_BIN}/claude"
}

# Moves the fixture skill to <root>/plugin/skills/<name>, with a shared folder two levels up and
# a sibling skill, like a real plugin layout.
nest_skill_in_plugin_layout() {
    local plugin_root="${TEST_ROOT}/plugin"
    mkdir -p "${plugin_root}/skills" "${plugin_root}/shared" "${plugin_root}/skills/sibling-skill" "${plugin_root}/.claude-plugin"
    mv "${SKILL_DIR}" "${plugin_root}/skills/${SKILL_NAME}"
    SKILL_DIR="${plugin_root}/skills/${SKILL_NAME}"
    mkdir -p "${SKILL_DIR}/references"
    echo "local reference" > "${SKILL_DIR}/references/local.md"
    echo "shared reference" > "${plugin_root}/shared/shared.md"
    printf -- '---\nname: sibling-skill\ndescription: Sibling.\n---\n' > "${plugin_root}/skills/sibling-skill/SKILL.md"
}

run_with_view_log_env() {
    local environment=(
        "PATH=${STUB_BIN}:${PATH}"
        "CLAUDE_ARGS_LOG=${CLAUDE_ARGS_LOG}"
        "VIEW_LOG=${VIEW_LOG}"
        "GOLFO_MARKETPLACE_EVAL_PROVIDER=claude"
    )
    run --separate-stderr env "${environment[@]}" "${EVAL_RUNNER}" --jobs 1 "$@"
}

@test "the agent reads a copy of the skill without its evals directory" {
    nest_skill_in_plugin_layout

    run_with_view_log_env "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    grep -q '^skill_md=yes$' "${VIEW_LOG}"
    grep -q '^evals=hidden$' "${VIEW_LOG}"
    ! grep -q "view=${SKILL_DIR}$" "${VIEW_LOG}"
    ! grep -q -- "${SKILL_DIR}" "${CLAUDE_ARGS_LOG}"
    # The original skill keeps its evals untouched.
    [ -f "${SKILL_DIR}/evals/eval-config.json" ]
}

@test "relative references inside the skill, to its parent and to sibling skills keep resolving" {
    nest_skill_in_plugin_layout

    run_with_view_log_env "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    grep -q '^own_reference=yes$' "${VIEW_LOG}"
    grep -q '^parent_reference=yes$' "${VIEW_LOG}"
    grep -q '^sibling_skill=yes$' "${VIEW_LOG}"
}

@test "sibling and parent folders do not lead back to the original evals directory" {
    nest_skill_in_plugin_layout

    run_with_view_log_env "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    grep -q '^sibling_traversal=hidden$' "${VIEW_LOG}"
    grep -q '^parent_traversal=hidden$' "${VIEW_LOG}"
}

@test "a held-out config stored next to the skill is not copied into the view" {
    nest_skill_in_plugin_layout
    local held_out="${SKILL_DIR}/../held-out-eval-config.json"
    jq '.test_cases[0].id = "adjacent-held-out-case"' "${SKILL_DIR}/evals/eval-config.json" > "${held_out}"

    run_with_view_log_env --config "${held_out}" "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    printf '%s\n' "$output" | jq -e 'select(.event == "case" and .id == "adjacent-held-out-case")' > /dev/null
    grep -q '^adjacent_config=hidden$' "${VIEW_LOG}"
    [ -f "${held_out}" ]
}

@test "a skill outside any plugin or repository copies only itself" {
    mkdir -p "${TEST_ROOT}/unrelated-tree"
    echo "unrelated content" > "${TEST_ROOT}/unrelated-tree/file.txt"

    run_with_view_log_env "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    grep -q '^skill_md=yes$' "${VIEW_LOG}"
    grep -q '^evals=hidden$' "${VIEW_LOG}"
    grep -q '^unrelated_tree=hidden$' "${VIEW_LOG}"
}

@test "the isolated view is removed after the run" {
    nest_skill_in_plugin_layout

    run_with_view_log_env "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    view=$(sed -n 's/^view=//p' "${VIEW_LOG}" | head -1)
    [ -n "$view" ]
    [ ! -e "$view" ]
}

@test "--config runs an eval-config kept outside the skill and never shows its path to the agent" {
    local held_out="${TEST_ROOT}/held-out"
    mkdir -p "${held_out}"
    jq '.test_cases[0].id = "held-out-case"' "${SKILL_DIR}/evals/eval-config.json" > "${held_out}/eval-config.json"
    rm -rf "${SKILL_DIR}/evals"

    run_with_view_log_env --config "${held_out}/eval-config.json" "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    printf '%s\n' "$output" | jq -e 'select(.event == "case" and .id == "held-out-case" and .status == "passed")' > /dev/null
    ! grep -q -- "${held_out}" "${CLAUDE_ARGS_LOG}"
    grep -q '^evals=hidden$' "${VIEW_LOG}"
}

@test "EVAL_CONFIG works like --config" {
    local held_out="${TEST_ROOT}/held-out"
    mkdir -p "${held_out}"
    jq '.test_cases[0].id = "env-config-case"' "${SKILL_DIR}/evals/eval-config.json" > "${held_out}/eval-config.json"

    EVAL_CONFIG="${held_out}/eval-config.json" run_with_view_log_env "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    printf '%s\n' "$output" | jq -e 'select(.event == "case" and .id == "env-config-case")' > /dev/null
}

@test "--config with a missing file fails without calling the agent" {
    run_with_view_log_env --config "${TEST_ROOT}/missing/eval-config.json" "${SKILL_DIR}"

    [ "$status" -ne 0 ]
    [[ "$stderr" == *"eval config not found"* ]]
    [ ! -s "${CLAUDE_ARGS_LOG}" ]
}

@test "--config cannot be combined with --all" {
    run_with_view_log_env --config "${SKILL_DIR}/evals/eval-config.json" --all

    [ "$status" -eq 2 ]
    [[ "$stderr" == *"cannot be combined with --all"* ]]
}

@test "an unknown assertion type is rejected instead of passing unchecked" {
    jq '.test_cases[0].assertions[0].type = "not_contains"' "${SKILL_DIR}/evals/eval-config.json" > "${TEST_ROOT}/typo.json"
    mv "${TEST_ROOT}/typo.json" "${SKILL_DIR}/evals/eval-config.json"

    run_with_view_log_env "${SKILL_DIR}"

    [ "$status" -ne 0 ]
    [[ "$stderr" == *"Invalid eval-config.json"* ]]
    [ ! -s "${CLAUDE_ARGS_LOG}" ]
}
