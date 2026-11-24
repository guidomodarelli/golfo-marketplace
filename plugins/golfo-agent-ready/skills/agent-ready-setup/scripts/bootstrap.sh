#!/bin/bash
# bootstrap.sh
# Projects Agent Ready templates into Claude, shared-agent, and Codex trees.
# Profiles (assets/profiles.json) select which templates apply. Managed assets
# follow the ownership contract of agent-ready-state.py: a file that still
# matches its lockfile base is updated, a locally modified one is preserved and
# reported, and assets no longer published are retired only when unmodified.
# Without a lockfile (first apply) managed assets are overwritten once.
# Instruction files are normalized so AGENTS.md is canonical and every CLAUDE.md
# is the root proxy template. Writes .agents/agent-ready.json (manifest) and
# .agents/agent-ready.lock.json (lockfile).
#
# Usage:
#   bash bootstrap.sh --skill-dir <path> [--profiles <a,b> | --stack <stack>]
#     [--provider <claude|codex>] [--updates <pinned|auto>] [--update-source <name>]... [--update-to <ref>]
#     [--plan | --status | --config] [--offline] [--json]
#
# Without --profiles or --stack, the profiles come from .agents/agent-ready.json
# and, when the repository has no manifest yet, from the initial detection of
# agent-ready-state.py, which fails if the signals do not determine one stack.
# --plan and --status never write to the repository or install tools. They refresh the
# marketplace snapshot and the profile sources in the user cache to tell whether
# everything is current; --offline and AGENT_READY_SETUP_REVIEW_MODE=1 keep them off the
# network. --config prints the effective configuration and the layer of each value, without
# the network. Reports (plan, status, config) go to stdout, and --json prints them as JSON;
# progress and errors go to stderr. --plan --update-source <name> shows what adopting that
# source would change: it only downloads into the user cache. Every run validates the configuration first and fails before writing when a
# layer has an unknown key or an invalid value. CI pipelines use "agent-ready-state.py check",
# which needs no provider.
# An apply follows the sources in auto; --update-source also moves a pinned one, golfo-agent-ready
# included, and --update-to picks the tag, branch or commit of that single source.
# --from-lock applies exactly the lock: its selection and the revision of every source, and
# fails before writing, naming the source, when a digest or a sha256 does not match.
# Instruction normalization alone runs through normalize-instructions.sh.

set -euo pipefail

# Hermes exports these to stop Git Bash from translating paths, but this script
# hands POSIX paths to native Windows Python, which needs that translation.
unset MSYS_NO_PATHCONV MSYS2_ARG_CONV_EXCL

# Diagnostics go to stderr. File descriptor 3 keeps the original stdout for the reports of
# --plan, --status and --config, so "bootstrap.sh --plan > plan.txt" holds only the plan.
exec 3>&1 1>&2

# The libraries of bootstrap.sh load from this script's own directory, so they all stay on its version:
# the shared normalization, the skill source (bootstrap-skill-source.sh) and the asset projection
# (bootstrap-asset-projection.sh). They all load here, before the marketplace upgrade, which can replace
# this directory with a newer version while this script still runs. Their function names do not repeat
# those of asset-sync-common.sh, which loads later from the resolved source.
BOOTSTRAP_SCRIPTS_DIRECTORY="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly BOOTSTRAP_SCRIPTS_DIRECTORY
# shellcheck source=instruction-normalization.sh
source "$BOOTSTRAP_SCRIPTS_DIRECTORY/instruction-normalization.sh"
# shellcheck source=bootstrap-skill-source.sh
source "$BOOTSTRAP_SCRIPTS_DIRECTORY/bootstrap-skill-source.sh"
# shellcheck source=bootstrap-asset-projection.sh
source "$BOOTSTRAP_SCRIPTS_DIRECTORY/bootstrap-asset-projection.sh"

# shellcheck disable=SC2034
readonly MARKETPLACE_NAME="golfo-marketplace"
# Same value as MISSING_PREREQUISITE_EXIT_CODE in setup-browser-tools.py.
readonly BROWSER_MISSING_PREREQUISITE_EXIT_CODE=4
readonly SKILL_NAME="agent-ready-setup"
# Codex resolves its user home from CODEX_HOME; config, snapshot and cache follow it.
readonly CODEX_HOME_DIRECTORY="${CODEX_HOME:-$HOME/.codex}"

