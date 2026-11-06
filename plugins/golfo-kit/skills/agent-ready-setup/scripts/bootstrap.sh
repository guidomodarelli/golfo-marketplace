#!/bin/bash
# bootstrap.sh
# Projects Agent Ready templates into Claude, shared-agent, and Codex trees.
# Profiles (assets/profiles.json) select which templates apply. Managed assets
# follow the ownership contract of agent-ready-state.py: a file that still
# matches its lockfile base is updated, a locally modified one is preserved and
# reported, and assets no longer published are retired only when unmodified.
# Without a lockfile (first apply) managed assets are overwritten once.
# Instruction files are normalized so AGENTS.md is canonical and every CLAUDE.md
# is the root proxy template. Writes .agents/agent-ready.json (manifest) and
# .agents/agent-ready.lock.json (lockfile).
#
# Usage:
#   bash bootstrap.sh --skill-dir <path> [--profiles <a,b> | --stack <frontend|node|java|go|android>]
#     [--provider <claude|codex>] [--updates <pinned|auto>] [--plan | --status]
#
# Without --profiles or --stack, the profiles come from .agents/agent-ready.json.
# --plan and --status are read-only: no marketplace upgrade, no writes, no tool
# installation. Instruction normalization alone runs through normalize-instructions.sh.

set -euo pipefail

# Hermes exports these to stop Git Bash from translating paths, but this script
# hands POSIX paths to native Windows Python, which needs that translation.
unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL

# Bootstrap may run inside SessionStart; keep diagnostics off hook stdout.
exec 1>&2

# Shared normalization loads from this script's own directory so both stay on one version.
# shellcheck source=instruction-normalization.sh
source "$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/instruction-normalization.sh"

# shellcheck disable=SC2034
readonly MARKETPLACE_NAME="golfo-marketplace"
readonly SKILL_NAME="agent-ready-setup"
# Codex resolves its user home from CODEX_HOME; config, snapshot and cache follow it.
readonly CODEX_HOME_DIRECTORY="${CODEX_HOME:-$HOME/.codex}"

STACK=""
PROFILES=""
REQUESTED_SKILL_DIR=""
UPDATE_MODE=""
# apply (default), plan or status.
RUN_MODE="apply"
SKILL_DIR=""
PROVIDER="${AGENT_READY_SETUP_ACTIVE_PROVIDER:-}"
MARKETPLACE_ALREADY_UPGRADED="${AGENT_READY_SETUP_MARKETPLACE_UPGRADED:-0}"
readonly SYNC_LOCK_DIRECTORY=".agents/.agent-ready-assets.lock"
# shellcheck disable=SC2034
readonly SYNC_LOCK_OWNER_FILE="$SYNC_LOCK_DIRECTORY/owner"
# shellcheck disable=SC2034
SYNC_LOCK_ACQUIRED=0
# shellcheck disable=SC2034
SYNC_LOCK_INHERITED=0
SYNC_LOCK_ENABLED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack)
      [[ $# -ge 2 ]] || { echo "ERROR: --stack requires a value" >&2; exit 1; }
      STACK="$2"
      shift 2
      ;;
    --skill-dir)
      [[ $# -ge 2 ]] || { echo "ERROR: --skill-dir requires a value" >&2; exit 1; }
      REQUESTED_SKILL_DIR="$2"
      shift 2
      ;;
    --provider)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "ERROR: --provider requires claude or codex" >&2; exit 1; }
      PROVIDER="$2"
      shift 2
      ;;
    --profiles)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "ERROR: --profiles requires a comma separated list" >&2; exit 1; }
      PROFILES="$2"
      shift 2
      ;;
    --updates)
      [[ $# -ge 2 && ( "${2:-}" == pinned || "${2:-}" == auto ) ]] || {
        echo "ERROR: --updates requires pinned or auto" >&2
        exit 1
      }
      UPDATE_MODE="$2"
      shift 2
      ;;
    --plan|--status)
      [[ "$RUN_MODE" == apply ]] || { echo "ERROR: --plan and --status are mutually exclusive" >&2; exit 1; }
      RUN_MODE="${1#--}"
      shift
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

case "$MARKETPLACE_ALREADY_UPGRADED" in
  0|1) ;;
  *)
    echo "ERROR: AGENT_READY_SETUP_MARKETPLACE_UPGRADED must be 0 or 1" >&2
    exit 1
    ;;
esac

if [[ -z "$REQUESTED_SKILL_DIR" ]]; then
  echo "ERROR: --skill-dir is required" >&2
  exit 1
fi

if [[ -n "$STACK" && -n "$PROFILES" ]]; then
  echo "ERROR: --stack and --profiles are mutually exclusive" >&2
  exit 1
fi

case "$STACK" in
  ""|frontend|node|java|go|android) ;;
  *)
    echo "ERROR: Unsupported stack '$STACK'. Expected frontend, node, java, go, or android." >&2
    exit 1
    ;;
