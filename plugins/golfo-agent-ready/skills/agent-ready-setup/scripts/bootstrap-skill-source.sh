#!/bin/bash
# bootstrap-skill-source.sh
# Part of bootstrap.sh, which sources it from its own directory: which agent-ready-setup source a run
# uses (the --skill-dir it got, the provider marketplace snapshot or the plugin cache, the newest valid
# one) and the checks that source must pass before anything is written. It reads the globals bootstrap.sh
# sets: REQUESTED_SKILL_DIR, SKILL_DIR, PROVIDER and the marketplace names.

is_valid_skill_dir() {
  local candidate="$1"

  # The engine carries no content (agent_ready_content.py): its scripts and CI catalog identify it.
  [[ -f "$candidate/SKILL.md" && \
    -f "$candidate/scripts/bootstrap.sh" && \
    -f "$candidate/scripts/agent-ready-state.py" && \
    -f "$candidate/assets/ci/profiles.json" ]]
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
  printf '%s/plugins/golfo-agent-ready/skills/%s\n' "$(marketplace_snapshot_root "$1")" "$SKILL_NAME"
}

# Reads the plugin manifest version beside the snapshot skill; both provider
# manifests share the same version.
marketplace_snapshot_version() {
  local plugin_root
  local manifest

  plugin_root="$(marketplace_snapshot_root "$1")/plugins/golfo-agent-ready"
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
  cache_root="$provider_root/plugins/cache/$MARKETPLACE_NAME/golfo-agent-ready"

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
    candidate="$project_root/plugins/golfo-agent-ready/skills/$SKILL_NAME"
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
