#!/bin/bash
# managed-block.sh
# Shared AGENTS.md managed-block logic for merge-instructions.sh, which also runs
# the provider redundancy review, and apply-managed-block.sh, which only applies
# the verbatim managed block. Consumers source this file from their own scripts
# directory, install `trap cleanup EXIT`, and call the steps in order.

# shellcheck source=stack-directory.sh
source "$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/stack-directory.sh"

# shellcheck disable=SC2034
readonly AGENTS_FILE="AGENTS.md"
readonly HUMAN_REQUIRED_EXIT_CODE=2

PROVIDER=""
STACK=""
SKILL_DIR=""
NON_INTERACTIVE="${AGENT_READY_SETUP_NON_INTERACTIVE:-0}"
TEMPORARY_DIRECTORY=""
GIT_DIRECTORY=""
RECHECK=0
CACHED_REVIEW_FILE=""
REVIEW_MODEL=""
REVIEW_EFFORT=""
MERGE_LOCK_DIRECTORY=".agents/.agent-ready-instructions.lock"
# The review cache the hooks also use; its entries live in the Git info directory, not in the repository.
REVIEW_CACHE_SCRIPT="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)/assets/common/hooks/review-cache.py"
readonly INSTRUCTIONS_CHECK="instructions"
# Bump when the review prompt or its schema changes: it is part of every cache key.
readonly INSTRUCTIONS_CHECK_VERSION=2
# An AGENTS.md created from the template needs no review, whatever the provider.
readonly TEMPLATE_REVIEWER="template"
# Where fcntl is missing (Windows), AGENTS.md writers coordinate through this file in the git dir.
AGENTS_WRITE_LOCK_NAME="agent-ready-agents-md.lock"
LOCK_ACQUIRED=0

# shellcheck disable=SC2329
cleanup() {
  if [[ -n "$TEMPORARY_DIRECTORY" && -d "$TEMPORARY_DIRECTORY" ]]; then
    rm -rf -- "$TEMPORARY_DIRECTORY"
  fi
  if [[ "$LOCK_ACQUIRED" -eq 1 ]]; then
    rmdir -- "$MERGE_LOCK_DIRECTORY" 2>/dev/null || true
  fi
}

parse_managed_block_arguments() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --provider|-p)
        [[ $# -ge 2 && -n "${2:-}" ]] || {
          echo "ERROR: $1 requires claude or codex" >&2
          exit 1
        }
        PROVIDER="$2"
        shift 2
        ;;
      --stack)
        [[ $# -ge 2 && -n "${2:-}" ]] || {
          echo "ERROR: --stack requires frontend, node, java, go, or android" >&2
          exit 1
        }
        STACK="$2"
        shift 2
        ;;
      --skill-dir)
        [[ $# -ge 2 && -n "${2:-}" ]] || {
          echo "ERROR: --skill-dir requires a value" >&2
          exit 1
        }
        SKILL_DIR="$2"
        shift 2
        ;;
      --recheck)
        RECHECK=1
        shift
        ;;
      *)
        echo "ERROR: Unknown argument: $1" >&2
        exit 1
        ;;
    esac
  done
}

