#!/bin/bash
# PostToolUse hook for Claude file inputs and Codex apply_patch commands.
# Reviews rules and skills with the CLI of the provider that edited them:
# `claude --print` for Claude Code and `codex exec` (read-only sandbox) for
# Codex. A Codex-only machine never needs the Claude binary; when the provider
# CLI is missing, the check is skipped with a warning instead of failing.
set -euo pipefail

readonly CONSISTENCY_PROMPT='Read all .md files in rules/ and all SKILL.md files in skills/*/. \
Check for contradictions or inconsistencies (conflicting mocking strategies, directory conventions, naming rules, etc). \
Output ONLY the conflicts found as a bullet list, or a single line '\''No contradictions found.'\'' if all is consistent. Be concise.'

hook_payload="$(cat)"

# AGENT_READY_HARNESS_CHECK_PROVIDER overrides the provider inferred from the
# payload: Codex edits arrive as apply_patch, Claude edits as Write or Edit.
provider="${AGENT_READY_HARNESS_CHECK_PROVIDER:-}"
if [[ -z "$provider" ]]; then
  provider="$(printf '%s' "$hook_payload" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError:
    payload = {}
tool_name = payload.get("tool_name") if isinstance(payload, dict) else None
print("codex" if tool_name == "apply_patch" else "claude")
')"
fi
case "$provider" in
  claude|codex) ;;
  *)
    printf '[harness-check] unsupported provider %s; expected claude or codex\n' "$provider" >&2
    exit 1
    ;;
esac

# Extract only roots from file paths or patch headers, never execute patch text.
harness_roots=$(printf '%s' "$hook_payload" | python3 -c '
import json
import re
import sys

try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)
if not isinstance(payload, dict):
    sys.exit(0)
tool_input = payload.get("tool_input")
if not isinstance(tool_input, dict):
    sys.exit(0)
paths = []
file_path = tool_input.get("file_path")
if isinstance(file_path, str):
    paths.append(file_path)
command = tool_input.get("command")
if payload.get("tool_name") == "apply_patch" and isinstance(command, str):
    for line in command.splitlines():
        header = re.match(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", line)
        if header:
            paths.append(header.group(1))
roots = set()
for path in paths:
    if re.search(r"(^|/)\.claude/(rules/|skills/|CLAUDE\.md$)", path):
        roots.add(".claude")
    if re.search(r"(^|/)\.agents/(rules/|skills/)", path):
        roots.add(".agents")
for root in sorted(roots):
    print(root)
')
[[ -n "$harness_roots" ]] || exit 0

if ! command -v "$provider" >/dev/null 2>&1; then
  printf '[harness-check] %s CLI is not available; consistency check skipped.\n' "$provider" >&2
  exit 0
fi

project_root=$(git rev-parse --show-toplevel)
while IFS= read -r harness_root; do
  # Windows Python ends lines with CRLF.
  harness_root="${harness_root%$'\r'}"
  printf '[harness-check] %s modified — running consistency check with %s...\n' "$harness_root" "$provider"
  (
    cd -- "$project_root/$harness_root"
    if [[ "$provider" == codex ]]; then
      codex exec --sandbox read-only --skip-git-repo-check "$CONSISTENCY_PROMPT"
    else
      claude --print "$CONSISTENCY_PROMPT"
    fi
  )
done <<< "$harness_roots"
