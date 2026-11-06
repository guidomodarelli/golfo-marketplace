#!/bin/bash
# Shared primitives for Agent Ready asset synchronization scripts.
# Consumers define record_conflict and configure shared paths/state before calls.

get_process_start_time() {
  local process_id="$1"

  ps -p "$process_id" -o lstart= 2>/dev/null | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

write_sync_lock_owner() {
  local owner_metadata_temp

  if ! owner_metadata_temp="$(mktemp "${SYNC_LOCK_DIRECTORY}/owner.XXXXXX")"; then
    return 1
  fi
  if ! printf '%s\n%s\n' "$$" "$(get_process_start_time "$$")" > "$owner_metadata_temp"; then
    rm -f -- "$owner_metadata_temp"
    return 1
  fi
  if ! mv -f -- "$owner_metadata_temp" "$SYNC_LOCK_OWNER_FILE"; then
    rm -f -- "$owner_metadata_temp"
    return 1
  fi
}

# A lock is stale only when its owner metadata names a process that ended or
# was replaced; a lock without readable owner metadata stays ambiguous.
is_sync_lock_stale() {
  local owner_pid
  local owner_start_time=""
  local current_start_time

  [[ -d "$SYNC_LOCK_DIRECTORY" && ! -L "$SYNC_LOCK_DIRECTORY" ]] || return 1
  [[ -f "$SYNC_LOCK_OWNER_FILE" && ! -L "$SYNC_LOCK_OWNER_FILE" ]] || return 1

  IFS= read -r owner_pid < "$SYNC_LOCK_OWNER_FILE" || owner_pid=""
  [[ "$owner_pid" =~ ^[1-9][0-9]*$ ]] || return 1
  if ! kill -0 "$owner_pid" 2>/dev/null; then
    return 0
  fi

  IFS= read -r owner_start_time < <(sed -n '2p' "$SYNC_LOCK_OWNER_FILE") || true
  if [[ -n "$owner_start_time" ]]; then
    current_start_time="$(get_process_start_time "$owner_pid")"
    [[ -n "$current_start_time" && "$current_start_time" != "$owner_start_time" ]] && return 0
  fi

  return 1
}

reclaim_stale_sync_lock() {
  is_sync_lock_stale || return 1

  rm -f -- "$SYNC_LOCK_OWNER_FILE"
  rmdir -- "$SYNC_LOCK_DIRECTORY" 2>/dev/null
}

has_current_sync_lock_owner() {
  local owner_pid
  local owner_start_time=""
  local current_start_time

  [[ -f "$SYNC_LOCK_OWNER_FILE" && ! -L "$SYNC_LOCK_OWNER_FILE" ]] || return 1
  IFS= read -r owner_pid < "$SYNC_LOCK_OWNER_FILE" || return 1
  [[ "$owner_pid" == "$$" ]] || return 1

  IFS= read -r owner_start_time < <(sed -n '2p' "$SYNC_LOCK_OWNER_FILE") || true
  current_start_time="$(get_process_start_time "$$")"
  # Git Bash ps has no -o, so neither side has a start time. exec keeps the PID there
  # while the Windows process (and its start time) changes; the PID already matched.
  if [[ -z "$owner_start_time" && -z "$current_start_time" ]]; then
    return 0
  fi
  [[ -n "$owner_start_time" && -n "$current_start_time" && "$current_start_time" == "$owner_start_time" ]]
}

# shellcheck disable=SC2329
release_sync_lock() {
  if [[ "${SYNC_LOCK_ACQUIRED:-0}" -eq 1 ]]; then
    rm -f -- "$SYNC_LOCK_OWNER_FILE"
    rmdir -- "$SYNC_LOCK_DIRECTORY" 2>/dev/null || true
  fi
}

acquire_sync_lock() {
  [[ "${SYNC_LOCK_ENABLED:-1}" -eq 1 ]] || return 0

  if [[ "${SYNC_LOCK_INHERITED:-0}" -eq 1 ]] && has_current_sync_lock_owner; then
    SYNC_LOCK_ACQUIRED=1
    trap release_sync_lock EXIT
    return 0
  fi

  if mkdir -p -- "$(dirname -- "$SYNC_LOCK_DIRECTORY")" && \
    mkdir -- "$SYNC_LOCK_DIRECTORY" 2>/dev/null; then
    SYNC_LOCK_ACQUIRED=1
    trap release_sync_lock EXIT
    write_sync_lock_owner
    return $?
  fi

  if reclaim_stale_sync_lock && mkdir -- "$SYNC_LOCK_DIRECTORY" 2>/dev/null; then
    SYNC_LOCK_ACQUIRED=1
    trap release_sync_lock EXIT
    write_sync_lock_owner
    return $?
  fi

  printf 'WARNING: another asset synchronization is running or left an active/ambiguous lock; no asset was changed\n' >&2
  return 1
}

# Projection touches every managed asset on each SessionStart; parameter
# expansion and skipping existing directories avoid one fork per path.
ensure_parent_directory() {
  local path="$1"
  local parent_directory="${path%/*}"

  [[ "$parent_directory" == "$path" || -z "$parent_directory" || -d "$parent_directory" ]] && return 0
  mkdir -p -- "$parent_directory"
}

validate_destination_parent() {
  local destination="$1"
  local parent_directory
  local current_path="."
  local path_component
  local relative_parent
  local -a path_components

  parent_directory="${destination%/*}"
  [[ "$parent_directory" == "$destination" || "$parent_directory" == "." ]] && return 0

  relative_parent="${parent_directory#./}"
  IFS='/' read -r -a path_components <<< "$relative_parent"
  for path_component in "${path_components[@]}"; do
    [[ -z "$path_component" || "$path_component" == "." ]] && continue
    current_path="$current_path/$path_component"

    if [[ -L "$current_path" ]]; then
      record_conflict "$destination parent directory contains symlink $current_path; neither was changed"
      return 1
    fi
    if [[ -e "$current_path" && ! -d "$current_path" ]]; then
      record_conflict "$destination parent directory is not a directory: $current_path; neither was changed"
      return 1
    fi
  done
}

show_sync_diff() {
  local source="$1"
  local destination="$2"
  local source_description="${3:-$source}"

  printf 'Diff for %s (source: %s):\n' "$destination" "$source_description"
  if [[ -f "$destination" ]]; then
    diff -u -- "$destination" "$source" || true
  else
    diff -u -- /dev/null "$source" || true
  fi
}

relative_shared_target() {
  local relative="$1"
  local destination_directory
  local slash_count
  local parent_levels=1
  local level
  local prefix=""

  if [[ "$relative" == */* ]]; then
    destination_directory="${relative%/*}"
    slash_count="${destination_directory//[^\/]/}"
    parent_levels=$(( ${#slash_count} + 2 ))
  fi

  for ((level = 0; level < parent_levels; level++)); do
    prefix+="../"
  done

  printf '%s%s/%s\n' "$prefix" "$SHARED_DIR" "$relative"
}

# Ownership gate. agent-ready-state.py plan --format protected lists the managed
# destinations whose local content changed since the last apply (lockfile base);
# sync_file preserves them and reports a conflict instead of overwriting them.
# The list is wrapped in newlines so membership needs no fork per path.
AGENT_READY_PROTECTED_DESTINATIONS=""

load_protected_destinations() {
  AGENT_READY_PROTECTED_DESTINATIONS=$'\n'"${1//$'\r'/}"$'\n'
}

is_protected_destination() {
  [[ -n "$AGENT_READY_PROTECTED_DESTINATIONS" &&
    "$AGENT_READY_PROTECTED_DESTINATIONS" == *$'\n'"${1#./}"$'\n'* ]]
}

# A checkout with core.autocrlf only changes line endings, which is not a change to
# apply: rewriting the file would mark it as modified in Git with an empty diff.
matches_ignoring_line_endings() {
  local destination="$1"
  local source="$2"

  cmp -s "$destination" "$source" || tr -d '\r' < "$destination" | cmp -s - "$source"
}

# Reason shared by every consumer that preserves a protected destination.
# shellcheck disable=SC2034 # Read by the sync_file implementations that source this file.
AGENT_READY_PROTECTED_HINT="never applied by agent-ready-setup; preserved (rename or delete it to receive the managed asset)"

# A symlink at a managed path is replaced, never followed; the link is removed
# before the rename so a link to a directory cannot redirect the write elsewhere.
# Consumers define record_conflict and record_updated.
replace_managed_symlink() {
  local source="$1"
  local destination="$2"
  local previous_target
  local temporary_destination=""

  if ! previous_target="$(readlink -- "$destination")"; then
    record_conflict "could not read symlink $destination; neither was changed"
    return 0
  fi
  if ! temporary_destination="$(mktemp "${destination}.agent-ready-sync.XXXXXX")" || \
    ! cp -p -- "$source" "$temporary_destination"; then
    [[ -n "$temporary_destination" ]] && rm -f -- "$temporary_destination"
    record_conflict "could not stage template content for $destination; neither was changed"
    return 0
  fi
  if [[ ! -L "$destination" || "$(readlink -- "$destination")" != "$previous_target" ]]; then
    rm -f -- "$temporary_destination"
    record_conflict "$destination changed during synchronization; neither was changed"
    return 0
  fi
  if ! rm -f -- "$destination" || ! mv -- "$temporary_destination" "$destination"; then
    rm -f -- "$temporary_destination"
    record_conflict "could not replace symlink $destination with the template; review it manually"
    return 0
  fi
  record_updated "$destination (symlink replaced with template)"
}

# Claude views are symlinks to the shared asset where the platform allows them. Without
# the symlink privilege (Windows without Developer Mode or elevation) they fall back to a
# hard link to the same file, which needs no privilege; never to a copy that would drift.
# Hard-link views are listed in this manifest: once their asset is deleted they look
# like any project file, and the manifest is what allows pruning them safely.
# Why a Claude view could not be created; shared by every consumer that reports it.
CLAUDE_VIEW_FAILURE_HINT="symlinks need Developer Mode or an elevated shell on Windows, and hard links need the view and the asset on the same volume"

hard_link_views_manifest() {
  printf '%s/.agent-ready-hard-link-views' "$CLAUDE_DIR"
}

remember_hard_link_view() {
  local relative="$1"
  local manifest

  [[ -n "$relative" ]] || return 0
  manifest="$(hard_link_views_manifest)"
  [[ ! -L "$manifest" ]] || return 0
  grep -Fxq -- "$relative" "$manifest" 2>/dev/null || printf '%s\n' "$relative" >> "$manifest"
}

# True when path already is the managed view of the shared asset: a symlink with the
# expected relative target, or the same file as the asset through a hard link.
is_current_claude_view() {
  local path="$1"
  local target="$2"
  local source="$3"

  if [[ -L "$path" ]]; then
    [[ "$(readlink -- "$path")" == "$target" ]]
    return
  fi
  [[ -n "$source" && -f "$path" && -f "$source" && ! -L "$source" && "$path" -ef "$source" ]]
}

# Creates link_path as the Claude view of the shared asset. Git Bash copies on `ln -s`
# by default; nativestrict makes it create a real Windows symlink or fail instead.
create_claude_view_link() {
  local target="$1"
  local source="$2"
  local link_path="$3"
  local relative="${4:-}"

  if MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict" ln -s -- "$target" "$link_path" 2>/dev/null &&
    [[ -L "$link_path" ]]; then
    return 0
  fi
  [[ -L "$link_path" ]] || rm -f -- "$link_path"
  if [[ -n "$source" && -f "$source" && ! -L "$source" ]] &&
    ln -- "$source" "$link_path" 2>/dev/null && [[ "$link_path" -ef "$source" ]]; then
    remember_hard_link_view "$relative"
    return 0
  fi
  rm -f -- "$link_path"
  return 1
}

# First line of the agent-ready post-index-change hook; identifies a hook it may update.
AGENT_READY_GIT_HOOK_MARKER="# agent-ready-setup: relinks .claude hard-link views detached by git."

# Config-based hook (git config hook.<name>.event) that relinks hard-link views. Git runs it
# next to the hooks of core.hooksPath (husky, lefthook) or .git/hooks, without touching them.
AGENT_READY_GIT_HOOK_NAME="agent-ready-relink"
AGENT_READY_GIT_HOOK_EVENT="post-index-change"
AGENT_READY_GIT_HOOK_COMMAND="sh .agents/hooks/relink-hard-link-views.sh"

# True when git runs hooks defined in config. Probed once per run in a scratch repository,
# because the feature depends on the git version.
git_supports_config_hooks() {
  local probe_directory

  if [[ -z "${GIT_CONFIG_HOOKS_SUPPORTED:-}" ]]; then
    GIT_CONFIG_HOOKS_SUPPORTED=0
    if probe_directory="$(mktemp -d "${TMPDIR:-/tmp}/agent-ready-hook-probe.XXXXXX")"; then
      if git init -q "$probe_directory/repository" 2>/dev/null &&
        git -C "$probe_directory/repository" config hook.probe.event "$AGENT_READY_GIT_HOOK_EVENT" &&
        git -C "$probe_directory/repository" config hook.probe.command "echo ran > probe-ran" &&
        git -C "$probe_directory/repository" hook run "$AGENT_READY_GIT_HOOK_EVENT" -- 0 0 >/dev/null 2>&1 &&
        [[ -f "$probe_directory/repository/probe-ran" ]]; then
        GIT_CONFIG_HOOKS_SUPPORTED=1
      fi
      rm -rf -- "$probe_directory"
    fi
  fi
  [[ "$GIT_CONFIG_HOOKS_SUPPORTED" == "1" ]]
}

# Registers the hook that relinks hard-link views after git operations that recreate
# .agents files (reset, stash, cherry-pick, revert, aborts). Only needed while hard-link
# views exist. Without config-based hooks it falls back to a file in the hooks directory,
# never overwriting a hook manager (core.hooksPath) or a project hook. Consumers define
# record_conflict, record_created and record_removed.
install_hard_link_git_hook() {
  local hook_template="$1"
  local manifest
  local hooks_directory
  local hook_path
  local temporary_hook

  manifest="$(hard_link_views_manifest)"
  [[ -s "$manifest" && ! -L "$manifest" ]] || return 0

  if git_supports_config_hooks; then
    if [[ "$(git config --get "hook.$AGENT_READY_GIT_HOOK_NAME.event" 2>/dev/null)" == "$AGENT_READY_GIT_HOOK_EVENT" &&
      "$(git config --get "hook.$AGENT_READY_GIT_HOOK_NAME.command" 2>/dev/null)" == "$AGENT_READY_GIT_HOOK_COMMAND" ]]; then
      return 0
    fi
    if git config "hook.$AGENT_READY_GIT_HOOK_NAME.event" "$AGENT_READY_GIT_HOOK_EVENT" &&
      git config "hook.$AGENT_READY_GIT_HOOK_NAME.command" "$AGENT_READY_GIT_HOOK_COMMAND"; then
      record_created "git config hook.$AGENT_READY_GIT_HOOK_NAME ($AGENT_READY_GIT_HOOK_EVENT)"
    else
      record_conflict "could not register git config hook.$AGENT_READY_GIT_HOOK_NAME; hard-link views relink on the next sync instead"
    fi
    return 0
  fi

  [[ -f "$hook_template" ]] || return 0
  if [[ -n "$(git config --get core.hooksPath 2>/dev/null)" ]]; then
    record_conflict "core.hooksPath is set and this git has no config-based hooks, so the hook that relinks .claude hard-link views was not installed; run $hook_template from your $AGENT_READY_GIT_HOOK_EVENT hook"
    return 0
  fi
  hooks_directory="$(git rev-parse --git-path hooks 2>/dev/null)" || return 0
  hook_path="$hooks_directory/$AGENT_READY_GIT_HOOK_EVENT"
  if [[ -e "$hook_path" || -L "$hook_path" ]]; then
    if [[ -L "$hook_path" ]] || ! grep -Fq -- "$AGENT_READY_GIT_HOOK_MARKER" "$hook_path"; then
      record_conflict "$hook_path already exists, so the hook that relinks .claude hard-link views was not installed; run $hook_template from it"
      return 0
    fi
    cmp -s "$hook_template" "$hook_path" && return 0
  fi
  mkdir -p -- "$hooks_directory" || return 0
  temporary_hook="$hook_path.agent-ready.$$"
  if cp -- "$hook_template" "$temporary_hook" && chmod +x "$temporary_hook" && mv -f -- "$temporary_hook" "$hook_path"; then
    record_created "$hook_path"
  else
    rm -f -- "$temporary_hook"
    record_conflict "could not install $hook_path; hard-link views relink on the next sync instead"
  fi
}

# Removes hard-link views whose shared asset was deleted and forgets the ones that are
# no longer hard links. Consumers define record_removed.
prune_hard_link_views() {
  local manifest
  local relative
  local view_path
  local remaining=""

  manifest="$(hard_link_views_manifest)"
  [[ -f "$manifest" && ! -L "$manifest" ]] || return 0
  while IFS= read -r relative; do
    case "$relative" in
      ""|/*|../*|*/../*|*/..) continue ;;
    esac
    view_path="$CLAUDE_DIR/$relative"
    [[ -f "$view_path" && ! -L "$view_path" ]] || continue
    if [[ -e "$SHARED_DIR/$relative" || -L "$SHARED_DIR/$relative" ]]; then
      remaining+="$relative"$'\n'
      continue
    fi
    if rm -f -- "$view_path"; then
      record_removed "$view_path"
    else
      remaining+="$relative"$'\n'
    fi
  done < "$manifest"
  if [[ -n "$remaining" ]]; then
    printf '%s' "$remaining" > "$manifest"
  else
    rm -f -- "$manifest"
  fi
}

# Replaces a modified Claude view (regular file, foreign symlink, or detached hard
# link) with the managed view of the canonical shared asset.
replace_with_claude_view() {
  local destination="$1"
  local target="$2"
  local source="${3:-}"
  local relative="${4:-}"
  local temporary_link="${destination}.agent-ready-link.$$"

  if [[ -e "$temporary_link" || -L "$temporary_link" ]]; then
    record_conflict "temporary normalization path already exists for $destination; neither was changed"
    return 0
  fi
  if ! create_claude_view_link "$target" "$source" "$temporary_link" "$relative"; then
    record_conflict "could not create Claude view $destination; neither was changed ($CLAUDE_VIEW_FAILURE_HINT)"
    return 0
  fi
  if ! rm -f -- "$destination" || ! mv -- "$temporary_link" "$destination"; then
    rm -f -- "$temporary_link"
    record_conflict "could not replace Claude view $destination; review it manually"
    return 0
  fi
  record_updated "$destination -> managed view"
}

# Claude registers agents and commands natively from .claude/agents and
# .claude/commands. A .claude/skills view of their Codex adapter would register
# the same workflow twice. The name belongs to agent-ready-setup, so the view is
# removed even when it was edited; only non-regular paths are left for manual
# review. Consumers define record_removed.
remove_claude_skill_view() {
  local skill_name="$1"
  local view_directory="$CLAUDE_DIR/skills/$skill_name"
  local view_path="$view_directory/SKILL.md"

  [[ -e "$view_path" || -L "$view_path" ]] || return 0
  if [[ ! -L "$view_path" && ! -f "$view_path" ]]; then
    record_conflict "$view_path duplicates Claude agent or command $skill_name but is not a regular file; preserved"
    return 0
  fi
  if ! rm -f -- "$view_path"; then
    record_conflict "could not remove duplicate Claude skill view $view_path; preserved"
    return 0
  fi
  record_removed "$view_path"
  rmdir -- "$view_directory" 2>/dev/null || true
}

# Rules the repository adds under .agents/rules/ get the same Claude view as
# template rules, so Claude loads them natively. The renderer owns the
# definition of a project rule; managed views whose rule was deleted are pruned.
# Consumers define link_claude_asset and record_removed.
project_rule_claude_views() {
  local template_renderer="$1"
  local template_rules_directory="$2"
  local common_rules_directory="${3:-}"
  local relative_path
  local rule_file
  local view_path
  local rule_files_list
  local -a renderer_arguments=(--list-rules --rules-dir "$template_rules_directory")

  [[ -d "$SHARED_DIR/rules" && ! -L "$SHARED_DIR/rules" ]] || return 0

  if [[ -n "$common_rules_directory" && -d "$common_rules_directory" ]]; then
    renderer_arguments+=(--common-rules-dir "$common_rules_directory")
  fi
  renderer_arguments+=(--project-rules-dir "$SHARED_DIR/rules")
  rule_files_list="$(bash "$template_renderer" "${renderer_arguments[@]}")" || return 1

  while IFS=$'\t' read -r relative_path rule_file; do
    [[ "$rule_file" == "$SHARED_DIR/rules/"* ]] || continue
    link_claude_asset "rules/$relative_path"
  done <<< "$rule_files_list"

  [[ -d "$CLAUDE_DIR/rules" && ! -L "$CLAUDE_DIR/rules" ]] || return 0
  while IFS= read -r -d '' view_path; do
    relative_path="${view_path#"$CLAUDE_DIR/"}"
    [[ -e "$SHARED_DIR/$relative_path" || -L "$SHARED_DIR/$relative_path" ]] && continue
    [[ "$(readlink -- "$view_path")" == "$(relative_shared_target "$relative_path")" ]] || continue
    if rm -f -- "$view_path"; then
      record_removed "$view_path"
    fi
  done < <(find "$CLAUDE_DIR/rules" -type l -print0)
}

merge_managed_settings() {
  local template_path="$1"
  local settings_path="$2"
  local matching_mode="${3:-strict}"
  local -a matching_options=()

  case "$matching_mode" in
    strict) ;;
    nested) matching_options+=(--allow-nested-template-match) ;;
    *)
      printf 'ERROR: unsupported managed settings matching mode: %s\n' "$matching_mode" >&2
      return 2
      ;;
  esac

  python3 "$ASSET_SYNC_SKILL_DIR/scripts/merge-managed-settings.py" \
    ${matching_options[@]+"${matching_options[@]}"} \
    "$template_path" \
    "$settings_path"
}

