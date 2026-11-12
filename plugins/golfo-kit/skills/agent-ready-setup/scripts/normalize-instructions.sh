#!/bin/bash
# normalize-instructions.sh
# Normalizes project instruction files so AGENTS.md is canonical and every
# CLAUDE.md is the root proxy template, without projecting other assets,
# upgrading the marketplace, or installing tools. SessionStart sync runs it
# after projecting managed assets.
#
# Usage:
#   bash normalize-instructions.sh --stack <react|nextjs|nextjs-app-router|node|java|go|android>

set -euo pipefail

# Runs inside SessionStart; keep diagnostics off hook stdout.
exec 1>&2

SCRIPT_DIRECTORY="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIRECTORY
readonly SKILL_DIR="${SCRIPT_DIRECTORY%/scripts}"
STACK=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "ERROR: --stack requires react, nextjs, nextjs-app-router, node, java, go, or android" >&2; exit 1; }
      STACK="$2"
      shift 2
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

case "$STACK" in
  react|nextjs|nextjs-app-router|node|java|go|android) ;;
  *)
    echo "ERROR: --stack requires react, nextjs, nextjs-app-router, node, java, go, or android" >&2
    exit 1
    ;;
esac

if ! command -v git >/dev/null 2>&1 || [[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" != true ]]; then
  echo "ERROR: instruction normalization must run inside a Git worktree" >&2
  exit 1
fi

# shellcheck source=asset-sync-common.sh
source "$SCRIPT_DIRECTORY/asset-sync-common.sh"
# shellcheck source=instruction-normalization.sh
source "$SCRIPT_DIRECTORY/instruction-normalization.sh"

# Normalization state shared with instruction-normalization.sh.
# shellcheck disable=SC2034
CREATED=()
SKIPPED=()
# shellcheck disable=SC2034
MIGRATED=()
# shellcheck disable=SC2034
RENAMED=()
CONFLICTS=()
# shellcheck disable=SC2034
PROVIDER_ROOT_CONFLICTS=()

record_conflict() {
  CONFLICTS+=("$1")
}

record_created() {
  CREATED+=("$1")
}

record_skipped() {
  SKIPPED+=("$1")
}

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd -- "$PROJECT_ROOT"

validate_provider_roots
configure_instruction_templates "$SKILL_DIR" "$STACK"
validate_instruction_templates "$STACK" || exit 1

normalize_instructions
report_instruction_normalization