validate_managed_block_inputs() {
  case "$STACK" in
    frontend|node|java|go|android) ;;
    *)
      echo "ERROR: --stack must be frontend, node, java, go, or android" >&2
      exit 1
      ;;
  esac

  case "$NON_INTERACTIVE" in
    0|1) ;;
    *)
      echo "ERROR: AGENT_READY_SETUP_NON_INTERACTIVE must be 0 or 1" >&2
      exit 1
      ;;
  esac

  if [[ ! -d "$SKILL_DIR" ]]; then
    echo "ERROR: --skill-dir must point to an existing directory: $SKILL_DIR" >&2
    exit 1
  fi

  STACK_TEMPLATE_DIRECTORY="$(resolve_stack_template_directory "$SKILL_DIR" "$STACK")" || exit 1
  # One base template for every stack: each stack adds its own section to AGENTS.md as a block.
  TEMPLATE_FILE="$SKILL_DIR/assets/common/agents-template.md"
  RULES_DIRECTORY="$STACK_TEMPLATE_DIRECTORY/rules"
  COMMON_RULES_DIRECTORY="$SKILL_DIR/assets/common/rules"
  readonly PROJECT_RULES_DIRECTORY=".agents/rules"
  TEMPLATE_RENDERER="$SKILL_DIR/scripts/render-instruction-template.sh"
  CENTRALIZATION_TEMPLATE="$SKILL_DIR/assets/instruction-centralization.md"
  if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "ERROR: base instruction template is missing: $TEMPLATE_FILE" >&2
    exit 1
  fi
  if [[ ! -d "$RULES_DIRECTORY" ]]; then
    echo "ERROR: stack rules directory is missing: $RULES_DIRECTORY" >&2
    exit 1
  fi
  if [[ ! -f "$TEMPLATE_RENDERER" ]]; then
    echo "ERROR: instruction template renderer is missing: $TEMPLATE_RENDERER" >&2
    exit 1
  fi

  if [[ -L "$AGENTS_FILE" ]]; then
    echo "ERROR: $AGENTS_FILE is a symlink; merge stopped without following it" >&2
    exit 1
  fi
  if [[ -e "$AGENTS_FILE" && ! -f "$AGENTS_FILE" ]]; then
    echo "ERROR: $AGENTS_FILE is not a regular file; merge stopped" >&2
    exit 1
  fi

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: merge must run inside a Git worktree" >&2
    exit 1
  fi
  if ! GIT_DIRECTORY="$(git rev-parse --absolute-git-dir 2>/dev/null)"; then
    echo "ERROR: could not resolve worktree Git directory for merge metadata" >&2
    exit 1
  fi
  if [[ -L "$GIT_DIRECTORY" || ( -e "$GIT_DIRECTORY" && ! -d "$GIT_DIRECTORY" ) ]]; then
    echo "ERROR: worktree Git path is not a safe directory for merge metadata" >&2
    exit 1
  fi
}

prepare_managed_block_files() {
  TEMPORARY_DIRECTORY="$(mktemp -d "${TMPDIR:-/tmp}/agent-ready-merge.XXXXXX")"
  FULL_TEMPLATE_FILE="$TEMPORARY_DIRECTORY/template.md"
  MANAGED_BLOCK_FILE="$TEMPORARY_DIRECTORY/managed-block.md"
  PROJECT_CONTENT_FILE="$TEMPORARY_DIRECTORY/project-content.md"
  DETERMINISTIC_FILE="$TEMPORARY_DIRECTORY/deterministic.md"
  # The stack sections of AGENTS.md, keyed by the placeholder line that stands for each in the project content.
  SECTIONS_FILE="$TEMPORARY_DIRECTORY/sections.json"
  MERGED_FILE="$TEMPORARY_DIRECTORY/merged.md"
  SCHEMA_FILE="$TEMPORARY_DIRECTORY/result-schema.json"
  RESULT_FILE="$TEMPORARY_DIRECTORY/provider-result.json"
  readonly MANAGED_BLOCK_START='<!-- BEGIN AGENT-READY MANAGED -->'
  readonly MANAGED_BLOCK_END='<!-- END AGENT-READY MANAGED -->'
  readonly MANAGED_BLOCK_PLACEHOLDER='<!-- AGENT-READY MANAGED BLOCK -->'
  # A stack section is "<!-- BEGIN AGENT-READY MANAGED: <id> -->" ... "<!-- END AGENT-READY MANAGED: <id> -->"
  # (agent_ready_blocks.py); in the project content each becomes "<!-- AGENT-READY MANAGED SECTION: <id> -->".
  readonly SECTION_MARKER_PATTERN='<!-- (BEGIN|END) AGENT-READY MANAGED: (.+?) -->'
  readonly SECTION_PLACEHOLDER_PREFIX='<!-- AGENT-READY MANAGED SECTION: '
}

sha256_file() {
  local file_path="$1"

  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file_path" | cut -d ' ' -f 1
  else
    shasum -a 256 "$file_path" | cut -d ' ' -f 1
  fi
}

