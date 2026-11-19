#!/bin/bash
# learning-hook.sh
# The hooks of learning (references/learning.md of agent-ready-setup): on every prompt of the user it
# touches the episode of the session, at the start of a session (also after a compaction) it prints
# what the project learned lately, and at the end of a chat or before a compaction it hands the
# episode to the review in the background. The provider passes its payload as JSON on stdin; only its
# session_id and transcript_path are read. It prints nothing while the learning profile is not in use,
# and never fails the prompt or the session: any problem ends it silently.
#
# Usage: learning-hook.sh --provider claude|codex --event prompt|session-start|session-end|pre-compact

set -uo pipefail

# Hermes exports these to stop Git Bash from translating paths, but this hook
# hands POSIX paths to native Windows Python, which needs that translation.
unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL

provider=""
event=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider)
      [[ $# -ge 2 && ( "$2" == claude || "$2" == codex ) ]] || { printf 'ERROR: --provider requires claude or codex\n' >&2; exit 2; }
      provider="$2"
      shift 2
      ;;
    --event)
      [[ $# -ge 2 && ( "$2" == prompt || "$2" == session-start || "$2" == session-end || "$2" == pre-compact ) ]] \
        || { printf 'ERROR: --event requires prompt, session-start, session-end or pre-compact\n' >&2; exit 2; }
      event="$2"
      shift 2
      ;;
    -h|--help)
      printf 'Usage: %s --provider claude|codex --event prompt|session-start|session-end|pre-compact\n' "${0##*/}"
      exit 0
      ;;
    *)
      printf 'ERROR: unsupported argument: %s\n' "$1" >&2
      exit 2
      ;;
  esac
done
if [[ -z "$provider" || -z "$event" ]]; then
  printf 'ERROR: --provider and --event are required\n' >&2
  exit 2
fi

payload="$(cat)"
command -v python3 >/dev/null 2>&1 || exit 0
project_root="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd -- "$project_root" || exit 0
# Without the lock no apply ran here, so the learning profile cannot be in use.
[[ -f .agents/agent-ready.lock.json ]] || exit 0

# shellcheck source=agent-ready-skill-source.sh
source "$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/agent-ready-skill-source.sh"
skill_dir="$(resolve_skill_dir 2>/dev/null)" || exit 0
cli="$skill_dir/scripts/agent-ready"

if [[ "$event" == session-start ]]; then
  python3 "$cli" learn summary --project . 2>/dev/null || true
  exit 0
fi
# The session and the transcript, one per line; a payload that is not JSON gives two empty lines.
fields="$(printf '%s' "$payload" | python3 -c 'import json, sys
try:
    payload = json.load(sys.stdin)
except ValueError:
    payload = {}
payload = payload if isinstance(payload, dict) else {}
print(payload.get("session_id") or "")
print(payload.get("transcript_path") or "")' 2>/dev/null | tr -d '\r')"
session_id="$(printf '%s\n' "$fields" | sed -n 1p)"
transcript="$(printf '%s\n' "$fields" | sed -n 2p)"
[[ -n "$session_id" ]] || exit 0
case "$event" in
  prompt) mode=--touch ;;
  session-end) mode=--end ;;
  pre-compact) mode=--review-now ;;
esac
arguments=(learn episode --project . --session "$session_id" "$mode" --provider "$provider")
[[ -n "$transcript" ]] && arguments+=(--transcript "$transcript")
python3 "$cli" "${arguments[@]}" 2>/dev/null || true
exit 0
