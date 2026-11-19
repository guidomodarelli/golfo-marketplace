#!/bin/bash
# resolve-provider.sh
# Resolves active provider from an explicit override or installed skill path.

set -euo pipefail

skill_dir=""
provider_override="${AGENT_READY_SETUP_ACTIVE_PROVIDER:-}"
# Codex resolves its user home from CODEX_HOME; skills installed there belong to Codex.
readonly CODEX_HOME_DIRECTORY="${CODEX_HOME:-$HOME/.codex}"
# Hermes is not a target provider, but it runs this skill from its own plugin or
# skill directories; the CLI that runs the upgrade and the review must be one of these.
readonly SUPPORTED_PROVIDER_CLIS=(claude codex)

# Prints every Hermes home that may contain this skill: $HERMES_HOME, the POSIX
# default and, on Windows, %LOCALAPPDATA%/hermes.
hermes_home_directories() {
  if [[ -n "${HERMES_HOME:-}" ]]; then
    to_posix_path "$HERMES_HOME"
  fi
  printf '%s\n' "$HOME/.hermes"
  if [[ -n "${LOCALAPPDATA:-}" ]]; then
    printf '%s/hermes\n' "$(to_posix_path "$LOCALAPPDATA")"
  fi
}

# Hermes on Windows exports HERMES_HOME as C:\...; compare paths in the POSIX
# form Git Bash uses. Without cygpath the path is already POSIX.
to_posix_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -u "$1"
  else
    printf '%s\n' "$1"
  fi
}

is_inside_hermes_home() {
  local hermes_home
  local posix_skill_dir
  posix_skill_dir="$(to_posix_path "$skill_dir")"
  while IFS= read -r hermes_home; do
    if [[ "$posix_skill_dir" == "$hermes_home" || "$posix_skill_dir" == "$hermes_home/"* ]]; then
      return 0
    fi
  done < <(hermes_home_directories)
  return 1
}

# From a Hermes installation the provider is the only supported CLI in PATH;
# with both or none it cannot be inferred, so the user has to choose.
resolve_hermes_provider() {
  local provider_cli
  local -a installed_provider_clis=()
  for provider_cli in "${SUPPORTED_PROVIDER_CLIS[@]}"; do
    if command -v "$provider_cli" >/dev/null 2>&1; then
      installed_provider_clis+=("$provider_cli")
    fi
  done
  case "${#installed_provider_clis[@]}" in
    1)
      printf '%s\n' "${installed_provider_clis[0]}"
      ;;
    0)
      printf 'ERROR: skill directory %s belongs to Hermes, which is not a target provider, and neither claude nor codex is in PATH; install one of them or set AGENT_READY_SETUP_ACTIVE_PROVIDER\n' "$skill_dir" >&2
      return 1
      ;;
    *)
      printf 'ERROR: skill directory %s belongs to Hermes and both claude and codex are in PATH; ask the user which one runs the marketplace upgrade and the review, then set AGENT_READY_SETUP_ACTIVE_PROVIDER=claude|codex\n' "$skill_dir" >&2
      return 1
      ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill-dir)
      [[ $# -ge 2 && -n "${2:-}" ]] || {
        printf 'ERROR: --skill-dir requires a value\n' >&2
        exit 1
      }
      skill_dir="$2"
      shift 2
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$skill_dir" ]]; then
  printf 'ERROR: --skill-dir is required\n' >&2
  exit 1
fi

if [[ -n "$provider_override" ]]; then
  case "$provider_override" in
    claude|codex)
      printf '%s\n' "$provider_override"
      exit 0
      ;;
    *)
      printf 'ERROR: AGENT_READY_SETUP_ACTIVE_PROVIDER must be claude or codex\n' >&2
      exit 1
      ;;
  esac
fi

if [[ "$skill_dir" == "$CODEX_HOME_DIRECTORY" || "$skill_dir" == "$CODEX_HOME_DIRECTORY/"* ]]; then
  printf '%s\n' "codex"
elif [[ "$skill_dir" == "$HOME/.claude" || "$skill_dir" == "$HOME/.claude/"* ]]; then
  printf '%s\n' "claude"
elif [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && ( "$skill_dir" == "$CLAUDE_PLUGIN_ROOT" || "$skill_dir" == "$CLAUDE_PLUGIN_ROOT/"* ) ]]; then
  printf '%s\n' "claude"
elif is_inside_hermes_home; then
  resolve_hermes_provider || exit 1
else
  printf 'ERROR: could not infer provider from skill directory: %s; set AGENT_READY_SETUP_ACTIVE_PROVIDER or pass --provider\n' "$skill_dir" >&2
  exit 1
fi
