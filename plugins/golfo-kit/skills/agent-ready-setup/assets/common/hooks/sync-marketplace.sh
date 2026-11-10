#!/bin/bash
# sync-marketplace.sh
# Upgrades golfo-marketplace and projects managed Agent Ready assets locally.
# Runs automatically on session start (SessionStart hook), where it never makes the
# session wait: it reports the last update and starts the next one detached.
#
# With updates.mode auto (the default of the configuration) that update applies the
# same ownership contract as bootstrap.sh: managed assets are overwritten, local
# changes included, and only files that no apply wrote are preserved and reported.
# Pinned repositories are only checked: the update refreshes the user cache, and the
# hook reports drift and pending updates without writing. updates.enabled false makes
# SessionStart do nothing at all; an explicit sync still runs.
# AGENT_READY_SETUP_REVIEW_MODE=1 (automated reviews) never writes or uses the network.
# AGENT_READY_SETUP_SYNC_FOREGROUND=1, or --stack and --profiles, run the sync right here.

set -euo pipefail

# Hermes exports these to stop Git Bash from translating paths, but this hook
# hands POSIX paths to native Windows Python, which needs that translation.
unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL

# Keep hook stdout empty: progress (including child commands) belongs on stderr.
# Codex treats output starting with '[' or '{' as JSON, not plain-text logs.
exec 1>&2

# shellcheck disable=SC2034
readonly MARKETPLACE_NAME="golfo-marketplace"
readonly SKILL_NAME="agent-ready-setup"
readonly SHARED_DIR=".agents"
readonly CLAUDE_DIR=".claude"
readonly CODEX_DIR=".codex"
# Codex resolves its user home from CODEX_HOME; config, snapshot and cache follow it.
readonly CODEX_HOME_DIRECTORY="${CODEX_HOME:-$HOME/.codex}"
readonly RUN_DETACHED_SCRIPT="scripts/run-detached.py"
readonly ASSET_SYNC_HELPER_PATH="scripts/asset-sync-common.sh"
readonly MARKETPLACE_UPGRADE_INTERVAL_MINUTES=60
readonly SYNC_LOCK_DIRECTORY="$SHARED_DIR/.agent-ready-assets.lock"
# shellcheck disable=SC2034
readonly SYNC_LOCK_OWNER_FILE="$SYNC_LOCK_DIRECTORY/owner"
# shellcheck disable=SC2034
SYNC_LOCK_ACQUIRED=0
SYNC_LOCK_INHERITED=0
# shellcheck disable=SC2034
SYNC_LOCK_ENABLED=1

provider=""
stack_override="${AGENT_READY_SETUP_STACK:-}"
profiles_override="${AGENT_READY_SETUP_PROFILES:-}"
review_mode="${AGENT_READY_SETUP_REVIEW_MODE:-0}"
# Only --stack or --profiles on the command line turn a pinned check into an
# explicit apply; the environment overrides only choose the selection.
explicit_selection=0
marketplace_already_upgraded="${AGENT_READY_SETUP_MARKETPLACE_UPGRADED:-0}"
force_marketplace_upgrade="${AGENT_READY_SETUP_FORCE_UPGRADE:-0}"
foreground_sync="${AGENT_READY_SETUP_SYNC_FOREGROUND:-0}"
sync_lock_inherited="${AGENT_READY_SETUP_SYNC_LOCK_HELD:-0}"
backup_directory="${AGENT_READY_SETUP_BACKUP_DIRECTORY:-}"
created_assets=()
updated_assets=()
skipped_assets=()
removed_assets=()
backups=()
conflicts=()
original_arguments=("$@")
# Absolute: the detached update starts from the project root, not from this directory.
hook_path="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/$(basename -- "${BASH_SOURCE[0]}")"

record_conflict() {
  conflicts+=("$1")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider|-p)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        printf 'ERROR: %s requires claude or codex\n' "$1" >&2
        exit 1
      fi
      if [[ -n "$provider" ]]; then
        printf 'ERROR: provider argument was provided more than once\n' >&2
        exit 1
      fi
      provider="$2"
      shift 2
      ;;
    claude|codex)
      if [[ -n "$provider" ]]; then
        printf 'ERROR: provider argument does not accept extra values\n' >&2
        exit 1
      fi
      provider="$1"
      shift
      ;;
    --stack)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        printf 'ERROR: --stack requires frontend, node, java, go, or android\n' >&2
        exit 1
      fi
      stack_override="$2"
      # A flag beats the selection that came from the environment.
      profiles_override=""
      explicit_selection=1
      shift 2
      ;;
    --profiles)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        printf 'ERROR: --profiles requires a comma separated list\n' >&2
        exit 1
      fi
      profiles_override="$2"
      stack_override=""
      explicit_selection=1
      shift 2
      ;;
    *)
      printf 'ERROR: unsupported marketplace sync argument: %s\n' "$1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$provider" ]]; then
  case "$0" in
    .agents/hooks/sync-marketplace.sh|*/.agents/hooks/sync-marketplace.sh)
      provider="codex"
      ;;
    *)
      provider="claude"
      ;;
  esac
fi

case "$provider" in
  claude|codex) ;;
  *)
    printf 'ERROR: unsupported marketplace provider: %s\n' "$provider" >&2
    exit 1
    ;;
esac

if [[ "$marketplace_already_upgraded" != 0 && "$marketplace_already_upgraded" != 1 ]]; then
  printf 'ERROR: AGENT_READY_SETUP_MARKETPLACE_UPGRADED must be 0 or 1\n' >&2
  exit 1
