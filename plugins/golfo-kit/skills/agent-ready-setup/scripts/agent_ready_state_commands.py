"""The commands of agent-ready-state.py besides check: resolve, detect, plan, finalize, status, pack-scripts,
config, trust, fetch-sources and content-source. build_parser, in the entry point, routes each to its handler.
"""

import os
import sys

import agent_ready_conflicts as conflicts_review
import agent_ready_content as content_source
import agent_ready_pack_scripts as pack_scripts
import agent_ready_pack_tools as pack_tools
from agent_ready_actions import ACTION_CONFLICT, ACTION_RETIRE_CONFLICT
from agent_ready_check import report_conflicts
from agent_ready_common import (
    LOCAL_NOT_A_FILE,
    IncompleteEvaluationError,
    ProfileError,
    find_repository_root,
    read_json_file,
    serialize_json,
    write_text_atomically,
    write_text_if_changed,
)
from agent_ready_config import (
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
from agent_ready_desired_assets import compose_stack_directory, profile_digests, workspace_profile_origins
from agent_ready_detection import STATUS_NONE, STATUS_RESOLVED, detect_profiles, format_evidence_list
from agent_ready_finalize import finalize, print_finalize_report
from agent_ready_lockfile import read_lock
from agent_ready_manifest import (
    configuration_of,
    declared_sources,
    print_configuration_values,
    print_ignored_configuration,
    read_manifest,
    state_script_path,
)
from agent_ready_merged_files import claude_proxy_drift, merged_file_changes
from agent_ready_options import (
    DETECTION_ENABLED_KEY,
    EDIT_CONFLICTS_ENABLED_KEY,
    PROFILES_KEY,
    SESSION_START_CONFLICTS_ENABLED_KEY,
    TRUSTED_PROJECTS_KEY,
    UPDATES_AUTO,
)
from agent_ready_output import paint, write_line
from agent_ready_packs import download_declared_sources, effective_update_mode, refresh_declared_sources
from agent_ready_plan import (
    added_dependencies,
    capability_suggestions,
    composed_workspace_assets,
    compute_plan,
    compute_status,
    describe_detected_stack,
    print_conflict_warnings,
    print_detection_matches,
    print_incomplete_plan,
    print_plan,
    resolve_workspaces,
    semantic_conflicts,
    workspace_suggestions,
)
from agent_ready_profiles import (
    load_effective_catalog,
    locked_sources_of,
    primary_stack,
    resolve_project_profiles,
    resolved_tools,
)
from agent_ready_review_findings import review_summary
from agent_ready_selection import read_source_state, resolve_selection, stack_names_of
from agent_ready_source_identity import (
    enforce_lock_reproduction,
    enforce_sync_policy,
    keep_locked_entries_of_unselected_sources,
    validate_pack_destinations,
)
from agent_ready_state_contract import (
    CONFLICTS_FORMAT,
    CONFLICTS_HOOK_PREFIX,
    CONFLICTS_JSON_FORMAT,
    CONFLICTS_MOMENT_EDIT,
    CONTENT_PENDING_STATUS,
    DETECTION_UNRESOLVED_STATUS,
    DRIFT_STATUS,
    INCOMPLETE_EVALUATION_STATUS,
    SELECTION_DETECTION,
    SOURCE_MODE_SYNC,
)
from agent_ready_status import conflict_inputs_changed, pack_tools_report, print_status, status_has_drift
from agent_ready_structural import competing_skills_report, structural_conflicts


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
    script = state_script_path()
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
