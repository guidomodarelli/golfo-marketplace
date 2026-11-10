#!/bin/sh
# Managed by agent-ready-setup (ci.provider): an apply rewrites it. Every CI provider calls this
# script; it runs the agent-ready check with its exit statuses: 0 up to date or skipped
# (ci.enabled: false), 4 outdated, 5 a profile source is not available, 2 a configuration error.
# ci.mode: warn reports the same and exits with 0 when outdated or a source is not available.
#
# Private packs: AGENT_READY_GIT_TOKEN holds a read token (a secret of the CI, never a file) and
# AGENT_READY_GIT_URL the URL prefix of the packs, e.g. https://github.com/acme/. Git takes the
# credential from the environment (Git 2.31+), so the token is never written anywhere.
set -u

# ci.enabled: false in the manifest turns the check off without reaching the network, as
# agent-ready check does: the clone below must not be able to fail a check that is off.
root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if python3 -c 'import json, sys; sys.exit(0 if (json.load(open(sys.argv[1], encoding="utf-8")).get("ci") or {}).get("enabled") is False else 1)'     "$root/.agents/agent-ready.json" 2>/dev/null; then
  echo "Agent Ready check skipped: ci.enabled is false in .agents/agent-ready.json"
  exit 0
fi

marketplace="${AGENT_READY_MARKETPLACE_URL:-https://github.com/guidomodarelli/golfo-marketplace}"
checkout="$(mktemp -d)" || exit 1
trap 'rm -rf "$checkout"' EXIT

# Outside the repository: inside it, the CLAUDE.md files of the skill would count as project files.
git clone --quiet --depth 1 "$marketplace" "$checkout/golfo-marketplace" || exit 1

if [ -n "${AGENT_READY_GIT_TOKEN:-}" ] && [ -n "${AGENT_READY_GIT_URL:-}" ]; then
  scheme="${AGENT_READY_GIT_URL%%://*}"
  address="${AGENT_READY_GIT_URL#*://}"
  GIT_CONFIG_COUNT=1
  GIT_CONFIG_KEY_0="url.${scheme}://${AGENT_READY_GIT_USER:-oauth2}:${AGENT_READY_GIT_TOKEN}@${address}.insteadOf"
  GIT_CONFIG_VALUE_0="$AGENT_READY_GIT_URL"
  export GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0
fi

python3 "$checkout/golfo-marketplace/plugins/golfo-kit/skills/agent-ready-setup/scripts/agent-ready" check "$@"