fi

if [[ "$force_marketplace_upgrade" != 0 && "$force_marketplace_upgrade" != 1 ]]; then
  printf 'ERROR: AGENT_READY_SETUP_FORCE_UPGRADE must be 0 or 1\n' >&2
  exit 1
fi

if [[ "$review_mode" != 0 && "$review_mode" != 1 ]]; then
  printf 'ERROR: AGENT_READY_SETUP_REVIEW_MODE must be 0 or 1\n' >&2
  exit 1
fi

if [[ "$foreground_sync" != 0 && "$foreground_sync" != 1 ]]; then
  printf 'ERROR: AGENT_READY_SETUP_SYNC_FOREGROUND must be 0 or 1\n' >&2
  exit 1
fi

# A session start never waits for the network: the sync below runs detached instead.
defer_to_background=0
if [[ "$review_mode" -eq 0 && "$foreground_sync" -eq 0 && "$explicit_selection" -eq 0 ]]; then
  defer_to_background=1
fi

if [[ "$sync_lock_inherited" != 0 && "$sync_lock_inherited" != 1 ]]; then
  printf 'ERROR: AGENT_READY_SETUP_SYNC_LOCK_HELD must be 0 or 1\n' >&2
  exit 1
fi

is_valid_skill_dir() {
  local candidate="$1"
  local require_asset_sync_helper="${2:-0}"

  [[ -f "$candidate/SKILL.md" && \
    -d "$candidate/assets/stacks" && \
    -f "$candidate/assets/common/hooks/sync-marketplace.sh" && \
    -f "$candidate/assets/common/settings.json" && \
    -f "$candidate/assets/codex/hooks.json" && \
    -f "$candidate/scripts/merge-managed-settings.py" && \
    ("$require_asset_sync_helper" -eq 0 || -f "$candidate/$ASSET_SYNC_HELPER_PATH") ]]
}

# The upgrade is a network round trip on every SessionStart; within the window
# the installed marketplace copy is reused. The stamp lives outside the project
# and is written only after a successful upgrade, one per provider.
marketplace_upgrade_stamp="${XDG_CACHE_HOME:-$HOME/.cache}/agent-ready-setup/marketplace-upgrade-$provider.stamp"

