#!/bin/bash
# check-conflicts.sh
# Lists the structural conflicts between the selected profiles after an edit, offline and without
# writing: harness-review.py runs it from the PostToolUse hook with the paths the edit changed.
# Prints one "[conflicts]" line per conflict, and nothing when no changed path is an input of the
# checks, when there is none or when conflicts.onEdit.enabled is false.
#
# Usage: check-conflicts.sh --provider claude|codex [--changed <path>]...

set -euo pipefail

# Hermes exports these to stop Git Bash from translating paths, but this hook
# hands POSIX paths to native Windows Python, which needs that translation.
unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL

provider=""
changed_arguments=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider|-p)
      if [[ $# -lt 2 || ( "$2" != claude && "$2" != codex ) ]]; then
        printf 'ERROR: %s requires claude or codex\n' "$1" >&2
        exit 2
      fi
      provider="$2"
      shift 2
      ;;
    --changed)
      if [[ $# -lt 2 || -z "$2" ]]; then
        printf 'ERROR: --changed requires a path\n' >&2
        exit 2
      fi
      changed_arguments+=(--changed "$2")
      shift 2
      ;;
    -h|--help)
      printf 'Usage: %s --provider claude|codex [--changed <path>]...\n' "${0##*/}"
      exit 0
      ;;
    *)
      printf 'ERROR: unsupported argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done
if [[ -z "$provider" ]]; then
  printf 'ERROR: --provider claude|codex is required\n' >&2
  exit 2
fi

# shellcheck source=agent-ready-skill-source.sh
source "$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/agent-ready-skill-source.sh"

if ! skill_dir="$(resolve_skill_dir)"; then
  printf 'WARNING: could not resolve the %s source; conflicts not checked.\n' "$SKILL_NAME" >&2
  exit 0
fi
if ! project_root="$(git rev-parse --show-toplevel 2>/dev/null)" || ! command -v python3 >/dev/null 2>&1; then
  exit 0
fi
cd -- "$project_root"
state_script="$skill_dir/scripts/agent-ready-state.py"
# A pinned golfo-kit brings its content from the revision of the lock, read from the cache only.
if ! content_skill_dir="$(python3 "$state_script" golfo-kit-source --project . --skill-dir "$skill_dir" --offline --read-only)"; then
  exit 0
fi
if [[ -n "$content_skill_dir" ]]; then
  skill_dir="$content_skill_dir"
  state_script="$skill_dir/scripts/agent-ready-state.py"
fi
exec python3 "$state_script" status --project . --skill-dir "$skill_dir" --conflicts-only edit "${changed_arguments[@]}"
