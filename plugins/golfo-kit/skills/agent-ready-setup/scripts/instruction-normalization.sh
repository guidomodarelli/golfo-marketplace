#!/bin/bash
# instruction-normalization.sh
# Shared instruction normalization for bootstrap.sh and normalize-instructions.sh.
# Consumers source this file from their own scripts directory, source
# asset-sync-common.sh, and define before calling: record_conflict,
# record_created, record_skipped and the CREATED, SKIPPED, MIGRATED, RENAMED,
# CONFLICTS and PROVIDER_ROOT_CONFLICTS arrays.

# shellcheck source=stack-directory.sh
source "$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/stack-directory.sh"

# shellcheck disable=SC2034
CLAUDE_DIR=".claude"
SHARED_DIR=".agents"
CODEX_DIR=".codex"
AGENTS_FILE="AGENTS.md"
CLAUDE_FILE="CLAUDE.md"
CLAUDE_PROXY="@AGENTS.md"

# Template paths derive from the resolved skill source and the selected
# profiles; a single stack profile resolves to assets/stacks/<stack>.
configure_instruction_templates() {
  local skill_dir="$1"
  local stack="$2"

  COMMON_SRC="$skill_dir/assets/common"
  SRC="$(resolve_stack_template_directory "$skill_dir" "$stack")" || exit 1
  # One template for the managed block; the skeleton of a new AGENTS.md can come from a profile of
  # the selection (software-development) instead of the neutral one of the template.
  AGENTS_TEMPLATE="$COMMON_SRC/agents-template.md"
  AGENTS_SKELETON="$SRC/agents-skeleton.md"
  [[ -f "$AGENTS_SKELETON" ]] || AGENTS_SKELETON=""
  ROOT_CLAUDE_TEMPLATE="$skill_dir/assets/claude-proxy.md"
  CENTRALIZATION_TEMPLATE="$skill_dir/assets/instruction-centralization.md"
  TEMPLATE_RENDERER="$skill_dir/scripts/render-instruction-template.sh"
}

validate_instruction_templates() {
  local stack="$1"

  if [[ ! -d "$SRC" ]]; then
    echo "ERROR: No template found for stack '$stack' at $SRC" >&2
    return 1
  fi
  if [[ ! -f "$AGENTS_TEMPLATE" ]]; then
    echo "ERROR: Base template is missing agents-template.md: $AGENTS_TEMPLATE" >&2
    return 1
  fi
  if [[ ! -d "$SRC/rules" ]]; then
    echo "ERROR: Stack template is missing rules directory: $SRC/rules" >&2
    return 1
  fi
  if [[ ! -f "$TEMPLATE_RENDERER" ]]; then
    echo "ERROR: Instruction template renderer is missing: $TEMPLATE_RENDERER" >&2
    return 1
  fi
  if [[ ! -f "$ROOT_CLAUDE_TEMPLATE" ]]; then
    echo "ERROR: Root CLAUDE.md template is missing: $ROOT_CLAUDE_TEMPLATE" >&2
    return 1
  fi
  if [[ ! -f "$CENTRALIZATION_TEMPLATE" ]]; then
    echo "ERROR: Instruction centralization template is missing: $CENTRALIZATION_TEMPLATE" >&2
    return 1
  fi
}

validate_provider_roots() {
  local provider_root

  for provider_root in "$CLAUDE_DIR" "$SHARED_DIR" "$CODEX_DIR"; do
    if [[ -L "$provider_root" ]]; then
      PROVIDER_ROOT_CONFLICTS+=("$provider_root is a symlink; neither provider asset was changed")
    elif [[ -e "$provider_root" && ! -d "$provider_root" ]]; then
      PROVIDER_ROOT_CONFLICTS+=("$provider_root is not a directory; neither provider asset was changed")
    fi
  done

  if [[ ${#PROVIDER_ROOT_CONFLICTS[@]} -gt 0 ]]; then
    echo "Provider root conflicts (manual resolution required):" >&2
    for conflict in "${PROVIDER_ROOT_CONFLICTS[@]}"; do
      printf '  ! %s\n' "$conflict" >&2
    done
    exit 1
  fi
}

is_ignored_path() {
  local path="$1"
  local check_status

  if git check-ignore -q -- "$path" 2>/dev/null; then
    check_status=0
  else
    check_status=$?
  fi

  case "$check_status" in
    0)
      return 0
      ;;
    1)
      return 1
      ;;
    *)
      return 2
      ;;
  esac
}

