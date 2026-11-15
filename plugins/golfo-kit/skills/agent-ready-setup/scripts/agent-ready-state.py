#!/usr/bin/env python3
"""Profiles, ownership and lockfile state for agent-ready-setup.

This module owns the declarative side of Agent Ready projection:

* resolves composable profiles from ``assets/profiles.json`` and composes their
  assets into a single stack tree that the Bash projection consumes;
* maps every template file to its managed destination in the project;
* compares the applied base (lockfile), the local file and the new template
  content to decide create, update, conflict or retire for each destination;
* writes the repository manifest and lockfile after an apply.

``status`` and ``plan`` never write files, install tools or touch user
configuration. Bash keeps doing the actual writes (atomic replacements, Claude
views, settings merges); it consults the protected list that ``plan`` emits so
locally modified assets are preserved instead of overwritten.

Subcommands: resolve, manifest, detect, fetch-sources, plan, finalize, status,
check, background-update, update-report. Only fetch-sources and check use the
network; plan and status read what the cache already has.
"""

import argparse
import os
import shutil
import sys
import tempfile
import types

# Shared modules load from this script's own directory and leave no bytecode beside
# the skill source, which may be a read-only snapshot.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_ready_common import (  # noqa: E402
    LOCAL_NOT_A_FILE,
    IncompleteEvaluationError,
    ProfileError,
    StateError,
    bash_executable,
    read_json_file,
    run_quiet,
    serialize_json,
    write_text_atomically,
    write_text_if_changed,
)
from agent_ready_lockfile import (  # noqa: E402
    LOCK_RELATIVE_PATH,
    read_lock,
)
from agent_ready_background import command_background_update, command_update_report  # noqa: E402
import agent_ready_removal as removal  # noqa: E402
from agent_ready_manifest import (  # noqa: E402
    configuration_of,
    declared_sources,
    print_configuration_values,
    print_ignored_configuration,
    read_manifest,
)
from agent_ready_merged_files import claude_proxy_drift, merged_file_changes  # noqa: E402
from agent_ready_plan import (  # noqa: E402
    added_dependencies,
    capability_suggestions,
    composed_workspace_assets,
    compute_plan,
    compute_status,
    describe_detected_stack,
    nested_instruction_files,
    print_conflict_warnings,
    print_detection_matches,
    print_incomplete_plan,
    print_plan,
    resolve_workspaces,
    semantic_conflicts,
    workspace_suggestions,
)
from agent_ready_profiles import (  # noqa: E402
    load_effective_catalog,
    load_profile_catalog,
    locked_sources_of,
    primary_stack,
    profiles_for_stack,
    rejecting_ci_profiles,
    resolve_project_profiles,
    resolved_tools,
    split_profile_names,
)
from agent_ready_structural import (  # noqa: E402
    competing_skills_report,
    structural_conflict_lines,
    structural_conflicts,
)
from agent_ready_desired_assets import (  # noqa: E402
    compose_stack_directory,
    profile_digests,
    workspace_profile_origins,
)
from agent_ready_layout import (  # noqa: E402
    ENGINE_SKILL_DIRECTORY,
    MANIFEST_RELATIVE_PATH,
    PROFILE_CATALOG_RELATIVE_PATH,
    review_cache_module,
)
from agent_ready_source_identity import (  # noqa: E402
    enforce_lock_reproduction,
    enforce_sync_policy,
    keep_locked_entries_of_unselected_sources,
    validate_pack_destinations,
)
from agent_ready_actions import (  # noqa: E402
    ACTION_CONFLICT,
    ACTION_RETIRE_CONFLICT,
    ACTION_UNCHANGED,
)
from agent_ready_finalize import (  # noqa: E402
    finalize,
    print_finalize_report,
)
from agent_ready_review_findings import project_owned_instructions, review_summary  # noqa: E402
from agent_ready_status import (  # noqa: E402
    conflict_inputs_changed,
    describe_source,
    pack_tools_report,
    print_status,
    status_has_drift,
)
from agent_ready_output import paint, write_line  # noqa: E402
from agent_ready_config import (  # noqa: E402
    LAYER_USER,
    describe_layer,
    format_value,
    load_schema,
    normalized_project_path,
    read_layer_file,
    render_reference,
    set_sparse,
    user_config_path,
    validate_layer,
)
from agent_ready_options import (  # noqa: E402
    CI_ENABLED_KEY,
    CI_MODE_KEY,
    CI_CONFLICTS_STRUCTURAL_KEY,
    CI_CONFLICTS_SEMANTIC_KEY,
    CI_CONFLICTS_OFF,
    CI_CONFLICTS_FAIL,
    CI_WARN,
    DETECTION_ENABLED_KEY,
    COMPETING_SKILLS_ENABLED_KEY,
    EDIT_CONFLICTS_ENABLED_KEY,
    SESSION_START_CONFLICTS_ENABLED_KEY,
    PROFILES_KEY,
    CONFLICTS_ENABLED_KEY,
    REVIEWS_ENABLED_KEY,
    SUPPORTED_PROVIDERS,
    UPDATE_MODES,
    UPDATES_AUTO,
    TRUSTED_PROJECTS_KEY,
)
from agent_ready_detection import (  # noqa: E402
    STACK_PROFILE_KIND,
    STATUS_AMBIGUOUS,
    STATUS_NONE,
    STATUS_RESOLVED,
    detect_profiles,
    format_evidence_list,
)
import agent_ready_conflicts as conflicts_review  # noqa: E402
import agent_ready_skill_overlap as skill_overlap  # noqa: E402
import agent_ready_pack_scripts as pack_scripts  # noqa: E402
import agent_ready_pack_tools as pack_tools  # noqa: E402
import agent_ready_content as content_source  # noqa: E402
from agent_ready_packs import (  # noqa: E402
    KEBAB_CASE_NAME,
    PACK_CATALOG_FILE_NAME,
    download_declared_sources,
    effective_update_mode,
    is_pack_profile,
    refresh_declared_sources,
)