acquire_merge_lock() {
  if [[ -L ".agents" || ( -e ".agents" && ! -d ".agents" ) ]]; then
    echo "ERROR: .agents is not a safe directory for merge lock" >&2
    return 1
  fi
  mkdir -p -- .agents

  if ! mkdir -- "$MERGE_LOCK_DIRECTORY" 2>/dev/null; then
    echo "Human confirmation required: another instruction merge is running or left a stale lock at $MERGE_LOCK_DIRECTORY" >&2
    return "$HUMAN_REQUIRED_EXIT_CODE"
  fi
  LOCK_ACQUIRED=1
}

# Sets REVIEW_MODEL and REVIEW_EFFORT for the review of AGENTS.md: the defaults that
# review-cache.py keeps for every AI review, unless AGENT_READY_SETUP_MERGE_MODEL or
# AGENT_READY_SETUP_MERGE_REASONING_EFFORT change them. The model is part of the cache key.
resolve_review_model() {
  local default_model=""
  local default_effort=""

  [[ -z "$REVIEW_MODEL" ]] || return 0
  read -r default_model default_effort < <(python3 -B "$REVIEW_CACHE_SCRIPT" defaults --provider "$PROVIDER") || true
  # Native Windows Python ends the line with CRLF.
  default_effort="${default_effort%$'\r'}"
  if [[ -z "$default_model" || -z "$default_effort" ]]; then
    echo "ERROR: could not read the review defaults of $PROVIDER from $REVIEW_CACHE_SCRIPT" >&2
    exit 1
  fi
  REVIEW_MODEL="${AGENT_READY_SETUP_MERGE_MODEL:-$default_model}"
  REVIEW_EFFORT="${AGENT_READY_SETUP_MERGE_REASONING_EFFORT:-$default_effort}"
}

# --file arguments of the review cache: the AGENTS.md bytes and every rule the review sees.
review_cache_files() {
  local relative_path
  local rule_file

  REVIEW_CACHE_FILES=(--file "$AGENTS_FILE" "$AGENTS_FILE")
  while IFS=$'\t' read -r relative_path rule_file; do
    REVIEW_CACHE_FILES+=(--file ".agents/rules/$relative_path" "$rule_file")
  done < "$RULE_FILES_LIST"
}

# Exit 0 when the review cache holds a current entry for the AGENTS.md and rules the
# review would see: reviewed by this provider and model, or created from the template.
# The entry is left in CACHED_REVIEW_FILE, so the caller can repeat its findings.
instructions_review_cached() {
  local -a recheck_arguments=()
  local reviewer

  CACHED_REVIEW_FILE="$TEMPORARY_DIRECTORY/cached-review.json"
  [[ "$RECHECK" -eq 1 ]] && recheck_arguments=(--recheck)
  review_cache_files
  for reviewer in "$PROVIDER" "$TEMPLATE_REVIEWER"; do
    [[ -n "$reviewer" ]] || continue
    local model=""
    if [[ "$reviewer" != "$TEMPLATE_REVIEWER" ]]; then
      resolve_review_model
      model="$REVIEW_MODEL"
    fi
    if python3 -B "$REVIEW_CACHE_SCRIPT" lookup --project . --check "$INSTRUCTIONS_CHECK" \
      --version "$INSTRUCTIONS_CHECK_VERSION" --provider "$reviewer" --model "$model" \
      "${REVIEW_CACHE_FILES[@]}" ${recheck_arguments[@]+"${recheck_arguments[@]}"} \
      > "$CACHED_REVIEW_FILE" 2>/dev/null; then
      return 0
    fi
  done
  return 1
}

# Exit 0 while the AI reviews are on; the last apply recorded reviews.enabled for the hooks too.
instruction_reviews_enabled() {
  python3 -B "$REVIEW_CACHE_SCRIPT" enabled --project . >/dev/null 2>&1 || [[ $? -ne 1 ]]
}

# Records a finished review of the current AGENTS.md: $1 is the reviewer, $2 a JSON file
# with findings and the fields to keep. A cache that cannot be written never fails the merge.
store_instructions_review() {
  local reviewer="$1"
  local result_file="$2"
  local model=""

  if [[ "$reviewer" != "$TEMPLATE_REVIEWER" ]]; then
    resolve_review_model
    model="$REVIEW_MODEL"
  fi
  review_cache_files
  python3 -B "$REVIEW_CACHE_SCRIPT" store --project . --check "$INSTRUCTIONS_CHECK" \
    --version "$INSTRUCTIONS_CHECK_VERSION" --provider "$reviewer" --model "$model" \
    "${REVIEW_CACHE_FILES[@]}" --result "$result_file" || true
}