is_marketplace_upgrade_recent() {
  [[ "$force_marketplace_upgrade" -eq 0 ]] || return 1
  [[ -f "$marketplace_upgrade_stamp" && ! -L "$marketplace_upgrade_stamp" ]] || return 1
  [[ -n "$(find "$marketplace_upgrade_stamp" -mmin "-$MARKETPLACE_UPGRADE_INTERVAL_MINUTES" -print 2>/dev/null)" ]]
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

is_marketplace_upgrade_unsupported() {
  [[ "$provider" == "codex" ]] && is_codex_local_marketplace
}

report_local_marketplace_upgrade_skip() {
  echo "[marketplace-sync] $MARKETPLACE_NAME es un marketplace Codex local; se omite el upgrade y se usa su source configurado."
}

# Each provider refreshes its own marketplace snapshot through its CLI.
run_marketplace_upgrade() {
  if [[ "$provider" == "claude" ]]; then
    claude plugin marketplace update "$MARKETPLACE_NAME"
  else
    codex plugin marketplace upgrade "$MARKETPLACE_NAME"
  fi
}

record_marketplace_upgrade() {
  local stamp_directory="${marketplace_upgrade_stamp%/*}"

  [[ ! -L "$marketplace_upgrade_stamp" && ! -L "$stamp_directory" ]] || return 0
  mkdir -p -- "$stamp_directory" 2>/dev/null && touch -- "$marketplace_upgrade_stamp" 2>/dev/null || true
}

# Automated reviews need neither network nor a provider CLI: rules come from the checkout.
if [[ "$review_mode" -eq 1 ]]; then
  echo "[marketplace-sync] Review mode: the marketplace upgrade is skipped."
elif [[ "$defer_to_background" -eq 1 ]]; then
  : # The detached sync upgrades the marketplace.
elif [[ "$marketplace_already_upgraded" -eq 1 ]]; then
  echo "[marketplace-sync] El caller ya completó el upgrade del marketplace."
elif is_marketplace_upgrade_unsupported; then
  report_local_marketplace_upgrade_skip
elif is_marketplace_upgrade_recent; then
  printf '[marketplace-sync] El marketplace se actualizó hace menos de %s minutos; se omite el upgrade. Definí AGENT_READY_SETUP_FORCE_UPGRADE=1 para forzarlo.\n' \
    "$MARKETPLACE_UPGRADE_INTERVAL_MINUTES"
else
  echo "[marketplace-sync] Haciendo upgrade de $MARKETPLACE_NAME para $provider..."
  run_marketplace_upgrade
  record_marketplace_upgrade
  echo "[marketplace-sync] Upgrade del marketplace completado."
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
  local hook_directory
  local project_root
  local snapshot_candidate
  local require_asset_sync_helper="${1:-0}"

  if [[ -n "${AGENT_READY_SETUP_SKILL_DIR:-}" ]]; then
    candidate="$AGENT_READY_SETUP_SKILL_DIR"
    if is_valid_skill_dir "$candidate" "$require_asset_sync_helper"; then
      printf '%s\n' "$candidate"
      return 0
    fi
    printf 'ERROR: AGENT_READY_SETUP_SKILL_DIR is not a valid %s source: %s\n' "$SKILL_NAME" "$candidate" >&2
    return 1
  fi

  if [[ "$provider" == "claude" ]]; then
    provider_root="$HOME/.claude"
  else
    provider_root="$CODEX_HOME_DIRECTORY"
  fi

  snapshot_candidate="$(marketplace_snapshot_skill_dir "$provider")"
  if ! is_valid_skill_dir "$snapshot_candidate" "$require_asset_sync_helper"; then
    snapshot_candidate=""
  fi

  # The snapshot wins unless the cache already holds a newer version, so
  # projection never waits for a provider plugin update.
  cache_root="$provider_root/plugins/cache/$MARKETPLACE_NAME/golfo-kit"
  while IFS= read -r candidate; do
    candidate="${candidate%/SKILL.md}"
    if is_valid_skill_dir "$candidate" "$require_asset_sync_helper"; then
      if [[ -n "$snapshot_candidate" ]] && \
        [[ ! "$(semantic_version_key "$(marketplace_snapshot_version "$provider")")" < \
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
      if is_valid_skill_dir "$candidate" "$require_asset_sync_helper"; then
        printf '%s\n' "$candidate"
        return 0
      fi
    done
  fi

  hook_directory="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  for candidate in \
    "$hook_directory/../../../.." \
    "$hook_directory/../../.."; do
    if is_valid_skill_dir "$candidate" "$require_asset_sync_helper"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  candidate="$provider_root/skills/$SKILL_NAME"
  if is_valid_skill_dir "$candidate" "$require_asset_sync_helper"; then
    printf '%s\n' "$candidate"
    return 0
  fi

  if project_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    candidate="$project_root/plugins/golfo-kit/skills/$SKILL_NAME"
    if is_valid_skill_dir "$candidate" "$require_asset_sync_helper"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  return 1
}

describe_skill_source() {
  local source="$1"
  local source_version

  if [[ "$source" == "$(marketplace_snapshot_skill_dir "$provider")" ]]; then
    source_version="$(marketplace_snapshot_version "$provider")"
    printf '[marketplace-sync] Using %s marketplace snapshot version %s.\n' \
      "$SKILL_NAME" "${source_version:-unknown}"
    return 0
  fi

  source_version="$(cache_skill_version "$source")"
  if [[ "$source_version" =~ ^[0-9]+(\.[0-9]+){0,2}([+-].*)?$ ]]; then
    printf '[marketplace-sync] Using %s cache version %s.\n' "$SKILL_NAME" "$source_version"
  else
    printf '[marketplace-sync] Using local %s source.\n' "$SKILL_NAME"
  fi
}

refresh_missing_asset_sync_helper() {
  local refreshed_skill_dir

  if [[ -f "$skill_dir/$ASSET_SYNC_HELPER_PATH" ]]; then
    return 0
  fi
  # A review stays offline; a source this old has no state to report anyway.
  [[ "$review_mode" -eq 0 ]] || return 1

  echo "[marketplace-sync] Falta el helper compartido de sincronización; refrescando $MARKETPLACE_NAME para $provider..."
  if is_marketplace_upgrade_unsupported; then
    report_local_marketplace_upgrade_skip
  else
    if ! command -v "$provider" >/dev/null 2>&1; then
      printf 'ERROR: se requiere la CLI de %s para descargar %s\n' "$provider" "$ASSET_SYNC_HELPER_PATH" >&2
      return 1
    fi
    if ! run_marketplace_upgrade; then
      printf 'ERROR: falló el refresh del marketplace al descargar %s\n' "$ASSET_SYNC_HELPER_PATH" >&2
      return 1
    fi
    record_marketplace_upgrade
  fi

  if ! refreshed_skill_dir="$(resolve_skill_dir 1)"; then
    printf 'ERROR: el source refrescado de %s no está disponible; no se pudo descargar %s\n' \
      "$SKILL_NAME" "$ASSET_SYNC_HELPER_PATH" >&2
    return 1
  fi
  skill_dir="$refreshed_skill_dir"

  if [[ ! -f "$skill_dir/$ASSET_SYNC_HELPER_PATH" ]]; then
    printf 'ERROR: el refresh del marketplace se completó pero %s sigue faltando en %s\n' \
      "$ASSET_SYNC_HELPER_PATH" "$skill_dir" >&2
    return 1
  fi
}

case "$stack_override" in
  ""|frontend|node|java|go|android) ;;
  *)
    printf 'ERROR: unsupported stack: %s\n' "$stack_override" >&2
    exit 1
    ;;
esac

if ! skill_dir="$(resolve_skill_dir)" && [[ "$defer_to_background" -eq 1 ]] && \
  [[ -z "${AGENT_READY_SETUP_SKILL_DIR:-}" ]] && ! is_marketplace_upgrade_unsupported; then
  # A machine without a source yet has no scripts to detach with: the only synchronous fetch.
  echo "[marketplace-sync] Haciendo upgrade de $MARKETPLACE_NAME para $provider..."
  run_marketplace_upgrade && record_marketplace_upgrade
  skill_dir="$(resolve_skill_dir)" || skill_dir=""
fi
if [[ -z "${skill_dir:-}" ]]; then
  if [[ -n "${AGENT_READY_SETUP_SKILL_DIR:-}" ]]; then
    exit 1
  fi
  printf 'WARNING: could not resolve updated %s source; local projection skipped.\n' "$SKILL_NAME" >&2
  printf 'Set AGENT_READY_SETUP_SKILL_DIR or rerun this hook after installing the provider plugin.\n' >&2
  exit 0