# Infers the provider of a run from the environment and the installation path.
PROVIDER_RESOLVER_RELATIVE_PATH = "scripts/resolve-provider.sh"
PLUGIN_NAME = "golfo-kit"
# Results of `check` and their exit statuses: the stable contract of a CI pipeline.
CHECK_UP_TO_DATE = "up-to-date"
CHECK_OUTDATED = "outdated"
CHECK_SOURCE_UNAVAILABLE = "source-unavailable"
CHECK_CONFIG_ERROR = "config-error"
CHECK_SKIPPED = "skipped"
CHECK_CONFLICTS = "conflicts"
# Exit status when the selected profiles cannot be resolved or composed.
PROFILE_ERROR_STATUS = 2
# Exit status of `detect` when the signals do not determine one primary stack.
DETECTION_UNRESOLVED_STATUS = 3
# Exit status of `status --check` when the checkout or the source drifted from the lock.
DRIFT_STATUS = 4
# Exit status when a profile source the selection needs is not available or not adopted.
INCOMPLETE_EVALUATION_STATUS = 5
# agent-ready conflicts and agent-ready check found conflicts between the profiles.
CONFLICTS_STATUS = 6
# content-source: the content pack of the repository is not on this machine yet (sync-marketplace.sh).
CONTENT_PENDING_STATUS = 7
# The commands that read the content: given the installed engine, they compose it first (main).
CONTENT_COMMANDS = ("resolve", "detect", "plan", "finalize", "pack-scripts", "status")
# The moments a hook asks status for the conflicts alone, and the prefix of each line it prints.
CONFLICTS_MOMENT_SESSION_START = "session-start"
CONFLICTS_MOMENT_EDIT = "edit"
CONFLICTS_HOOK_PREFIX = "[conflicts]"
# plan formats that print only the conflicts, for agent-ready conflicts.
CONFLICTS_FORMAT = "conflicts"
CONFLICTS_JSON_FORMAT = "conflicts-json"
CHECK_EXIT_STATUSES = {
    CHECK_UP_TO_DATE: 0,
    CHECK_SKIPPED: 0,
    CHECK_CONFIG_ERROR: PROFILE_ERROR_STATUS,
    CHECK_OUTDATED: DRIFT_STATUS,
    CHECK_SOURCE_UNAVAILABLE: INCOMPLETE_EVALUATION_STATUS,
    CHECK_CONFLICTS: CONFLICTS_STATUS,
}

# How a command treats profile sources. Read-only evaluates what is there and reports
# differences. Sync (SessionStart with automatic updates) also refuses to adopt them.
SOURCE_MODE_READ_ONLY = "read-only"
SOURCE_MODE_SYNC = "sync"

# Where the effective selection came from, by precedence.
SELECTION_PROFILES_FLAG = "--profiles"
SELECTION_STACK_FLAG = "--stack"
SELECTION_MANIFEST = "manifest"
SELECTION_DETECTION = "detection"


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def read_source_state(arguments):
    """Commits an apply just adopted, or None outside an apply."""
    state_path = getattr(arguments, "source_state", None)
    return read_json_file(state_path, "profile source state") if state_path else None


def stack_names_of(catalog):
    """Names of the stack profiles of a catalog, sorted."""
    return sorted(name for name, profile in catalog["profiles"].items() if profile.get("kind") == STACK_PROFILE_KIND)


def stack_from_initial_detection(catalog, detection):
    """The stack a repository without a selection starts with, None without any stack signal.

    Without signals the repository gets the core only (no stack is optional); several stacks
    that match without a priority still need an explicit selection.
    """
    if detection["status"] == STATUS_RESOLVED:
        return detection["primaryStack"]
    if detection["status"] == STATUS_NONE:
        return None
    selection_hint = f"select one with --stack {'|'.join(stack_names_of(catalog))} or --profiles <a,b>"
    if detection["status"] == STATUS_AMBIGUOUS:
        matches = ", ".join(f"{name} ({format_evidence_list(detection['stacks'][name])})" for name in detection["candidates"])
        raise ProfileError(f"could not detect project stack: several stacks match and none has priority: {matches}; {selection_hint}")
    raise ProfileError(f"could not detect project stack: no signal matched; {selection_hint}")


def resolve_selection(arguments, catalog):
    """Requested profiles and their origin: flags, then the manifest, then initial detection."""
    if getattr(arguments, "profiles", None):
        return rejecting_ci_profiles(catalog, split_profile_names(arguments.profiles)), SELECTION_PROFILES_FLAG
    if getattr(arguments, "stack", None):
        return profiles_for_stack(catalog, arguments.stack), SELECTION_STACK_FLAG
    configuration = configuration_of(arguments.project)
    # An empty list in the manifest is a selection too: the core only, which detection never changes.
    if configuration.value(PROFILES_KEY) is not None:
        return rejecting_ci_profiles(catalog, configuration.value(PROFILES_KEY)), SELECTION_MANIFEST
    if not configuration.value(DETECTION_ENABLED_KEY):
        raise ProfileError(f"detection is off ({DETECTION_ENABLED_KEY}: false): select the profiles with --stack or --profiles")
    detection = detect_profiles(catalog["profiles"], arguments.project)
    stack = stack_from_initial_detection(catalog, detection)
    return (profiles_for_stack(catalog, stack) if stack else []), SELECTION_DETECTION