esac

case "${AGENT_READY_SETUP_UPDATES:-}" in
  ""|pinned|auto) ;;
  *)
    echo "ERROR: AGENT_READY_SETUP_UPDATES must be pinned or auto" >&2
    exit 1
    ;;
esac
UPDATE_MODE="${UPDATE_MODE:-${AGENT_READY_SETUP_UPDATES:-}}"

is_valid_skill_dir() {
  local candidate="$1"

  [[ -f "$candidate/SKILL.md" && \
    -f "$candidate/scripts/bootstrap.sh" && \
    -d "$candidate/assets/stacks" ]]
}

if [[ ! -d "$REQUESTED_SKILL_DIR" ]]; then
  echo "ERROR: --skill-dir must point to an existing directory: $REQUESTED_SKILL_DIR" >&2
  exit 1
fi

SKILL_DIR="$REQUESTED_SKILL_DIR"
if [[ -z "$PROVIDER" ]]; then
  provider_resolver="$SKILL_DIR/scripts/resolve-provider.sh"
  if [[ ! -f "$provider_resolver" ]]; then
    echo "ERROR: provider is not explicit and resolver is missing: $provider_resolver" >&2
    exit 1
  fi
  PROVIDER="$(bash "$provider_resolver" --skill-dir "$SKILL_DIR")"
fi

case "$PROVIDER" in
  claude|codex) ;;
  *)
    echo "ERROR: Unsupported provider '$PROVIDER'. Expected claude or codex." >&2
    exit 1
    ;;
esac