STACK=""
PROFILES=""
REQUESTED_SKILL_DIR=""
UPDATE_MODE=""
UPDATE_SOURCES=()
UPDATE_TO=""
FROM_LOCK=0
OFFLINE=0
JSON_OUTPUT=0
# --conflicts: a plan that prints only the conflicts between the profiles (agent-ready conflicts).
CONFLICTS_ONLY=0
# apply (default), plan, status or config.
RUN_MODE="apply"
SKILL_DIR=""
PROVIDER="${AGENT_READY_SETUP_ACTIVE_PROVIDER:-}"
MARKETPLACE_ALREADY_UPGRADED="${AGENT_READY_SETUP_MARKETPLACE_UPGRADED:-0}"
readonly SYNC_LOCK_DIRECTORY=".agents/.agent-ready-assets.lock"
# shellcheck disable=SC2034
readonly SYNC_LOCK_OWNER_FILE="$SYNC_LOCK_DIRECTORY/owner"
# shellcheck disable=SC2034
SYNC_LOCK_ACQUIRED=0
# shellcheck disable=SC2034
SYNC_LOCK_INHERITED=0
SYNC_LOCK_ENABLED=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack)
      [[ $# -ge 2 ]] || { echo "ERROR: --stack requires a value" >&2; exit 1; }
      STACK="$2"
      shift 2
      ;;
    --skill-dir)
      [[ $# -ge 2 ]] || { echo "ERROR: --skill-dir requires a value" >&2; exit 1; }
      REQUESTED_SKILL_DIR="$2"
      shift 2
      ;;
    --provider)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "ERROR: --provider requires claude or codex" >&2; exit 1; }
      PROVIDER="$2"
      shift 2
      ;;
    --profiles)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "ERROR: --profiles requires a comma separated list" >&2; exit 1; }
      PROFILES="$2"
      shift 2
      ;;
    --updates)
      [[ $# -ge 2 && ( "${2:-}" == pinned || "${2:-}" == auto ) ]] || {
        echo "ERROR: --updates requires pinned or auto" >&2
        exit 1
      }
      UPDATE_MODE="$2"
      shift 2
      ;;
    --update-to)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "ERROR: --update-to requires a tag, branch or commit" >&2; exit 1; }
      UPDATE_TO="$2"
      shift 2
      ;;
    --from-lock)
      FROM_LOCK=1
      shift
      ;;
    --update-source)
      [[ $# -ge 2 && -n "${2:-}" ]] || { echo "ERROR: --update-source requires a source name" >&2; exit 1; }
      UPDATE_SOURCES+=("$2")
      shift 2
      ;;
    --plan|--status|--config)
      [[ "$RUN_MODE" == apply ]] || { echo "ERROR: --plan, --status, --config and --conflicts are mutually exclusive" >&2; exit 1; }
      RUN_MODE="${1#--}"
      shift
      ;;
    --conflicts)
      [[ "$RUN_MODE" == apply ]] || { echo "ERROR: --plan, --status, --config and --conflicts are mutually exclusive" >&2; exit 1; }
      RUN_MODE=plan
      CONFLICTS_ONLY=1
      shift
      ;;
    --offline)
      OFFLINE=1
      shift
      ;;
    --json)
      JSON_OUTPUT=1
      shift
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$RUN_MODE" != apply && "$RUN_MODE" != plan && ${#UPDATE_SOURCES[@]} -gt 0 ]]; then
  echo "ERROR: --update-source only works on an apply or a --plan" >&2
  exit 1
