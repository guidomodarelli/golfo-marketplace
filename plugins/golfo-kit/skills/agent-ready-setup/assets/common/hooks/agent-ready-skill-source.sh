#!/bin/bash
# agent-ready-skill-source.sh
# Library sourced by the hooks beside it (sync-marketplace.sh, check-conflicts.sh): finds the
# agent-ready-setup source the session uses, from AGENT_READY_SETUP_SKILL_DIR, the provider
# marketplace snapshot, the plugin cache or the checkout. The caller sets $provider (claude or
# codex) before resolving; nothing here reaches the network or writes.

# shellcheck disable=SC2034
readonly MARKETPLACE_NAME="golfo-marketplace"
readonly SKILL_NAME="agent-ready-setup"
# Codex resolves its user home from CODEX_HOME; config, snapshot and cache follow it.
readonly CODEX_HOME_DIRECTORY="${CODEX_HOME:-$HOME/.codex}"
readonly ASSET_SYNC_HELPER_PATH="scripts/asset-sync-common.sh"

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
