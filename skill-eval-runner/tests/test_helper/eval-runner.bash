EVAL_RUNNER="${BATS_TEST_DIRNAME}/../run-evals.sh"

setup_eval_runner_fixture() {
    TEST_ROOT="${BATS_TEST_TMPDIR}/eval-runner-${BATS_TEST_NUMBER}"
    STUB_BIN="${TEST_ROOT}/bin"
    SKILL_NAME="contract-skill-${BATS_TEST_NUMBER}"
    SKILL_DIR="${TEST_ROOT}/${SKILL_NAME}"
    CLAUDE_ARGS_LOG="${TEST_ROOT}/claude-args.log"

    mkdir -p "${STUB_BIN}" "${SKILL_DIR}/evals"
    : > "${CLAUDE_ARGS_LOG}"

    cat > "${SKILL_DIR}/SKILL.md" <<SKILL
---
name: ${SKILL_NAME}
description: Contract skill for eval runner environment tests.
---

# Contract Skill
SKILL

    cat > "${SKILL_DIR}/evals/eval-config.json" <<JSON
{
  "skill": "${SKILL_NAME}",
  "test_cases": [
    {
      "id": "contract",
      "description": "runner contract",
      "input": "Reply ok",
      "assertions": [
        {
          "type": "contains",
          "value": "ok"
        }
      ]
    }
  ]
}
JSON

    cat > "${STUB_BIN}/claude" <<'CLAUDE_STUB'
#!/bin/bash

# Mirrors `claude -p --output-format json`: the response text lives in
# `.result` next to usage metadata.
emit_response() {
  if [[ "$*" == *"--output-format json"* ]]; then
    jq -n --arg result "$response_text" '{
      type: "result",
      is_error: false,
      result: $result,
      total_cost_usd: 0.0123,
      num_turns: 2,
      usage: {
        input_tokens: 10,
        cache_creation_input_tokens: 200,
        cache_read_input_tokens: 3000,
        output_tokens: 40
      }
    }'
  else
    printf '%s\n' "$response_text"
  fi
}

case "$*" in
  *eval-provider-ready*)
    response_text='eval-provider-ready'
    emit_response "$@"
    ;;
  *)
    printf '%s\n' "$*" >> "$CLAUDE_ARGS_LOG"
    if [[ -n "${CLAUDE_RESPONSE_FILE:-}" ]]; then
      # Repeated runs: call N answers with "$CLAUDE_RESPONSE_FILE.N" when that file exists.
      calls_file="${CLAUDE_RESPONSE_FILE}.calls"
      call_number=$(( $(cat "$calls_file" 2>/dev/null || echo 0) + 1 ))
      printf '%s\n' "$call_number" > "$calls_file"
      if [[ "${CLAUDE_KILL_CASE_ON_CALL:-}" == "$call_number" ]]; then
        # Simulates a case worker that dies before writing its result: kill the runner's
        # background case subshell, the ancestor right below the top-level run-evals.sh.
        ancestor=$PPID case_worker=""
        while [[ "$ancestor" -gt 1 ]] && tr '\0' ' ' < "/proc/$ancestor/cmdline" 2>/dev/null | grep -q 'run-evals.sh'; do
          parent=$(awk '{print $4}' "/proc/$ancestor/stat" 2>/dev/null)
          tr '\0' ' ' < "/proc/$parent/cmdline" 2>/dev/null | grep -q 'run-evals.sh' || break
          case_worker=$ancestor ancestor=$parent
        done
        [[ -n "$case_worker" ]] && kill -9 "$case_worker"
        exit 1
      fi
      if [[ -f "${CLAUDE_RESPONSE_FILE}.${call_number}" ]]; then
        response_text="$(cat "${CLAUDE_RESPONSE_FILE}.${call_number}")"
      elif [[ -f "$CLAUDE_RESPONSE_FILE" ]]; then
        response_text="$(cat "$CLAUDE_RESPONSE_FILE")"
      else
        printf 'ERROR: CLAUDE_RESPONSE_FILE not found: %s\n' "$CLAUDE_RESPONSE_FILE" >&2
        exit 1
      fi
    else
      response_text='ok'
    fi
    emit_response "$@"
    ;;
esac
CLAUDE_STUB
    chmod +x "${STUB_BIN}/claude"
}

install_failures_touch_stub() {
    cat > "${STUB_BIN}/touch" <<'TOUCH_STUB'
#!/bin/bash

case "$1" in
  *.failures)
    exit 1
    ;;
  *)
    /usr/bin/touch "$@"
    ;;
esac
TOUCH_STUB
    chmod +x "${STUB_BIN}/touch"
}

run_eval_runner() {
    local environment=(
        "PATH=${STUB_BIN}:${PATH}"
        "CLAUDE_ARGS_LOG=${CLAUDE_ARGS_LOG}"
        "GOLFO_MARKETPLACE_EVAL_PROVIDER=claude"
    )

    if [[ -n "${GOLFO_MARKETPLACE_EVAL_MODEL:-}" ]]; then
        environment+=("GOLFO_MARKETPLACE_EVAL_MODEL=${GOLFO_MARKETPLACE_EVAL_MODEL}")
    fi
    if [[ -n "${GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT:-}" ]]; then
        environment+=("GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT=${GOLFO_MARKETPLACE_EVAL_REASONING_EFFORT}")
    fi
    if [[ -n "${CLAUDE_RESPONSE_FILE:-}" ]]; then
        environment+=("CLAUDE_RESPONSE_FILE=${CLAUDE_RESPONSE_FILE}")
    fi
    if [[ -n "${CLAUDE_KILL_CASE_ON_CALL:-}" ]]; then
        environment+=("CLAUDE_KILL_CASE_ON_CALL=${CLAUDE_KILL_CASE_ON_CALL}")
    fi

    run --separate-stderr env "${environment[@]}" \
        "${EVAL_RUNNER}" --jobs 1 "$@" "${SKILL_DIR}"
}