def command_resolve(arguments):
    """Print the resolution as key<TAB>value lines for Bash."""
    # A manifest that cannot be read stops the apply even when flags pick the
    # profiles: it may declare a pinned repository that must not be written.
    read_manifest(arguments.project)
    catalog = load_effective_catalog(arguments.project, arguments.skill_dir, read_source_state(arguments))
    requested, selection = resolve_selection(arguments, catalog)
    resolved = resolve_project_profiles(catalog, requested, arguments.project)
    workspaces = resolve_workspaces(arguments.project, catalog, requested, resolved)
    workspace_profiles, workspace_rules, shared_texts, assets = composed_workspace_assets(
        arguments.skill_dir, catalog, resolved, workspaces)
    selected = list(resolved) + workspace_profiles
    validate_pack_destinations(arguments.project, assets)
    if arguments.source_mode == SOURCE_MODE_SYNC:
        enforce_sync_policy(arguments.project, arguments.skill_dir, catalog, resolved,
                            profile_digests(arguments.skill_dir, catalog, selected), selected,
                            workspace_profile_origins(arguments.skill_dir, catalog, workspace_profiles))
    stack_dir = compose_stack_directory(arguments.skill_dir, catalog, resolved, arguments.compose_dir, workspace_rules,
                                        workspace_profiles, shared_texts)
    if selection == SELECTION_DETECTION:
        detection = detect_profiles(catalog["profiles"], arguments.project)
        primary = detection["primaryStack"]
        if primary:
            write_line(f"Detected stack: {primary} ({format_evidence_list(detection['stacks'][primary])})", sys.stderr)
        else:
            write_line("No stack signal: the core only (select a stack or capabilities with --profiles)", sys.stderr)
    write_line(f"profiles\t{','.join(resolved)}")
    write_line(f"requested\t{','.join(requested)}")
    write_line(f"selection\t{selection}")
    write_line(f"primary\t{primary_stack(catalog, resolved) or ''}")
    write_line(f"stack_dir\t{stack_dir}")
    write_line(f"tools\t{','.join(resolved_tools(catalog, selected))}")
    return 0


def automatic_sources(configuration):
    """Names of the sources whose effective update mode is auto: the content, then the declared packs."""
    names = [content_source.CONTENT_SOURCE_NAME] if content_source.update_mode(configuration) == UPDATES_AUTO else []
    return names + [declaration["name"] for declaration in declared_sources(configuration.project_root)
                    if effective_update_mode(configuration, declaration) == UPDATES_AUTO]


def print_configuration_text(configuration):
    """Layers, every effective value with its origin, then what was ignored."""
    stream = sys.stdout
    write_line(paint("Agent Ready configuration (effective value and the layer it comes from)", "heading", stream))
    for layer in configuration.layers:
        if layer["path"]:
            presence = "present" if layer["present"] else "not present"
            write_line(f"  {layer['name']}: {layer['path']} ({presence})")
    approval = "approved" if configuration.project_approved else "not approved"
    write_line(f"  this repository on this machine: {approval} to loosen security from its manifest")
    print_configuration_values(configuration)
    print_ignored_configuration(configuration, stream)


def command_config(arguments):
    """Print the effective configuration: text explains it, json and tsv are for scripts.

    tsv prints one ``key<TAB>value`` line per option (booleans as true/false, lists joined
    with commas) and the derived line ``auto_sources``: the content and the declared sources in auto.
    """
    configuration = configuration_of(arguments.project, arguments.offline)
    if arguments.format == "json":
        write_line(serialize_json(configuration_report(configuration)).rstrip("\n"))
        return 0
    if arguments.format == "tsv":
        print_ignored_configuration(configuration, sys.stderr)
        for key in sorted(configuration.schema.leaves):
            write_line(f"{key}\t{format_value(configuration.value(key))}")
        write_line(f"auto_sources\t{','.join(automatic_sources(configuration))}")
        # profiles prints [] and an unset value alike: Bash tells a pinned empty selection from none here.
        write_line(f"profiles_selected\t{'true' if configuration.value(PROFILES_KEY) is not None else 'false'}")
        return 0
    print_configuration_text(configuration)
    return 0


def command_config_reference(arguments):
    """Print the Markdown reference of every option, generated from the schemas."""
    write_line(render_reference(load_schema()).rstrip("\n"))
    return 0


def command_trust(arguments):
    """Approve (or revoke) this repository on this machine, in the user configuration."""
    project_root = find_repository_root(arguments.project)
    path = user_config_path(os.environ)
    schema = load_schema()
    label = describe_layer(LAYER_USER, path)
    document = read_layer_file(path, LAYER_USER) or {}
    validate_layer(schema, document, LAYER_USER, label)
    current = document.get("security", {}).get("trustedProjects", [])
    approved = [entry for entry in current if normalized_project_path(entry) != normalized_project_path(project_root)]
    if not arguments.revoke:
        approved.append(project_root)
    set_sparse(document, TRUSTED_PROJECTS_KEY, approved, schema)
    validate_layer(schema, document, LAYER_USER, label)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_text_if_changed(path, serialize_json(document))
    script = os.path.abspath(__file__)
    if arguments.revoke:
        write_line(f"Revoked: the manifest of {project_root} can no longer loosen security on this machine ({path}).")
    else:
        write_line(f"Approved on this machine: the manifest of {project_root} may loosen security keys ({path}).")
        write_line(f'Revoke it with: python3 "{script}" trust --revoke --project "{project_root}"')
    return 0


def command_fetch_sources(arguments):
    """Bring profile sources into the cache; a refresh reports failures without stopping."""
    declarations = declared_sources(arguments.project)
    locked_sources = locked_sources_of(arguments.project)
    if arguments.refresh:
        with_tags = configuration_of(arguments.project).value(pack_tools.CHECK_SIGNATURE_KEY)
        for failure in refresh_declared_sources(declarations, locked_sources, with_tags):
            write_line(f"WARNING: comparing with the local cache: {failure}", sys.stderr)
        return 0
    pins = download_declared_sources(declarations, locked_sources, arguments.update_source or [],
                                     configuration_of(arguments.project), arguments.project, to_ref=arguments.to,
                                     from_lock=arguments.from_lock, offline=arguments.offline)
    if arguments.state_file:
        write_text_atomically(arguments.state_file, serialize_json(pins))
    return 0


def content_dir_of(project_root, skill_dir, offline=False, read_only=True):
    """Skill directory with the content this repository uses, composed with the engine ``skill_dir``.

    Offline, a revision missing from the cache raises ContentPendingError for a run that writes nothing.
    """
    lock = read_lock(project_root)
    content_dir, warning = content_source.content_skill_dir(
        configuration_of(project_root, offline), skill_dir, (lock or {}).get("source"),
        offline=offline, read_only=read_only,
    )
    if warning:
        write_line(f"WARNING: {warning}", sys.stderr)
    return content_dir