fi

if ! refresh_missing_asset_sync_helper; then
  if [[ -n "${AGENT_READY_SETUP_SKILL_DIR:-}" ]]; then
    exit 1
  fi
  printf 'WARNING: %s no está disponible después del refresh del marketplace; se omite la proyección local.\n' \
    "$ASSET_SYNC_HELPER_PATH" >&2
  exit 0
fi

describe_skill_source "$skill_dir"

# shellcheck disable=SC2034
ASSET_SYNC_SKILL_DIR="$skill_dir"
# shellcheck disable=SC1090
source "$skill_dir/$ASSET_SYNC_HELPER_PATH"
# shellcheck disable=SC2034
SYNC_LOCK_INHERITED="$sync_lock_inherited"

if ! project_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  printf 'WARNING: could not resolve Git project root; local projection skipped.\n' >&2
  exit 0
fi
cd -- "$project_root"

state_script="$skill_dir/scripts/agent-ready-state.py"
if ! command -v python3 >/dev/null 2>&1; then
  printf 'WARNING: python3 is unavailable; local projection skipped.\n' >&2
  exit 0
fi

# Every layer is validated before anything else: an unknown key or an invalid value
# could hide a pinned repository, so the sync stops without writing.
if ! configuration="$(python3 "$state_script" config --project . --format tsv)"; then
  printf 'WARNING: the Agent Ready configuration is not valid; nothing was synchronized.\n' >&2
  exit 0
fi
updates_enabled=true
update_mode=""
auto_sources=""
refresh_enabled=true
tools_enabled=true
while IFS=$'\t' read -r configuration_key configuration_value; do
  configuration_value="${configuration_value%$'\r'}"
  case "$configuration_key" in
    updates.enabled) updates_enabled="$configuration_value" ;;
    updates.mode) update_mode="$configuration_value" ;;
    updates.refresh) refresh_enabled="$configuration_value" ;;
    tools.enabled) tools_enabled="$configuration_value" ;;
    auto_sources) auto_sources="$configuration_value" ;;
  esac
done <<< "$configuration"
# golfo-kit is a source too: pinned, its content comes from the revision of the lock and the
# engine stays this one (agent_ready_golfo_kit.py). Review mode and a session start that hands
# the sync to the background only read the cache: the detached sync resolves refs and downloads.
golfo_kit_arguments=(golfo-kit-source --project . --skill-dir "$skill_dir")
if [[ "$review_mode" -eq 1 || "$defer_to_background" -eq 1 ]]; then
  golfo_kit_arguments+=(--offline --read-only)
fi
if ! content_skill_dir="$(python3 "$state_script" "${golfo_kit_arguments[@]}")"; then
  printf 'WARNING: could not prepare the golfo-kit content; nothing was synchronized.\n' >&2
  exit 0
fi
if [[ -n "$content_skill_dir" ]]; then
  skill_dir="$content_skill_dir"
  state_script="$skill_dir/scripts/agent-ready-state.py"
  # shellcheck disable=SC2034
  ASSET_SYNC_SKILL_DIR="$skill_dir"
fi

# A pinned repository with a source in auto still syncs; its policy guards the rest.
only_check=0
if [[ "$update_mode" == pinned && -z "$auto_sources" && "$explicit_selection" -eq 0 ]]; then
  only_check=1
fi

# Automated reviews read the rules committed in the checkout; synchronizing
# would change the very context under review.
if [[ "$review_mode" -eq 1 ]]; then
  echo "[marketplace-sync] Review mode: Agent Ready assets are read from the checkout; nothing was synchronized."
  python3 "$state_script" status --project . --skill-dir "$skill_dir" --brief || true
  exit 0
fi

# Per-user state for background tasks; nothing machine-specific lands in the project.
background_cache_directory="${XDG_CACHE_HOME:-$HOME/.cache}/agent-ready-setup"

# Short stable key per project root, so concurrent projects never share a log.
project_log_key() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$PWD" | sha256sum | cut -c 1-12
  else
    printf '%s' "$PWD" | shasum -a 256 | cut -c 1-12
  fi
}

# Starts long-running or network work detached from the session, so SessionStart
# does not wait for it.
start_background_task() {
  local log_name="$1"
  shift

  if [[ ! -f "$skill_dir/$RUN_DETACHED_SCRIPT" ]] || ! command -v python3 >/dev/null 2>&1; then
    printf 'WARNING: background task %s skipped: python3 or %s is unavailable.\n' "$log_name" "$RUN_DETACHED_SCRIPT" >&2
    return 0
  fi
  if ! python3 "$skill_dir/$RUN_DETACHED_SCRIPT" --log "$background_cache_directory/$log_name.log" -- "$@"; then
    printf 'WARNING: background task %s could not start; it retries in the next session.\n' "$log_name" >&2
  fi
}

# The session-start scripts of the packs run on every session start, whatever the update mode,
# in the background and only as the last apply recorded them (agent_ready_pack_scripts.py).
if [[ "$defer_to_background" -eq 1 && -f .agents/agent-ready.lock.json ]] &&
  grep -q '"session-start"' .agents/agent-ready.lock.json; then
  python3 "$state_script" pack-scripts --project . --skill-dir "$skill_dir" --previous-report || true
  start_background_task "pack-scripts-$(project_log_key)" \
    python3 "$state_script" pack-scripts --project . --skill-dir "$skill_dir"
