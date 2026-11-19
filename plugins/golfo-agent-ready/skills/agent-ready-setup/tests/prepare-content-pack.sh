#!/usr/bin/env bash
# Print the checkout of the official content pack at the tag of content-pack.ref, cloning it once.
#
# The suites project this content (the engine carries none): a shared checkout that no test changes,
# read through AGENT_READY_SETUP_CONTENT_DIR, so the tests themselves use no network. The tag only
# moves on purpose: a new release of the pack does not change what the tests see.
#
# AGENT_READY_TEST_CONTENT_PACK picks the directory; by default it lives under node_modules/.cache of
# the repository, which Git ignores. Exit codes: 0 the checkout is ready, 1 it could not be cloned.
set -euo pipefail

readonly CONTENT_PACK_URL="https://github.com/guidomodarelli/golfo-agent-profiles"
readonly CONTENT_PACK_CATALOG="agent-ready-pack.json"
# The branch the engine follows by default (sources.golfo.ref): here it points at the pinned tag.
readonly DEFAULT_CONTENT_REF="main"

tests_directory="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repository_root="$(CDPATH='' cd -- "$tests_directory/../../../../.." && pwd -P)"
ref="$(tr -d '[:space:]' < "$tests_directory/content-pack.ref")"
checkout="${AGENT_READY_TEST_CONTENT_PACK:-$repository_root/node_modules/.cache/agent-ready-content-pack/$ref}"

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

if [[ ! -f "$checkout/$CONTENT_PACK_CATALOG" ]]; then
  mkdir -p "$(dirname "$checkout")"
  staging="$(mktemp -d "$(dirname "$checkout")/.clone.XXXXXX")"
  trap 'rm -rf "$staging"' EXIT
  # Without the configuration of the caller: the url.insteadOf of a test would point the clone at itself.
  : > "$staging/gitconfig"
  if ! GIT_CONFIG_GLOBAL="$staging/gitconfig" GIT_CONFIG_NOSYSTEM=1 \
    git -c advice.detachedHead=false clone --quiet --branch "$ref" "$CONTENT_PACK_URL" "$staging/pack"; then
    printf 'ERROR: prepare-content-pack: could not clone %s at %s into %s\n' "$CONTENT_PACK_URL" "$ref" "$checkout" >&2
    exit 1
  fi
  git -C "$staging/pack" checkout --quiet -B "$DEFAULT_CONTENT_REF"
  # Another suite running in parallel may have cloned it first: its checkout is the same. The test
  # scripts and the CI prepare it before bats starts, so this only races on a bare `bats` run.
  if [[ ! -e "$checkout" ]]; then
    mv "$staging/pack" "$checkout"
  fi
fi
native_path "$checkout"
