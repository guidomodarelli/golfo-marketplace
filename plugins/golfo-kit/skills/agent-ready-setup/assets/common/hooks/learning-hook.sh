#!/bin/bash
# learning-hook.sh
# The hooks of learning (references/learning.md of agent-ready-setup): on every prompt of the user it
# touches the episode of the session, and at the start of a session (also after a compaction) it
# prints what the project learned lately. The provider passes its payload as JSON on stdin; only its
# session_id is read. It prints nothing while the learning profile is not in use, and never fails the
# prompt or the session: any problem ends it silently.
#
# Usage: learning-hook.sh --provider claude|codex --event prompt|session-start

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
      [[ $# -ge 2 && ( "$2" == prompt || "$2" == session-start ) ]] || { printf 'ERROR: --event requires prompt or session-start\n' >&2; exit 2; }
      event="$2"
      shift 2
      ;;
    -h|--help)
      printf 'Usage: %s --provider claude|codex --event prompt|session-start\n' "${0##*/}"
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
session_id="$(printf '%s' "$payload" | python3 -c 'import json, sys
try:
    print(json.load(sys.stdin).get("session_id") or "")
except ValueError:
    print("")' 2>/dev/null | tr -d '\r')"
[[ -n "$session_id" ]] || exit 0
python3 "$cli" learn episode --project . --session "$session_id" --touch 2>/dev/null || true
exit 0