def command_content_source(arguments):
    """Print the skill directory with the content of this run composed with this engine; see agent_ready_content."""
    lock = read_lock(arguments.project)
    try:
        content_dir, warning = content_source.content_skill_dir(
            configuration_of(arguments.project, arguments.offline), arguments.skill_dir, (lock or {}).get("source"),
            update=arguments.update, to_ref=arguments.to, offline=arguments.offline, read_only=arguments.read_only,
            from_lock=arguments.from_lock,
        )
    except content_source.ContentPendingError as pending_error:
        write_line(f"WARNING: {pending_error}", sys.stderr)
        return CONTENT_PENDING_STATUS
    if warning:
        write_line(f"WARNING: {warning}", sys.stderr)
    # A forward-slash path that Bash on every system can use.
    write_line(content_dir.replace(os.sep, "/"))
    return 0


def command_detect(arguments):
    """Print what the project signals say; it never changes a selection."""
    catalog = load_effective_catalog(arguments.project, arguments.skill_dir)
    if not configuration_of(arguments.project).value(DETECTION_ENABLED_KEY):
        write_line(f"Detection is off ({DETECTION_ENABLED_KEY}: false): select the profiles with --stack or --profiles.")
        return DETECTION_UNRESOLVED_STATUS
    detection = detect_profiles(catalog["profiles"], arguments.project)
    write_line(f"Stack: {describe_detected_stack(detection)}")
    print_detection_matches(detection)
    if detection["capabilities"]:
        write_line("Capabilities detected (suggestions only; detection never applies them):")
        for name, evidence in sorted(detection["capabilities"].items()):
            write_line(f"  ? {name}: {format_evidence_list(evidence)}")
    if detection["status"] == STATUS_RESOLVED:
        return 0
    if detection["status"] == STATUS_NONE:
        # Not an error: a repository without code gets the core only.
        write_line(f"No stack signal: an apply without a selection gives the core only. To pick a stack or capabilities, "
                   f"pass --profiles ({', '.join(stack_names_of(catalog))}, or capabilities from agent-ready profiles list).")
        return 0
    write_line(f"No primary stack: select one explicitly with --stack or --profiles ({', '.join(stack_names_of(catalog))}).")
    return DETECTION_UNRESOLVED_STATUS


def command_plan(arguments):
    """Compute the plan; print it, save it, or list protected destinations."""
    catalog = load_effective_catalog(arguments.project, arguments.skill_dir, read_source_state(arguments))
    requested, selection = resolve_selection(arguments, catalog)
    try:
        plan = compute_plan(arguments.project, arguments.skill_dir, catalog, requested)
    except IncompleteEvaluationError as incomplete_error:
        if arguments.format == "protected":
            raise
        if arguments.format in ("json", CONFLICTS_JSON_FORMAT):
            write_line(serialize_json({"complete": False, "requestedProfiles": requested, "selection": selection,
                                       "incomplete": str(incomplete_error)}).rstrip("\n"))
            return INCOMPLETE_EVALUATION_STATUS
        print_incomplete_plan(arguments.project, arguments.skill_dir, selection, requested, incomplete_error)
        return INCOMPLETE_EVALUATION_STATUS
    if arguments.source_mode == SOURCE_MODE_SYNC:
        enforce_sync_policy(arguments.project, arguments.skill_dir, catalog, plan["profiles"], plan["profileDigests"],
                            plan["selectedProfiles"], plan["workspaceOrigins"])
        keep_locked_entries_of_unselected_sources(plan, read_lock(arguments.project))
    tools_report = pack_tools_report(plan, catalog, configuration_of(arguments.project, arguments.offline))
    if tools_report:
        plan["packTools"] = tools_report
    # agent-ready conflicts looks at the whole repository: the project's AGENTS.md against the rules
    # already applied too, not only against what an apply changes.
    conflicts = semantic_conflicts(arguments, plan,
                                   instructions_with_applied=arguments.format in (CONFLICTS_FORMAT, CONFLICTS_JSON_FORMAT))
    # Before the apply too: it publishes what the previews reviewed to the versioned cache.
    competing_skills = competing_skills_report(arguments, plan, catalog,
                                               configuration_of(arguments.project, arguments.offline))
    if competing_skills is not None:
        plan["competingSkills"] = competing_skills
    if conflicts is not None:
        plan["semanticConflicts"] = conflicts
        if arguments.format == "protected":
            print_conflict_warnings(conflicts)
            if conflicts["block"]:
                problem = conflicts_review.blocking_problem(conflicts)
                if problem:
                    raise ProfileError(problem)
    if arguments.from_lock:
        lock = read_lock(arguments.project)
        enforce_lock_reproduction(plan, lock)
        # Same revisions and digests: the lock keeps its entries, with the refs they came from.
        plan["profileSources"] = dict((lock or {}).get("profileSources", {}))
    plan["profiles_requested"] = requested
    plan["selection"] = selection
    plan["addedDependencies"] = added_dependencies(catalog, requested, plan["profiles"])
    if arguments.save:
        write_text_atomically(arguments.save, serialize_json(plan))
    if arguments.format == "protected":
        # Non-regular destinations stay with the projection, which already
        # preserves them and reports the structural conflict.
        for entry in plan["entries"]:
            if entry["action"] in (ACTION_CONFLICT, ACTION_RETIRE_CONFLICT) and entry["local"] != LOCAL_NOT_A_FILE:
                write_line(entry["destination"])
        for view in plan["detachedViews"]:
            write_line(view)
    else:
        configuration = configuration_of(arguments.project, arguments.offline)
        if configuration.value(DETECTION_ENABLED_KEY):
            plan["detection"] = detect_profiles(catalog["profiles"], arguments.project)
            plan["suggestions"] = capability_suggestions(catalog, plan["detection"], plan["profiles"])
            plan["workspaceSuggestions"] = workspace_suggestions(arguments.project, catalog, plan["profiles"], configuration)
        plan.update(structural_conflicts(arguments.project, arguments.skill_dir, plan, catalog, configuration))
        if arguments.format in (CONFLICTS_FORMAT, CONFLICTS_JSON_FORMAT):
            return report_conflicts(plan, arguments.format == CONFLICTS_JSON_FORMAT)
        if arguments.format == "json":
            write_line(serialize_json(plan_report(arguments.project, arguments.skill_dir, plan, configuration)).rstrip("\n"))
            return 0
        print_plan(
            arguments.project, arguments.skill_dir, plan, arguments.provider,
            os.environ.get("AGENT_READY_SETUP_MARKETPLACE_UPGRADED") == "1", configuration,
        )
    return 0