fi

# Only an explicit sync runs with automatic updates off.
if [[ "$updates_enabled" != true && "$defer_to_background" -eq 1 ]]; then
  echo "[marketplace-sync] Automatic updates are off (updates.enabled: false); nothing was checked or synchronized."
  exit 0
fi

if [[ "$defer_to_background" -eq 0 && "$only_check" -eq 1 ]]; then
  echo "[marketplace-sync] Repository pinned (updates.mode: pinned); checking without writing."
  if [[ "$refresh_enabled" == true ]]; then
    python3 "$state_script" fetch-sources --project . --skill-dir "$skill_dir" --refresh || true
  fi
  python3 "$state_script" status --project . --skill-dir "$skill_dir" --brief || true
  exit 0
fi

if [[ "$defer_to_background" -eq 1 ]]; then
  python3 "$state_script" update-report --project . || true
  if [[ "$only_check" -eq 1 ]]; then
    echo "[marketplace-sync] Repository pinned (updates.mode: pinned); checking without writing."
    python3 "$state_script" status --project . --skill-dir "$skill_dir" --brief || true
  fi
  # A pinned repository with refresh off has nothing to do in the background.
  if [[ "$only_check" -eq 0 || "$refresh_enabled" == true ]]; then
    start_background_task "background-update-$(project_log_key)" \
      python3 "$state_script" background-update --project . --skill-dir "$skill_dir" \
      --hook "$hook_path" --provider "$provider"
  fi
  exit 0
fi

profile_selection=()
if [[ -n "$profiles_override" ]]; then
  profile_selection=(--profiles "$profiles_override")
elif [[ -n "$stack_override" ]]; then
  profile_selection=(--stack "$stack_override")
fi

# Without flags, resolve uses the manifest and then the initial detection; if neither
# determines one stack it names the matches and asks for an explicit selection.
stack=""
stack_dir=""
resolved_tools=""
requested_profiles=""
selection_origin=""
# Profile sources in auto follow their ref here; a failure leaves everything as it was.
source_state_file="$(mktemp "${TMPDIR:-/tmp}/agent-ready-sources.XXXXXX")"
trap 'rm -f -- "$source_state_file"' EXIT
if ! python3 "$state_script" fetch-sources --project . --skill-dir "$skill_dir" --state-file "$source_state_file"; then
  printf 'WARNING: the profile sources could not be prepared; local projection skipped and nothing was changed.\n' >&2
  exit 0
fi
sync_policy=(--source-state "$source_state_file")
if [[ "$explicit_selection" -eq 0 ]]; then
  sync_policy+=(--source-mode sync)
fi
profile_resolution_status=0
profile_resolution="$(python3 "$state_script" resolve --project . --skill-dir "$skill_dir" "${sync_policy[@]}" \
  ${profile_selection[@]+"${profile_selection[@]}"} \
  --compose-dir "${XDG_CACHE_HOME:-$HOME/.cache}/agent-ready-setup/compose")" || profile_resolution_status=$?
if [[ "$profile_resolution_status" -eq 5 ]]; then
  printf 'WARNING: a profile source is not ready; local projection skipped and nothing was changed.\n' >&2
  exit 0
fi
if [[ "$profile_resolution_status" -ne 0 ]]; then
  printf 'WARNING: Agent Ready profiles could not be resolved; local projection skipped.\n' >&2
  exit 0
fi
while IFS=$'\t' read -r resolution_key resolution_value; do
  resolution_value="${resolution_value%$'\r'}"
  case "$resolution_key" in
    primary) stack="$resolution_value" ;;
    stack_dir) stack_dir="$resolution_value" ;;
    tools) resolved_tools="$resolution_value" ;;
    requested) requested_profiles="$resolution_value" ;;
    selection) selection_origin="$resolution_value" ;;
  esac
done <<< "$profile_resolution"
# The sync projects what this resolution detected, even if the signals change meanwhile.
if [[ "$selection_origin" == detection ]]; then
  profile_selection=(--profiles "$requested_profiles")
fi
# Child scripts (normalization, managed block, background review) read the same tree.
export AGENT_READY_SETUP_STACK_DIR="$stack_dir"

record_created() {
  created_assets+=("$1")
}

record_updated() {
  updated_assets+=("$1")
}

record_skipped() {
  skipped_assets+=("$1")
}

record_removed() {
  removed_assets+=("$1")
}

ensure_backup_directory() {
  if [[ -n "$backup_directory" ]]; then
    [[ -d "$backup_directory" && ! -L "$backup_directory" ]]
    return
  fi

  backup_directory="$(mktemp -d "${TMPDIR:-/tmp}/agent-ready-backups.XXXXXX")" || return 1
}

backup_file() {
  local destination="$1"
  local relative_destination
  local backup_destination

  if ! ensure_backup_directory; then
    return 1
  fi
  relative_destination="${destination#./}"
  backup_destination="$backup_directory/$relative_destination"
  if ! ensure_parent_directory "$backup_destination"; then
    return 1
  fi
  if ! backup_destination="$(mktemp "${backup_destination}.agent-ready-backup.XXXXXX")"; then
    return 1
  fi
  if ! cp -p -- "$destination" "$backup_destination"; then
    rm -f -- "$backup_destination"
    return 1
  fi
  backups+=("$backup_destination")
}

