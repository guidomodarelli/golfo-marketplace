#!/bin/bash
# resolve-provider.sh
# Resolves active provider from an explicit override or installed skill path.

set -euo pipefail

skill_dir=""
provider_override="${AGENT_READY_SETUP_ACTIVE_PROVIDER:-}"
# Codex resolves its user home from CODEX_HOME; skills installed there belong to Codex.
readonly CODEX_HOME_DIRECTORY="${CODEX_HOME:-$HOME/.codex}"
# Antigravity keeps its configuration, plugins and app data under ~/.gemini.
readonly ANTIGRAVITY_HOME_DIRECTORY="$HOME/.gemini"
# Hermes is not a target provider, but it runs this skill from its own plugin or
# skill directories; the CLI that runs the upgrade and the review must be one of these.
readonly SUPPORTED_PROVIDER_CLIS=(claude codex agy)

# The provider a CLI belongs to: agy is Antigravity.
provider_of_cli() {
  if [[ "$1" == agy ]]; then
    printf '%s\n' antigravity
  else
    printf '%s\n' "$1"
  fi
}

# The supported provider CLIs in PATH, one per line.
installed_provider_clis() {
  local provider_cli
  for provider_cli in "${SUPPORTED_PROVIDER_CLIS[@]}"; do
    if command -v "$provider_cli" >/dev/null 2>&1; then
      printf '%s\n' "$provider_cli"
    fi
  done
}

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
  local found_cli
  local -a found_clis=()
  # A read loop, not mapfile: the Bash 3.2 of macOS has no mapfile.
  while IFS= read -r found_cli; do
    found_clis+=("$found_cli")
  done < <(installed_provider_clis)
  case "${#found_clis[@]}" in
    1)
      provider_of_cli "${found_clis[0]}"
      ;;
    0)
      printf 'ERROR: skill directory %s belongs to Hermes, which is not a target provider, and none of claude, codex or agy is in PATH; install one of them or set AGENT_READY_SETUP_ACTIVE_PROVIDER\n' "$skill_dir" >&2
      return 1
      ;;
    *)
      printf 'ERROR: skill directory %s belongs to Hermes and several of claude, codex and agy are in PATH; ask the user which one runs the marketplace upgrade and the review, then set AGENT_READY_SETUP_ACTIVE_PROVIDER=claude|codex|antigravity\n' "$skill_dir" >&2
      return 1
      ;;
  esac
}

# From an installation no provider owns, Antigravity is inferred when agy is the only provider CLI in
# PATH: someone with only a Google subscription has no claude or codex to fall back to.
resolve_only_antigravity_cli() {
  local found_cli
  local -a found_clis=()
  # A read loop, not mapfile: the Bash 3.2 of macOS has no mapfile.
  while IFS= read -r found_cli; do
    found_clis+=("$found_cli")
  done < <(installed_provider_clis)
  [[ "${#found_clis[@]}" -eq 1 && "${found_clis[0]}" == agy ]] || return 1
  printf '%s\n' antigravity
}

# A skill run from a checkout (a clone of the marketplace) is in no provider directory: the
# provider is then the agent of the session, from the variables it exports. A session started
# from another one inherits its variables, so with both it is ambiguous and nothing is printed.
resolve_session_provider() {
  local -a session_providers=()
  [[ "${CLAUDECODE:-}" == "1" ]] && session_providers+=(claude)
  [[ -n "${CODEX_SESSION_ID:-}" || -n "${CODEX_THREAD_ID:-}" ]] && session_providers+=(codex)
  [[ "${#session_providers[@]}" -eq 1 ]] || return 1
  printf '%s\n' "${session_providers[0]}"
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
    claude|codex|antigravity)
      printf '%s\n' "$provider_override"
      exit 0
      ;;
    *)
      printf 'ERROR: AGENT_READY_SETUP_ACTIVE_PROVIDER must be claude, codex or antigravity\n' >&2
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
elif [[ "$skill_dir" == "$ANTIGRAVITY_HOME_DIRECTORY" || "$skill_dir" == "$ANTIGRAVITY_HOME_DIRECTORY/"* ]]; then
  printf '%s\n' "antigravity"
elif is_inside_hermes_home; then
  resolve_hermes_provider || exit 1
elif session_provider="$(resolve_session_provider)"; then
  printf '%s\n' "$session_provider"
elif resolve_only_antigravity_cli; then
  :
else
  printf 'ERROR: could not infer provider from skill directory: %s; set AGENT_READY_SETUP_ACTIVE_PROVIDER or pass --provider\n' "$skill_dir" >&2
  exit 1
fi