# Creates an absent instruction file atomically from a template.
create_instruction_from_template() {
  local source="$1"
  local destination="$2"
  local temporary_destination

  validate_destination_parent "$destination" || return 0
  ensure_parent_directory "$destination"
  if ! temporary_destination="$(mktemp "${destination}.agent-ready-sync.XXXXXX")"; then
    CONFLICTS+=("could not stage new content for $destination; neither was changed")
    return 0
  fi
  if ! cp -p -- "$source" "$temporary_destination" || ! mv -f -- "$temporary_destination" "$destination"; then
    rm -f -- "$temporary_destination"
    CONFLICTS+=("could not create $destination atomically; neither was changed")
    return 0
  fi
  record_created "$destination"
}

record_renamed() {
  RENAMED+=("$1")
}

is_claude_filename() {
  case "$1" in
    [cC][lL][aA][uU][dD][eE].[mM][dD]) return 0 ;;
    *) return 1 ;;
  esac
}

normalize_claude_filename() {
  local directory="$1"
  local claude_file="$directory/$CLAUDE_FILE"
  local candidate
  local case_variant=""
  local case_variant_count=0
  local exact_name_found=0
  local temporary_path
  local ignore_status

  while IFS= read -r -d '' candidate; do
    if is_ignored_path "$candidate"; then
      continue
    else
      ignore_status=$?
      if [[ "$ignore_status" -eq 2 ]]; then
        CONFLICTS+=("could not determine whether $candidate is ignored; neither was renamed")
        return 0
      fi
    fi

    if [[ "${candidate##*/}" == "$CLAUDE_FILE" ]]; then
      exact_name_found=1
    else
      case_variant="$candidate"
      case_variant_count=$((case_variant_count + 1))
    fi
  done < <(find "$directory" -mindepth 1 -maxdepth 1 -iname "$CLAUDE_FILE" -print0)

  if [[ "$case_variant_count" -eq 0 ]]; then
    return 0
  fi

  if [[ "$exact_name_found" -eq 1 || "$case_variant_count" -ne 1 ]]; then
    CONFLICTS+=("$directory contains multiple case variants of $CLAUDE_FILE; neither was renamed")
    return 0
  fi

  if [[ -L "$case_variant" || ! -f "$case_variant" ]]; then
    CONFLICTS+=("$case_variant is not a regular file; $claude_file was not renamed")
    return 0
  fi

  if ! temporary_path="$(mktemp "$directory/.${CLAUDE_FILE}.agent-ready-name.XXXXXX")"; then
    CONFLICTS+=("could not stage rename for $case_variant; $claude_file was not changed")
    return 0
  fi
  rm -f -- "$temporary_path"

  if ! mv -- "$case_variant" "$temporary_path" || ! mv -n -- "$temporary_path" "$claude_file"; then
    if [[ -e "$temporary_path" || -L "$temporary_path" ]]; then
      if mv -n -- "$temporary_path" "$case_variant"; then
        CONFLICTS+=("could not rename $case_variant to $claude_file; destination changed concurrently and was preserved")
      else
        CONFLICTS+=("could not rename $case_variant to $claude_file; staged content was preserved at $temporary_path")
      fi
    else
      CONFLICTS+=("could not rename $case_variant to $claude_file; neither was changed")
    fi
    return 0
  fi

  if [[ -e "$temporary_path" || -L "$temporary_path" ]]; then
    if mv -n -- "$temporary_path" "$case_variant"; then
      CONFLICTS+=("could not rename $case_variant to $claude_file; destination changed concurrently and was preserved")
    else
      CONFLICTS+=("could not rename $case_variant to $claude_file; staged content was preserved at $temporary_path")
    fi
    return 0
  fi

  record_renamed "$case_variant -> $claude_file"
}