sync_file() {
  local source="$1"
  local destination="$2"
  local expected_destination
  local temporary_destination
  local supplied_snapshot="${4:-}"

  if [[ ! -f "$source" ]]; then
    conflicts+=("$source is not a regular file; $destination was not changed")
    return 0
  fi
  if is_protected_destination "$destination"; then
    record_conflict "$destination: $AGENT_READY_PROTECTED_HINT"
    return 0
  fi
  # A caller may require the exact pre-merge snapshot, including initial absence.
  if [[ -n "$supplied_snapshot" ]] && ! destination_matches_snapshot "$destination" "$supplied_snapshot"; then
    record_conflict "$destination changed during synchronization; neither was changed"
    return 0
  fi

  if ! validate_destination_parent "$destination"; then
    return 0
  fi
  ensure_parent_directory "$destination"

  if [[ -L "$destination" ]]; then
    if [[ -n "$supplied_snapshot" ]]; then
      record_conflict "$destination changed during synchronization; neither was changed"
      return 0
    fi
    replace_managed_symlink "$source" "$destination"
    return 0
  fi
  if [[ -e "$destination" && ! -f "$destination" ]]; then
    conflicts+=("$destination is not a regular file; neither was changed")
    return 0
  fi
  if [[ ! -e "$destination" ]]; then
    if ! temporary_destination="$(mktemp "${destination}.agent-ready-sync.XXXXXX")"; then
      conflicts+=("could not stage new content for $destination; neither was changed")
      return 0
    fi
    if ! cp -p -- "$source" "$temporary_destination"; then
      rm -f -- "$temporary_destination"
      conflicts+=("could not stage new content for $destination; neither was changed")
      return 0
    fi
    if [[ -n "$supplied_snapshot" ]] && ! destination_matches_snapshot "$destination" "$supplied_snapshot"; then
      rm -f -- "$temporary_destination"
      record_conflict "$destination changed during synchronization; neither was changed"
      return 0
    fi
    if ! mv -f -- "$temporary_destination" "$destination"; then
      rm -f -- "$temporary_destination"
      conflicts+=("could not create $destination atomically; neither was changed")
      return 0
    fi
    record_created "$destination"
    return 0
  fi
  if matches_ignoring_line_endings "$destination" "$source"; then
    record_skipped "$destination"
    return 0
  fi

  expected_destination="$(mktemp "${destination}.agent-ready-expected.XXXXXX")"
  if ! cp -p -- "${supplied_snapshot:-$destination}" "$expected_destination"; then
    rm -f -- "$expected_destination"
    conflicts+=("could not snapshot $destination; neither was changed")
    return 0
  fi

  show_sync_diff "$source" "$destination"
  if ! backup_file "$destination"; then
    rm -f -- "$expected_destination"
    conflicts+=("could not back up $destination; neither was changed")
    return 0
  fi

  temporary_destination="$(mktemp "${destination}.agent-ready-sync.XXXXXX")"
  if ! cp -p -- "$source" "$temporary_destination"; then
    rm -f -- "$temporary_destination" "$expected_destination"
    conflicts+=("could not stage updated content for $destination; neither was changed")
    return 0
  fi
  if [[ -L "$destination" || ! -f "$destination" ]] || \
     ! cmp -s "$destination" "$expected_destination"; then
    rm -f -- "$temporary_destination" "$expected_destination"
    conflicts+=("$destination changed during synchronization; neither was changed")
    return 0
  fi
  if ! mv -f -- "$temporary_destination" "$destination"; then
    rm -f -- "$temporary_destination" "$expected_destination"
    conflicts+=("could not replace $destination atomically; neither was changed")
    return 0
  fi

  rm -f -- "$expected_destination"
  record_updated "$destination"
}

link_claude_asset() {
  local relative="$1"
  local source="$SHARED_DIR/$relative"
  local destination="$CLAUDE_DIR/$relative"
  local target
  local temporary_link

  case "$relative" in
    ""|/*|../*|*/../*|*/..)
      conflicts+=("invalid shared asset path: $relative; no Claude view was created")
      return 0
      ;;
  esac

  if [[ ! -e "$source" && ! -L "$source" ]]; then
    conflicts+=("canonical shared asset is missing: $source; no Claude view was created")
    return 0
  fi
  if ! validate_destination_parent "$destination"; then
    return 0
  fi
  ensure_parent_directory "$destination"
  target="$(relative_shared_target "$relative")"

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
      conflicts+=("$destination is not a regular file; neither was changed")
      return 0
    fi
    if is_protected_destination "$destination"; then
      record_conflict "$destination: $AGENT_READY_PROTECTED_HINT"
      return 0
    fi
    # Relinking discards what the view holds, so it gets the same copy as an asset.
    if ! matches_ignoring_line_endings "$destination" "$source" && ! backup_file "$destination"; then
      conflicts+=("could not back up $destination; neither was changed")
      return 0
    fi
    replace_with_claude_view "$destination" "$target" "$source" "$relative"
    return 0
  fi

  temporary_link="${destination}.agent-ready-link.$$"
  if [[ -e "$temporary_link" || -L "$temporary_link" ]]; then
    conflicts+=("temporary normalization path already exists for $destination; neither was changed")
    return 0
  fi
  if ! create_claude_view_link "$target" "$source" "$temporary_link" "$relative" ||
    ! mv -- "$temporary_link" "$destination"; then
    rm -f -- "$temporary_link"
    conflicts+=("could not create Claude view $destination; neither was changed (${CLAUDE_VIEW_FAILURE_HINT:-symlinks or hard links are unavailable})")
    return 0
  fi
  record_created "$destination"
}

