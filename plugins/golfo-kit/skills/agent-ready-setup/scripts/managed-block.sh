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
GIT_INFO_DIRECTORY=""
REVIEW_HASH_FILE=""
TEMPORARY_HASH_FILE=""
MERGE_LOCK_DIRECTORY=".agents/.agent-ready-instructions.lock"
# Where fcntl is missing (Windows), AGENTS.md writers coordinate through this file in the git dir.
AGENTS_WRITE_LOCK_NAME="agent-ready-agents-md.lock"
LOCK_ACQUIRED=0

# shellcheck disable=SC2329
cleanup() {
  if [[ -n "$TEMPORARY_DIRECTORY" && -d "$TEMPORARY_DIRECTORY" ]]; then
    rm -rf -- "$TEMPORARY_DIRECTORY"
  fi
  if [[ -n "$TEMPORARY_HASH_FILE" ]]; then
    rm -f -- "$TEMPORARY_HASH_FILE"
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
  TEMPLATE_FILE="$STACK_TEMPLATE_DIRECTORY/agents-template.md"
  RULES_DIRECTORY="$STACK_TEMPLATE_DIRECTORY/rules"
  COMMON_RULES_DIRECTORY="$SKILL_DIR/assets/common/rules"
  readonly PROJECT_RULES_DIRECTORY=".agents/rules"
  TEMPLATE_RENDERER="$SKILL_DIR/scripts/render-instruction-template.sh"
  CENTRALIZATION_TEMPLATE="$SKILL_DIR/assets/instruction-centralization.md"
  if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "ERROR: stack instruction template is missing: $TEMPLATE_FILE" >&2
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
  GIT_INFO_DIRECTORY="$GIT_DIRECTORY/info"
  if [[ -L "$GIT_INFO_DIRECTORY" || ( -e "$GIT_INFO_DIRECTORY" && ! -d "$GIT_INFO_DIRECTORY" ) ]]; then
    echo "ERROR: worktree Git info path is not a safe directory for merge metadata" >&2
    exit 1
  fi
}

prepare_managed_block_files() {
  TEMPORARY_DIRECTORY="$(mktemp -d "${TMPDIR:-/tmp}/agent-ready-merge.XXXXXX")"
  FULL_TEMPLATE_FILE="$TEMPORARY_DIRECTORY/template.md"
  MANAGED_BLOCK_FILE="$TEMPORARY_DIRECTORY/managed-block.md"
  PROJECT_CONTENT_FILE="$TEMPORARY_DIRECTORY/project-content.md"
  DETERMINISTIC_FILE="$TEMPORARY_DIRECTORY/deterministic.md"
  MERGED_FILE="$TEMPORARY_DIRECTORY/merged.md"
  SCHEMA_FILE="$TEMPORARY_DIRECTORY/result-schema.json"
  RESULT_FILE="$TEMPORARY_DIRECTORY/provider-result.json"
  REVIEW_HASH_FILE="$GIT_INFO_DIRECTORY/agent-ready-instructions-reviewed.sha256"
  readonly MANAGED_BLOCK_START='<!-- BEGIN AGENT-READY MANAGED -->'
  readonly MANAGED_BLOCK_END='<!-- END AGENT-READY MANAGED -->'
  readonly MANAGED_BLOCK_PLACEHOLDER='<!-- AGENT-READY MANAGED BLOCK -->'
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

review_hash=""
validate_review_hash_path() {
  if [[ -L "$REVIEW_HASH_FILE" || ( -e "$REVIEW_HASH_FILE" && ! -f "$REVIEW_HASH_FILE" ) ]]; then
    echo "ERROR: instruction review hash path is not a regular file" >&2
    return 1
  fi
}

write_review_hash() {
  if [[ -L "$GIT_INFO_DIRECTORY" || ( -e "$GIT_INFO_DIRECTORY" && ! -d "$GIT_INFO_DIRECTORY" ) ]]; then
    echo "ERROR: Git info path is not a safe directory for merge metadata" >&2
    return 1
  fi
  mkdir -p -- "$GIT_INFO_DIRECTORY"
  if ! validate_review_hash_path; then
    return 1
  fi

  TEMPORARY_HASH_FILE="$(mktemp "${REVIEW_HASH_FILE}.XXXXXX")"
  if ! printf '%s\n' "$review_hash" > "$TEMPORARY_HASH_FILE"; then
    return 1
  fi
  if ! mv -f -- "$TEMPORARY_HASH_FILE" "$REVIEW_HASH_FILE"; then
    return 1
  fi
  TEMPORARY_HASH_FILE=""
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

# The review is valid only for the exact AGENTS.md bytes and rule contents it
# saw; any change to either requires a new redundancy review.
compute_review_hash() {
  local agents_path="$1"
  local digest_input="$TEMPORARY_DIRECTORY/review-digest.txt"
  local relative_path
  local rule_file

  {
    sha256_file "$agents_path"
    while IFS=$'\t' read -r relative_path rule_file; do
      printf '%s %s\n' "$relative_path" "$(sha256_file "$rule_file")"
    done < "$RULE_FILES_LIST"
  } > "$digest_input"
  sha256_file "$digest_input"
}

# Takes the merge lock and validates the review hash path before any AGENTS.md write.
start_managed_block_update() {
  acquire_status=0
  acquire_merge_lock || acquire_status=$?
  if [[ "$acquire_status" -ne 0 ]]; then
    exit "$acquire_status"
  fi

  if ! validate_review_hash_path; then
    exit 1
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
    review_hash="$(compute_review_hash "$AGENTS_FILE")"
    write_review_hash
    printf 'Created %s from %s; no project instructions existed.\n' "$AGENTS_FILE" "$TEMPLATE_FILE"
    exit 0
  fi
}

# Splits AGENTS.md into project content (managed block replaced by a
# placeholder line) and a deterministic result with the rendered block copied
# verbatim. Exit 0: managed markers found; 3: legacy file without markers;
# 4: malformed markers.
split_agents_file() {
  python3 - "$AGENTS_FILE" "$MANAGED_BLOCK_FILE" "$PROJECT_CONTENT_FILE" "$DETERMINISTIC_FILE" \
    "$MANAGED_BLOCK_START" "$MANAGED_BLOCK_END" "$MANAGED_BLOCK_PLACEHOLDER" <<'PY'
import sys

(agents_path, block_path, project_path, deterministic_path,
 block_start, block_end, placeholder) = sys.argv[1:]

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
    write(project_path, lines)
    legacy_lines = list(lines)
    while legacy_lines and not legacy_lines[-1].strip():
        legacy_lines.pop()
    write(deterministic_path, legacy_lines + ([""] if legacy_lines else []) + block)
    sys.exit(3)

if len(start_indexes) != 1 or len(end_indexes) != 1 or start_indexes[0] > end_indexes[0]:
    sys.exit(4)

before = lines[:start_indexes[0]]
after = lines[end_indexes[0] + 1:]
write(project_path, before + [placeholder] + after)
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