def command_finalize(arguments):
    """Retire assets and write the lockfile from a saved pre-apply plan."""
    plan = read_json_file(arguments.plan, "saved plan")
    report = finalize(arguments.project, arguments.skill_dir, plan, arguments.updates)
    print_finalize_report(report)
    return 0


def configuration_report(configuration):
    """Effective configuration as JSON-ready data: values, origins and what was ignored."""
    return {
        "values": configuration.tree(),
        "origins": {key: configuration.origin(key) for key in sorted(configuration.values)},
        "ignored": configuration.ignored,
        "layers": configuration.layers,
        "projectApproved": configuration.project_approved,
    }


def plan_report(project_root, skill_dir, plan, configuration):
    """The plan as JSON-ready data, with the merged files and the configuration it used."""
    report = {key: value for key, value in plan.items() if key != "profiles_requested"}
    report["complete"] = True
    report["requestedProfiles"] = plan["profiles_requested"]
    report["mergedChanges"] = [
        {"destination": destination, "action": action, "reason": reason}
        for destination, action, reason in merged_file_changes(project_root, skill_dir, plan)
    ]
    report["claudeProxiesToNormalize"] = claude_proxy_drift(project_root, skill_dir)
    report["configuration"] = configuration_report(configuration)
    report["reviews"] = review_summary(project_root)
    return report


def status_report(status):
    """The status as JSON-ready data; the full plan stays out, plan --format json has it."""
    report = {key: value for key, value in status.items() if key not in ("configuration", "plan")}
    report["drift"] = status_has_drift(status)
    report["configuration"] = configuration_report(status["configuration"])
    return report


def command_pack_scripts(arguments):
    """Run the session-start scripts of the packs; only the session hook calls it, in the background.

    With --previous-report it only shows, once, what failed in the last run.
    """
    if arguments.previous_report:
        for problem in pack_scripts.previous_session_report(arguments.project):
            write_line(f"[marketplace-sync] A session-start script of a profile pack failed: {problem}")
        return 0
    lock = read_lock(arguments.project)
    locked = (lock or {}).get("scripts", {})
    if os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") == "1" or not any(
            entry.get("event") == pack_scripts.EVENT_SESSION_START for entry in locked.values()):
        return 0
    configuration = configuration_of(arguments.project, True)
    catalog = load_effective_catalog(arguments.project, arguments.skill_dir)
    plan = compute_plan(arguments.project, arguments.skill_dir, catalog, lock.get("profileOrder") or [])
    report = pack_tools_report(plan, catalog, configuration)
    result = pack_scripts.run_session_start(arguments.project, report, locked,
                                            configuration.value(pack_tools.CHECK_LOCK_DIGEST_KEY))
    for line in result["ran"]:
        write_line(f"ran {line}")
    for line in result["skipped"]:
        write_line(f"skipped {line}")
    for problem in result["failed"]:
        sys.stderr.write(f"Script of a profile pack failed: {problem}\n")
    return 1 if result["failed"] else 0


def command_status(arguments):
    """Print the read-only status."""
    if arguments.conflicts_only:
        # The hooks: only the structural conflicts, and nothing at all when there is none.
        key = (EDIT_CONFLICTS_ENABLED_KEY if arguments.conflicts_only == CONFLICTS_MOMENT_EDIT
               else SESSION_START_CONFLICTS_ENABLED_KEY)
        if arguments.changed is not None and not conflict_inputs_changed(arguments.changed, arguments.skill_dir):
            return 0
        lines = compute_status(arguments.project, arguments.skill_dir, key).get("conflicts") or []
        for line in lines:
            write_line(f"{CONFLICTS_HOOK_PREFIX} {line.strip()}")
        if lines:
            write_line(f"{CONFLICTS_HOOK_PREFIX} Each one with its fix: agent-ready conflicts")
        return 0
    # The session hook asks for --brief; agent-ready status always lists them.
    conflicts_key = SESSION_START_CONFLICTS_ENABLED_KEY if arguments.brief else True
    status = compute_status(arguments.project, arguments.skill_dir, conflicts_key)
    if arguments.format == "json":
        write_line(serialize_json(status_report(status)).rstrip("\n"))
        return DRIFT_STATUS if arguments.check and status_has_drift(status) else 0
    print_status(status, arguments.brief)
    if arguments.check and status_has_drift(status):
        return DRIFT_STATUS
    return 0


def merged_file_problems(project_root, skill_dir, plan):
    """Merged files and CLAUDE.md proxies that an apply would change."""
    catalog = load_effective_catalog(project_root, skill_dir)
    with tempfile.TemporaryDirectory(prefix="agent-ready-check.") as compose_root:
        previous_stack_dir = os.environ.get("AGENT_READY_SETUP_STACK_DIR")
        os.environ["AGENT_READY_SETUP_STACK_DIR"] = compose_stack_directory(skill_dir, catalog, plan["profiles"], compose_root)
        try:
            changes = merged_file_changes(project_root, skill_dir, plan)
        finally:
            if previous_stack_dir is None:
                del os.environ["AGENT_READY_SETUP_STACK_DIR"]
            else:
                os.environ["AGENT_READY_SETUP_STACK_DIR"] = previous_stack_dir
    problems = [f"{destination}: {reason}" for destination, action, reason in changes if action != ACTION_UNCHANGED]
    problems += [f"{path}: an apply would normalize it to the proxy" for path in claude_proxy_drift(project_root, skill_dir)]
    return problems


