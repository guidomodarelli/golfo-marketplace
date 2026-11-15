#!/usr/bin/env bats

bats_require_minimum_version 1.13.0

load 'test_helper/eval-runner'

# A directory of rules (a stack, a profile or base/ of a content pack) is an eval target of its own:
# rules are not skills, so their evals live next to them and the agent is told to apply the rules,
# read from a copy of the pack without that directory's evals/.

setup() {
    unset EVAL_CONFIG
    setup_eval_runner_fixture
    VIEW_LOG="${TEST_ROOT}/view.log"
    : > "${VIEW_LOG}"
    create_pack_fixture
    install_rules_inspecting_stub
}

# A pack with a stack that holds rules, a skill of its own and its evals, and a rule in base/ that
# the stack's rules reference by file name.
create_pack_fixture() {
    PACK_ROOT="${TEST_ROOT}/pack"
    STACK_DIR="${PACK_ROOT}/stacks/web"
    mkdir -p "${PACK_ROOT}/.git" "${PACK_ROOT}/base/rules" "${STACK_DIR}/rules" "${STACK_DIR}/skills/web-skill" "${STACK_DIR}/evals"
    printf '# Web style\n\nFollow shared.md.\n' > "${STACK_DIR}/rules/web-style.md"
    printf '# Shared\n' > "${PACK_ROOT}/base/rules/shared.md"
    printf -- '---\nname: web-skill\ndescription: A skill of the stack.\n---\n' > "${STACK_DIR}/skills/web-skill/SKILL.md"
    cat > "${STACK_DIR}/evals/eval-config.json" <<'JSON'
{
  "skill": "web-rules",
  "test_cases": [
    {
      "id": "rules-contract",
      "description": "the agent applies the rules of the stack",
      "input": "Reply ok",
      "assertions": [{ "type": "contains", "value": "ok" }]
    }
  ]
}
JSON
}

# Replaces the claude stub with one that reads, at call time, the rules directory named in the
# contract prompt and records what the agent could see.
install_rules_inspecting_stub() {
    cat > "${STUB_BIN}/claude" <<'CLAUDE_STUB'
#!/bin/bash
prompt="$*"
case "$prompt" in
  *eval-provider-ready*) response_text='eval-provider-ready' ;;
  *)
    printf '%s\n' "$prompt" >> "$CLAUDE_ARGS_LOG"
    view=$(printf '%s\n' "$prompt" | sed -n 's/.*Read the rules in \(.*\)\/rules\/, apply every rule.*/\1/p' | head -1)
    readable="none" previous=""
    for argument in "$@"; do
      [ "$previous" = "--add-dir" ] && readable="$argument"
      previous="$argument"
    done
    {
      echo "call kind=$([ -n "$view" ] && echo contract || echo baseline)"
      [ -f "$view/rules/web-style.md" ] && echo "stack_rule=yes" || echo "stack_rule=no"
      [ -e "$view/evals" ] && echo "evals=visible" || echo "evals=hidden"
      [ -f "$view/../../base/rules/shared.md" ] && echo "base_rule=yes" || echo "base_rule=no"
      case "$view" in "$readable"/*) echo "view_in_readable=yes" ;; *) echo "view_in_readable=no" ;; esac
      echo "installed_skills=$(ls -A .claude/skills 2>/dev/null | wc -l | tr -d ' ')"
    } >> "$VIEW_LOG"
    response_text='ok'
    ;;
esac
jq -n --arg result "$response_text" '{type: "result", is_error: false, result: $result, total_cost_usd: 0, num_turns: 1,
  usage: {input_tokens: 1, cache_creation_input_tokens: 0, cache_read_input_tokens: 0, output_tokens: 1}}'
CLAUDE_STUB
    chmod +x "${STUB_BIN}/claude"
}

run_rules_evals() {
    run --separate-stderr env "PATH=${STUB_BIN}:${PATH}" "CLAUDE_ARGS_LOG=${CLAUDE_ARGS_LOG}" "VIEW_LOG=${VIEW_LOG}" \
        "GOLFO_MARKETPLACE_EVAL_PROVIDER=claude" "${EVAL_RUNNER}" --jobs 1 "$@"
}

@test "a directory of rules is graded with its own evals, from a copy without them" {
    run_rules_evals "${STACK_DIR}"

    [ "$status" -eq 0 ]
    run jq -e 'select(.event == "summary" and .skill == "web-rules" and .total == 1 and .passed == 1)' <<< "$output"
    [ "$status" -eq 0 ]
    grep -q '^call kind=contract$' "${VIEW_LOG}"
    grep -q '^stack_rule=yes$' "${VIEW_LOG}"
    grep -q '^evals=hidden$' "${VIEW_LOG}"
    grep -q '^view_in_readable=yes$' "${VIEW_LOG}"
    ! grep -q -- "${STACK_DIR}" "${CLAUDE_ARGS_LOG}"
    [ -f "${STACK_DIR}/evals/eval-config.json" ]
}

@test "a rule of the stack can follow a rule of base by its file name" {
    run_rules_evals "${STACK_DIR}"

    [ "$status" -eq 0 ]
    grep -q '^base_rule=yes$' "${VIEW_LOG}"
}

@test "rules are named in the prompt and never installed as a skill" {
    run_rules_evals "${STACK_DIR}"

    [ "$status" -eq 0 ]
    grep -q '^installed_skills=0$' "${VIEW_LOG}"
    ! grep -q 'SKILL.md' "${CLAUDE_ARGS_LOG}"
}

@test "with --baseline, the rules get a run without them" {
    run_rules_evals --baseline "${STACK_DIR}"

    [ "$status" -eq 0 ]
    grep -q '^call kind=baseline$' "${VIEW_LOG}"
    run jq -e 'select(.event == "case" and .baseline.status == "passed")' <<< "$output"
    [ "$status" -eq 0 ]
}

@test "a directory with neither a SKILL.md nor rules fails without calling the agent" {
    rm -rf "${STACK_DIR}/rules"

    run_rules_evals "${STACK_DIR}"

    [ "$status" -ne 0 ]
    [[ "$stderr" == *"neither a SKILL.md nor rules"* ]]
    [ ! -s "${CLAUDE_ARGS_LOG}" ]
}

@test "a skill that bundles a rules directory is still evaluated as a skill" {
    mkdir -p "${SKILL_DIR}/rules"
    printf '# Local rule\n' > "${SKILL_DIR}/rules/local.md"

    run_rules_evals "${SKILL_DIR}"

    [ "$status" -eq 0 ]
    grep -q "Read and apply .*/${SKILL_NAME}/SKILL.md" "${CLAUDE_ARGS_LOG}"
}
