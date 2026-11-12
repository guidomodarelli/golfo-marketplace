#!/bin/bash
# apply-managed-block.sh
# Applies the verbatim AGENTS.md managed block from the stack template without
# invoking any provider, so the current session sees new rule references
# immediately. Creates AGENTS.md when it does not exist. A legacy AGENTS.md
# without managed markers is left for merge-instructions.sh, whose provider
# review migrates it. SessionStart sync runs this before launching that review
# in the background.
#
# Usage:
#   bash apply-managed-block.sh --stack <react|nextjs|nextjs-app-router|node|java|go|android> --skill-dir <path>

set -euo pipefail

# Shared managed-block logic loads from this script's own directory so both stay on one version.
# shellcheck source=managed-block.sh
source "$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/managed-block.sh"
trap cleanup EXIT

parse_managed_block_arguments "$@"

validate_managed_block_inputs
prepare_managed_block_files
load_managed_block_rules
start_managed_block_update
create_agents_from_template_if_missing
read_agents_layout

if [[ "$agents_layout" == "legacy" ]]; then
  echo "$AGENTS_FILE has no managed markers yet; the background instruction review migrates it."
  exit 0
fi

if cmp -s "$AGENTS_FILE" "$DETERMINISTIC_FILE"; then
  echo "$AGENTS_FILE managed block is current."
  exit 0
fi

cp -- "$DETERMINISTIC_FILE" "$MERGED_FILE"
write_status=0
write_if_unchanged || write_status=$?
if [[ "$write_status" -ne 0 ]]; then
  echo "ERROR: $AGENTS_FILE changed or could not be written; managed block was not applied" >&2
  exit "$write_status"
fi
printf 'Updated %s: managed block copied from template; the redundancy review runs in the background.\n' "$AGENTS_FILE"