if [[ "$SKILL_DIR" != /* ]]; then
  if ! SKILL_DIR="$(CDPATH='' cd -- "$SKILL_DIR" && pwd)"; then
    echo "ERROR: could not resolve --skill-dir: $SKILL_DIR" >&2
    exit 1
  fi
fi

sorted_skill_candidates() {
  local cache_root="$1"
  local skill_name="$2"

  # Prefix candidates with zero-padded numeric components before lexical sorting.
  find "$cache_root" -type f -path "*/skills/$skill_name/SKILL.md" -print 2>/dev/null |
    awk -F/ '
      {
        version = $(NF - 3)
        if (version !~ /^[0-9]+(\.[0-9]+)?(\.[0-9]+)?([+-].*)?$/) {
          printf "%020d.%020d.%020d\t%s\n", 0, 0, 0, $0
          next
        }
        split(version, components, /[.+-]/)
        printf "%020d.%020d.%020d\t%s\n", components[1] + 0, components[2] + 0, components[3] + 0, $0
      }
    ' |
    sort -r |
    cut -f2-
}

# Uses the same zero-padded numeric components as sorted_skill_candidates so
# snapshot and cache versions compare identically.
semantic_version_key() {
  printf '%s\n' "$1" |
    awk '
      {
        if ($0 !~ /^[0-9]+(\.[0-9]+)?(\.[0-9]+)?([+-].*)?$/) {
          printf "%020d.%020d.%020d\n", 0, 0, 0
          next
        }
        split($0, components, /[.+-]/)
        printf "%020d.%020d.%020d\n", components[1] + 0, components[2] + 0, components[3] + 0
      }
    '
}

# Prints one value from the Codex marketplace section; accepts basic ("...")
# and literal ('...') TOML strings because Codex may write either form.
codex_marketplace_config_value() {
  local config_key="$1"
  local codex_config="$CODEX_HOME_DIRECTORY/config.toml"

  [[ -f "$codex_config" ]] || return 0
  awk -v section="[marketplaces.$MARKETPLACE_NAME]" -v config_key="$config_key" '
    /^[[:space:]]*\[/ {
      current = $0
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", current)
      in_section = (current == section)
      next
    }
    in_section && match($0, "^[[:space:]]*" config_key "[[:space:]]*=[[:space:]]*") {
      value = substr($0, RLENGTH + 1)
      quote = substr(value, 1, 1)
      if (quote != "\"" && quote != "\047") {
        next
      }
      value = substr(value, 2)
      closing_quote = index(value, quote)
      if (closing_quote > 0) {
        print substr(value, 1, closing_quote - 1)
        exit
      }
    }
  ' "$codex_config" 2>/dev/null || true
}

# `codex plugin marketplace upgrade` refreshes only Git marketplaces; a local
# marketplace is read in place from its configured source.
is_codex_local_marketplace() {
  [[ "$(codex_marketplace_config_value source_type)" == "local" ]]
}

# The marketplace upgrade refreshes only the provider marketplace snapshot; the
# versioned plugin cache advances only after a provider plugin update, so the
# snapshot is the source that carries the latest published templates.
marketplace_snapshot_root() {
  local marketplace_provider="$1"
  local known_marketplaces="$HOME/.claude/plugins/known_marketplaces.json"
  local configured_location=""

  if [[ "$marketplace_provider" == "claude" ]]; then
    if [[ -f "$known_marketplaces" ]] && command -v python3 >/dev/null 2>&1; then
      configured_location="$(python3 - "$known_marketplaces" "$MARKETPLACE_NAME" <<'PY' 2>/dev/null || true
import json
import sys

with open(sys.argv[1], encoding="utf-8") as known_marketplaces_file:
    marketplace = json.load(known_marketplaces_file).get(sys.argv[2]) or {}
install_location = marketplace.get("installLocation") if isinstance(marketplace, dict) else None
if isinstance(install_location, str):
    print(install_location)
PY
)"
      # Windows Python ends lines with CRLF; keep the path free of a trailing carriage return.
      configured_location="${configured_location%$'\r'}"
    fi
    printf '%s\n' "${configured_location:-$HOME/.claude/plugins/marketplaces/$MARKETPLACE_NAME}"
    return 0
  fi

  if is_codex_local_marketplace; then
    configured_location="$(codex_marketplace_config_value source)"
  fi
  printf '%s\n' "${configured_location:-$CODEX_HOME_DIRECTORY/.tmp/marketplaces/$MARKETPLACE_NAME}"
}

marketplace_snapshot_skill_dir() {
  printf '%s/plugins/golfo-kit/skills/%s\n' "$(marketplace_snapshot_root "$1")" "$SKILL_NAME"
}

# Reads the plugin manifest version beside the snapshot skill; both provider
# manifests share the same version.
marketplace_snapshot_version() {
  local plugin_root
  local manifest

  plugin_root="$(marketplace_snapshot_root "$1")/plugins/golfo-kit"
  for manifest in "$plugin_root/.claude-plugin/plugin.json" "$plugin_root/.codex-plugin/plugin.json"; do
    if [[ -f "$manifest" ]]; then
      sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$manifest" | head -n 1
      return 0
    fi
  done
}

cache_skill_version() {
  basename "$(dirname "$(dirname "$1")")"
}

resolve_skill_dir() {
  local candidate
  local provider_root
  local cache_root
  local project_root
  local snapshot_candidate
  local snapshot_provider

  if [[ -n "${AGENT_READY_SETUP_SKILL_DIR:-}" ]]; then
    candidate="$AGENT_READY_SETUP_SKILL_DIR"
    if is_valid_skill_dir "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
    printf 'ERROR: AGENT_READY_SETUP_SKILL_DIR is not a valid %s source: %s\n' \
      "$SKILL_NAME" "$candidate" >&2
    return 1
  fi

  if [[ "$MARKETPLACE_ALREADY_UPGRADED" -eq 1 ]]; then
    if is_valid_skill_dir "$REQUESTED_SKILL_DIR"; then
      printf '%s\n' "$REQUESTED_SKILL_DIR"
      return 0
    fi
    return 1
  fi

  if [[ "$REQUESTED_SKILL_DIR" == "$CODEX_HOME_DIRECTORY/plugins/cache/$MARKETPLACE_NAME"/* ]]; then
    snapshot_provider="codex"
  elif [[ "$REQUESTED_SKILL_DIR" == "$HOME/.claude/plugins/cache/$MARKETPLACE_NAME"/* ]]; then
    snapshot_provider="claude"
  elif [[ "$PROVIDER" == "claude" ]]; then
    snapshot_provider="claude"
  else
    snapshot_provider="codex"
  fi
  if [[ "$snapshot_provider" == "claude" ]]; then
    provider_root="$HOME/.claude"
  else
    provider_root="$CODEX_HOME_DIRECTORY"
  fi
  cache_root="$provider_root/plugins/cache/$MARKETPLACE_NAME/golfo-kit"

  if [[ "$REQUESTED_SKILL_DIR" != "$cache_root"/* ]] && \
    is_valid_skill_dir "$REQUESTED_SKILL_DIR"; then
    printf '%s\n' "$REQUESTED_SKILL_DIR"
    return 0
  fi

  snapshot_candidate="$(marketplace_snapshot_skill_dir "$snapshot_provider")"
  if ! is_valid_skill_dir "$snapshot_candidate"; then
    snapshot_candidate=""
  fi

  # The requested cache version stays eligible: excluding it downgraded callers
  # that already pass the newest version to the next older cache entry. The
  # snapshot wins unless the cache already holds a newer version, so projection
  # never waits for a provider plugin update.
  while IFS= read -r candidate; do
    candidate="${candidate%/SKILL.md}"
    if is_valid_skill_dir "$candidate"; then
      if [[ -n "$snapshot_candidate" ]] && \
        [[ ! "$(semantic_version_key "$(marketplace_snapshot_version "$snapshot_provider")")" < \
          "$(semantic_version_key "$(cache_skill_version "$candidate")")" ]]; then
        candidate="$snapshot_candidate"
      fi
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(sorted_skill_candidates "$cache_root" "$SKILL_NAME")

  if [[ -n "$snapshot_candidate" ]]; then
    printf '%s\n' "$snapshot_candidate"
    return 0
  fi

  if [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    for candidate in \
      "$CLAUDE_PLUGIN_ROOT/skills/$SKILL_NAME" \
      "$CLAUDE_PLUGIN_ROOT"; do
      if [[ "$candidate" != "$REQUESTED_SKILL_DIR" ]] && is_valid_skill_dir "$candidate"; then
        printf '%s\n' "$candidate"
        return 0
      fi
    done
  fi

  candidate="$provider_root/skills/$SKILL_NAME"
  if [[ "$candidate" != "$REQUESTED_SKILL_DIR" ]] && is_valid_skill_dir "$candidate"; then
    printf '%s\n' "$candidate"
    return 0
  fi

  if project_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    candidate="$project_root/plugins/golfo-kit/skills/$SKILL_NAME"
    if [[ "$candidate" != "$REQUESTED_SKILL_DIR" ]] && is_valid_skill_dir "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  if is_valid_skill_dir "$REQUESTED_SKILL_DIR"; then
    printf '%s\n' "$REQUESTED_SKILL_DIR"
    return 0
  fi

  return 1
}

describe_skill_source() {
  local source="$1"
  local source_version
  local snapshot_provider

  for snapshot_provider in claude codex; do
    if [[ "$source" == "$(marketplace_snapshot_skill_dir "$snapshot_provider")" ]]; then
      source_version="$(marketplace_snapshot_version "$snapshot_provider")"
      printf '[marketplace-bootstrap] Using %s marketplace snapshot version %s.\n' \
        "$SKILL_NAME" "${source_version:-unknown}"
      return 0
    fi
  done

  source_version="$(cache_skill_version "$source")"
  if [[ "$source_version" =~ ^[0-9]+(\.[0-9]+){0,2}([+-].*)?$ ]]; then
    printf '[marketplace-bootstrap] Using %s cache version %s.\n' "$SKILL_NAME" "$source_version"
  else
    printf '[marketplace-bootstrap] Using local %s source.\n' "$SKILL_NAME"
  fi
}

validate_skill_source() {
  configure_instruction_templates "$SKILL_DIR" "$STACK"
  CODEX_ASSETS="$SKILL_DIR/assets/codex"

  if [[ ! -d "$COMMON_SRC" ]]; then
    echo "ERROR: Common assets directory is missing: $COMMON_SRC" >&2
    exit 1
  fi

  if [[ ! -f "$COMMON_SRC/settings.json" ]]; then
    echo "ERROR: Common Claude settings template is missing: $COMMON_SRC/settings.json" >&2
    exit 1
  fi

  if [[ ! -f "$COMMON_SRC/hooks/sync-marketplace.sh" ]]; then
    echo "ERROR: Common marketplace sync hook is missing: $COMMON_SRC/hooks/sync-marketplace.sh" >&2
    exit 1
  fi

  validate_instruction_templates "$STACK" || exit 1

  if [[ ! -f "$SKILL_DIR/scripts/asset-sync-common.sh" ]]; then
    echo "ERROR: Shared asset synchronization helper is missing: $SKILL_DIR/scripts/asset-sync-common.sh" >&2
    exit 1
  fi

  if [[ ! -f "$SKILL_DIR/scripts/merge-managed-settings.py" ]]; then
    echo "ERROR: Managed settings merger is missing: $SKILL_DIR/scripts/merge-managed-settings.py" >&2
    exit 1
  fi

  if [[ ! -f "$CODEX_ASSETS/hooks.json" ]]; then
    echo "ERROR: Codex hook template is missing: $CODEX_ASSETS/hooks.json" >&2
    exit 1
  fi
}

CREATED=()
UPDATED=()
SKIPPED=()
MIGRATED=()
RENAMED=()
REMOVED=()
CONFLICTS=()
CLEANUP_CONFLICTS=()
# shellcheck disable=SC2034 # Read by validate_provider_roots in instruction-normalization.sh.
PROVIDER_ROOT_CONFLICTS=()

record_conflict() {
  CONFLICTS+=("$1")
}

if ! command -v git >/dev/null 2>&1 || [[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" != true ]]; then
  echo "ERROR: bootstrap must run inside a Git worktree" >&2
  exit 1
fi

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd -- "$PROJECT_ROOT"

if [[ -z "$STACK" && -z "$PROFILES" && ! -f .agents/agent-ready.json ]]; then
  echo "ERROR: pass --profiles or --stack; this repository has no .agents/agent-ready.json yet" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required to resolve profiles and the lockfile" >&2
  exit 1
fi

validate_provider_roots

# Each provider refreshes its own marketplace snapshot through its CLI.
upgrade_marketplace() {
  local -a upgrade_command

  if [[ "$PROVIDER" == "codex" ]] && is_codex_local_marketplace; then
    echo "[marketplace-bootstrap] $MARKETPLACE_NAME es un marketplace Codex local; se omite el upgrade y se usa su source configurado."
    return 0
  fi

  if [[ "$PROVIDER" == "claude" ]]; then
    upgrade_command=(claude plugin marketplace update "$MARKETPLACE_NAME")
  else
    upgrade_command=(codex plugin marketplace upgrade "$MARKETPLACE_NAME")
  fi

  if ! command -v "$PROVIDER" >/dev/null 2>&1; then
    printf 'ERROR: se requiere la CLI de %s para hacer upgrade de %s antes del bootstrap.\n' "$PROVIDER" "$MARKETPLACE_NAME" >&2
    return 1
  fi

  echo "[marketplace-bootstrap] Haciendo upgrade de $MARKETPLACE_NAME para $PROVIDER..."
  if ! "${upgrade_command[@]}"; then
    printf 'ERROR: falló el upgrade del marketplace para %s/%s; no se modificó ningún asset del proyecto.\n' \
      "$MARKETPLACE_NAME" "$PROVIDER" >&2
    return 1
  fi
  echo "[marketplace-bootstrap] Upgrade del marketplace completado."
}

if [[ "$RUN_MODE" != apply ]]; then
  echo "[marketplace-bootstrap] Read-only $RUN_MODE: the marketplace upgrade is skipped."
elif [[ "$MARKETPLACE_ALREADY_UPGRADED" -eq 0 ]]; then
  if ! upgrade_marketplace; then
    exit 1
  fi
else
  echo "[marketplace-bootstrap] El caller ya completó el upgrade del marketplace."
fi

if ! SKILL_DIR="$(resolve_skill_dir)"; then
  echo "ERROR: no se pudo resolver el source actualizado de $SKILL_NAME después del upgrade del marketplace" >&2
  exit 1
fi
describe_skill_source "$SKILL_DIR"
STATE_SCRIPT="$SKILL_DIR/scripts/agent-ready-state.py"
PROFILE_SELECTION=()
if [[ -n "$PROFILES" ]]; then
  PROFILE_SELECTION=(--profiles "$PROFILES")
elif [[ -n "$STACK" ]]; then
  PROFILE_SELECTION=(--stack "$STACK")
fi

if [[ "$RUN_MODE" == status ]]; then
  python3 "$STATE_SCRIPT" status --project . --skill-dir "$SKILL_DIR"
  exit $?
fi

# Resolves profiles once; every later step reads the same stack tree.
RESOLVED_PROFILES=""
RESOLVED_TOOLS=""
if ! resolution="$(python3 "$STATE_SCRIPT" resolve --project . --skill-dir "$SKILL_DIR" \
  ${PROFILE_SELECTION[@]+"${PROFILE_SELECTION[@]}"} --compose-dir "$(agent_ready_compose_directory)")"; then
  exit 1
fi
while IFS=$'\t' read -r resolution_key resolution_value; do
  resolution_value="${resolution_value%$'\r'}"
  case "$resolution_key" in
    profiles) RESOLVED_PROFILES="$resolution_value" ;;
    primary) STACK="$resolution_value" ;;
    stack_dir) export AGENT_READY_SETUP_STACK_DIR="$resolution_value" ;;
    tools) RESOLVED_TOOLS="$resolution_value" ;;
  esac
done <<< "$resolution"

if [[ "$RUN_MODE" == plan ]]; then
  python3 "$STATE_SCRIPT" plan --project . --skill-dir "$SKILL_DIR" --provider "$PROVIDER" \
    ${PROFILE_SELECTION[@]+"${PROFILE_SELECTION[@]}"}
  exit $?
fi

validate_skill_source
# shellcheck disable=SC2034
ASSET_SYNC_SKILL_DIR="$SKILL_DIR"
# Serializes sync writers so concurrent invocations cannot replace each other's
# files. Upgrade runs before this lock to keep failed upgrades write-free.
# shellcheck disable=SC1091
source "$SKILL_DIR/scripts/asset-sync-common.sh"
# shellcheck disable=SC2034
SYNC_LOCK_ENABLED=1

if ! acquire_sync_lock; then
  exit 0
fi

# The pre-apply plan decides ownership: protected destinations are preserved by
# sync_file, and finalize retires assets and writes the lockfile from it.
PLAN_FILE="$(mktemp "${TMPDIR:-/tmp}/agent-ready-plan.XXXXXX")"
trap 'rm -f -- "$PLAN_FILE"; release_sync_lock' EXIT
if ! protected_destinations="$(python3 "$STATE_SCRIPT" plan --project . --skill-dir "$SKILL_DIR" \
  --format protected --save "$PLAN_FILE" ${PROFILE_SELECTION[@]+"${PROFILE_SELECTION[@]}"})"; then
  echo "ERROR: could not compute the Agent Ready plan; no asset was changed" >&2
  exit 1
fi
load_protected_destinations "$protected_destinations"

record_created() {
  CREATED+=("$1")
}

record_updated() {
  UPDATED+=("$1")
}

record_skipped() {
  SKIPPED+=("$1")
}

sync_file() {
  local src="$1"
  local dst="$2"
  local source_description="${3:-$src}"
  local expected_destination=""
  local temporary_destination
  local supplied_snapshot="${4:-}"

  if [[ ! -f "$src" ]]; then
    CONFLICTS+=("$source_description is not a regular file; $dst was not changed")
    return 0
  fi

  if is_protected_destination "$dst"; then
    record_conflict "$dst: $AGENT_READY_PROTECTED_HINT"
    return 0
  fi

  # A caller may require the exact pre-merge snapshot, including initial absence.
  if [[ -n "$supplied_snapshot" ]] && ! destination_matches_snapshot "$dst" "$supplied_snapshot"; then
    record_conflict "$dst changed during synchronization; neither was changed"
    return 0
  fi

  if ! validate_destination_parent "$dst"; then
    return 0
  fi
  ensure_parent_directory "$dst"

  if [[ -L "$dst" ]]; then
    if [[ -n "$supplied_snapshot" ]]; then
      record_conflict "$dst changed during synchronization; neither was changed"
      return 0
    fi
    replace_managed_symlink "$src" "$dst"
    return 0
  fi

  if [[ -e "$dst" && ! -f "$dst" ]]; then
    CONFLICTS+=("$dst is not a regular file; neither it nor its parent was changed")
    return 0
  fi

  if [[ ! -e "$dst" ]]; then
    if ! temporary_destination="$(mktemp "${dst}.agent-ready-sync.XXXXXX")"; then
      CONFLICTS+=("could not stage new content for $dst; neither was changed")
      return 0
    fi
    if ! cp -p -- "$src" "$temporary_destination"; then
      rm -f -- "$temporary_destination"
      CONFLICTS+=("could not stage new content for $dst; neither was changed")
      return 0
    fi
    if [[ -n "$supplied_snapshot" ]] && ! destination_matches_snapshot "$dst" "$supplied_snapshot"; then
      rm -f -- "$temporary_destination"
      record_conflict "$dst changed during synchronization; neither was changed"
      return 0
    fi
    if ! mv -f -- "$temporary_destination" "$dst"; then
      rm -f -- "$temporary_destination"
      CONFLICTS+=("could not create $dst atomically; neither was changed")
      return 0
    fi
    record_created "$dst"
    return 0
  fi

  if matches_ignoring_line_endings "$dst" "$src"; then
    record_skipped "$dst"
    return 0
  fi

  expected_destination="$(mktemp "${dst}.agent-ready-expected.XXXXXX")"
  if ! cp -p -- "${supplied_snapshot:-$dst}" "$expected_destination"; then
    rm -f -- "$expected_destination"
    CONFLICTS+=("could not snapshot $dst before replacement; neither was changed")
    return 0
  fi

  show_sync_diff "$src" "$dst" "$source_description"

  temporary_destination="$(mktemp "${dst}.agent-ready-sync.XXXXXX")"
  if ! cp -p -- "$src" "$temporary_destination"; then
    rm -f -- "$temporary_destination" "$expected_destination"
    CONFLICTS+=("could not stage updated content for $dst; neither was changed")
    return 0
  fi

  if [[ -L "$dst" || ! -f "$dst" ]] || ! cmp -s "$dst" "$expected_destination"; then
    rm -f -- "$temporary_destination" "$expected_destination"
    CONFLICTS+=("$dst changed during synchronization; neither was changed")
    return 0
  fi

  # The sync lock serializes cooperating writers through this final check and
  # atomic rename; changed external content fails the snapshot comparison.
  if ! mv -f -- "$temporary_destination" "$dst"; then
    rm -f -- "$temporary_destination" "$expected_destination"
    CONFLICTS+=("could not replace $dst atomically; neither was changed")
    return 0
  fi
  rm -f -- "$expected_destination"
  record_updated "$dst"
}

link_claude_asset() {
  local relative="$1"
  local source="$SHARED_DIR/$relative"
  local destination="$CLAUDE_DIR/$relative"
  local target

  case "$relative" in
    ""|/*|../*|*/../*|*/..)
      echo "ERROR: Invalid shared asset path: $relative" >&2
      return 1
      ;;
  esac

  if [[ ! -e "$source" && ! -L "$source" ]]; then
    echo "ERROR: Canonical shared asset is missing: $source" >&2
    return 1
  fi

  if ! validate_destination_parent "$destination"; then
    return 0
  fi
  ensure_parent_directory "$destination"
  target=$(relative_shared_target "$relative")

  if is_current_claude_view "$destination" "$target" "$source"; then
    record_skipped "$destination"
    return 0
  fi
  if [[ -L "$destination" ]]; then
    replace_with_claude_view "$destination" "$target" "$source" "$relative"
    return 0
  fi

  if [[ -e "$destination" ]]; then
    if [[ ! -f "$destination" ]]; then
      CONFLICTS+=("$destination is not a regular file; neither was changed")
      return 0
    fi
    if is_protected_destination "$destination"; then
      record_conflict "$destination: $AGENT_READY_PROTECTED_HINT"
      return 0
    fi
    replace_with_claude_view "$destination" "$target" "$source" "$relative"
    return 0
  fi

  if ! create_claude_view_link "$target" "$source" "$destination" "$relative"; then
    CONFLICTS+=("could not create Claude view $destination; neither was changed ($CLAUDE_VIEW_FAILURE_HINT)")
    return 0
  fi
  record_created "$destination -> $source"
}

record_removed() {
  REMOVED+=("$1")
}

record_cleanup_conflict() {
  CLEANUP_CONFLICTS+=("$1")
}

cleanup_stale_claude_links() {
  local link_path
  local relative
  local target
  local expected_target
  local source_path

  [[ -d "$CLAUDE_DIR" ]] || return 0

  while IFS= read -r -d '' link_path; do
    relative="${link_path#"$CLAUDE_DIR/"}"
    [[ "$relative" == "settings.json" || "$relative" == "hooks" || "$relative" == hooks/* ]] && continue

    if ! target="$(readlink -- "$link_path")"; then
      record_cleanup_conflict "$link_path target could not be read; preserved"
      continue
    fi
    expected_target="$(relative_shared_target "$relative")"
    if [[ "$target" == "$expected_target" ]]; then
      source_path="$SHARED_DIR/$relative"
      if [[ ! -e "$source_path" && ! -L "$source_path" ]]; then
        if rm -f -- "$link_path"; then
          record_removed "$link_path"
        else
          record_cleanup_conflict "could not remove stale managed symlink $link_path; preserved"
        fi
      fi
    elif [[ "$target" == *".agents/"* ]]; then
      record_cleanup_conflict "$link_path points to a non-managed .agents target; preserved"
    fi
  done < <(find "$CLAUDE_DIR" -type l -print0)
}

sync_claude_settings() {
  local template="$1"
  local destination="$CLAUDE_DIR/settings.json"
  local temporary_settings
  local merge_status=0

  if [[ -L "$destination" ]]; then
    record_cleanup_conflict "$destination is a symlink; preserved"
    return 0
  fi
  if [[ -e "$destination" && ! -f "$destination" ]]; then
    record_cleanup_conflict "$destination is not a regular file; preserved"
    return 0
  fi
  if [[ ! -f "$destination" ]]; then
    sync_file "$template" "$destination" "$template"
    return 0
  fi

  temporary_settings="$(mktemp "${TMPDIR:-/tmp}/agent-ready-settings.XXXXXX")"
  merge_managed_settings "$template" "$destination" nested > "$temporary_settings" || merge_status=$?

  case "$merge_status" in
    0)
      sync_file "$temporary_settings" "$destination" "$template"
      ;;
    10)
      cp -- "$template" "$temporary_settings"
      sync_file "$temporary_settings" "$destination" "$template"
      ;;
    *)
      record_cleanup_conflict "$destination contains invalid JSON; preserved"
      ;;
  esac
  rm -f -- "$temporary_settings"
}

# The centralization rule is part of the managed AGENTS.md block, which
# merge-instructions.sh copies verbatim from the template on every sync.
normalize_instructions

# Templates already carry provider frontmatter, so skill adapters are verbatim
# copies of their source template.
create_skill_adapter() {
  local src="$1"
  local skill_name="$2"

  sync_file "$src" "$SHARED_DIR/skills/$skill_name/SKILL.md"
}

# Project shared assets into the canonical .agents tree. Claude-specific
# settings remain copied to .claude; non-hook Claude assets are symlinked views
# of the canonical shared files so providers cannot drift independently. Hooks
# remain only in .agents because both providers execute the canonical scripts.
project_asset_tree() {
  local source_root="$1"
  local file
  local relative
  local skill_name

  while IFS= read -r -d '' file; do
    relative="${file#"$source_root/"}"

    if [[ "$relative" == "agents-template.md" ]]; then
      continue
    elif [[ "$relative" == "settings.json" ]]; then
      sync_claude_settings "$file"
    else
      case "$relative" in
        github/*)
          sync_file "$file" ".github/${relative#github/}"
          continue
          ;;
        skills/*/SKILL.md)
          skill_name="${relative#skills/}"
          skill_name="${skill_name%/SKILL.md}"
          create_skill_adapter "$file" "$skill_name"
          ;;
        skills/*/*.md)
          sync_file "$file" "$SHARED_DIR/$relative"
          ;;
        agents/*.md|commands/*.md|skills/*.md)
          sync_file "$file" "$SHARED_DIR/$relative"
          skill_name="${relative##*/}"
          skill_name="${skill_name%.md}"
          create_skill_adapter "$file" "$skill_name"
          case "$relative" in
            skills/*.md) link_claude_asset "skills/$skill_name/SKILL.md" ;;
            *) remove_claude_skill_view "$skill_name" ;;
          esac
          ;;
        *)
          sync_file "$file" "$SHARED_DIR/$relative"
          ;;
      esac

      if [[ "$relative" != hooks/* ]]; then
        link_claude_asset "$relative"
      fi
    fi
  done < <(find "$source_root" -type f -print0)
}

project_asset_tree "$COMMON_SRC"
project_asset_tree "$SRC"
project_rule_claude_views "$TEMPLATE_RENDERER" "$SRC/rules" "$COMMON_SRC/rules"
prune_hard_link_views
install_hard_link_git_hook "$SKILL_DIR/assets/git-hooks/post-index-change"

cleanup_stale_claude_links

# Codex-specific plugin assets use Codex's supported names while retaining the
# same MCP definitions and shared hook scripts.
if [[ -f "$SRC/mcp.json" ]]; then
  sync_file "$SRC/mcp.json" "$CODEX_DIR/.mcp.json"
fi
sync_codex_hooks "$CODEX_ASSETS/hooks.json"

finalize_arguments=(finalize --project . --skill-dir "$SKILL_DIR" --plan "$PLAN_FILE")
[[ -n "$UPDATE_MODE" ]] && finalize_arguments+=(--updates "$UPDATE_MODE")
FINALIZE_REPORT=""
if ! FINALIZE_REPORT="$(python3 "$STATE_SCRIPT" "${finalize_arguments[@]}")"; then
  CONFLICTS+=("could not write .agents/agent-ready.lock.json; the next apply treats this run as unlocked")
fi

browser_setup_status=0
case "${AGENT_READY_SETUP_BROWSER_INSTALL:-1}" in
  1)
    if [[ ",$RESOLVED_TOOLS," == *",browser,"* ]]; then
      python3 "$SKILL_DIR/scripts/setup-browser-tools.py" --project "$PWD" || browser_setup_status=$?
    else
      printf 'Browser installation skipped: no selected profile needs browser tools\n'
    fi
    ;;
  0) printf 'Browser installation skipped by AGENT_READY_SETUP_BROWSER_INSTALL=0\n' ;;
  *) printf 'ERROR: AGENT_READY_SETUP_BROWSER_INSTALL must be 0 or 1\n'; browser_setup_status=1 ;;
esac

# Print report
printf '\nStack: %s\n' "$STACK"
printf 'Profiles: %s\n' "$RESOLVED_PROFILES"
printf 'Providers: Claude Code + Codex-compatible shared tree\n'
# Stable line the agent reads to run follow-up scripts from the resolved source.
printf 'Resolved %s source: %s\n\n' "$SKILL_NAME" "$SKILL_DIR"

if [[ ${#CREATED[@]} -gt 0 ]]; then
  echo "Created:"
  for file in "${CREATED[@]}"; do printf '  + %s\n' "$file"; done
fi

if [[ ${#UPDATED[@]} -gt 0 ]]; then
  echo ""
  echo "Updated from templates:"
  for file in "${UPDATED[@]}"; do printf '  ↻ %s\n' "$file"; done
fi

if [[ ${#RENAMED[@]} -gt 0 ]]; then
  echo ""
  echo "Renamed instruction files:"
  for file in "${RENAMED[@]}"; do printf '  ↪ %s\n' "$file"; done
fi

if [[ ${#MIGRATED[@]} -gt 0 ]]; then
  echo ""
  echo "Normalized instructions:"
  for file in "${MIGRATED[@]}"; do printf '  ↔ %s\n' "$file"; done
fi

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
  echo ""
  echo "Already existed (skipped):"
  for file in "${SKIPPED[@]}"; do printf '  ~ %s\n' "$file"; done
fi

if [[ ${#REMOVED[@]} -gt 0 ]]; then
  echo ""
  echo "Removed stale managed assets:"
  for file in "${REMOVED[@]}"; do printf '  - %s\n' "$file"; done
fi

if [[ ${#CLEANUP_CONFLICTS[@]} -gt 0 ]]; then
  echo ""
  echo "Managed asset cleanup conflicts (preserved):" >&2
  for conflict in "${CLEANUP_CONFLICTS[@]}"; do printf '  ! %s\n' "$conflict" >&2; done
fi

if [[ ${#CONFLICTS[@]} -gt 0 ]]; then
  echo ""
  echo "Instruction conflicts or differences (agent resolution may be required):" >&2
  for conflict in "${CONFLICTS[@]}"; do printf '  ! %s\n' "$conflict" >&2; done
fi

if [[ -n "$FINALIZE_REPORT" ]]; then
  echo ""
  printf '%s\n' "$FINALIZE_REPORT"
fi

echo ""
echo "Done."
exit "$browser_setup_status"