def check_problems(project_root, skill_dir):
    """Everything that shows the committed assets are not up to date. Returns (problems, incomplete)."""
    status = compute_status(project_root, skill_dir)
    # A catalog, a selection or a provider that cannot be evaluated is not an outdated repository.
    if status["errors"]:
        raise ProfileError("; ".join(status["errors"]))
    problems = []
    if status["manifest"] is None:
        problems.append(f"{MANIFEST_RELATIVE_PATH} is missing")
    if not status["hasLock"]:
        problems.append(f"{LOCK_RELATIVE_PATH} is missing")
    labels = (("modified", "modified"), ("missing", "missing"), ("conflict", "preserved conflict"),
              ("failed", "failed to apply"), ("retiredPreserved", "retired but preserved"))
    for key, label in labels:
        problems += [f"{destination}: {label}" for destination in status["checkout"][key]]
    if status["incomplete"]:
        return sorted(set(problems)), status["incomplete"]
    for name, item in status["sources"].items():
        problems += [f"profile source {name}: {difference}" for difference in item["differences"]]
        if item["pendingUpdate"]:
            problems.append(f"profile source {name}: {item['pendingUpdate']}")
    problems += status["selectionDifferences"]
    problems += status["workspaceDifferences"]
    update = status["update"]
    if update and update["available"]:
        plan = status["plan"]
        locked_digest = (status["lockedSource"] or {}).get("contentDigest")
        if locked_digest != plan["source"]["contentDigest"]:
            problems.append(f"{content_source.CONTENT_SOURCE_NAME}: the lock has {describe_source(status['lockedSource'])}; the source is {describe_source(plan['source'])}")
        problems += [f"{destination}: an apply would change it" for destination in update["changedDestinations"]]
    if status.get("plan") and status["hasLock"]:
        problems += merged_file_problems(project_root, skill_dir, status["plan"])
    return sorted(set(problems)), None


def find_repository_root(start):
    """Root of the repository that holds a directory, without running anything: ci off runs nothing."""
    current = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return os.path.abspath(start)
        current = parent


def evaluate_check(project_root, skill_dir, offline):
    """Result of the check, before the ``ci`` mode decides the exit status."""
    configuration = configuration_of(project_root, offline)
    ci = {"enabled": configuration.value(CI_ENABLED_KEY), "mode": configuration.value(CI_MODE_KEY)}
    if not ci["enabled"]:
        return {"status": CHECK_SKIPPED, "ci": ci, "problems": [], "unavailable": []}
    unavailable = []
    if not offline:
        unavailable = refresh_declared_sources(declared_sources(project_root), locked_sources_of(project_root))
    # The repository is checked against the content of its revision, like an apply.
    locked_source = (read_lock(project_root) or {}).get("source")
    content_source.declaration_of(configuration)  # an invalid declaration is a configuration error
    try:
        content_dir, missing_content = content_source.content_skill_dir(
            configuration, skill_dir, locked_source, offline=offline, read_only=True,
        )
    except ProfileError as fetch_error:
        # The revision or its ref could not be fetched: like a pack that cannot refresh.
        content_dir, missing_content = skill_dir, str(fetch_error)
    if missing_content:
        # Comparing with the installed content would report changes an apply never makes.
        return {"status": CHECK_SOURCE_UNAVAILABLE, "ci": ci, "problems": [], "unavailable": unavailable + [missing_content]}
    problems, incomplete = check_problems(project_root, content_dir)
    if incomplete:
        unavailable.append(incomplete)
    conflicts, failing_conflicts = {}, False
    if not unavailable:
        # With a source missing the selection cannot be evaluated: source-unavailable already says so.
        try:
            conflicts, failing_conflicts = check_conflicts(project_root, content_dir, offline)
        except IncompleteEvaluationError as incomplete_error:
            unavailable.append(str(incomplete_error))
    if unavailable:
        status = CHECK_SOURCE_UNAVAILABLE
    elif problems:
        status = CHECK_OUTDATED
    elif failing_conflicts:
        status = CHECK_CONFLICTS
    else:
        status = CHECK_UP_TO_DATE
    return {"status": status, "ci": ci, "problems": problems, "unavailable": unavailable, "conflicts": conflicts}


def semantic_conflict_lines(report):
    """One line per finding of the AI reviews, and how many pairs they could not review."""
    module = review_cache_module()
    lines, unchecked = [], 0
    for key in ("semanticConflicts", "competingSkills"):
        review = report.get(key) or {}
        lines += [f"  {module.finding_line(finding)}" for finding in review.get("findings", [])]
        unchecked += review.get("unchecked", 0)
    return lines, unchecked


def report_conflicts(plan, as_json):
    """agent-ready conflicts: every conflict of the selection, and exit 6 when there is one."""
    structural = structural_conflict_lines(plan)
    semantic, unchecked = semantic_conflict_lines(plan)
    found = bool(structural or semantic)
    if as_json:
        keys = ("machine", "repoReality", "parity", "competingTools", "settingsConflicts", "semanticConflicts",
                "competingSkills")
        write_line(serialize_json({"structural": structural, "semantic": semantic, "unchecked": unchecked,
                                   "found": found, "details": {key: plan[key] for key in keys if key in plan}})
                   .rstrip("\n"))
        return CONFLICTS_STATUS if found else 0
    stream = sys.stdout
    if not found:
        write_line(paint("No conflicts between the profiles", "ok", stream))
    for title, lines in (("Structural conflicts", structural), ("AI review findings", semantic)):
        if lines:
            write_line(paint(f"{title}:", "warning", stream))
            for line in lines:
                write_line(line)
    if unchecked:
        write_line(f"{unchecked} pair(s) of the AI reviews could not be reviewed in this run.")
    return CONFLICTS_STATUS if found else 0


