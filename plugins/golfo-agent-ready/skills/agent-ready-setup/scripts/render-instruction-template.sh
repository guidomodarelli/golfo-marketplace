#!/bin/bash
# render-instruction-template.sh
# Materializes the stack template's managed AGENTS.md block (common, stack and
# project rule references plus the centralization rule) and validates that the
# managed block references every current rule with a provider-neutral path.

set -euo pipefail

readonly RULE_REFERENCE_PLACEHOLDER='{{AGENT_READY_RULE_REFERENCES}}'
readonly CENTRALIZATION_PLACEHOLDER='{{AGENT_READY_CENTRALIZATION}}'
readonly MANAGED_BLOCK_START='<!-- BEGIN AGENT-READY MANAGED -->'
readonly MANAGED_BLOCK_END='<!-- END AGENT-READY MANAGED -->'

TEMPLATE_FILE=""
RULES_DIRECTORY=""
COMMON_RULES_DIRECTORY=""
PROJECT_RULES_DIRECTORY=""
CENTRALIZATION_FILE=""
SKELETON_FILE=""
VALIDATE_FILE=""
MANAGED_BLOCK_ONLY=0
LIST_RULES=0
# Under .agents/rules/: the rules of each workspace of a monorepo (agent_ready_workspaces.py).
WORKSPACE_RULES_DIRECTORY="workspaces"

