#!/bin/bash
# PostToolUse hook for Claude file inputs and Codex apply_patch commands.
# Reviews the rules and skills that an edit changed against every other rule and
# skill of the same root, with the CLI of the provider that edited them (claude for
# Claude Code, codex exec with a read-only sandbox for Codex). Each pair of files is
# reviewed once and cached until one of them changes, so editing a rule never
# reviews the rest again. A Codex-only machine never needs the Claude binary; when
# the provider CLI is missing, the check is skipped with a warning instead of failing.
set -euo pipefail

# The review and its cache load from this hook's own directory; -B leaves no bytecode in the repository.
# Native Windows Python needs Windows paths: Git Bash prints them with the pwd -W builtin, which
# works whatever the PATH holds; elsewhere pwd -W fails and the POSIX path is the right one.
native_directory() {
  (CDPATH='' cd -- "$1" && { pwd -W 2>/dev/null || pwd -P; })
}
hook_source="${BASH_SOURCE[0]}"
[[ "$hook_source" == */* ]] || hook_source="./$hook_source"
hook_directory="$(native_directory "${hook_source%/*}")"
hook_bash="$(native_directory "${BASH%/*}")/${BASH##*/}"
exec python3 -B "$hook_directory/harness-review.py" --bash "$hook_bash"
