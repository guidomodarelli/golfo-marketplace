#!/bin/bash
# bootstrap-asset-projection.sh
# Part of bootstrap.sh, which sources it from its own directory after asset-sync-common.sh: how an apply
# projects the assets of the composed stack into .agents (canonical), the .claude views and settings and
# the Codex hooks, and records what it created, updated, skipped or removed in the arrays of bootstrap.sh.

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
  local destination_snapshot
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
    sync_file "$template" "$destination" "$template" absent
    return 0
  fi

  # Settings hold project content: a save during the merge must not be lost.
  temporary_settings="$(mktemp "${TMPDIR:-/tmp}/agent-ready-settings.XXXXXX")"
  destination_snapshot="$(mktemp "${TMPDIR:-/tmp}/agent-ready-current-settings.XXXXXX")"
  cp -- "$destination" "$destination_snapshot"
  merge_managed_settings "$template" "$destination_snapshot" nested > "$temporary_settings" || merge_status=$?

  case "$merge_status" in
    0)
      sync_file "$temporary_settings" "$destination" "$template" "$destination_snapshot"
      ;;
    10)
      cp -- "$template" "$temporary_settings"
      sync_file "$temporary_settings" "$destination" "$template" "$destination_snapshot"
      ;;
    *)
      record_cleanup_conflict "$destination contains invalid JSON; preserved"
      ;;
  esac
  rm -f -- "$temporary_settings" "$destination_snapshot"
}

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

    if [[ "$relative" == "agents-template.md" || "$relative" == "agents-skeleton.md" ]]; then
      continue
    elif [[ "$relative" == "settings.json" ]]; then
      sync_claude_settings "$file"
    else
      case "$relative" in
        blocks/*|nested/*)
          # Managed blocks go inside files shared with the project, and nested ones inside the
          # AGENTS.md of a folder: finalize writes them.
          continue
          ;;
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