usage() {
  cat >&2 <<'EOF'
Usage:
  render-instruction-template.sh --template <file> --rules-dir <directory>
    [--common-rules-dir <directory>] [--project-rules-dir <directory>]
    [--centralization <file>] [--skeleton <file>] [--managed-block]
  render-instruction-template.sh --validate <file> --rules-dir <directory>
    [--common-rules-dir <directory>] [--project-rules-dir <directory>]
  render-instruction-template.sh --list-rules --rules-dir <directory>
    [--common-rules-dir <directory>] [--project-rules-dir <directory>]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template)
      [[ $# -ge 2 ]] || { echo "ERROR: --template requires a value" >&2; exit 1; }
      TEMPLATE_FILE="$2"
      shift 2
      ;;
    --rules-dir)
      [[ $# -ge 2 ]] || { echo "ERROR: --rules-dir requires a value" >&2; exit 1; }
      RULES_DIRECTORY="${2%/}"
      shift 2
      ;;
    --common-rules-dir)
      [[ $# -ge 2 ]] || { echo "ERROR: --common-rules-dir requires a value" >&2; exit 1; }
      COMMON_RULES_DIRECTORY="${2%/}"
      shift 2
      ;;
    --project-rules-dir)
      [[ $# -ge 2 ]] || { echo "ERROR: --project-rules-dir requires a value" >&2; exit 1; }
      PROJECT_RULES_DIRECTORY="${2%/}"
      shift 2
      ;;
    --centralization)
      [[ $# -ge 2 ]] || { echo "ERROR: --centralization requires a value" >&2; exit 1; }
      CENTRALIZATION_FILE="$2"
      shift 2
      ;;
    --managed-block)
      MANAGED_BLOCK_ONLY=1
      shift
      ;;
    --skeleton)
      # The project part of a new AGENTS.md, in place of the one of the template: the managed block
      # stays the template's, the single source of the instructions every repository gets.
      [[ $# -ge 2 ]] || { echo "ERROR: --skeleton requires a value" >&2; exit 1; }
      SKELETON_FILE="$2"
      shift 2
      ;;
    --list-rules)
      LIST_RULES=1
      shift
      ;;
    --validate)
      [[ $# -ge 2 ]] || { echo "ERROR: --validate requires a value" >&2; exit 1; }
      VALIDATE_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$RULES_DIRECTORY" || ! -d "$RULES_DIRECTORY" ]]; then
  echo "ERROR: --rules-dir must point to an existing directory: $RULES_DIRECTORY" >&2
  exit 1
fi

if [[ -n "$TEMPLATE_FILE" && -n "$VALIDATE_FILE" ]]; then
  echo "ERROR: --template and --validate are mutually exclusive" >&2
  exit 1
fi

if [[ -z "$TEMPLATE_FILE" && -z "$VALIDATE_FILE" && "$LIST_RULES" -eq 0 ]]; then
  echo "ERROR: provide --template, --validate, or --list-rules" >&2
  usage
  exit 1
fi

if [[ -n "$TEMPLATE_FILE" && ! -f "$TEMPLATE_FILE" ]]; then
  echo "ERROR: --template must point to a regular file: $TEMPLATE_FILE" >&2
  exit 1
fi

if [[ -n "$SKELETON_FILE" && ! -f "$SKELETON_FILE" ]]; then
  echo "ERROR: --skeleton must point to a regular file: $SKELETON_FILE" >&2
  exit 1
fi

if [[ -n "$VALIDATE_FILE" && (! -f "$VALIDATE_FILE" || -L "$VALIDATE_FILE") ]]; then
  echo "ERROR: --validate must point to a non-symlink regular file: $VALIDATE_FILE" >&2
  exit 1
fi

if [[ -n "$COMMON_RULES_DIRECTORY" && ! -d "$COMMON_RULES_DIRECTORY" ]]; then
  echo "ERROR: --common-rules-dir must point to an existing directory: $COMMON_RULES_DIRECTORY" >&2
  exit 1
fi

TEMPLATE_RULES_DIRECTORIES=("$RULES_DIRECTORY")
if [[ -n "$COMMON_RULES_DIRECTORY" ]]; then
  TEMPLATE_RULES_DIRECTORIES=("$COMMON_RULES_DIRECTORY" "$RULES_DIRECTORY")
fi

for template_rules_directory in "${TEMPLATE_RULES_DIRECTORIES[@]}"; do
  if [[ -L "$template_rules_directory" ]]; then
    echo "ERROR: template rules directory must not be a symlink: $template_rules_directory" >&2
    exit 1
  fi

  first_symlink="$(find "$template_rules_directory" -type l -print -quit 2>/dev/null || true)"
  if [[ -n "$first_symlink" ]]; then
    echo "ERROR: rule files must not be symlinks: $first_symlink" >&2
    exit 1
  fi
done

# Common and stack rules are both template rules and are projected into the
# same .agents/rules/ tree, so one relative path must have a single source.
list_template_rules() {
  local template_rules_directory
  local rule_file
  local relative_path
  local previous_path=""

  for template_rules_directory in "${TEMPLATE_RULES_DIRECTORIES[@]}"; do
    while IFS= read -r rule_file; do
      relative_path="${rule_file#"$template_rules_directory"/}"
      case "$relative_path" in
        ""|/*|../*|*/../*|*/..)
          echo "ERROR: unsafe rule path: $relative_path" >&2
          return 1
          ;;
      esac
      # The rules of a workspace are listed by its own AGENTS.md, never by the root one.
      [[ "$relative_path" == "$WORKSPACE_RULES_DIRECTORY"/* ]] && continue
      printf '%s\t%s\n' "$relative_path" "$rule_file"
    done < <(find "$template_rules_directory" -type f -print)
  done | LC_ALL=C sort -t $'\t' -k1,1 | while IFS=$'\t' read -r relative_path rule_file; do
    if [[ "$relative_path" == "$previous_path" ]]; then
      echo "ERROR: rule is defined in both common and stack rules: $relative_path" >&2
      return 1
    fi
    previous_path="$relative_path"
    printf '%s\t%s\n' "$relative_path" "$rule_file"
  done
}

list_rule_paths() {
  local template_rules
  local relative_path
  local rule_file

  template_rules="$(list_template_rules)" || return 1
  [[ -n "$template_rules" ]] || return 0
  while IFS=$'\t' read -r relative_path rule_file; do
    printf '%s\n' "$relative_path"
  done <<< "$template_rules"
}

is_template_rule() {
  local relative_path="$1"
  local template_rules_directory

  for template_rules_directory in "${TEMPLATE_RULES_DIRECTORIES[@]}"; do
    [[ -e "$template_rules_directory/$relative_path" ]] && return 0
  done
  return 1
}

# Fail fast: later callers read the catalog through process substitution,
# which would otherwise hide a duplicate or unsafe rule path.
list_template_rules > /dev/null || exit 1

# Project rules are Markdown files the repository added under .agents/rules/
# without a template counterpart. Symlinks are skipped so a rule never points
# outside the project tree.
list_project_rule_paths() {
  local rule_file
  local relative_path

  [[ -n "$PROJECT_RULES_DIRECTORY" && -d "$PROJECT_RULES_DIRECTORY" && ! -L "$PROJECT_RULES_DIRECTORY" ]] || return 0

  while IFS= read -r rule_file; do
    relative_path="${rule_file#"$PROJECT_RULES_DIRECTORY"/}"
    case "$relative_path" in
      ""|/*|../*|*/../*|*/..)
        echo "ERROR: unsafe project rule path: $relative_path" >&2
        return 1
        ;;
    esac
    is_template_rule "$relative_path" && continue
    [[ "$relative_path" == "$WORKSPACE_RULES_DIRECTORY"/* ]] && continue
    printf '%s\n' "$relative_path"
  done < <(find "$PROJECT_RULES_DIRECTORY" -type f -name '*.md' -print | LC_ALL=C sort)
}

list_all_rule_paths() {
  list_rule_paths
  list_project_rule_paths
}

render_rule_references() {
  local relative_path
  local project_rule_paths

  while IFS= read -r relative_path; do
    printf '%s\n' "- Read and follow \`.agents/rules/$relative_path\`."
  done < <(list_rule_paths)

  project_rule_paths="$(list_project_rule_paths)"
  [[ -n "$project_rule_paths" ]] || return 0
  printf '\n%s\n\n' '### Project rules'
  while IFS= read -r relative_path; do
    printf '%s\n' "- Read and follow \`.agents/rules/$relative_path\`."
  done <<< "$project_rule_paths"
}

if [[ "$LIST_RULES" -eq 1 ]]; then
  template_rules="$(list_template_rules)"
  [[ -z "$template_rules" ]] || printf '%s\n' "$template_rules"
  while IFS= read -r relative_path; do
    printf '%s\t%s\n' "$relative_path" "$PROJECT_RULES_DIRECTORY/$relative_path"
  done < <(list_project_rule_paths)
  exit 0
fi

render_placeholder_block() {
  local placeholder="$1"

  case "$placeholder" in
    "$RULE_REFERENCE_PLACEHOLDER")
      render_rule_references
      ;;
    "$CENTRALIZATION_PLACEHOLDER")
      if [[ -z "$CENTRALIZATION_FILE" || ! -f "$CENTRALIZATION_FILE" ]]; then
        echo "ERROR: template uses $CENTRALIZATION_PLACEHOLDER but --centralization is missing" >&2
        return 1
      fi
      cat -- "$CENTRALIZATION_FILE"
      ;;
  esac
}

if [[ -n "$TEMPLATE_FILE" ]]; then
  placeholder_count="$(grep -Fxc "$RULE_REFERENCE_PLACEHOLDER" "$TEMPLATE_FILE" || true)"
  if [[ "$placeholder_count" -ne 1 ]]; then
    echo "ERROR: template must contain exactly one $RULE_REFERENCE_PLACEHOLDER placeholder" >&2
    exit 1
  fi
  if [[ "$MANAGED_BLOCK_ONLY" -eq 1 ]] && { \
    [[ "$(grep -Fxc "$MANAGED_BLOCK_START" "$TEMPLATE_FILE" || true)" -ne 1 ]] || \
    [[ "$(grep -Fxc "$MANAGED_BLOCK_END" "$TEMPLATE_FILE" || true)" -ne 1 ]]; }; then
    echo "ERROR: template must contain exactly one managed block to use --managed-block" >&2
    exit 1
  fi

  temporary_directory="$(mktemp -d "${TMPDIR:-/tmp}/agent-ready-template.XXXXXX")"
  trap 'rm -rf -- "$temporary_directory"' EXIT
  for placeholder in "$RULE_REFERENCE_PLACEHOLDER" "$CENTRALIZATION_PLACEHOLDER"; do
    placeholder_file="$temporary_directory/$(printf '%s' "$placeholder" | tr -cd '[:alnum:]_').md"
    if grep -Fxq "$placeholder" "$TEMPLATE_FILE"; then
      render_placeholder_block "$placeholder" > "$placeholder_file"
    fi
  done

  # An empty placeholder also drops its following blank separator so optional
  # sections leave no double blank line behind.
  # The skeleton path goes through the environment: awk -v reads backslashes as escapes, and a
  # Windows path to the composed tree (compose\<hash>) would lose them.
  AGENT_READY_SKELETON_FILE="$SKELETON_FILE" awk \
    -v block_directory="$temporary_directory" \
    -v managed_only="$MANAGED_BLOCK_ONLY" \
    -v managed_start="$MANAGED_BLOCK_START" \
    -v managed_end="$MANAGED_BLOCK_END" '
    BEGIN { skeleton = ENVIRON["AGENT_READY_SKELETON_FILE"] }
    function placeholder_path(placeholder, name) {
      name = placeholder
      gsub(/[^[:alnum:]_]/, "", name)
      return block_directory "/" name ".md"
    }
    function emit(line) {
      # A skeleton replaces everything the template has before its managed block.
      if (skeleton != "" && !seen_managed) {
        return
      }
      if (managed_only == 0 || in_managed) {
        print line
      }
    }
    $0 == managed_start {
      if (skeleton != "" && managed_only == 0) {
        while ((getline line < skeleton) > 0) {
          print line
        }
        close(skeleton)
      }
      seen_managed = 1
      in_managed = 1
      emit($0)
      next
    }
    $0 == managed_end { emit($0); in_managed = 0; next }
    skip_blank && $0 == "" { skip_blank = 0; next }
    { skip_blank = 0 }
    /^\{\{AGENT_READY_[A-Z_]+\}\}$/ {
      path = placeholder_path($0)
      rendered = 0
      while ((getline line < path) > 0) {
        emit(line)
        rendered = 1
      }
      close(path)
      if (!rendered) {
        skip_blank = 1
      }
      next
    }
    { emit($0) }
  ' "$TEMPLATE_FILE"
  exit 0
fi

start_count="$(grep -Fxc "$MANAGED_BLOCK_START" "$VALIDATE_FILE" || true)"
end_count="$(grep -Fxc "$MANAGED_BLOCK_END" "$VALIDATE_FILE" || true)"
if [[ "$start_count" -ne 1 || "$end_count" -ne 1 ]]; then
  echo "ERROR: AGENTS.md must contain exactly one managed block" >&2
  exit 1
fi

if grep -Fq "$RULE_REFERENCE_PLACEHOLDER" "$VALIDATE_FILE"; then
  echo "ERROR: AGENTS.md contains an unrendered rule-reference placeholder" >&2
  exit 1
fi

if grep -Eq '@[^[:space:]]*rules/|@path/to/folder' "$VALIDATE_FILE"; then
  echo "ERROR: AGENTS.md contains Claude-only or placeholder @ references" >&2
  exit 1
fi

managed_block_file="$(mktemp "${TMPDIR:-/tmp}/agent-ready-managed-rules.XXXXXX")"
trap 'rm -f -- "$managed_block_file"' EXIT
awk -v start="$MANAGED_BLOCK_START" -v end="$MANAGED_BLOCK_END" '
  $0 == start { in_block = 1; next }
  $0 == end { in_block = 0; next }
  in_block { print }
' "$VALIDATE_FILE" > "$managed_block_file"

rule_path_is_current() {
  local candidate_path="$1"
  local relative_path

  while IFS= read -r relative_path; do
    [[ ".agents/rules/$relative_path" == "$candidate_path" ]] && return 0
  done < <(list_all_rule_paths)
  return 1
}

rule_reference_has_read_instruction() {
  local reference_path="$1"
  local line

  while IFS= read -r line; do
    if [[ "$line" == *"$reference_path"* ]] && \
       [[ "$line" =~ (Read|read|Follow|follow|Leer|leer|Seguir|seguir) ]]; then
      return 0
    fi
  done < "$managed_block_file"
  return 1
}

missing_references=0
while IFS= read -r relative_path; do
  reference_path=".agents/rules/$relative_path"
  if ! grep -Fq -- "$reference_path" "$managed_block_file"; then
    echo "ERROR: AGENTS.md managed block is missing rule reference: $reference_path" >&2
    missing_references=1
  elif ! rule_reference_has_read_instruction "$reference_path"; then
    echo "ERROR: AGENTS.md managed rule reference lacks read/follow instruction: $reference_path" >&2
    missing_references=1
  fi
done < <(list_all_rule_paths)

stale_references=0
while IFS= read -r reference_path; do
  [[ "$reference_path" == *. ]] && reference_path="${reference_path%.}"
  if ! rule_path_is_current "$reference_path"; then
    echo "ERROR: AGENTS.md managed block contains stale rule reference: $reference_path" >&2
    stale_references=1
  fi
done < <(grep -Eo '\.agents/rules/[[:alnum:]_.\/-]+' "$managed_block_file" | LC_ALL=C sort -u || true)

if [[ "$missing_references" -ne 0 || "$stale_references" -ne 0 ]]; then
  exit 1
fi