def has_review_pairs(project_root, plan, catalog):
    """True when the AI reviews of agent-ready check have a pair to review: without one there is
    nothing to check, and no provider is needed."""
    configuration = configuration_of(project_root)
    module = review_cache_module()
    if configuration.value(CONFLICTS_ENABLED_KEY):
        lock = read_lock(project_root)
        directions, _ = conflicts_review.conflict_pairs(
            project_root, plan["entries"], (lock or {}).get("assets", {}), module.normalized_text,
            project_owned_instructions, ENGINE_SKILL_DIRECTORY, is_pack_profile, True, nested_instruction_files(plan))
        if directions:
            return True
    if configuration.value(COMPETING_SKILLS_ENABLED_KEY):
        directions, _ = skill_overlap.skill_pairs(project_root, plan["entries"], catalog, is_pack_profile,
                                                  module.normalized_text)
        if directions:
            return True
    return False


def session_provider():
    """The provider of this run as resolve-provider.sh infers it (the environment, then the
    installation), the same as every other command; None when it cannot tell."""
    from_environment = os.environ.get("AGENT_READY_SETUP_ACTIVE_PROVIDER")
    if from_environment in SUPPORTED_PROVIDERS:
        return from_environment
    resolved = run_quiet([bash_executable(), os.path.join(ENGINE_SKILL_DIRECTORY, PROVIDER_RESOLVER_RELATIVE_PATH),
                          "--skill-dir", ENGINE_SKILL_DIRECTORY])
    return resolved if resolved in SUPPORTED_PROVIDERS else None


# Pack-author mode of agent-ready conflicts: the pack is copied into a throwaway consumer repository,
# under this folder, and every profile it publishes is checked there with the base of the content and its requires.
PACK_CHECK_DIRECTORY = "agent-packs"


def pack_profile_conflicts(run, profile):
    """The conflicts of one pack profile with the base and its requires: (structural, semantic, unchecked).

    The author's machine is not the consumer's: shadowing, the user's MCP servers and settings stay out.
    """
    catalog = load_effective_catalog(run.project, run.skill_dir)
    plan = compute_plan(run.project, run.skill_dir, catalog, [profile])
    configuration = configuration_of(run.project, run.offline)
    tools_report = pack_tools_report(plan, catalog, configuration)
    if tools_report:
        plan["packTools"] = tools_report
    report = structural_conflicts(run.project, run.skill_dir, plan, catalog, configuration, with_context=False,
                                  with_machine=False)
    report["semanticConflicts"] = semantic_conflicts(run, plan)
    report["competingSkills"] = competing_skills_report(run, plan, catalog, configuration)
    semantic, unchecked = semantic_conflict_lines(report)
    return structural_conflict_lines(report), semantic, unchecked


def command_pack_conflicts(arguments):
    """agent-ready conflicts --pack: each profile of a pack against the base of the content and its requires,
    without a consumer repository. Exits 6 when one has a conflict, 2 when the pack cannot resolve."""
    pack_root = os.path.abspath(arguments.pack)
    catalog_path = os.path.join(pack_root, PACK_CATALOG_FILE_NAME)
    if not os.path.isfile(catalog_path):
        raise ProfileError(f"{pack_root} has no {PACK_CATALOG_FILE_NAME}: --pack takes the root of a profile pack")
    pack_catalog = read_json_file(catalog_path, "pack catalog")
    pack_name = pack_catalog.get("name") or os.path.basename(pack_root)
    # The name becomes a folder of the throwaway repository: only a source name, never a path.
    if not isinstance(pack_name, str) or not KEBAB_CASE_NAME.fullmatch(pack_name):
        raise ProfileError(f"{catalog_path} has an invalid pack name {pack_name!r}; use kebab-case")
    results = {}
    with tempfile.TemporaryDirectory(prefix="agent-ready-pack-check.") as scratch:
        project = os.path.join(scratch, "project")
        shutil.copytree(pack_root, os.path.join(project, PACK_CHECK_DIRECTORY, pack_name),
                        ignore=shutil.ignore_patterns(".git"), symlinks=True)
        if run_quiet(["git", "init", "-q", project]) is None:
            raise StateError(f"git init failed in {project}: the pack check needs Git")
        run = types.SimpleNamespace(project=project, skill_dir=arguments.skill_dir, offline=arguments.offline,
                                    profiles=None, stack=None, format="text",
                                    provider=arguments.provider or session_provider())
        source = {"name": pack_name, "source": f"path:./{PACK_CHECK_DIRECTORY}/{pack_name}"}
        manifest_path = os.path.join(project, *MANIFEST_RELATIVE_PATH.split("/"))
        # The whole catalog is validated first, as a consumer loads it: an empty or invalid pack fails
        # here even when it publishes no profile to check.
        write_text_atomically(manifest_path, serialize_json({"profiles": [], "sources": {"packs": [source]}}))
        run.skill_dir = content_dir_of(project, arguments.skill_dir, offline=arguments.offline, read_only=False)
        load_effective_catalog(project, run.skill_dir)
        profiles = [f"{pack_name}/{name}" for name in pack_catalog.get("profiles", {})]
        for profile in profiles:
            write_text_atomically(manifest_path, serialize_json({"profiles": [profile], "sources": {"packs": [source]}}))
            try:
                structural, semantic, unchecked = pack_profile_conflicts(run, profile)
                results[profile] = {"structural": structural, "semantic": semantic, "unchecked": unchecked}
            except (ProfileError, IncompleteEvaluationError) as caught_error:
                results[profile] = {"error": str(caught_error)}
    errors = any("error" in result for result in results.values())
    found = any(result.get("structural") or result.get("semantic") for result in results.values())
    if arguments.format == "json":
        write_line(serialize_json({"pack": pack_name, "profiles": results, "found": found}).rstrip("\n"))
    else:
        print_pack_conflicts(pack_name, results)
    if errors:
        return PROFILE_ERROR_STATUS
    return CONFLICTS_STATUS if found else 0


def print_pack_conflicts(pack_name, results):
    """One block per profile of the pack: its conflicts, or that it has none."""
    stream = sys.stdout
    write_line(f"Pack {pack_name}: {len(results)} profile(s) checked against the golfo base and their requires")
    for profile, result in results.items():
        if "error" in result:
            write_line(paint(f"{profile}: does not resolve: {result['error']}", "error", stream))
            continue
        lines = result["structural"] + result["semantic"]
        if not lines:
            write_line(paint(f"{profile}: no conflicts", "ok", stream))
        else:
            write_line(paint(f"{profile}:", "warning", stream))
            for line in lines:
                write_line(paint(line, "warning", stream))
        if result["unchecked"]:
            write_line(f"  {result['unchecked']} pair(s) of the AI reviews could not be reviewed in this run.")


