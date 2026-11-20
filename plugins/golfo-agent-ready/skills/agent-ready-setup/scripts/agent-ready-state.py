#!/usr/bin/env python3
"""Profiles, ownership and lockfile state for agent-ready-setup.

The entry point of the engine: it parses the subcommand and runs its handler. The engine itself lives in the
agent_ready_*.py modules beside it: profiles and their assets, the plan, finalize, status, check, the removal
and the background update.

``status`` and ``plan`` never write files, install tools or touch user configuration. Bash keeps doing the
actual writes (atomic replacements, Claude views, settings merges); it consults the protected list that
``plan`` emits so locally modified assets are preserved instead of overwritten.

Subcommands: resolve, manifest, detect, fetch-sources, plan, finalize, status,
check, background-update, update-report. Only fetch-sources and check use the
network; plan and status read what the cache already has.
"""

import argparse
import os
import sys

# Shared modules load from this script's own directory and leave no bytecode beside
# the skill source, which may be a read-only snapshot.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent_ready_removal as removal  # noqa: E402
from agent_ready_background import command_background_update, command_update_report  # noqa: E402
from agent_ready_check import command_check, command_pack_conflicts  # noqa: E402
from agent_ready_common import IncompleteEvaluationError, ProfileError, StateError  # noqa: E402
from agent_ready_content import content_dir_of  # noqa: E402
from agent_ready_layout import PROFILE_CATALOG_RELATIVE_PATH  # noqa: E402
from agent_ready_options import SUPPORTED_PROVIDERS, UPDATE_MODES  # noqa: E402
from agent_ready_profiles import load_profile_catalog  # noqa: E402
from agent_ready_state_commands import (  # noqa: E402
    command_config,
    command_config_reference,
    command_content_source,
    command_detect,
    command_fetch_sources,
    command_finalize,
    command_pack_scripts,
    command_plan,
    command_resolve,
    command_status,
    command_trust,
)
from agent_ready_state_contract import (  # noqa: E402
    CONFLICTS_FORMAT,
    CONFLICTS_JSON_FORMAT,
    CONFLICTS_MOMENT_EDIT,
    CONFLICTS_MOMENT_SESSION_START,
    CONFLICTS_STATUS,
    DRIFT_STATUS,
    INCOMPLETE_EVALUATION_STATUS,
    PROFILE_ERROR_STATUS,
    SOURCE_MODE_READ_ONLY,
    SOURCE_MODE_SYNC,
)

# The agent-ready CLI (agent_ready_cli_*.py) reaches these through engine(), which loads this script, so they
# stay importable from it.
import agent_ready_content as content_source  # noqa: E402,F401
from agent_ready_detection import detect_profiles, format_evidence_list  # noqa: E402,F401
from agent_ready_layout import review_cache_module  # noqa: E402,F401
from agent_ready_lockfile import LOCK_RELATIVE_PATH, read_lock  # noqa: E402,F401
from agent_ready_manifest import configuration_of  # noqa: E402,F401
from agent_ready_output import paint  # noqa: E402,F401
from agent_ready_plan import capability_suggestions, resolve_workspaces, workspace_suggestions  # noqa: E402,F401
from agent_ready_profiles import (  # noqa: E402,F401
    load_effective_catalog,
    profiles_for_stack,
    resolve_project_profiles,
    split_profile_names,
)
from agent_ready_selection import stack_from_initial_detection, stack_names_of  # noqa: E402,F401

# The commands that read the content: given the installed engine, they compose it first (main).
CONTENT_COMMANDS = ("resolve", "detect", "plan", "finalize", "pack-scripts", "status")


def plan_removal(project_root, skill_dir):
    """What `agent-ready remove` deletes, edits and keeps (agent_ready_removal.py), with this engine's catalog loader."""
    return removal.plan_removal(project_root, skill_dir, load_profile_catalog)


def remove_from_repository(project_root, skill_dir):
    """Remove agent-ready-setup from the repository (agent_ready_removal.py), with this engine's catalog loader."""
    return removal.remove_from_repository(project_root, skill_dir, load_profile_catalog)