# Prints on stderr, under the header $2, the findings of $1 (JSON with findings) that nobody
# accepted or dismissed, each with its id; prints nothing when none is left to show.
report_instructions_findings() {
  local result_file="$1"
  local header="$2"
  local lines

  review_cache_files
  lines="$(python3 -B "$REVIEW_CACHE_SCRIPT" report --project . --check "$INSTRUCTIONS_CHECK" \
    --version "$INSTRUCTIONS_CHECK_VERSION" --provider "${PROVIDER:-$TEMPLATE_REVIEWER}" \
    "${REVIEW_CACHE_FILES[@]}" --result "$result_file")" || return 0
  [[ -n "$lines" ]] || return 0
  printf '%s\n%s\n' "$header" "$lines" >&2
  printf '%s\n' '  Accept or dismiss one with: agent-ready review accept <id> --reason "..."' >&2
}

run_template_renderer() {
  local -a renderer_arguments=("$@")

  if [[ -d "$COMMON_RULES_DIRECTORY" ]]; then
    renderer_arguments+=(--common-rules-dir "$COMMON_RULES_DIRECTORY")
  fi

  bash "$TEMPLATE_RENDERER" "${renderer_arguments[@]}"
}

render_template() {
  run_template_renderer \
    --template "$TEMPLATE_FILE" \
    --rules-dir "$RULES_DIRECTORY" \
    --project-rules-dir "$PROJECT_RULES_DIRECTORY" \
    --centralization "$CENTRALIZATION_TEMPLATE" \
    "$@"
}

load_managed_block_rules() {
  RULE_FILES_LIST="$TEMPORARY_DIRECTORY/rule-files.tsv"
  # Template and project rules share one catalog so the managed block, the review
  # hash, and the review prompt always see the same set of rules.
  if ! run_template_renderer --list-rules \
    --rules-dir "$RULES_DIRECTORY" \
    --project-rules-dir "$PROJECT_RULES_DIRECTORY" > "$RULE_FILES_LIST"; then
    echo "ERROR: could not list template and project rules; $AGENTS_FILE was not changed" >&2
    exit 1
  fi

  if ! render_template --managed-block > "$MANAGED_BLOCK_FILE"; then
    echo "ERROR: could not render stack instruction template; $AGENTS_FILE was not changed" >&2
    exit 1
  fi
}

# Takes the merge lock before any AGENTS.md write.
start_managed_block_update() {
  acquire_status=0
  acquire_merge_lock || acquire_status=$?
  if [[ "$acquire_status" -ne 0 ]]; then
    exit "$acquire_status"
  fi
}

# Creates AGENTS.md from the full template and exits when it does not exist yet.
create_agents_from_template_if_missing() {
  if [[ ! -e "$AGENTS_FILE" ]]; then
    # The full template (project scaffold plus managed block) is only needed here.
    if ! render_template > "$FULL_TEMPLATE_FILE"; then
      echo "ERROR: could not render stack instruction template; $AGENTS_FILE was not created" >&2
      exit 1
    fi
    temporary_destination="$(mktemp "${AGENTS_FILE}.agent-ready-merge.XXXXXX")"
    chmod 0644 "$temporary_destination"
    cat -- "$FULL_TEMPLATE_FILE" > "$temporary_destination"
    mv -f -- "$temporary_destination" "$AGENTS_FILE"
    printf '%s\n' '{"findings": [], "reason": "created from the template; nothing of the project to review"}' \
      > "$TEMPORARY_DIRECTORY/template-review.json"
    store_instructions_review "$TEMPLATE_REVIEWER" "$TEMPORARY_DIRECTORY/template-review.json"
    printf 'Created %s from %s; no project instructions existed.\n' "$AGENTS_FILE" "$TEMPLATE_FILE"
    exit 0
  fi
}