def check_conflicts(project_root, content_dir, offline):
    """The conflicts agent-ready check reports under ci.conflicts: (result, whether they fail the check)."""
    configuration = configuration_of(project_root, offline)
    structural_mode = configuration.value(CI_CONFLICTS_STRUCTURAL_KEY)
    semantic_mode = configuration.value(CI_CONFLICTS_SEMANTIC_KEY)
    result = {"structuralMode": structural_mode, "semanticMode": semantic_mode, "structural": [], "semantic": [],
              "unchecked": 0}
    if structural_mode == CI_CONFLICTS_OFF and semantic_mode == CI_CONFLICTS_OFF:
        return result, False
    catalog = load_effective_catalog(project_root, content_dir)
    run = types.SimpleNamespace(project=project_root, skill_dir=content_dir, offline=offline, profiles=None, stack=None,
                                format="text", provider=session_provider())
    # The same selection the rest of the check evaluated: the manifest, else the lock's, and only then
    # detection, so a repository that relies on its lock never needs detection here.
    requested = configuration.value(PROFILES_KEY)
    if requested is None:
        requested = (read_lock(project_root) or {}).get("profileOrder")
    if requested is None:
        requested, _ = resolve_selection(run, catalog)
    plan = compute_plan(project_root, content_dir, catalog, requested)
    tools_report = pack_tools_report(plan, catalog, configuration)
    if tools_report:
        plan["packTools"] = tools_report
    if structural_mode != CI_CONFLICTS_OFF:
        result["structural"] = structural_conflict_lines(
            structural_conflicts(project_root, content_dir, plan, catalog, configuration))
    # The reviews this configuration runs at all: none, and there is nothing to check or to call.
    reviews_on = configuration.value(REVIEWS_ENABLED_KEY) and (
        configuration.value(CONFLICTS_ENABLED_KEY) or configuration.value(COMPETING_SKILLS_ENABLED_KEY))
    reviewing = semantic_mode != CI_CONFLICTS_OFF and reviews_on and has_review_pairs(project_root, plan, catalog)
    if reviewing and run.provider is None:
        # Without a provider the reviews cannot even read their cache, whose keys include it.
        result["unchecked"] = 1
        result["semanticProblem"] = "no provider could be inferred; set AGENT_READY_SETUP_ACTIVE_PROVIDER"
    elif reviewing:
        reviews = {"semanticConflicts": semantic_conflicts(run, plan, instructions_with_applied=True),
                   "competingSkills": competing_skills_report(run, plan, catalog, configuration)}
        result["semantic"], result["unchecked"] = semantic_conflict_lines(reviews)
    failing = ((structural_mode == CI_CONFLICTS_FAIL and bool(result["structural"]))
               or (semantic_mode == CI_CONFLICTS_FAIL and bool(result["semantic"] or result["unchecked"])))
    return result, failing


def print_check_text(result):
    """Readable result of the check; the text is not a contract, the exit status is."""
    stream = sys.stdout
    headlines = {
        CHECK_UP_TO_DATE: ("up to date", "ok"),
        CHECK_OUTDATED: ("updates pending", "warning"),
        CHECK_SOURCE_UNAVAILABLE: ("source not available", "error"),
        CHECK_CONFIG_ERROR: ("configuration error", "error"),
        CHECK_SKIPPED: ("skipped", "muted"),
        CHECK_CONFLICTS: ("conflicts between the profiles", "error"),
    }
    headline, color = headlines[result["status"]]
    ci = result["ci"]
    if not ci:
        mode = ""
    elif ci["enabled"]:
        mode = f" ({CI_MODE_KEY}: {ci['mode']})"
    else:
        mode = f" ({CI_ENABLED_KEY}: false)"
    write_line(paint(f"Agent Ready check: {headline}{mode}", color, stream))
    for message in result["unavailable"] + result["problems"]:
        write_line(f"  ! {message}")
    conflicts = result.get("conflicts") or {}
    for kind, mode_key in (("structural", CI_CONFLICTS_STRUCTURAL_KEY), ("semantic", CI_CONFLICTS_SEMANTIC_KEY)):
        if conflicts.get(kind):
            write_line(f"Conflicts ({mode_key}: {conflicts[kind + 'Mode']}):")
            for line in conflicts[kind]:
                write_line(line)
    if conflicts.get("semanticProblem"):
        write_line(f"  ! the AI reviews could not run: {conflicts['semanticProblem']} "
                   f"({CI_CONFLICTS_SEMANTIC_KEY}: {conflicts['semanticMode']})")
    elif conflicts.get("unchecked"):
        write_line(f"  ! {conflicts['unchecked']} pair(s) of the AI reviews could not be reviewed "
                   f"({CI_CONFLICTS_SEMANTIC_KEY}: {conflicts['semanticMode']})")
    if result["status"] in (CHECK_OUTDATED, CHECK_SOURCE_UNAVAILABLE):
        write_line("Apply with bootstrap.sh, review the diff of the assets and the lockfile, and commit it.")


def command_check(arguments):
    """Compare sources, lock and committed assets; any CI provider can run this.

    It needs python3, git and bash, and reaches private sources only through Git.
    """
    project_root = find_repository_root(arguments.project)
    try:
        result = evaluate_check(project_root, arguments.skill_dir, arguments.offline)
    except (ProfileError, StateError) as configuration_error:
        result = {"status": CHECK_CONFIG_ERROR, "ci": None, "problems": [str(configuration_error)], "unavailable": []}
    exit_status = CHECK_EXIT_STATUSES[result["status"]]
    if result["ci"] and result["ci"]["mode"] == CI_WARN:
        exit_status = 0
    result["exitStatus"] = exit_status
    if arguments.format == "json":
        write_line(serialize_json(result).rstrip("\n"))
    else:
        print_check_text(result)
    return exit_status


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