def build_parser():
    """Command line parser for every subcommand."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser, needs_skill=True):
        subparser.add_argument("--project", default=".", help="project root (default: current directory)")
        if needs_skill:
            subparser.add_argument("--skill-dir", required=True, help="resolved agent-ready-setup source")

    def add_selection(subparser):
        group = subparser.add_mutually_exclusive_group()
        group.add_argument("--profiles", help="comma separated profiles, e.g. nextjs,browser")
        group.add_argument("--stack", help="legacy alias: the stack profile plus its defaults")
        subparser.add_argument("--source-state", help="commits adopted by fetch-sources during this apply")
        subparser.add_argument(
            "--source-mode", choices=(SOURCE_MODE_READ_ONLY, SOURCE_MODE_SYNC), default=SOURCE_MODE_READ_ONLY,
            help="sync refuses a profile source that differs from the lock",
        )

    resolve_parser = subparsers.add_parser("resolve", help="resolve and compose profiles")
    add_common(resolve_parser)
    add_selection(resolve_parser)
    resolve_parser.add_argument("--compose-dir", help="cache directory for composed stack trees")
    resolve_parser.set_defaults(handler=command_resolve)

    config_parser = subparsers.add_parser("config", help="effective configuration with the layer of each value")
    add_common(config_parser, needs_skill=False)
    config_parser.add_argument("--format", choices=("text", "json", "tsv"), default="text", help="tsv is for Bash")
    config_parser.add_argument("--offline", action="store_true", help="this run uses no network (updates.refresh: false)")
    config_parser.set_defaults(handler=command_config)

    reference_parser = subparsers.add_parser("config-reference", help="Markdown reference generated from the schemas")
    reference_parser.set_defaults(handler=command_config_reference, project=".")

    trust_parser = subparsers.add_parser("trust", help="approve this repository on this machine to loosen security")
    add_common(trust_parser, needs_skill=False)
    trust_parser.add_argument("--revoke", action="store_true", help="remove the approval")
    trust_parser.set_defaults(handler=command_trust)

    content_parser = subparsers.add_parser("content-source", help="skill directory with the content of this run composed with this engine")
    add_common(content_parser)
    content_parser.add_argument("--update", action="store_true", help="adopt the latest revision of its ref")
    content_parser.add_argument("--to", help="adopt this tag, branch or full commit")
    content_parser.add_argument("--offline", action="store_true", help="use no network: only revisions already in the cache")
    content_parser.add_argument("--from-lock", action="store_true", help="the revision of the lock, whatever the mode")
    content_parser.add_argument("--read-only", action="store_true",
                                  help="the run writes nothing: offline, a missing revision compares with the installed one")
    content_parser.set_defaults(handler=command_content_source)

    detect_parser = subparsers.add_parser("detect", help="read-only detection of stacks and capabilities")
    add_common(detect_parser)
    detect_parser.set_defaults(handler=command_detect)

    fetch_parser = subparsers.add_parser("fetch-sources", help="bring profile sources into the user cache")
    add_common(fetch_parser)
    fetch_parser.add_argument("--update-source", action="append", help="resolve this source's ref again; repeatable")
    fetch_parser.add_argument("--to", help="tag, branch or full commit the single --update-source adopts")
    fetch_parser.add_argument("--state-file", help="write the adopted commits here, for resolve and plan")
    fetch_parser.add_argument("--refresh", action="store_true", help="only update the cache and the last commit seen per ref")
    fetch_parser.add_argument("--from-lock", action="store_true", help="the commit of the lock for every source, whatever its mode")
    fetch_parser.add_argument("--offline", action="store_true", help="download nothing: a revision missing from the cache fails")
    fetch_parser.set_defaults(handler=command_fetch_sources)

    check_parser = subparsers.add_parser(
        "check",
        help=f"compare sources, lock and committed assets; exits {DRIFT_STATUS} when outdated, "
             f"{INCOMPLETE_EVALUATION_STATUS} when a source is unavailable and {PROFILE_ERROR_STATUS} on a configuration error",
    )
    add_common(check_parser)
    check_parser.add_argument("--offline", action="store_true", help="compare with the cache, without the network")
    check_parser.add_argument("--format", choices=("text", "json"), default="text", help="json is for pipelines")
    check_parser.set_defaults(handler=command_check)

    pack_conflicts_parser = subparsers.add_parser(
        "pack-conflicts",
        help=f"each profile of a pack against the golfo base and its requires; exits {CONFLICTS_STATUS} on a conflict")
    add_common(pack_conflicts_parser)
    pack_conflicts_parser.add_argument("--pack", required=True, help="root of the profile pack (its agent-ready-pack.json)")
    pack_conflicts_parser.add_argument("--offline", action="store_true", help="the AI reviews answer from the cache only")
    pack_conflicts_parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS,
                                       help="CLI of the AI reviews (default: the session's, as resolve-provider.sh infers it)")
    pack_conflicts_parser.add_argument("--format", choices=("text", "json"), default="text", help="json is for scripts")
    pack_conflicts_parser.set_defaults(handler=command_pack_conflicts)

    background_parser = subparsers.add_parser("background-update", help="run the sync hook and record its result")
    add_common(background_parser)
    background_parser.add_argument("--hook", required=True, help="sync hook to run")
    background_parser.add_argument("--provider", required=True, choices=SUPPORTED_PROVIDERS)
    background_parser.set_defaults(handler=command_background_update)

    report_parser = subparsers.add_parser("update-report", help="show the last background update once")
    add_common(report_parser, needs_skill=False)
    report_parser.set_defaults(handler=command_update_report)

    plan_parser = subparsers.add_parser("plan", help="read-only plan")
    add_common(plan_parser)
    add_selection(plan_parser)
    plan_parser.add_argument("--format", choices=("text", "json", "protected", CONFLICTS_FORMAT, CONFLICTS_JSON_FORMAT),
                             default="text", help="json is for scripts; protected lists the destinations an apply "
                             f"preserves; {CONFLICTS_FORMAT} prints only the conflicts and exits {CONFLICTS_STATUS} on one")
    plan_parser.add_argument("--save", help="also save the full plan as JSON to this path")
    plan_parser.add_argument("--provider", default="claude", choices=SUPPORTED_PROVIDERS)
    plan_parser.add_argument("--offline", action="store_true", help="this run uses no network (updates.refresh: false)")
    plan_parser.add_argument("--from-lock", action="store_true",
                             help="fail unless the plan reproduces the lock: selection, revisions, digests and sha256")
    plan_parser.set_defaults(handler=command_plan)

    finalize_parser = subparsers.add_parser("finalize", help="retire assets and write the lockfile")
    add_common(finalize_parser)
    finalize_parser.add_argument("--plan", required=True, help="plan saved before the projection")
    finalize_parser.add_argument("--updates", choices=UPDATE_MODES, help="manifest update mode")
    finalize_parser.set_defaults(handler=command_finalize)

    scripts_parser = subparsers.add_parser("pack-scripts", help="run the session-start scripts of the packs")
    add_common(scripts_parser)
    scripts_parser.add_argument("--previous-report", action="store_true",
                                help="show once what failed in the last session-start run")
    scripts_parser.set_defaults(handler=command_pack_scripts)

    status_parser = subparsers.add_parser("status", help="read-only status")
    add_common(status_parser, needs_skill=False)
    status_parser.add_argument("--skill-dir", help="resolved source, to detect pending updates")
    status_parser.add_argument("--brief", action="store_true", help="summary lines only")
    status_parser.add_argument("--conflicts-only", choices=(CONFLICTS_MOMENT_SESSION_START, CONFLICTS_MOMENT_EDIT),
                               help="only the structural conflicts, for the session or the edit hook "
                                    "(conflicts.sessionStart.enabled, conflicts.onEdit.enabled)")
    status_parser.add_argument("--changed", action="append", metavar="PATH",
                               help="with --conflicts-only edit: the edited paths, relative to the project; "
                                    "nothing is checked when none of them is an input of the checks")
    status_parser.add_argument("--check", action="store_true", help=f"exit {DRIFT_STATUS} when anything drifted")
    status_parser.add_argument("--format", choices=("text", "json"), default="text", help="json is for scripts")
    status_parser.set_defaults(handler=command_status)
    return parser


def use_utf8_output():
    """Emit UTF-8 with LF everywhere; Windows defaults to the locale code page and CRLF."""
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace", newline="\n")


def main(argv=None):
    """Entry point; prints a one-line error and a non-zero status on failure."""
    use_utf8_output()
    arguments = build_parser().parse_args(argv)
    arguments.project = os.path.abspath(arguments.project)
    if getattr(arguments, "skill_dir", None):
        arguments.skill_dir = os.path.abspath(arguments.skill_dir)
    try:
        # Run with the installed engine, which carries no content, a command that reads it composes the
        # content of the repository first, as bootstrap.sh and the hooks do (content-source).
        if (arguments.command in CONTENT_COMMANDS and getattr(arguments, "skill_dir", None)
                and not os.path.isfile(os.path.join(arguments.skill_dir, PROFILE_CATALOG_RELATIVE_PATH))):
            arguments.skill_dir = content_dir_of(arguments.project, arguments.skill_dir,
                                                 offline=bool(getattr(arguments, "offline", False)))
        return arguments.handler(arguments)
    except IncompleteEvaluationError as caught_error:
        sys.stderr.write(f"Evaluation incomplete: {caught_error}\n")
        return INCOMPLETE_EVALUATION_STATUS
    except ProfileError as caught_error:
        sys.stderr.write(f"ERROR: agent-ready profiles: {caught_error}\n")
        return PROFILE_ERROR_STATUS
    except StateError as caught_error:
        sys.stderr.write(f"ERROR: agent-ready state: {caught_error}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