# Compare against the snapshot used to produce merged content, never a newer copy.
destination_matches_snapshot() {
  local destination="$1"
  local snapshot="$2"

  if [[ "$snapshot" == absent ]]; then
    [[ ! -e "$destination" && ! -L "$destination" ]]
  else
    [[ -f "$destination" && ! -L "$destination" ]] && cmp -s "$destination" "$snapshot"
  fi
}

# Merge the template into Codex's hooks file, keeping custom hooks. Persist the
# merged output only when the destination still matches the snapshot it came from.
sync_codex_hooks() {
  local template="$1"
  local destination="$CODEX_DIR/hooks.json"
  local staged_hooks
  local destination_snapshot

  validate_destination_parent "$destination" || return 0
  if [[ -L "$destination" || ( -e "$destination" && ! -f "$destination" ) ]]; then
    record_conflict "$destination is a symlink or non-file; Codex hooks preserved"
    return 0
  fi
  if [[ ! -e "$destination" ]]; then
    sync_file "$template" "$destination" "$template" absent
    return 0
  fi

  staged_hooks="$(mktemp "${TMPDIR:-/tmp}/agent-ready-codex-hooks.XXXXXX")"
  destination_snapshot="$(mktemp "${TMPDIR:-/tmp}/agent-ready-current-hooks.XXXXXX")"
  cp -- "$destination" "$destination_snapshot"
  if python3 "$ASSET_SYNC_SKILL_DIR/scripts/merge-codex-hooks.py"     "$template" "$destination_snapshot" > "$staged_hooks"; then
    sync_file "$staged_hooks" "$destination" "$template" "$destination_snapshot"
  else
    record_conflict "Codex hooks contain invalid configuration; original file preserved"
  fi
  rm -f -- "$staged_hooks" "$destination_snapshot"
}