# Splits AGENTS.md into project content (managed block replaced by a
# placeholder line) and a deterministic result with the rendered block copied
# verbatim. The sections of the stacks are the engine's too: the project content
# carries one placeholder line per section, and SECTIONS_FILE their verbatim lines,
# so the provider review never takes them for project lines it may delete.
# Exit 0: managed markers found; 3: legacy file without markers; 4: malformed markers.
split_agents_file() {
  python3 - "$AGENTS_FILE" "$MANAGED_BLOCK_FILE" "$PROJECT_CONTENT_FILE" "$DETERMINISTIC_FILE" \
    "$MANAGED_BLOCK_START" "$MANAGED_BLOCK_END" "$MANAGED_BLOCK_PLACEHOLDER" \
    "$SECTIONS_FILE" "$SECTION_MARKER_PATTERN" "$SECTION_PLACEHOLDER_PREFIX" <<'PY'
import json
import re
import sys

(agents_path, block_path, project_path, deterministic_path,
 block_start, block_end, placeholder, sections_path, section_pattern, section_prefix) = sys.argv[1:]
section_marker = re.compile(section_pattern)


def without_sections(content_lines):
    """The lines with each stack section replaced by its placeholder, and the sections.

    Markers that do not pair up leave every line in place: the review then sees them, and
    the check that rejects managed markers in its result keeps the file as it was.
    """
    result, sections, open_section = [], {}, None
    for line in content_lines:
        match = section_marker.fullmatch(line)
        if open_section is None:
            if match and match.group(1) == "BEGIN":
                open_section = (match.group(2), [line])
            elif match:
                return content_lines, {}
            else:
                result.append(line)
            continue
        open_section[1].append(line)
        if match:
            if match.group(1) != "END" or match.group(2) != open_section[0]:
                return content_lines, {}
            key = section_prefix + open_section[0] + " -->"
            if key in sections:
                return content_lines, {}
            sections[key] = open_section[1]
            result.append(key)
            open_section = None
    if open_section is not None:
        return content_lines, {}
    return result, sections


def write_sections(sections):
    with open(sections_path, "w", encoding="utf-8", newline="\n") as sections_file:
        json.dump(sections, sections_file)

with open(agents_path, encoding="utf-8") as agents_file:
    lines = agents_file.read().splitlines()
with open(block_path, encoding="utf-8") as block_file:
    block = block_file.read().splitlines()

start_indexes = [index for index, line in enumerate(lines) if line == block_start]
end_indexes = [index for index, line in enumerate(lines) if line == block_end]


def write(path, content_lines):
    # newline: Windows text mode would write CRLF and break byte-exact managed blocks.
    with open(path, "w", encoding="utf-8", newline="\n") as output_file:
        output_file.write("\n".join(content_lines).rstrip("\n") + "\n")


if not start_indexes and not end_indexes:
    project_lines, sections = without_sections(lines)
    write_sections(sections)
    write(project_path, project_lines)
    legacy_lines = list(lines)
    while legacy_lines and not legacy_lines[-1].strip():
        legacy_lines.pop()
    write(deterministic_path, legacy_lines + ([""] if legacy_lines else []) + block)
    sys.exit(3)

if len(start_indexes) != 1 or len(end_indexes) != 1 or start_indexes[0] > end_indexes[0]:
    sys.exit(4)

before = lines[:start_indexes[0]]
after = lines[end_indexes[0] + 1:]
project_lines, sections = without_sections(before + [placeholder] + after)
write_sections(sections)
write(project_path, project_lines)
write(deterministic_path, before + block + after)
PY
}

# Sets agents_layout and original_agents_hash, or exits for malformed markers.
read_agents_layout() {
  split_status=0
  split_agents_file || split_status=$?
  case "$split_status" in
    0) agents_layout="managed" ;;
    3) agents_layout="legacy" ;;
    4)
      printf 'Human confirmation required: %s must contain exactly one "%s" line followed by one "%s" line; file preserved.\n' \
        "$AGENTS_FILE" "$MANAGED_BLOCK_START" "$MANAGED_BLOCK_END" >&2
      exit "$HUMAN_REQUIRED_EXIT_CODE"
      ;;
    *)
      echo "ERROR: could not read $AGENTS_FILE managed block; file preserved" >&2
      exit 1
      ;;
  esac

  original_agents_hash="$(sha256_file "$AGENTS_FILE")"
}