# Templates already carry provider frontmatter, so skill adapters are verbatim
# copies of their source template.
create_skill_adapter() {
  local source="$1"
  local skill_name="$2"

  sync_file "$source" "$SHARED_DIR/skills/$skill_name/SKILL.md"
}

project_assets() {
  local source_root="$1"
  local project_codex_mcp="$2"
  local source_asset
  local relative_asset
  local skill_name

  [[ -d "$source_root" ]] || return 0

  while IFS= read -r -d '' source_asset; do
    relative_asset="${source_asset#"$source_root/"}"
    case "$relative_asset" in
      github/*)
        sync_file "$source_asset" ".github/${relative_asset#github/}"
        ;;
      agents-template.md|settings.json)
        continue
        ;;
      hooks/*)
        sync_file "$source_asset" "$SHARED_DIR/$relative_asset"
        ;;
      mcp.json)
        sync_file "$source_asset" "$SHARED_DIR/$relative_asset"
        link_claude_asset "$relative_asset"
        if [[ "$project_codex_mcp" -eq 1 ]]; then
          sync_file "$source_asset" "$CODEX_DIR/.mcp.json"
        fi
        ;;
      skills/*/SKILL.md)
        skill_name="${relative_asset#skills/}"
        skill_name="${skill_name%/SKILL.md}"
        create_skill_adapter "$source_asset" "$skill_name"
        link_claude_asset "$relative_asset"
        ;;
      skills/*/*.md)
        sync_file "$source_asset" "$SHARED_DIR/$relative_asset"
        link_claude_asset "$relative_asset"
        ;;
      agents/*.md|commands/*.md|skills/*.md)
        sync_file "$source_asset" "$SHARED_DIR/$relative_asset"
        link_claude_asset "$relative_asset"
        skill_name="${relative_asset##*/}"
        skill_name="${skill_name%.md}"
        create_skill_adapter "$source_asset" "$skill_name"
        case "$relative_asset" in
          skills/*.md) link_claude_asset "skills/$skill_name/SKILL.md" ;;
          *) remove_claude_skill_view "$skill_name" ;;
        esac
        ;;
      *)
        sync_file "$source_asset" "$SHARED_DIR/$relative_asset"
        link_claude_asset "$relative_asset"
        ;;
    esac
  done < <(find "$source_root" -type f -print0)
}

sync_claude_settings() {
  local template="$1"
  local destination="$CLAUDE_DIR/settings.json"
  local temporary_settings
  local destination_snapshot
  local merge_status=0

  if [[ -L "$destination" ]]; then
    conflicts+=("$destination is a symlink; preserved")
    return 0
  fi
  if [[ -e "$destination" && ! -f "$destination" ]]; then
    conflicts+=("$destination is not a regular file; preserved")
    return 0
  fi
  if [[ ! -f "$destination" ]]; then
    sync_file "$template" "$destination" "$template" absent
    return 0
  fi

  # Settings hold project content: a save during the merge must not be lost.
  temporary_settings="$(mktemp "${TMPDIR:-/tmp}/agent-ready-settings.XXXXXX")"
  destination_snapshot="$(mktemp "${TMPDIR:-/tmp}/agent-ready-current-settings.XXXXXX")"
  cp -- "$destination" "$destination_snapshot"
  merge_managed_settings "$template" "$destination_snapshot" strict > "$temporary_settings" || merge_status=$?

  case "$merge_status" in
    0)
      sync_file "$temporary_settings" "$destination" "$template" "$destination_snapshot"
      ;;
    10)
      cp -- "$template" "$temporary_settings"
      sync_file "$temporary_settings" "$destination" "$template" "$destination_snapshot"
      ;;
    *)
      conflicts+=("$destination contains invalid JSON; preserved")
      ;;
  esac
  rm -f -- "$temporary_settings" "$destination_snapshot"
}

if [[ -L "$SHARED_DIR" || ( -e "$SHARED_DIR" && ! -d "$SHARED_DIR" ) ]]; then
  echo "WARNING: .agents is a symlink or non-directory; no asset was changed" >&2
  exit 0
fi
if ! acquire_sync_lock; then
  exit 0
fi

# The pre-apply plan decides ownership for every managed destination.
plan_file="$(mktemp "${TMPDIR:-/tmp}/agent-ready-plan.XXXXXX")"
trap 'rm -f -- "$plan_file" "$source_state_file"; release_sync_lock' EXIT
if ! protected_destinations="$(python3 "$state_script" plan --project . --skill-dir "$skill_dir" \
  --provider "$provider" --format protected --save "$plan_file" "${sync_policy[@]}" ${profile_selection[@]+"${profile_selection[@]}"})"; then
  printf 'WARNING: Agent Ready plan could not be computed; no asset was changed.\n' >&2
  exit 0
fi
load_protected_destinations "$protected_destinations"

sync_hook_source="$skill_dir/assets/common/hooks/sync-marketplace.sh"
sync_hook_destination="$SHARED_DIR/hooks/sync-marketplace.sh"
sync_hook_destination_was_different=1
current_hook_needs_restart=0

if [[ -f "$sync_hook_destination" && ! -L "$sync_hook_destination" ]] && \
  cmp -s "$sync_hook_destination" "$sync_hook_source"; then
  sync_hook_destination_was_different=0
fi
if [[ -f "${BASH_SOURCE[0]}" ]] && ! cmp -s "${BASH_SOURCE[0]}" "$sync_hook_source"; then
  current_hook_needs_restart=1
fi

sync_file "$sync_hook_source" "$sync_hook_destination"

if [[ "$sync_hook_destination_was_different" -eq 1 || "$current_hook_needs_restart" -eq 1 ]] && \
  [[ -f "$sync_hook_destination" && ! -L "$sync_hook_destination" ]] && \
  cmp -s "$sync_hook_destination" "$sync_hook_source"; then
  echo "[marketplace-sync] Sync hook updated; restarting with latest version."
  export AGENT_READY_SETUP_MARKETPLACE_UPGRADED=1
  export AGENT_READY_SETUP_SYNC_LOCK_HELD=1
  if [[ -n "$backup_directory" ]]; then
    export AGENT_READY_SETUP_BACKUP_DIRECTORY="$backup_directory"
  fi
  # exec skips the EXIT trap; the restarted hook computes its own plan.
  rm -f -- "$plan_file"
  exec bash "$sync_hook_destination" "${original_arguments[@]}"
fi

# Project common and stack assets before merging instruction references. The
# shared tree remains canonical, while Claude and Codex receive provider views.
project_assets "$skill_dir/assets/common" 0
project_assets "$stack_dir" 1
project_rule_claude_views \
  "$skill_dir/scripts/render-instruction-template.sh" \
  "$stack_dir/rules" \
  "$skill_dir/assets/common/rules"
prune_hard_link_views
install_hard_link_git_hook "$skill_dir/assets/git-hooks/post-index-change"

# Reuse the shared conservative instruction normalizer so SessionStart also
# discovers project CLAUDE.md files under directories such as .claude/.
bash "$skill_dir/scripts/normalize-instructions.sh" --stack "$stack"

sync_claude_settings "$skill_dir/assets/common/settings.json"
sync_codex_hooks "$skill_dir/assets/codex/hooks.json"

finalize_arguments=(finalize --project . --skill-dir "$skill_dir" --plan "$plan_file")
if ! finalize_report="$(python3 "$state_script" "${finalize_arguments[@]}")"; then
  conflicts+=("could not write .agents/agent-ready.lock.json; the next apply treats this run as unlocked")
  finalize_report=""
fi

# Exit status of register-browser-servers.py when only a full install can provide the tools.
readonly BROWSER_NO_INSTALLATION_STATUS=3

# Registers browser MCP servers from the existing installation. When
# none exists, starts the full installation in the background so SessionStart
# never waits for package installs or the Chromium download.
sync_browser_registration() {
  local helper="$skill_dir/scripts/register-browser-servers.py"
  local installer="$skill_dir/scripts/start-browser-install.py"
  local registration_status=0

  [[ "$tools_enabled" == true ]] || return 0
  [[ ",$resolved_tools," == *",browser,"* ]] || return 0
  if ! command -v python3 >/dev/null 2>&1; then
    printf 'WARNING: python3 is unavailable; browser MCP registration sync skipped.\n' >&2
    return 0
  fi
  python3 "$helper" --project "$PWD" || registration_status=$?
  case "$registration_status" in
    0) ;;
    "$BROWSER_NO_INSTALLATION_STATUS")
      if ! python3 "$installer" --project "$PWD"; then
        printf 'WARNING: background browser install could not start; it retries in the next session.\n' >&2
      fi
      ;;
    *)
      printf 'WARNING: browser MCP registration sync incomplete; see the messages above.\n' >&2
      ;;
  esac
}

sync_browser_registration

echo "[marketplace-sync] Local managed asset projection completed for $stack."

if [[ ${#created_assets[@]} -gt 0 ]]; then
  echo "Created:"
  printf '  + %s\n' "${created_assets[@]}"
fi
if [[ ${#updated_assets[@]} -gt 0 ]]; then
  echo "Updated from templates:"
  printf '  ↻ %s\n' "${updated_assets[@]}"
fi
if [[ ${#removed_assets[@]} -gt 0 ]]; then
  echo "Removed duplicate Claude views:"
  printf '  - %s\n' "${removed_assets[@]}"
fi
if [[ ${#backups[@]} -gt 0 ]]; then
  echo "Local backups directory: $backup_directory"
  printf '  ↩ %s\n' "${backups[@]}"
fi
if [[ ${#conflicts[@]} -gt 0 ]]; then
  echo "Managed asset conflicts (preserved):" >&2
  printf '  ! %s\n' "${conflicts[@]}" >&2
fi
if [[ -n "$finalize_report" ]]; then
  printf '%s\n' "$finalize_report"
fi

# The verbatim managed block is local and applies now, so this session already
# sees new rule references; the provider redundancy review runs in the background.
apply_status=0
bash "$skill_dir/scripts/apply-managed-block.sh" --stack "$stack" --skill-dir "$skill_dir" || apply_status=$?
case "$apply_status" in
  0)
    start_background_task "instruction-review-$(project_log_key)" \
      env AGENT_READY_SETUP_NON_INTERACTIVE=1 bash "$skill_dir/scripts/merge-instructions.sh" \
      --provider "$provider" --stack "$stack" --skill-dir "$skill_dir"
    ;;
  2)
    echo "[marketplace-sync] AGENTS.md managed block requires human review; local file preserved."
    ;;
  *)
    printf 'ERROR: AGENTS.md managed block sync failed for %s; local file was preserved.\n' "$skill_dir" >&2
    exit 1
    ;;
esac