fi
if [[ "$FROM_LOCK" -eq 1 && ( ${#UPDATE_SOURCES[@]} -gt 0 || -n "$STACK$PROFILES$UPDATE_MODE" ) ]]; then
  echo "ERROR: --from-lock applies the selection and revisions of the lock; drop --update-source, --stack, --profiles and --updates" >&2
  exit 1
fi
if [[ "$FROM_LOCK" -eq 1 && "$RUN_MODE" != apply && "$RUN_MODE" != plan ]]; then
  echo "ERROR: --from-lock only works with an apply or --plan" >&2
  exit 1
fi
if [[ -n "$UPDATE_TO" && ${#UPDATE_SOURCES[@]} -ne 1 ]]; then
  echo "ERROR: --update-to needs exactly one --update-source" >&2
  exit 1
fi
if [[ "$OFFLINE" -eq 1 && ${#UPDATE_SOURCES[@]} -gt 0 ]]; then
  echo "ERROR: --update-source needs the network to resolve the source; drop --offline" >&2
  exit 1
fi
if [[ "$RUN_MODE" == apply && "$JSON_OUTPUT" -eq 1 ]]; then
  echo "ERROR: --json only works with --plan, --status or --config" >&2
  exit 1
fi
if [[ "$RUN_MODE" == apply && "$OFFLINE" -eq 1 ]]; then
  echo "ERROR: --offline only works with --plan, --status or --config" >&2
  exit 1
fi
if [[ "${AGENT_READY_SETUP_REVIEW_MODE:-0}" == 1 ]]; then
  OFFLINE=1
fi

case "$MARKETPLACE_ALREADY_UPGRADED" in
  0|1) ;;
  *)
    echo "ERROR: AGENT_READY_SETUP_MARKETPLACE_UPGRADED must be 0 or 1" >&2
    exit 1
    ;;
esac

if [[ -z "$REQUESTED_SKILL_DIR" ]]; then
  echo "ERROR: --skill-dir is required" >&2
  exit 1
fi

if [[ -n "$STACK" && -n "$PROFILES" ]]; then
  echo "ERROR: --stack and --profiles are mutually exclusive" >&2
  exit 1
fi

# Which stacks exist is the profile catalog's to say (a pack can add its own); here only the name.
if [[ -n "$STACK" && ! "$STACK" =~ ^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)?$ ]]; then
  echo "ERROR: Unsupported stack '$STACK'. A stack is a name such as node or acme/cobol." >&2
  exit 1
fi

if [[ ! -d "$REQUESTED_SKILL_DIR" ]]; then
  echo "ERROR: --skill-dir must point to an existing directory: $REQUESTED_SKILL_DIR" >&2
  exit 1
fi

SKILL_DIR="$REQUESTED_SKILL_DIR"
if [[ -z "$PROVIDER" ]]; then
  provider_resolver="$SKILL_DIR/scripts/resolve-provider.sh"
  if [[ ! -f "$provider_resolver" ]]; then
    echo "ERROR: provider is not explicit and resolver is missing: $provider_resolver" >&2
    exit 1
  fi
  PROVIDER="$(bash "$provider_resolver" --skill-dir "$SKILL_DIR")"
fi

case "$PROVIDER" in
  claude|codex) ;;
  *)
    echo "ERROR: Unsupported provider '$PROVIDER'. Expected claude or codex." >&2
    exit 1
    ;;
esac

if [[ "$SKILL_DIR" != /* ]]; then
  if ! SKILL_DIR="$(CDPATH='' cd -- "$SKILL_DIR" && pwd)"; then
    echo "ERROR: could not resolve --skill-dir: $SKILL_DIR" >&2
    exit 1
  fi
fi

CREATED=()
UPDATED=()
SKIPPED=()
MIGRATED=()
RENAMED=()
REMOVED=()
CONFLICTS=()
CLEANUP_CONFLICTS=()
# shellcheck disable=SC2034 # Read by validate_provider_roots in instruction-normalization.sh.
PROVIDER_ROOT_CONFLICTS=()

record_conflict() {
  CONFLICTS+=("$1")
}

if ! command -v git >/dev/null 2>&1 || [[ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" != true ]]; then
  echo "ERROR: bootstrap must run inside a Git worktree" >&2
  exit 1
fi

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd -- "$PROJECT_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required to resolve profiles and the lockfile" >&2
  exit 1
fi
OFFLINE_ARGUMENTS=()
[[ "$OFFLINE" -eq 1 ]] && OFFLINE_ARGUMENTS=(--offline)
FORMAT_ARGUMENTS=()
[[ "$JSON_OUTPUT" -eq 1 ]] && FORMAT_ARGUMENTS=(--format json)
if [[ "$CONFLICTS_ONLY" -eq 1 ]]; then
  FORMAT_ARGUMENTS=(--format conflicts)
  [[ "$JSON_OUTPUT" -eq 1 ]] && FORMAT_ARGUMENTS=(--format conflicts-json)
fi
if [[ "$RUN_MODE" == config ]]; then
  python3 "$SKILL_DIR/scripts/agent-ready-state.py" config --project . ${OFFLINE_ARGUMENTS[@]+"${OFFLINE_ARGUMENTS[@]}"} \
    ${FORMAT_ARGUMENTS[@]+"${FORMAT_ARGUMENTS[@]}"} >&3
  exit $?
fi

# Every layer is validated here, so an unknown key or an invalid value stops before the upgrade.
# Plan and status report ignored values themselves; an apply reports them from here.
configuration_messages="$(mktemp "${TMPDIR:-/tmp}/agent-ready-config.XXXXXX")"
if ! CONFIGURATION="$(python3 "$SKILL_DIR/scripts/agent-ready-state.py" config --project . --format tsv \
  ${OFFLINE_ARGUMENTS[@]+"${OFFLINE_ARGUMENTS[@]}"} 2>"$configuration_messages")"; then
  cat -- "$configuration_messages" >&2
  rm -f -- "$configuration_messages"
  echo "ERROR: the Agent Ready configuration is not valid; nothing was written" >&2
  exit 2
fi
[[ "$RUN_MODE" != apply ]] || cat -- "$configuration_messages" >&2
rm -f -- "$configuration_messages"
CONFIGURED_PROFILES=""
PROFILES_SELECTED=false
TOOLS_ENABLED=true
FROM_LOCK_CONFIGURED=false
while IFS=$'\t' read -r configuration_key configuration_value; do
  configuration_value="${configuration_value%$'\r'}"
  case "$configuration_key" in
    # updates.refresh false keeps plan and status off the network, like --offline. An explicit
    # update, its preview included, always resolves the revision it asks for.
    updates.refresh) [[ "$configuration_value" == false && ${#UPDATE_SOURCES[@]} -eq 0 ]] && OFFLINE=1 ;;
    tools.enabled) TOOLS_ENABLED="$configuration_value" ;;
    profiles) CONFIGURED_PROFILES="$configuration_value" ;;
    # A pinned empty selection ([]: the core only) is a selection; profiles alone prints it as empty.
    profiles_selected) PROFILES_SELECTED="$configuration_value" ;;
    updates.fromLock) FROM_LOCK_CONFIGURED="$configuration_value" ;;
  esac
done <<< "$CONFIGURATION"
# updates.fromLock: an apply or a plan that neither updates a source nor changes the selection
# reproduces the lock, like --from-lock, once there is one.
if [[ "$FROM_LOCK" -eq 0 && "$FROM_LOCK_CONFIGURED" == true && ( "$RUN_MODE" == apply || "$RUN_MODE" == plan ) &&
      ${#UPDATE_SOURCES[@]} -eq 0 && -z "$STACK$PROFILES$UPDATE_MODE" && -f .agents/agent-ready.lock.json ]]; then
  FROM_LOCK=1
  echo "updates.fromLock: this run reproduces the lock. Adopt a new version with agent-ready update <source>, or change the selection with --profiles or --stack." >&2
fi
OFFLINE_ARGUMENTS=()
[[ "$OFFLINE" -eq 1 ]] && OFFLINE_ARGUMENTS=(--offline)

validate_provider_roots

# True when the engine runs from a checkout of the marketplace, outside every agent home. That engine
# is used as it is (resolve_skill_dir) and the content comes from sources.golfo, so refreshing the
# marketplace of the user changes nothing this run reads: it only replaces a clone of the machine.
# AGENT_READY_SETUP_UPGRADE_FROM_CHECKOUT=1 refreshes it anyway.
runs_from_checkout() {
  local agent_home

  [[ "${AGENT_READY_SETUP_UPGRADE_FROM_CHECKOUT:-0}" == 1 ]] && return 1
  for agent_home in "$HOME/.claude" "$CODEX_HOME_DIRECTORY" "${CLAUDE_PLUGIN_ROOT:-}" "${HERMES_HOME:-}" "$HOME/.hermes"; do
    [[ -n "$agent_home" ]] || continue
    if [[ "$REQUESTED_SKILL_DIR" == "$agent_home" || "$REQUESTED_SKILL_DIR" == "$agent_home/"* ]]; then
      return 1
    fi
  done
  return 0
}

# Each provider refreshes its own marketplace snapshot through its CLI.
upgrade_marketplace() {
  local -a upgrade_command

  if runs_from_checkout; then
    echo "[marketplace-bootstrap] El motor corre desde un checkout ($REQUESTED_SKILL_DIR); se omite el upgrade del marketplace del usuario."
    return 0
  fi

  if [[ "$PROVIDER" == "codex" ]] && is_codex_local_marketplace; then
    echo "[marketplace-bootstrap] $MARKETPLACE_NAME es un marketplace Codex local; se omite el upgrade y se usa su source configurado."
    return 0
  fi

  if [[ "$PROVIDER" == "claude" ]]; then
    upgrade_command=(claude plugin marketplace update "$MARKETPLACE_NAME")
  else
    upgrade_command=(codex plugin marketplace upgrade "$MARKETPLACE_NAME")
  fi

  if ! command -v "$PROVIDER" >/dev/null 2>&1; then
    printf 'ERROR: se requiere la CLI de %s para hacer upgrade de %s antes del bootstrap.\n' "$PROVIDER" "$MARKETPLACE_NAME" >&2
    return 1
  fi

  echo "[marketplace-bootstrap] Haciendo upgrade de $MARKETPLACE_NAME para $PROVIDER..."
  if ! "${upgrade_command[@]}"; then
    printf 'ERROR: falló el upgrade del marketplace para %s/%s; no se modificó ningún asset del proyecto.\n' \
      "$MARKETPLACE_NAME" "$PROVIDER" >&2
    return 1
  fi
  echo "[marketplace-bootstrap] Upgrade del marketplace completado."
}

if [[ "$RUN_MODE" != apply && "$OFFLINE" -eq 1 ]]; then
  echo "[marketplace-bootstrap] Offline $RUN_MODE: the marketplace upgrade is skipped."
elif [[ "$RUN_MODE" != apply && "$MARKETPLACE_ALREADY_UPGRADED" -eq 0 ]]; then
  # Refreshing only tells whether something is pending: without it, the cache still answers.
  if ! upgrade_marketplace; then
    echo "WARNING: comparing with the marketplace snapshot already on this machine" >&2
  fi
elif [[ "$RUN_MODE" != apply ]]; then
  echo "[marketplace-bootstrap] El caller ya completó el upgrade del marketplace."
elif [[ "$MARKETPLACE_ALREADY_UPGRADED" -eq 0 ]]; then
  if ! upgrade_marketplace; then
    exit 1
  fi
else
  echo "[marketplace-bootstrap] El caller ya completó el upgrade del marketplace."
fi

if ! SKILL_DIR="$(resolve_skill_dir)"; then
  echo "ERROR: no se pudo resolver el source actualizado de $SKILL_NAME después del upgrade del marketplace" >&2
  exit 1
fi
describe_skill_source "$SKILL_DIR"
STATE_SCRIPT="$SKILL_DIR/scripts/agent-ready-state.py"

# The content (rules, skills, catalog, templates) is a source of its own, sources.golfo: a content pack
# at a revision, composed with this installed engine (agent_ready_content.py). Everything below reads
# the composed directory, so no step mixes two revisions of the content. A repository without a
# selection that detection cannot settle stops at the resolution, before writing.
CONTENT_SOURCE="golfo"
PACK_UPDATE_SOURCES=()
content_arguments=(content-source --project . --skill-dir "$SKILL_DIR")
for update_source in ${UPDATE_SOURCES[@]+"${UPDATE_SOURCES[@]}"}; do
  if [[ "$update_source" == "$CONTENT_SOURCE" ]]; then
    content_arguments+=(--update)
    [[ -n "$UPDATE_TO" ]] && content_arguments+=(--to "$UPDATE_TO")
  else
    PACK_UPDATE_SOURCES+=("$update_source")
  fi
done
# Plan and status stay off the network when asked to, with the revisions this machine already has.
# An apply always gets the revision it writes, downloading it if missing (updates.refresh only
# concerns plan and status), and review mode never uses the network: without it, it stops.
FROM_LOCK_ARGUMENTS=()
if [[ "$FROM_LOCK" -eq 1 ]]; then
  if [[ ! -f .agents/agent-ready.lock.json ]]; then
    echo "ERROR: --from-lock needs .agents/agent-ready.lock.json; this repository has no lockfile yet" >&2
    exit 1
  fi
  FROM_LOCK_ARGUMENTS=(--from-lock)
  content_arguments+=(--from-lock)
fi
if [[ "$RUN_MODE" != apply ]]; then
  content_arguments+=(--read-only)
  [[ "$OFFLINE" -eq 1 ]] && content_arguments+=(--offline)
elif [[ "${AGENT_READY_SETUP_REVIEW_MODE:-0}" == 1 ]]; then
  content_arguments+=(--offline)
fi
if ! CONTENT_SKILL_DIR="$(python3 "$STATE_SCRIPT" "${content_arguments[@]}")" || [[ -z "$CONTENT_SKILL_DIR" ]]; then
  echo "ERROR: could not prepare the golfo content; no asset was changed" >&2
  exit 1
fi
echo "[marketplace-bootstrap] Using the golfo content of $(python3 -c 'import json,sys; m=json.load(open(sys.argv[1], encoding="utf-8")); print(m["origin"] + " " + (m["commit"] or "")[:12])' "$CONTENT_SKILL_DIR/.agent-ready-content.json") with this engine."
# The installed engine is the source this run reports; everything below reads the composed content.
ENGINE_SKILL_DIR="$SKILL_DIR"
SKILL_DIR="$CONTENT_SKILL_DIR"
STATE_SCRIPT="$SKILL_DIR/scripts/agent-ready-state.py"
PROFILE_SELECTION=()
if [[ -n "$PROFILES" ]]; then
  PROFILE_SELECTION=(--profiles "$PROFILES")
elif [[ -n "$STACK" ]]; then
  PROFILE_SELECTION=(--stack "$STACK")
fi

if [[ "$RUN_MODE" != apply && "$OFFLINE" -eq 0 && "$FROM_LOCK" -eq 0 ]]; then
  python3 "$STATE_SCRIPT" fetch-sources --project . --skill-dir "$SKILL_DIR" --refresh || true
fi

if [[ "$RUN_MODE" == status ]]; then
  python3 "$STATE_SCRIPT" status --project . --skill-dir "$SKILL_DIR" ${FORMAT_ARGUMENTS[@]+"${FORMAT_ARGUMENTS[@]}"} >&3
  exit $?
fi

# An apply records the commits it adopted, so every later step reads the same revisions,
# and fails here before writing anything.
SOURCE_STATE_ARGUMENTS=()
TEMPORARY_PATHS=()
remove_temporary_paths() {
  [[ ${#TEMPORARY_PATHS[@]} -eq 0 ]] || rm -rf -- "${TEMPORARY_PATHS[@]}"
}
trap remove_temporary_paths EXIT
# A plan with --update-source resolves those sources the same way, into the user cache only.
if [[ "$RUN_MODE" == apply || ${#UPDATE_SOURCES[@]} -gt 0 || "$FROM_LOCK" -eq 1 ]]; then
  SOURCE_STATE_FILE="$(mktemp "${TMPDIR:-/tmp}/agent-ready-sources.XXXXXX")"
  TEMPORARY_PATHS+=("$SOURCE_STATE_FILE")
  fetch_arguments=(fetch-sources --project . --skill-dir "$SKILL_DIR" --state-file "$SOURCE_STATE_FILE"
    ${FROM_LOCK_ARGUMENTS[@]+"${FROM_LOCK_ARGUMENTS[@]}"})
  # A preview of the lock with updates.refresh off (or --offline) compares with the cache only.
  [[ "$FROM_LOCK" -eq 1 && "$RUN_MODE" != apply && "$OFFLINE" -eq 1 ]] && fetch_arguments+=(--offline)
  for update_source in ${PACK_UPDATE_SOURCES[@]+"${PACK_UPDATE_SOURCES[@]}"}; do
    fetch_arguments+=(--update-source "$update_source")
  done
  if [[ -n "$UPDATE_TO" && ${#PACK_UPDATE_SOURCES[@]} -eq 1 ]]; then
    fetch_arguments+=(--to "$UPDATE_TO")
  fi
  if ! python3 "$STATE_SCRIPT" "${fetch_arguments[@]}"; then
    echo "ERROR: could not prepare the profile sources; no asset was changed" >&2
    exit 1
  fi
  SOURCE_STATE_ARGUMENTS=(--source-state "$SOURCE_STATE_FILE")
fi

# A plan writes nothing outside a temporary directory, not even the composed tree.
COMPOSE_DIRECTORY="$(agent_ready_compose_directory)"
if [[ "$RUN_MODE" == plan ]]; then
  COMPOSE_DIRECTORY="$(mktemp -d "${TMPDIR:-/tmp}/agent-ready-compose.XXXXXX")"
  TEMPORARY_PATHS+=("$COMPOSE_DIRECTORY")
fi

# Resolves profiles once; every later step reads the same stack tree.
RESOLVED_PROFILES=""
RESOLVED_TOOLS=""
REQUESTED_PROFILES=""
SELECTION_ORIGIN=""
resolve_errors="$(mktemp "${TMPDIR:-/tmp}/agent-ready-resolve.XXXXXX")"
TEMPORARY_PATHS+=("$resolve_errors")
resolution_status=0
resolution="$(python3 "$STATE_SCRIPT" resolve --project . --skill-dir "$SKILL_DIR" \
  ${PROFILE_SELECTION[@]+"${PROFILE_SELECTION[@]}"} ${SOURCE_STATE_ARGUMENTS[@]+"${SOURCE_STATE_ARGUMENTS[@]}"} \
  --compose-dir "$COMPOSE_DIRECTORY" 2>"$resolve_errors")" || resolution_status=$?
if [[ "$RUN_MODE" == plan && "$resolution_status" -eq 5 ]]; then
  # A source is missing: the plan command reports the incomplete evaluation itself.
  python3 "$STATE_SCRIPT" plan --project . --skill-dir "$SKILL_DIR" --provider "$PROVIDER" \
    ${PROFILE_SELECTION[@]+"${PROFILE_SELECTION[@]}"} ${SOURCE_STATE_ARGUMENTS[@]+"${SOURCE_STATE_ARGUMENTS[@]}"} \
    ${OFFLINE_ARGUMENTS[@]+"${OFFLINE_ARGUMENTS[@]}"} ${FORMAT_ARGUMENTS[@]+"${FORMAT_ARGUMENTS[@]}"} >&3 || exit $?
  exit 0
fi
cat -- "$resolve_errors" >&2
# A configuration error (a selection or a workspace that cannot be) keeps its status 2, as the config check above.
if [[ "$resolution_status" -eq 2 ]]; then
  exit 2
elif [[ "$resolution_status" -ne 0 ]]; then
  exit 1
fi
while IFS=$'\t' read -r resolution_key resolution_value; do
  resolution_value="${resolution_value%$'\r'}"
  case "$resolution_key" in
    profiles) RESOLVED_PROFILES="$resolution_value" ;;
    requested) REQUESTED_PROFILES="$resolution_value" ;;
    selection) SELECTION_ORIGIN="$resolution_value" ;;
    primary) STACK="$resolution_value" ;;
    stack_dir) export AGENT_READY_SETUP_STACK_DIR="$resolution_value" ;;
    tools) RESOLVED_TOOLS="$resolution_value" ;;
  esac
done <<< "$resolution"

if [[ "$RUN_MODE" == plan ]]; then
  python3 "$STATE_SCRIPT" plan --project . --skill-dir "$SKILL_DIR" --provider "$PROVIDER" \
    ${PROFILE_SELECTION[@]+"${PROFILE_SELECTION[@]}"} ${SOURCE_STATE_ARGUMENTS[@]+"${SOURCE_STATE_ARGUMENTS[@]}"} \
    ${OFFLINE_ARGUMENTS[@]+"${OFFLINE_ARGUMENTS[@]}"} ${FORMAT_ARGUMENTS[@]+"${FORMAT_ARGUMENTS[@]}"} \
    ${FROM_LOCK_ARGUMENTS[@]+"${FROM_LOCK_ARGUMENTS[@]}"} >&3
  exit $?
fi

# The apply projects what this resolution detected, even if the signals change meanwhile.
if [[ "$SELECTION_ORIGIN" == detection ]]; then
  PROFILE_SELECTION=(--profiles "$REQUESTED_PROFILES")
fi

validate_skill_source
# shellcheck disable=SC2034
ASSET_SYNC_SKILL_DIR="$SKILL_DIR"
# Serializes sync writers so concurrent invocations cannot replace each other's
# files. Upgrade runs before this lock to keep failed upgrades write-free.
# shellcheck disable=SC1091
source "$SKILL_DIR/scripts/asset-sync-common.sh"
# shellcheck disable=SC2034
SYNC_LOCK_ENABLED=1

if ! acquire_sync_lock; then
  exit 0
fi

# The pre-apply plan decides ownership: protected destinations are preserved by
# sync_file, and finalize retires assets and writes the lockfile from it.
PLAN_FILE="$(mktemp "${TMPDIR:-/tmp}/agent-ready-plan.XXXXXX")"
TEMPORARY_PATHS+=("$PLAN_FILE")
trap 'remove_temporary_paths; release_sync_lock' EXIT
if ! protected_destinations="$(python3 "$STATE_SCRIPT" plan --project . --skill-dir "$SKILL_DIR" \
  --provider "$PROVIDER" --format protected --save "$PLAN_FILE" ${PROFILE_SELECTION[@]+"${PROFILE_SELECTION[@]}"} \
  ${SOURCE_STATE_ARGUMENTS[@]+"${SOURCE_STATE_ARGUMENTS[@]}"} ${FROM_LOCK_ARGUMENTS[@]+"${FROM_LOCK_ARGUMENTS[@]}"})"; then
  echo "ERROR: could not compute the Agent Ready plan; no asset was changed" >&2
  exit 1
fi
load_protected_destinations "$protected_destinations"

# The centralization rule is part of the managed AGENTS.md block, which
# merge-instructions.sh copies verbatim from the template on every sync.
normalize_instructions

project_asset_tree "$COMMON_SRC"
project_asset_tree "$SRC"
project_rule_claude_views "$TEMPLATE_RENDERER" "$SRC/rules" "$COMMON_SRC/rules"
project_skill_claude_views "$COMMON_SRC" "$SRC"
prune_hard_link_views
install_hard_link_git_hook "$SKILL_DIR/assets/git-hooks/post-index-change"

cleanup_stale_claude_links

# Codex-specific plugin assets use Codex's supported names while retaining the
# same MCP definitions and shared hook scripts.
if [[ -f "$SRC/mcp.json" ]]; then
  sync_file "$SRC/mcp.json" "$CODEX_DIR/.mcp.json"
fi
sync_codex_hooks "$CODEX_ASSETS/hooks.json"

finalize_arguments=(finalize --project . --skill-dir "$SKILL_DIR" --plan "$PLAN_FILE")
[[ -n "$UPDATE_MODE" ]] && finalize_arguments+=(--updates "$UPDATE_MODE")
FINALIZE_REPORT=""
if ! FINALIZE_REPORT="$(python3 "$STATE_SCRIPT" "${finalize_arguments[@]}")"; then
  CONFLICTS+=("could not write .agents/agent-ready.lock.json; the next apply treats this run as unlocked")
fi

browser_setup_status=0
if [[ "$TOOLS_ENABLED" != true ]]; then
  printf 'Browser installation skipped by tools.enabled: false\n'
elif [[ ",$RESOLVED_TOOLS," == *",browser,"* ]]; then
  python3 "$SKILL_DIR/scripts/setup-browser-tools.py" --project "$PWD" || browser_setup_status=$?
  # A machine without Node.js 24+ and npm is a warning, not a failed apply: setup-browser-tools.py
  # already said what is missing, and the next apply or session installs the tools once it exists.
  if [[ "$browser_setup_status" -eq "$BROWSER_MISSING_PREREQUISITE_EXIT_CODE" ]]; then
    browser_setup_status=0
  fi
else
  printf 'Browser installation skipped: no selected profile needs browser tools\n'
fi

# Print report
printf '\nStack: %s\n' "${STACK:-none}"
printf 'Profiles: %s\n' "$RESOLVED_PROFILES"
printf 'Providers: Claude Code + Codex-compatible shared tree\n'
# Hard-link views are committed as whole files: every rule and skill of .agents/ reaches the repository
# twice. Symlinks are a few bytes each, so the report says how to get them.
if [[ -s "$(hard_link_views_manifest)" ]]; then
  printf 'Vistas de .claude: copias por hard link, porque esta máquina no crea symlinks; en Git duplican cada rule y skill de .agents/. Con symlinks (en Windows, el modo desarrollador y git config core.symlinks true) cada vista pesa unos bytes.\n'
fi
# Stable line the agent reads to run follow-up scripts from the resolved source: the engine, which
# composes the content of the lock again (resolve_content_skill_directory in stack-directory.sh).
printf 'Resolved %s source: %s\n' "$SKILL_NAME" "$ENGINE_SKILL_DIR"
# The stack this apply composed, at the revisions it adopted: merge-instructions.sh renders from it
# (AGENT_READY_SETUP_STACK_DIR) instead of resolving the sources again.
[[ -n "${AGENT_READY_SETUP_STACK_DIR:-}" ]] && printf 'Resolved stack directory: %s\n' "$AGENT_READY_SETUP_STACK_DIR"
printf '\n'

if [[ ${#CREATED[@]} -gt 0 ]]; then
  echo "Created:"
  for file in "${CREATED[@]}"; do printf '  + %s\n' "$file"; done
fi

if [[ ${#UPDATED[@]} -gt 0 ]]; then
  echo ""
  echo "Updated from templates:"
  for file in "${UPDATED[@]}"; do printf '  ↻ %s\n' "$file"; done
fi

if [[ ${#RENAMED[@]} -gt 0 ]]; then
  echo ""
  echo "Renamed instruction files:"
  for file in "${RENAMED[@]}"; do printf '  ↪ %s\n' "$file"; done
fi

if [[ ${#MIGRATED[@]} -gt 0 ]]; then
  echo ""
  echo "Normalized instructions:"
  for file in "${MIGRATED[@]}"; do printf '  ↔ %s\n' "$file"; done
fi

if [[ ${#SKIPPED[@]} -gt 0 ]]; then
  echo ""
  echo "Already existed (skipped):"
  for file in "${SKIPPED[@]}"; do printf '  ~ %s\n' "$file"; done
fi

if [[ ${#REMOVED[@]} -gt 0 ]]; then
  echo ""
  echo "Removed stale managed assets:"
  for file in "${REMOVED[@]}"; do printf '  - %s\n' "$file"; done
fi

if [[ ${#CLEANUP_CONFLICTS[@]} -gt 0 ]]; then
  echo ""
  echo "Managed asset cleanup conflicts (preserved):" >&2
  for conflict in "${CLEANUP_CONFLICTS[@]}"; do printf '  ! %s\n' "$conflict" >&2; done
fi

if [[ ${#CONFLICTS[@]} -gt 0 ]]; then
  echo ""
  echo "Instruction conflicts or differences (agent resolution may be required):" >&2
  for conflict in "${CONFLICTS[@]}"; do printf '  ! %s\n' "$conflict" >&2; done
fi

if [[ -n "$FINALIZE_REPORT" ]]; then
  echo ""
  printf '%s\n' "$FINALIZE_REPORT"
fi

echo ""
echo "Done."
exit "$browser_setup_status"