write_if_unchanged() {
  AGENT_READY_AGENTS_WRITE_LOCK="$GIT_DIRECTORY/$AGENTS_WRITE_LOCK_NAME" \
    python3 - "$AGENTS_FILE" "$MERGED_FILE" "$original_agents_hash" <<'PY'
import hashlib
import os
import stat
import sys
import tempfile
import time

# Windows Python has no fcntl: an exclusive msvcrt lock on AGENT_READY_AGENTS_WRITE_LOCK
# plays the role of the directory flock for cooperating writers.
try:
    import fcntl
except ImportError:
    fcntl = None
    import msvcrt

LOCK_RETRY_INTERVAL_SECONDS = 0.05


def acquire_windows_lock(lock_path):
    """Blocks until the cooperative lock file is held, like fcntl.LOCK_EX."""
    lock_file = open(lock_path, "a+b")
    while True:
        try:
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return lock_file
        except PermissionError:
            time.sleep(LOCK_RETRY_INTERVAL_SECONDS)


def release_windows_lock(lock_file):
    """Unlocks and closes a lock taken by acquire_windows_lock."""
    try:
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        lock_file.close()


target_path, replacement_path, expected_hash = sys.argv[1:]
open_flags = os.O_RDWR
if hasattr(os, "O_EXLOCK"):
    open_flags |= os.O_EXLOCK
if hasattr(os, "O_NOFOLLOW"):
    open_flags |= os.O_NOFOLLOW

target_file = None
directory_file = None
windows_lock_file = None
temporary_path = None
try:
    target_directory = os.path.dirname(os.path.abspath(target_path)) or "."
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    # Keep pathname checks and replacement under one lock.
    if fcntl is not None:
        directory_file = os.open(target_directory, directory_flags)
        fcntl.flock(directory_file, fcntl.LOCK_EX)
    else:
        windows_lock_file = acquire_windows_lock(os.environ["AGENT_READY_AGENTS_WRITE_LOCK"])

    target_file = os.fdopen(os.open(target_path, open_flags), "r+b")
    if fcntl is not None:
        fcntl.flock(target_file.fileno(), fcntl.LOCK_EX)
    target_file.seek(0)
    original_content = target_file.read()
    current_hash = hashlib.sha256(original_content).hexdigest()
    if current_hash != expected_hash:
        print(
            f"ERROR: {target_path} changed before descriptor write; merge cancelled",
            file=sys.stderr,
        )
        sys.exit(2)

    with open(replacement_path, "rb") as replacement_file:
        replacement_content = replacement_file.read()

    target_mode = stat.S_IMODE(os.fstat(target_file.fileno()).st_mode)
    temporary_descriptor, temporary_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(target_path)}.agent-ready-merge.",
        dir=target_directory,
    )
    with os.fdopen(temporary_descriptor, "wb") as temporary_file:
        if hasattr(os, "fchmod"):
            os.fchmod(temporary_file.fileno(), target_mode)
        temporary_file.write(replacement_content)
        temporary_file.flush()
        os.fsync(temporary_file.fileno())

    original_target_stat = os.fstat(target_file.fileno())
    current_target_stat = os.stat(target_path, follow_symlinks=False)
    if (
        current_target_stat.st_dev,
        current_target_stat.st_ino,
    ) != (
        original_target_stat.st_dev,
        original_target_stat.st_ino,
    ):
        print(
            f"ERROR: {target_path} changed during descriptor merge; merge cancelled",
            file=sys.stderr,
        )
        sys.exit(2)

    if fcntl is None:
        # Windows refuses to replace a file that is still open; the cooperative lock stays held.
        target_file.close()
        target_file = None
    os.replace(temporary_path, target_path)
    temporary_path = None

    if directory_file is not None:
        os.fsync(directory_file)
except SystemExit:
    raise
except Exception as error:
    print(f"ERROR: could not update {target_path}: {error}", file=sys.stderr)
    sys.exit(1)
finally:
    if directory_file is not None:
        os.close(directory_file)
    if windows_lock_file is not None:
        release_windows_lock(windows_lock_file)
    if temporary_path is not None:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
    if target_file is not None:
        target_file.close()
PY
}
