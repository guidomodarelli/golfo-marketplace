#!/bin/bash
# stack-directory.sh
# Resolves the stack template tree that instruction normalization and the
# AGENTS.md managed block read. Consumers source this file.
#
# Precedence: AGENT_READY_SETUP_STACK_DIR (exported by bootstrap.sh and the
# SessionStart hook after resolving profiles), then the profiles declared in
# .agents/agent-ready.json, then the legacy assets/stacks/<stack> directory.

# Per-user cache where composed multi-profile stack trees live; nothing
# machine-specific lands in the project.
agent_ready_compose_directory() {
  printf '%s/agent-ready-setup/compose\n' "${XDG_CACHE_HOME:-$HOME/.cache}"
}

resolve_stack_template_directory() {
  local skill_dir="$1"
  local stack="$2"
  local key
  local value

  if [[ -n "${AGENT_READY_SETUP_STACK_DIR:-}" ]]; then
    printf '%s\n' "$AGENT_READY_SETUP_STACK_DIR"
    return 0
  fi
  if [[ -f .agents/agent-ready.json && -f "$skill_dir/scripts/agent-ready-state.py" ]] &&
    command -v python3 >/dev/null 2>&1; then
    while IFS=$'\t' read -r key value; do
      if [[ "$key" == stack_dir ]]; then
        # Windows Python ends lines with CRLF.
        printf '%s\n' "${value%$'\r'}"
        return 0
      fi
    done < <(python3 "$skill_dir/scripts/agent-ready-state.py" resolve --project . \
      --skill-dir "$skill_dir" --compose-dir "$(agent_ready_compose_directory)" 2>/dev/null || true)
  fi
  printf '%s/assets/stacks/%s\n' "$skill_dir" "$stack"
}