normalize_instruction_filenames() {
  local path
  local basename
  local directory

  normalize_claude_filename "."
  while IFS= read -r -d '' path; do
    basename="${path##*/}"
    if ! is_claude_filename "$basename"; then
      continue
    fi
    if [[ "$path" == */* ]]; then
      directory="${path%/*}"
    else
      directory="."
    fi
    normalize_claude_filename "$directory"
  done < <(git ls-files --cached --others --exclude-standard -z)
}

is_normalized_root_claude() {
  [[ -f "$CLAUDE_FILE" ]] && cmp -s "$CLAUDE_FILE" "$ROOT_CLAUDE_TEMPLATE"
}

is_normalized_claude_proxy() {
  local claude_file="$1"

  [[ -f "$claude_file" ]] && cmp -s "$claude_file" "$ROOT_CLAUDE_TEMPLATE"
}

write_claude_proxy() {
  local claude_file="$1"

  cp -- "$ROOT_CLAUDE_TEMPLATE" "$claude_file"
}

# A nested CLAUDE.md only imports its AGENTS.md: the root proxy and the managed block of the
# root AGENTS.md already carry the centralization rule for every folder.
write_nested_claude_proxy() {
  local claude_file="$1"

  printf '%s\n' "$CLAUDE_PROXY" > "$claude_file"
}

is_plain_claude_proxy() {
  local claude_file="$1"

  [[ -f "$claude_file" ]] && [[ "$(cat -- "$claude_file")" == "$CLAUDE_PROXY" ]]
}

create_root_agents_from_template() {
  local temporary_agents_file
  local -a renderer_arguments=(
    --template "$AGENTS_TEMPLATE"
    --rules-dir "$SRC/rules"
    --project-rules-dir "$SHARED_DIR/rules"
    --centralization "$CENTRALIZATION_TEMPLATE"
  )

  if [[ -d "$COMMON_SRC/rules" ]]; then
    renderer_arguments+=(--common-rules-dir "$COMMON_SRC/rules")
  fi
  if [[ -n "$AGENTS_SKELETON" ]]; then
    renderer_arguments+=(--skeleton "$AGENTS_SKELETON")
  fi

  mkdir -p -- "$(dirname -- "$AGENTS_FILE")"
  temporary_agents_file="$(mktemp "${AGENTS_FILE}.agent-ready-template.XXXXXX")"
  if ! bash "$TEMPLATE_RENDERER" "${renderer_arguments[@]}" > "$temporary_agents_file"; then
    rm -f -- "$temporary_agents_file"
    echo "ERROR: could not render stack instruction template for $AGENTS_FILE" >&2
    return 1
  fi
  chmod 0644 "$temporary_agents_file"
  mv -f -- "$temporary_agents_file" "$AGENTS_FILE"
  record_created "$AGENTS_FILE"
}

# Build root instruction files without maintaining two independent templates.
# Existing non-proxy CLAUDE.md is promoted only when AGENTS.md is absent or
# already contains the same bytes. Divergent files remain untouched.
normalize_root_instructions() {
  if [[ -L "$CLAUDE_FILE" || -L "$AGENTS_FILE" ]]; then
    CONFLICTS+=("$CLAUDE_FILE and $AGENTS_FILE include symlinked instructions; neither was followed or overwritten")
    return
  fi

  if [[ -e "$CLAUDE_FILE" && ! -f "$CLAUDE_FILE" ]]; then
    CONFLICTS+=("$CLAUDE_FILE is not a regular file; neither instruction file was changed")
    return
  fi

  if [[ -e "$AGENTS_FILE" && ! -f "$AGENTS_FILE" ]]; then
    CONFLICTS+=("$AGENTS_FILE is not a regular file; neither instruction file was changed")
    return
  fi

  if [[ -e "$CLAUDE_FILE" ]]; then
    if is_normalized_root_claude; then
      record_skipped "$CLAUDE_FILE"
      if [[ -e "$AGENTS_FILE" || -L "$AGENTS_FILE" ]]; then
        record_skipped "$AGENTS_FILE"
      else
        create_root_agents_from_template
      fi
      return
    fi

    if [[ ! -e "$AGENTS_FILE" && ! -L "$AGENTS_FILE" ]]; then
      cp -- "$CLAUDE_FILE" "$AGENTS_FILE"
      cp -- "$ROOT_CLAUDE_TEMPLATE" "$CLAUDE_FILE"
      MIGRATED+=("$CLAUDE_FILE -> $AGENTS_FILE")
      return
    fi

    if [[ -f "$CLAUDE_FILE" && -f "$AGENTS_FILE" ]] && cmp -s "$CLAUDE_FILE" "$AGENTS_FILE"; then
      cp -- "$ROOT_CLAUDE_TEMPLATE" "$CLAUDE_FILE"
      MIGRATED+=("$CLAUDE_FILE -> $AGENTS_FILE")
    elif is_plain_claude_proxy "$CLAUDE_FILE"; then
      cp -- "$ROOT_CLAUDE_TEMPLATE" "$CLAUDE_FILE"
      MIGRATED+=("$CLAUDE_FILE -> root instruction proxy")
    else
      CONFLICTS+=("$CLAUDE_FILE and $AGENTS_FILE differ; agent must merge compatible instructions before normalizing")
    fi
    return
  fi

  if [[ -e "$AGENTS_FILE" || -L "$AGENTS_FILE" ]]; then
    record_skipped "$AGENTS_FILE"
    create_instruction_from_template "$ROOT_CLAUDE_TEMPLATE" "$CLAUDE_FILE"
    return
  fi

  # The template is the single source. The renderer materializes its dynamic
  # rule catalog for the neutral shared tree consumed through AGENTS.md.
  create_root_agents_from_template
  cp -- "$ROOT_CLAUDE_TEMPLATE" "$CLAUDE_FILE"
  record_created "$CLAUDE_FILE"
}

normalize_nested_instruction_pair() {
  local directory="$1"
  local claude_file="$directory/$CLAUDE_FILE"
  local agents_file="$directory/$AGENTS_FILE"

  if [[ -L "$claude_file" || -L "$agents_file" ]]; then
    CONFLICTS+=("$claude_file and $agents_file include symlinked instructions; neither was followed or overwritten")
    return
  fi

  if [[ -e "$claude_file" && ! -f "$claude_file" ]]; then
    CONFLICTS+=("$claude_file is not a regular file; neither instruction file was changed")
    return
  fi

  if [[ -e "$agents_file" && ! -f "$agents_file" ]]; then
    CONFLICTS+=("$agents_file is not a regular file; neither instruction file was changed")
    return
  fi

  if [[ -e "$claude_file" ]]; then
    if is_ignored_path "$claude_file"; then
      return
    elif [[ "$?" -eq 2 ]]; then
      CONFLICTS+=("could not determine whether $claude_file is ignored; neither instruction file was changed")
      return
    fi
  fi

  if [[ -e "$agents_file" ]]; then
    if is_ignored_path "$agents_file"; then
      return
    elif [[ "$?" -eq 2 ]]; then
      CONFLICTS+=("could not determine whether $agents_file is ignored; neither instruction file was changed")
      return
    fi
  fi

  if [[ -e "$claude_file" ]]; then
    if is_plain_claude_proxy "$claude_file"; then
      if [[ -e "$agents_file" ]]; then
        record_skipped "$claude_file"
        record_skipped "$agents_file"
      elif validate_destination_parent "$agents_file" && : > "$agents_file"; then
        MIGRATED+=("$claude_file -> $agents_file (empty canonical sibling)")
      else
        CONFLICTS+=("$claude_file is an orphaned proxy; $agents_file could not be created")
      fi
      return
    fi

    # The root proxy repeats, in every folder, the rule the root already gives: it becomes the import alone.
    if is_normalized_claude_proxy "$claude_file"; then
      if [[ -e "$agents_file" ]]; then
        write_nested_claude_proxy "$claude_file"
        MIGRATED+=("$claude_file -> nested instruction proxy")
      elif validate_destination_parent "$agents_file" && : > "$agents_file"; then
        write_nested_claude_proxy "$claude_file"
        MIGRATED+=("$claude_file -> $agents_file (empty canonical sibling)")
      else
        CONFLICTS+=("$claude_file is an orphaned proxy; $agents_file could not be created")
      fi
      return
    fi

    if [[ ! -e "$agents_file" ]]; then
      cp -- "$claude_file" "$agents_file"
      write_nested_claude_proxy "$claude_file"
      MIGRATED+=("$claude_file -> $agents_file")
    elif cmp -s "$claude_file" "$agents_file"; then
      write_nested_claude_proxy "$claude_file"
      MIGRATED+=("$claude_file -> $agents_file")
    else
      CONFLICTS+=("$claude_file and $agents_file differ; neither was overwritten")
    fi
    return
  fi

  if [[ -e "$agents_file" ]]; then
    write_nested_claude_proxy "$claude_file"
    MIGRATED+=("$agents_file -> $claude_file proxy")
  fi
}

normalize_nested_instructions() {
  local path
  local basename
  local directory

  while IFS= read -r -d '' path; do
    basename="${path##*/}"
    if [[ "$basename" != "$CLAUDE_FILE" && "$basename" != "$AGENTS_FILE" ]]; then
      continue
    fi
    if [[ "$path" == */* ]]; then
      directory="${path%/*}"
    else
      directory="."
    fi
    [[ "$directory" == "." ]] && continue
    normalize_nested_instruction_pair "$directory"
  done < <(git ls-files --cached --others --exclude-standard -z)
}

# Normalizes every instruction pair so AGENTS.md is canonical and CLAUDE.md a proxy.
normalize_instructions() {
  normalize_instruction_filenames
  normalize_root_instructions
  normalize_nested_instructions
}

report_instruction_normalization() {
  printf '\nInstruction normalization completed from %s.\n' "$PROJECT_ROOT"
  if [[ ${#RENAMED[@]} -gt 0 ]]; then
    echo "Renamed instruction files:"
    for file in "${RENAMED[@]}"; do printf '  ↪ %s\n' "$file"; done
  fi
  if [[ ${#MIGRATED[@]} -gt 0 ]]; then
    echo "Normalized instructions:"
    for file in "${MIGRATED[@]}"; do printf '  ↔ %s\n' "$file"; done
  fi
  if [[ ${#SKIPPED[@]} -gt 0 ]]; then
    echo "Already existed (skipped):"
    for file in "${SKIPPED[@]}"; do printf '  ~ %s\n' "$file"; done
  fi
  if [[ ${#CONFLICTS[@]} -gt 0 ]]; then
    echo "Instruction conflicts or differences (preserved):" >&2
    for conflict in "${CONFLICTS[@]}"; do printf '  ! %s\n' "$conflict" >&2; done
  fi
}
