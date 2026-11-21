"""The plan: what an apply would create, update, adopt, retire or keep for the selection, the sources and the
versions it changes, how it prints, and compute_status, which compares the plan with the lock.
"""

import difflib
import os
import shutil
import sys

import agent_ready_blocks as managed_blocks
import agent_ready_conflicts as conflicts_review
import agent_ready_learning_customized as learning_customized
import agent_ready_learning_promote as learning_promote
import agent_ready_nested as nested
import agent_ready_pack_tools as pack_tools
import agent_ready_rule_changes as rule_changes
import agent_ready_sync as team_sync
import agent_ready_workspaces as workspace_selection
from agent_ready_actions import (
    ACTION_ADOPT,
    ACTION_CONFLICT,
    ACTION_CREATE,
    ACTION_DROP,
    ACTION_RETIRE,
    ACTION_RETIRE_CONFLICT,
    ACTION_SYMBOLS,
    ACTION_UNCHANGED,
    ACTION_UPDATE,
    DETACHED_VIEW_REASON,
    EDITED_VIEW_REASON,
    LINKED_PARENT_REASON,
    classify_retired,
)
from agent_ready_common import (
    LOCAL_ABSENT,
    LOCAL_NOT_A_FILE,
    LOCAL_SYMLINK,
    IncompleteEvaluationError,
    ProfileError,
    StateError,
    bash_executable,
    has_linked_parent,
    is_link,
    local_state,
    read_json_file,
    sha256_of_file,
)
from agent_ready_desired_assets import (
    desired_assets,
    desired_blocks,
    desired_nested_blocks,
    nested_contents,
    nested_index_block,
    profile_digests,
    shared_overrides,
    workspace_blocks,
    workspace_file_blocks,
    workspace_profile_origins,
    workspace_rule_files,
    workspace_shared_texts,
)
from agent_ready_detection import STATUS_AMBIGUOUS, STATUS_RESOLVED, detect_profiles, format_evidence_list
from agent_ready_finalize import print_machine_report, waiting_instruction_files, without_waiting_sections
from agent_ready_layout import (
    BROWSER_TOOL_NAME,
    ENGINE_SKILL_DIRECTORY,
    MANIFEST_RELATIVE_PATH,
    PROVIDER_CATALOG_RELATIVE_PATH,
    claude_view_of,
    review_cache_module,
)
from agent_ready_lockfile import (
    SCHEMA_VERSION,
    STATE_APPLIED,
    STATE_CONFLICT,
    STATE_FAILED,
    STATE_RETIRED_PRESERVED,
    read_lock,
    was_applied,
)
from agent_ready_manifest import (
    configuration_of,
    print_configuration_values,
    print_ignored_configuration,
    read_manifest,
)
from agent_ready_merged_files import claude_proxy_drift, merged_file_changes
from agent_ready_options import (
    CONFLICTS_BLOCK_KEY,
    CONFLICTS_ENABLED_KEY,
    DETECTION_ENABLED_KEY,
    DETECTION_WORKSPACES_KEY,
    EXCLUDED_DEFAULTS_KEY,
    HOOK_CONFLICTS_ENABLED_KEY,
    PROFILES_KEY,
    PROVIDERS_KEY,
    REVIEWS_CACHE_KEY,
    REVIEWS_COMMIT_KEY,
    REVIEWS_ENABLED_KEY,
    REVIEWS_REDUNDANCY_KEY,
    REVIEWS_TTL_KEY,
    SUPPORTED_PROVIDERS,
    TOOLS_ENABLED_KEY,
    WORKSPACES_KEY,
)
from agent_ready_output import ANSI_COLORS, paint, write_line
from agent_ready_packs import CONTENT_SOURCE_NAME, SOURCE_TYPE_GIT, is_pack_profile, pack_cache_root, source_of_profile
from agent_ready_profiles import (
    ASSET_REFERENCE_SEPARATOR,
    CI_PROFILE_KIND,
    DEFAULTS_KEY,
    load_effective_catalog,
    primary_stack,
    rejecting_ci_profiles,
    resolve_project_profiles,
    resolved_tools,
)
from agent_ready_review_findings import project_owned_instructions, review_summary
from agent_ready_rule_overrides import (
    MANAGED_DESTINATION_PREFIX,
    resolved_rule_overrides,
    rule_override_texts,
    selection_rules,
)
from agent_ready_source_identity import (
    golfo_blocks,
    merged_template_entries,
    source_entries,
    source_identity,
    source_report,
    validate_pack_destinations,
    version_changes,
)
from agent_ready_status import (
    describe_source,
    describe_source_item,
    pack_tools_report,
    print_pack_tools,
    print_review_summary,
    selection_differences,
    source_report_without_selection,
)
from agent_ready_structural import (
    print_competing_skills,
    print_competing_tools,
    print_context_budget,
    print_parity_report,
    print_repo_reality,
    print_rule_keys,
    print_settings_conflicts,
    structural_conflict_lines,
    structural_conflicts,
)


def classify_asset(destination, desired_entry, local, lock_entry, has_lock):
    """Decision for one desired destination: managed files always follow the template."""
    new_hash = desired_entry["sha256"]
    base_hash = lock_entry.get("sha256") if lock_entry else None
    if local == LOCAL_ABSENT:
        return ACTION_CREATE, "missing locally"
    if local == new_hash:
        return ACTION_UNCHANGED, "matches the template"
    if local == LOCAL_NOT_A_FILE:
        return ACTION_CONFLICT, "destination is not a regular file"
    if not has_lock:
        return ACTION_ADOPT, "no lockfile yet: first apply keeps the previous overwrite contract"
    if not was_applied(lock_entry):
        return ACTION_CONFLICT, "file exists but was never applied by agent-ready-setup"
    if local == base_hash:
        return ACTION_UPDATE, "local file still matches the applied base"
    if local == LOCAL_SYMLINK:
        return ACTION_UPDATE, "managed file was replaced by a symlink; the template replaces the link without following it"
    return ACTION_UPDATE, "overwrites local changes since the last apply"


def detached_views(project_root, assets, locked_assets):
    """Claude views that became regular files holding content no apply wrote.

    A view only mirrors its asset, so it may still hold the asset, the applied base
    or the new template; anything else is local content. The view of a managed asset
    is relinked and only reported. Until an apply links the view, that path may be a
    project file, so it is preserved. Returns (edited, preserved).
    """
    edited = []
    preserved = []
    for destination, desired_entry in sorted(assets.items()):
        view = claude_view_of(destination, desired_entry["source"])
        view_path = os.path.join(project_root, view) if view else None
        if not view or is_link(view_path) or not os.path.isfile(view_path):
            continue
        asset_path = os.path.join(project_root, destination)
        if os.path.isfile(asset_path) and os.path.samefile(view_path, asset_path):
            continue
        known_content = {desired_entry["sha256"], locked_assets.get(destination, {}).get("sha256"), local_state(asset_path)}
        if sha256_of_file(view_path) not in known_content:
            lock_entry = locked_assets.get(destination)
            is_managed_view = was_applied(lock_entry) and not lock_entry.get("viewPreserved")
            (edited if is_managed_view else preserved).append(view)
    return edited, preserved


def resolve_workspaces(project_root, catalog, profile_names, resolved, entries=None):
    """The workspaces of the manifest, or ``entries``, validated and resolved together with the root selection.

    A path that cannot be a workspace, or a selection that does not resolve with the root one, stops
    before anything is written (agent_ready_workspaces.py). agent-ready workspaces add checks its entries
    here before it writes them.
    """
    if entries is None:
        entries = configuration_of(project_root).value(WORKSPACES_KEY) or []
    workspace_selection.validate(project_root, entries, MANIFEST_RELATIVE_PATH)
    root_names = [name for name in profile_names if catalog["profiles"].get(name, {}).get("kind") != CI_PROFILE_KIND]
    for entry in entries:
        # resolve_project_profiles drops CI profiles, which a lock lists: a workspace naming one is an error.
        try:
            rejecting_ci_profiles(catalog, entry["profiles"])
        except ProfileError as profile_error:
            raise ProfileError(f"workspace {entry['path']}: {profile_error}") from profile_error
    return workspace_selection.resolve(entries, root_names, resolved,
                                       lambda names: resolve_project_profiles(catalog, names, project_root))


def composed_workspace_assets(skill_dir, catalog, resolved, workspaces, project_root=None):
    """(profiles only workspaces select, workspace rules, shared texts, desired assets) of a selection.

    ``project_root`` adds the overrides that the project's own rules declare (rule_override_texts).

    It raises ProfileError for what an apply cannot compose: an override of a root asset, two profiles of
    a workspace that publish one rule, two assets with one destination.
    """
    workspace_profiles = workspace_selection.added_profiles(resolved, workspaces)
    workspace_rules = workspace_rule_files(skill_dir, catalog, workspaces)
    shared_texts = rule_override_texts(skill_dir, catalog, resolved, project_root,
                                       workspace_rule_destinations(workspace_rules))
    shared_texts.update(workspace_shared_texts(skill_dir, catalog, workspaces, workspace_profiles, workspace_rules))
    assets = desired_assets(skill_dir, catalog, resolved, workspace_rules, workspace_profiles, shared_texts)
    return workspace_profiles, workspace_rules, shared_texts, assets


def workspace_rule_destinations(workspace_rules):
    """The destinations of the rules the workspaces get (workspace_rule_files): managed, never the project's own."""
    return {MANAGED_DESTINATION_PREFIX + tree_path for tree_path in workspace_rules}


def check_workspace_composition(project_root, skill_dir, catalog, resolved, workspaces):
    """Raise ProfileError when an apply could not project these workspaces: their assets
    (composed_workspace_assets), the destinations of their packs and their blocks. agent-ready workspaces
    add runs it before it writes the manifest."""
    _, workspace_rules, _, assets = composed_workspace_assets(skill_dir, catalog, resolved, workspaces, project_root)
    validate_pack_destinations(project_root, assets)
    root_blocks = desired_blocks(skill_dir, catalog, resolved, assets)
    workspace_file_blocks(skill_dir, catalog, workspaces, assets, root_blocks, workspace_rules)
    workspace_blocks(skill_dir, catalog, workspaces, workspace_rules)


def workspace_suggestions(project_root, catalog, resolved, configuration=None):
    """The folders detection suggests as workspaces (agent_ready_workspaces.suggestions), or [] when
    detection.enabled or detection.workspaces is off."""
    configuration = configuration or configuration_of(project_root)
    if not configuration.value(DETECTION_ENABLED_KEY) or not configuration.value(DETECTION_WORKSPACES_KEY):
        return []
    return workspace_selection.suggestions(project_root, catalog["profiles"], resolved,
                                           configuration.value(WORKSPACES_KEY) or [], detect_profiles)


def compute_plan(project_root, skill_dir, catalog, profile_names):
    """Build the read-only plan for the selected profiles."""
    resolved = resolve_project_profiles(catalog, profile_names, project_root)
    workspaces = resolve_workspaces(project_root, catalog, profile_names, resolved)
    workspace_profiles, workspace_rules, _, assets = composed_workspace_assets(skill_dir, catalog, resolved, workspaces,
                                                                              project_root)
    for workspace in workspaces:
        workspace["rules"] = sum(1 for entry in workspace_rules.values() if entry["workspace"] == workspace["path"])
        workspace["sharedAssets"] = sum(1 for entry in assets.values()
                                        if entry["profile"] in workspace["own"] and not entry.get("workspace"))
    validate_pack_destinations(project_root, assets)
    lock = read_lock(project_root)
    locked_assets = lock["assets"] if lock else {}
    entries = []
    for destination, desired_entry in sorted(assets.items()):
        local = local_state(os.path.join(project_root, destination))
        lock_entry = locked_assets.get(destination)
        action, reason = classify_asset(destination, desired_entry, local, lock_entry, lock is not None)
        entries.append({
            "destination": destination,
            "action": action,
            "reason": reason,
            "profile": desired_entry["profile"],
            "source": desired_entry["source"],
            "sourcePath": desired_entry["sourcePath"],
            "sha256": desired_entry["sha256"],
            "baseSha256": lock_entry.get("sha256") if lock_entry else None,
            "local": local,
            "workspace": desired_entry.get("workspace"),
        })
    root_blocks = desired_blocks(skill_dir, catalog, resolved, assets)
    blocks = {**root_blocks, **workspace_file_blocks(skill_dir, catalog, workspaces, assets, root_blocks, workspace_rules)}
    targets = nested_contents(skill_dir, catalog, resolved)
    nested_blocks, nested_report = desired_nested_blocks(
        project_root, catalog, resolved, {**targets, **nested_contents(skill_dir, catalog, workspace_profiles)}, workspaces,
        workspace_rules)
    nested_blocks.update(workspace_blocks(skill_dir, catalog, workspaces, workspace_rules))
    waiting_nested = waiting_instruction_files(project_root, skill_dir, {destination for destination, _ in nested_blocks})
    for target in nested_report:
        target["waiting"] = [folder for folder in target["paths"] if nested.destination_in(folder) in waiting_nested]
    nested_index, nested_index_report = nested_index_block(project_root, nested_blocks, waiting_nested)
    nested_blocks.update(nested_index)
    block_destinations = {destination for destination, _ in blocks}
    retiring_block_files = set()
    for destination, lock_entry in sorted(locked_assets.items()):
        if destination in assets:
            continue
        local = local_state(os.path.join(project_root, destination))
        action, reason = classify_retired(local, lock_entry)
        if action == ACTION_RETIRE and has_linked_parent(project_root, destination):
            action, reason = ACTION_RETIRE_CONFLICT, LINKED_PARENT_REASON
        if action == ACTION_RETIRE and destination in block_destinations:
            retiring_block_files.add(destination)
        entries.append({
            "destination": destination,
            "action": action,
            "reason": reason,
            "profile": lock_entry.get("profile"),
            "source": lock_entry.get("source"),
            "sha256": None,
            "baseSha256": lock_entry.get("sha256"),
            "local": local,
        })
    # Which atomic rules each written or retired rule file changes, and what depends on them now.
    rule_changes.annotate_entries(project_root, entries, (ACTION_UPDATE, ACTION_ADOPT, ACTION_CONFLICT, ACTION_RETIRE))
    merged = merged_template_entries(skill_dir, catalog, resolved)
    # A pack only a workspace selects is still projected: its digest and its pinned mode count.
    selected = list(resolved) + workspace_profiles
    digests = profile_digests(skill_dir, catalog, selected)
    # What the root selection projects, plus the files the profiles only workspaces select come from
    # (workspace_profile_origins): enforce_sync_policy rebuilds the same digest.
    golfo_assets = {destination: entry for destination, entry in assets.items()
                    if not is_pack_profile(entry["profile"]) and entry["profile"] not in workspace_profiles}
    workspace_origins = workspace_profile_origins(skill_dir, catalog, workspace_profiles)
    # Without a lockfile the first apply keeps the previous overwrite contract.
    edited_views, preserved_views = detached_views(project_root, assets, locked_assets) if lock else ([], [])
    identity = source_identity(skill_dir, golfo_assets, merged, golfo_blocks(root_blocks), golfo_blocks(targets),
                               workspace_origins)
    published_rules = selection_rules(skill_dir, catalog, resolved)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "profiles": resolved,
        "primaryStack": primary_stack(catalog, resolved),
        # A workspace profile that needs a tool installs it for the repository, as its skills.
        "tools": resolved_tools(catalog, selected),
        # Packs have their own entries: an update of a pack is not an update of Golfo.
        "source": identity,
        "profileDigests": digests,
        "selectedProfiles": selected,
        "workspaceOrigins": workspace_origins,
        "profileSources": source_entries(catalog, selected, digests, (lock or {}).get("profileSources", {})),
        "sourceReport": source_report(catalog, selected, digests, lock),
        "versionChanges": version_changes(catalog, identity, lock),
        "lockedSource": lock.get("source") if lock else None,
        "hasLock": lock is not None,
        "entries": entries,
        "blocks": managed_blocks.classify(project_root, *without_waiting_sections(project_root, skill_dir,
                                                                                    {**blocks, **nested_blocks},
                                                                                    (lock or {}).get("blocks", {})),
                                          retiring_block_files),
        "nested": nested_report,
        "workspaces": workspaces,
        "nestedIndex": nested_index_report,
        "editedViews": edited_views,
        "detachedViews": preserved_views,
        "merged": merged,
        # What the selected pack profiles declare besides files; the policy judges them later.
        "packToolDeclarations": declared_pack_tools(catalog, selected),
        "overrides": [{"profile": by, "replaces": f"{target}{ASSET_REFERENCE_SEPARATOR}{path}"}
                      for target, paths in sorted(shared_overrides(skill_dir, catalog, resolved, workspace_profiles).items())
                      for path, by in sorted(paths.items())],
        # An override of a learned rule whose managed rule the profile changed since: «customized, review».
        "ruleOverrides": learning_customized.mark(project_root, published_rules,
                                                  resolved_rule_overrides(skill_dir, catalog, resolved, project_root,
                                                                          workspace_rule_destinations(workspace_rules))),
        # A learned rule that says what a rule of the profiles says now, as after a promotion: to retire.
        "learnedDuplicates": learning_promote.duplicates(project_root, published_rules),
    }


def declared_pack_tools(catalog, resolved):
    """pack_tools.declared_tools, with a conflict between two declarations as a ProfileError."""
    try:
        return pack_tools.declared_tools(catalog, resolved, source_of_profile, is_pack_profile, CONTENT_SOURCE_NAME)
    except pack_tools.DeclarationError as declaration_error:
        raise ProfileError(str(declaration_error)) from declaration_error


def global_effects(plan, skip_marketplace_upgrade, tools_enabled):
    """Effects outside the repository that an apply may have, with their scope."""
    effects = []
    if not skip_marketplace_upgrade:
        effects.append(("user", "refresh the golfo-marketplace snapshot through the provider CLI before projecting"))
    if any(item["type"] == SOURCE_TYPE_GIT for item in plan["sourceReport"].values()):
        effects.append(("user-cache", f"download pinned profile sources that are missing under {pack_cache_root()}"))
    if BROWSER_TOOL_NAME in plan["tools"]:
        if tools_enabled:
            effects.append(("user-cache", "install or reuse browser tools under ~/.local/share/agent-ready-setup/browser-tools (profile browser)"))
            effects.append(("project", "register browser MCP servers in .mcp.json and .codex/config.toml"))
        else:
            effects.append(("none", f"browser tools are selected but {TOOLS_ENABLED_KEY}: false skips them"))
    effects.append(("repository-config", "register a git config hook only if .claude views fall back to hard links"))
    return effects


def requirements(provider, skip_marketplace_upgrade, tools):
    """Commands the apply needs, with availability on this machine."""
    needed = [("git", "projection runs inside a Git worktree"), ("bash", "projection scripts")]
    if not skip_marketplace_upgrade and provider in SUPPORTED_PROVIDERS:
        needed.append((provider, "marketplace upgrade before projecting"))
    if BROWSER_TOOL_NAME in tools:
        needed.append(("node", "browser tools (profile browser)"))
        needed.append(("npm", "browser tools (profile browser)"))
    return [(command, reason, shutil.which(command) is not None) for command, reason in needed]


def render_diff(project_root, entry):
    """Unified diff between the local file and the new template content."""
    destination_path = os.path.join(project_root, entry["destination"])
    try:
        with open(destination_path, encoding="utf-8") as file_handle:
            current_lines = file_handle.readlines()
    except (OSError, UnicodeDecodeError):
        current_lines = []
    source_path = entry.get("sourcePath")
    try:
        with open(source_path, encoding="utf-8") as file_handle:
            new_lines = file_handle.readlines()
    except (OSError, TypeError, UnicodeDecodeError):
        new_lines = []
    return "".join(difflib.unified_diff(
        current_lines, new_lines, fromfile=f"a/{entry['destination']}", tofile=f"b/{entry['destination']}"
    ))


def print_detection_matches(detection):
    """List each stack that matched with its evidence, and the limits of the evaluation."""
    for name, evidence in sorted(detection["stacks"].items()):
        winners = detection["supersededBy"].get(name)
        note = f" (superseded by {', '.join(winners)})" if winners else ""
        write_line(f"  {name}: {format_evidence_list(evidence)}{note}")
    for warning in detection["warnings"]:
        write_line(paint(f"  ! {warning}", "warning", sys.stdout))


def describe_detected_stack(detection):
    """The outcome of a detection in one line."""
    if detection["status"] == STATUS_RESOLVED:
        return detection["primaryStack"]
    if detection["status"] == STATUS_AMBIGUOUS:
        return f"ambiguous ({', '.join(detection['candidates'])})"
    return "none"


def capability_suggestions(catalog, detection, resolved):
    """Detected capabilities the selection lacks: only reported, never applied."""
    profiles = catalog["profiles"]
    suggestions = []
    for name, evidence in sorted(detection["capabilities"].items()):
        conflicts = set(profiles[name].get("conflicts", []))
        is_compatible = not conflicts.intersection(resolved) and not any(
            name in profiles[selected].get("conflicts", []) for selected in resolved
        )
        if name not in resolved and is_compatible:
            suggestions.append({"profile": name, "evidence": evidence})
    return suggestions


def print_plan_detection(plan):
    """Detected signals and suggestions of a plan; neither changes the selection."""
    stream = sys.stdout
    detection = plan.get("detection")
    if detection is None:
        return
    write_line(paint("Detection (it informs; only a repository without a selection starts from it)", "heading", stream))
    write_line(f"  Detected stack: {describe_detected_stack(detection)}")
    print_detection_matches(detection)
    if detection["primaryStack"] and detection["primaryStack"] != plan["primaryStack"]:
        write_line(paint(
            f"  ! Signals point to {detection['primaryStack']}, but the selection from {plan['selection']} keeps "
            f"{plan['primaryStack'] or 'no stack'}; change it explicitly with --stack or --profiles.",
            "warning", stream,
        ))
    write_line("")
    if plan["suggestions"]:
        write_line(paint("Suggestions (not applied: nothing is added to the manifest or installed)", "heading", stream))
        for suggestion in plan["suggestions"]:
            write_line(f"  ? {suggestion['profile']}: {format_evidence_list(suggestion['evidence'])}")
        adopted = plan["profiles_requested"] + [suggestion["profile"] for suggestion in plan["suggestions"]]
        write_line(f"  Adopt them with --profiles {','.join(adopted)}")
        write_line("")
    if plan.get("workspaceSuggestions"):
        write_line(paint("Workspaces suggested (not applied: the manifest does not change)", "heading", stream))
        for suggestion in plan["workspaceSuggestions"]:
            write_line(f"  ? {suggestion['path']}: {', '.join(suggestion['profiles'])} "
                       f"({format_evidence_list(suggestion['evidence'])})")
            write_line(f"    Add it with agent-ready workspaces add {suggestion['path']}")
        write_line("")


def added_dependencies(catalog, requested, resolved):
    """Profiles that the selection did not name: {name: {"requiredBy": [...], "defaultOf": [...]}}."""
    added = {}
    profiles = catalog["profiles"]
    for name in resolved:
        # The CI profiles come from ci.provider, not from a profile that requires them.
        if name not in requested and profiles[name].get("kind") != CI_PROFILE_KIND:
            added[name] = {
                "requiredBy": sorted(other for other in resolved if name in profiles[other].get("requires", [])),
                "defaultOf": sorted(other for other in resolved if name in profiles[other].get(DEFAULTS_KEY, [])),
            }
    return added


def print_plan_sources(plan):
    """Declared sources and how they differ from the lock."""
    if not plan["sourceReport"]:
        return
    stream = sys.stdout
    write_line(paint("Profile sources (updates are always explicit)", "heading", stream))
    for name, item in plan["sourceReport"].items():
        write_line(f"  {describe_source_item(name, item)}")
        if item["differences"]:
            changes = "; ".join(item["differences"])
            write_line(paint(f"  ! {name} differs from the lock: {changes}; an apply adopts it", "warning", stream))
        if item["pendingUpdate"]:
            write_line(paint(f"  ! {name}: {item['pendingUpdate']}", "warning", stream))
    write_line("")


def semantic_conflicts(arguments, plan, instructions_with_applied=False):
    """The AI review of managed rules against the project's own, or None when it is off.

    ``instructions_with_applied`` also pairs the project's AGENTS.md with the rules already applied,
    for a check of the whole repository rather than of what an apply changes.
    """
    configuration = configuration_of(arguments.project, arguments.offline)
    if not configuration.value(CONFLICTS_ENABLED_KEY) or not configuration.value(REVIEWS_ENABLED_KEY):
        conflicts_review.record_pending(arguments.project, [], check=conflicts_review.CONFLICT_CHECK)
        return None
    if not conflicts_review.engine_can_review(ENGINE_SKILL_DIRECTORY):
        return None
    module = review_cache_module()
    lock = read_lock(arguments.project)
    nested_files = nested_instruction_files(plan)
    directions, texts = conflicts_review.conflict_pairs(
        arguments.project, plan["entries"], (lock or {}).get("assets", {}), module.normalized_text,
        project_owned_instructions, ENGINE_SKILL_DIRECTORY, is_pack_profile, instructions_with_applied, nested_files,
        blocking_hook_documents(arguments.project, configuration))
    # Offline runs and automated reviews answer from the cache only.
    use_provider = not arguments.offline and os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") != "1"
    # The options of this run: the hooks' copy of them only changes when an apply finishes.
    settings = {"enabled": True, "cache": configuration.value(REVIEWS_CACHE_KEY),
                "ttl": configuration.value(REVIEWS_TTL_KEY), "commit": configuration.value(REVIEWS_COMMIT_KEY),
                "redundancy": configuration.value(REVIEWS_REDUNDANCY_KEY)}
    report = conflicts_review.review_conflicts(arguments.project, ENGINE_SKILL_DIRECTORY, module, arguments.provider,
                                               directions, texts, bash_executable(), use_provider, settings,
                                               publish=arguments.format == "protected")
    conflicts_review.record_pending(arguments.project, report.pop("pending", []), check=conflicts_review.CONFLICT_CHECK)
    report["block"] = configuration.value(CONFLICTS_BLOCK_KEY)
    levels = conflicts_review.document_levels(plan["entries"], nested_files)
    for finding in report["findings"] + report["redundancies"]:
        finding["levels"] = [levels.get(module.document_path(name), conflicts_review.ROOT_LEVEL)
                             for name in finding.get("files", [])]
    return report


def blocking_hook_documents(project_root, configuration):
    """The hooks that can stop a tool call, as documents of the conflict review (conflicts.hooks.enabled)."""
    if not configuration.value(HOOK_CONFLICTS_ENABLED_KEY):
        return {}
    return review_cache_module().hook_documents(project_root)


def nested_instruction_files(plan):
    """The nested AGENTS.md files the apply writes blocks to: the ones of the workspaces and of the nested
    targets."""
    return sorted({entry["destination"] for entry in plan.get("blocks", [])
                   if entry["destination"].endswith(conflicts_review.NESTED_AGENTS_SUFFIX)})


def describe_conflict(finding):
    module = review_cache_module()
    if any(module.is_hooks_document(name) for name in finding.get("files", [])):
        # A hook that can stop what a rule or skill asks for: the hook is the project's, never a rule.
        subject = "this update" if finding["direction"] == conflicts_review.DIRECTION_UPDATE else "a hook of the project"
        return f"{module.finding_line(finding)} ({subject}; a hook that blocks it)"
    direction = {conflicts_review.DIRECTION_UPDATE: "this update",
                 conflicts_review.DIRECTION_PROFILES: "two profiles",
                 conflicts_review.DIRECTION_LEVELS: "two levels"}.get(finding["direction"], "a project rule")
    levels = finding.get("levels") or []
    if len(set(levels)) > 1:
        # Each file with its level: the root, a workspace, or the folder of a nested AGENTS.md.
        direction += "; " + " and ".join(level if level == conflicts_review.ROOT_LEVEL else f"{level}/"
                                         for level in levels)
    return f"{review_cache_module().finding_line(finding)} ({direction})"


def print_conflict_warnings(report):
    """The apply shows its semantic conflicts on stderr, before writing; the protected list stays on stdout."""
    for finding in report["findings"]:
        write_line(f"WARNING: semantic conflict {describe_conflict(finding)}", sys.stderr)
    for finding in report.get("redundancies", []):
        write_line(f"WARNING: redundant rules {describe_conflict(finding)}", sys.stderr)
    if report["unchecked"]:
        write_line(f"WARNING: {report['unchecked']} pair(s) were not checked for semantic conflicts: {report['reason']}",
                   sys.stderr)


def print_plan_conflicts(plan):
    """Semantic conflicts of managed rules with the project's own, from the AI review and its cache."""
    report = plan.get("semanticConflicts")
    if not report or not report["pairs"]:
        return
    stream = sys.stdout
    write_line(paint("Semantic conflicts (AI review of the managed rules and the project's own)", "heading", stream))
    for finding in report["findings"]:
        write_line(paint(f"  {describe_conflict(finding)}", "warning", stream))
        for line in finding.get("lines", []):
            write_line(f"      {line}")
    redundancies = report.get("redundancies", [])
    if redundancies:
        # A warning: it neither stops an apply under conflicts.block nor fails agent-ready check.
        write_line(paint("  Redundant rules (a warning; keep one of each pair):", "warning", stream))
        for finding in redundancies:
            write_line(paint(f"  {describe_conflict(finding)}", "warning", stream))
            for line in finding.get("lines", []):
                write_line(f"      {line}")
    if report["findings"] or redundancies:
        write_line("  Accept or dismiss one with: agent-ready review accept <id> --reason \"...\"")
    if report["unchecked"]:
        write_line(paint(f"  Check incomplete: {report['unchecked']} of {report['pairs']} pairs were not reviewed "
                         f"({report['reason']}).", "warning", stream))
    elif not report["findings"] and not redundancies:
        write_line(f"  No conflicts found ({report['pairs']} pairs, {report['fromCache']} from the cache).")
    if report["block"]:
        write_line("  conflicts.block: an apply that brings a conflict stops before writing.")
    write_line("")


def print_plan_versions(plan):
    """Version jumps of the sources and the changes they declare, breaking ones first in the eye."""
    if not plan.get("versionChanges"):
        return
    stream = sys.stdout
    write_line(paint("Version changes (what each source declares in its changelog)", "heading", stream))
    for item in plan["versionChanges"]:
        jump = paint("  (major version jump)", "warning", stream) if item["majorJump"] else ""
        write_line(f"  {item['source']} {item['from']} -> {item['to']}{jump}")
        if not item["changes"]:
            write_line(paint("    no changelog declared for these versions", "muted", stream))
        for change in item["changes"]:
            if change.get("breaking"):
                write_line(paint(f"    ! breaking {change['version']}: {change['summary']}", "error", stream))
            else:
                write_line(f"    - {change['version']}: {change['summary']}")
    write_line("")


def print_plan_blocks(project_root, plan, counts, stream):
    """The managed blocks of files shared with the project, with the diff of each one that changes."""
    entries = plan.get("blocks", [])
    if not entries:
        return
    write_line(paint("Managed blocks (the rest of each file is the project's)", "heading", stream))
    for entry in entries:
        counts[entry["action"]] = counts.get(entry["action"], 0) + 1
        if entry["action"] == ACTION_UNCHANGED:
            continue
        symbol = ACTION_SYMBOLS.get(entry["action"], "!")
        label = f"{symbol} {entry['action']:<15} {entry['destination']} (block {entry['id']})"
        write_line("  " + paint(label, entry["action"] if entry["action"] in ANSI_COLORS else "muted", stream)
                   + f"  {entry['reason']}")
        if entry["action"] in (ACTION_CREATE, ACTION_UPDATE, ACTION_RETIRE):
            before, after = managed_blocks.diff_text(project_root, entry)
            if entry["action"] == ACTION_RETIRE:
                after = ""
            diff = difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        f"{entry['destination']} (block {entry['id']}, local)",
                                        f"{entry['destination']} (block {entry['id']}, template)")
            for line in diff:
                write_line("      " + line.rstrip("\n"))
    write_line("")


def print_plan(project_root, skill_dir, plan, provider, skip_marketplace_upgrade, configuration):
    """Human readable plan on stdout."""
    stream = sys.stdout
    write_line(paint("Agent Ready plan (read-only: nothing was written)", "heading", stream))
    if plan["profiles"]:
        write_line(f"Profiles: {', '.join(plan['profiles'])} (primary stack: {plan['primaryStack'] or 'none'})")
    else:
        write_line("Profiles: none (the core only: no stack and no capability)")
    write_line(f"Selected by: {plan['selection']}")
    for name, origin in plan["addedDependencies"].items():
        reasons = []
        if origin["requiredBy"]:
            reasons.append(f"required by {', '.join(origin['requiredBy'])}")
        if origin["defaultOf"]:
            reasons.append(f"default of {', '.join(origin['defaultOf'])}")
        write_line(f"Profile added: {name} ({'; '.join(reasons)})")
    excluded = configuration.value(EXCLUDED_DEFAULTS_KEY) or []
    if excluded:
        write_line(f"Defaults left out: {', '.join(excluded)} ({EXCLUDED_DEFAULTS_KEY})")
    for override in plan.get("overrides", []):
        write_line(f"Overridden: {override['replaces']} by {override['profile']} (only its own asset is projected)")
    duplicated = {duplicate["learningId"] for duplicate in plan.get("learnedDuplicates", [])}
    for override in plan.get("ruleOverrides", []):
        write_line(f"Rule overridden: {override['replaces']} by {override['rule']} of {override['profile']} "
                   f"({override['targetPath']} keeps its other rules)")
        # A learned rule the profile now says too is reported as a duplicate below, not to review.
        if override.get("customized") and override["customized"]["learningId"] not in duplicated:
            learning_id = override["customized"]["learningId"]
            write_line(f"  customized, review: the profile changed {override['replaces']} since {learning_id} replaced "
                       f"it; the learned version stays. Keep it (agent-ready learn keep {learning_id}) or take the "
                       f"profile's (agent-ready learn retire {learning_id})")
    for duplicate in plan.get("learnedDuplicates", []):
        write_line(f"Learned rule duplicated: {duplicate['rule']} ({duplicate['learningId']}) says what "
                   f"{duplicate['duplicates']} of {duplicate['profile']} says now. Retire it with agent-ready learn "
                   f"retire {duplicate['learningId']}")
    for workspace in plan.get("workspaces", []):
        write_line(f"Workspace {workspace_selection.describe(workspace)}")
        if workspace.get("rules"):
            write_line(f"  {workspace['rules']} rule(s) in .agents/rules/{workspace_selection.WORKSPACE_RULES_DIRECTORY}/"
                       f"{workspace['path']}/, listed in {nested.destination_in(workspace['path'])}")
        if workspace.get("sharedAssets"):
            write_line(f"  {workspace['sharedAssets']} skill, subagent and command file(s) of its profiles in .agents/, "
                       "for the whole repository")
    for target in plan.get("nested", []):
        suffix = f" (workspace {target['workspace']})" if target.get("workspace") else ""
        write_line(f"Nested AGENTS.md: {nested.describe(target)}{suffix}")
    index = plan.get("nestedIndex") or {}
    if index.get("destinations"):
        write_line(f"Nested AGENTS.md index for Codex: {len(index['destinations'])} file(s) listed in AGENTS.md, "
                   f"~{index['bytes']} bytes of its limit")
    if plan.get("context"):
        print_context_budget(plan["context"])
    print_machine_report(plan.get("machine"))
    print_repo_reality(plan.get("repoReality", []))
    print_rule_keys(plan.get("ruleKeys", []))
    print_settings_conflicts(plan.get("settingsConflicts", {}))
    print_parity_report(plan.get("parity", {}))
    print_competing_tools(plan.get("competingTools", []))
    print_competing_skills(plan.get("competingSkills"))
    write_line(f"Source:   {describe_source(plan['source'])}")
    write_line(f"Lock:     {describe_source(plan['lockedSource']) if plan['hasLock'] else 'none (first apply creates it)'}")
    write_line("")
    write_line(paint("Configuration (effective value and the layer it comes from)", "heading", stream))
    print_configuration_values(configuration)
    print_ignored_configuration(configuration, stream)
    write_line("")
    print_plan_sources(plan)
    print_plan_versions(plan)
    print_plan_conflicts(plan)
    print_pack_tools(plan.get("packTools"), sys.stdout)
    print_plan_detection(plan)
    write_line(paint("Project assets", "heading", stream))
    counts = {}
    for entry in plan["entries"]:
        counts[entry["action"]] = counts.get(entry["action"], 0) + 1
        if entry["action"] == ACTION_UNCHANGED:
            continue
        symbol = ACTION_SYMBOLS[entry["action"]]
        label = f"{symbol} {entry['action']:<15} {entry['destination']}"
        write_line("  " + paint(label, entry["action"] if entry["action"] in ANSI_COLORS else "muted", stream)
                   + f"  [{entry['profile']}] {entry['reason']}")
        for line in rule_changes.rule_change_lines(entry):
            write_line(paint(line, "warning", stream) if line.lstrip().startswith("!") else line)
    view_groups = (
        (plan["editedViews"], ACTION_UPDATE, EDITED_VIEW_REASON),
        (plan["detachedViews"], ACTION_CONFLICT, DETACHED_VIEW_REASON),
    )
    for views, action, reason in view_groups:
        for view in views:
            counts[action] = counts.get(action, 0) + 1
            label = f"{ACTION_SYMBOLS[action]} {action:<15} {view}"
            write_line("  " + paint(label, action, stream) + f"  [view] {reason}")
    write_line(f"  = unchanged: {counts.get(ACTION_UNCHANGED, 0)}")
    write_line("")
    print_plan_blocks(project_root, plan, counts, stream)
    write_line(paint("Merged files (project content preserved)", "heading", stream))
    for destination, action, reason in merged_file_changes(project_root, skill_dir, plan):
        write_line(f"  {ACTION_SYMBOLS[action]} {destination}: {reason}")
    drifted_proxies = claude_proxy_drift(project_root, skill_dir)
    if drifted_proxies:
        write_line(f"  ~ {len(drifted_proxies)} CLAUDE.md file(s) would be normalized to the proxy: {', '.join(drifted_proxies)}")
    write_line("")
    write_line(paint("Effects outside project assets (not applied by plan)", "heading", stream))
    for scope, description in global_effects(plan, skip_marketplace_upgrade, configuration.value(TOOLS_ENABLED_KEY)):
        write_line(f"  - [{scope}] {description}")
    write_line("")
    write_line(paint("Requirements", "heading", stream))
    for command, reason, available in requirements(provider, skip_marketplace_upgrade, plan["tools"]):
        marker = paint("ok", "ok", stream) if available else paint("missing", "error", stream)
        write_line(f"  {marker:<7} {command}: {reason}")
    diff_entries = [entry for entry in plan["entries"] if entry["action"] in (ACTION_UPDATE, ACTION_ADOPT, ACTION_CONFLICT)]
    if diff_entries:
        write_line("")
        write_line(paint("Diffs (local -> template)", "heading", stream))
        for entry in diff_entries:
            write_line(render_diff(project_root, entry).rstrip("\n"))
    reviews = review_summary(project_root)
    if reviews["units"] or reviews["stale"]:
        write_line("")
        print_review_summary(reviews, False, stream)
    write_line("")
    summary = ", ".join(f"{counts[action]} {action}" for action in sorted(counts) if action != ACTION_UNCHANGED) or "no changes"
    write_line(paint(f"Summary: {summary}", "heading", stream))


def print_incomplete_plan(project_root, skill_dir, selection, requested, incomplete_error):
    """Say what could not be evaluated. This is not a plan, so it lists no asset decision."""
    stream = sys.stdout
    write_line(paint("Agent Ready plan INCOMPLETE (read-only: nothing was written or downloaded)", "error", stream))
    write_line(f"Requested profiles: {', '.join(requested)}")
    write_line(f"Selected by: {selection}")
    write_line(paint(f"Could not evaluate: {incomplete_error}", "error", stream))
    catalog = load_effective_catalog(project_root, skill_dir)
    report = source_report_without_selection(catalog)
    if report:
        write_line("Profile sources:")
        for name, line in report.items():
            write_line(f"  {name}: {line}")
    write_line("This is not a validated plan. Run it without --offline, or an apply, to download what is missing.")


def compute_status(project_root, skill_dir, conflicts_key=None):
    """Read-only state: manifest, checkout versus lock, source versus lock.

    ``conflicts_key`` also lists the structural conflicts of the selection when that boolean key is
    on (True always lists them); without it, status stays as cheap as the checks that call it.
    """
    manifest = read_manifest(project_root)
    configuration = configuration_of(project_root)
    lock = read_lock(project_root)
    status = {
        "manifest": manifest,
        "configuration": configuration,
        "hasLock": lock is not None,
        "lockedSource": lock.get("source") if lock else None,
        "checkout": {"applied": [], "modified": [], "missing": [], "conflict": [], "failed": [], "retiredPreserved": []},
        "update": None,
        "capabilities": {},
        "errors": [],
        "incomplete": None,
        "sources": {},
        "selectionDifferences": [],
        "reviews": review_summary(project_root),
        "packTools": None,
        "workspaceDifferences": workspace_selection.differences(configuration.value(WORKSPACES_KEY) or [],
                                                                (lock or {}).get("workspaces") or {}) if lock else [],
    }
    if lock:
        for destination, entry in sorted(lock["assets"].items()):
            local = local_state(os.path.join(project_root, destination))
            state = entry.get("state", STATE_APPLIED)
            if state == STATE_FAILED:
                status["checkout"]["failed"].append(destination)
            elif state == STATE_RETIRED_PRESERVED:
                status["checkout"]["retiredPreserved"].append(destination)
            elif state == STATE_CONFLICT:
                status["checkout"]["conflict"].append(destination)
            elif local == LOCAL_ABSENT:
                status["checkout"]["missing"].append(destination)
            elif local != entry.get("sha256"):
                status["checkout"]["modified"].append(destination)
            else:
                status["checkout"]["applied"].append(destination)
        for destination in sorted(lock.get("merged", {})):
            if local_state(os.path.join(project_root, destination)) == LOCAL_ABSENT:
                status["checkout"]["missing"].append(destination)
        status["checkout"]["failed"].extend(
            label for label, entry in sorted(managed_blocks.inventory(lock).items()) if entry.get("state") == STATE_FAILED)

    manifest_profiles = configuration.value(PROFILES_KEY)
    # An empty selection is a selection too: the core-only repository gets the same drift checks.
    profile_names = manifest_profiles if manifest_profiles is not None else (lock.get("profileOrder") if lock else None)
    if profile_names is not None and skill_dir:
        try:
            catalog = load_effective_catalog(project_root, skill_dir)
            if manifest_profiles:
                # compute_plan drops the CI profiles of a lock; a manifest that names one is an error.
                rejecting_ci_profiles(catalog, manifest_profiles)
            plan = compute_plan(project_root, skill_dir, catalog, profile_names)
        except IncompleteEvaluationError as caught_error:
            status["incomplete"] = str(caught_error)
        except (ProfileError, StateError) as caught_error:
            status["errors"].append(str(caught_error))
        else:
            status["sources"] = plan["sourceReport"]
            status["plan"] = plan
            status["packTools"] = pack_tools_report(plan, catalog, configuration)
            if conflicts_key is True or (conflicts_key and configuration.value(conflicts_key)):
                if status["packTools"]:
                    plan["packTools"] = status["packTools"]
                status["conflicts"] = structural_conflict_lines(
                    structural_conflicts(project_root, skill_dir, plan, catalog, configuration, with_context=False))
            changed = [entry["destination"] for entry in plan["entries"]
                       if entry["action"] not in (ACTION_UNCHANGED, ACTION_DROP)]
            changed += [f"{entry['destination']} (block {entry['id']})" for entry in plan.get("blocks", [])
                        if entry["action"] not in (ACTION_UNCHANGED, ACTION_DROP)]
            status["checkout"]["modified"].extend(plan["editedViews"] + plan["detachedViews"])
            # A block someone edited by hand, or whose file lost it: the next apply writes it again.
            status["checkout"]["modified"].extend(
                f"{entry['destination']} (block {entry['id']})" for entry in plan.get("blocks", [])
                if entry["baseSha256"] and entry["sha256"] and entry["localSha256"] != entry["baseSha256"]
                and entry["action"] not in (ACTION_CONFLICT, ACTION_RETIRE_CONFLICT))
            # A block the apply cannot write: broken markers, or the file or a directory on its path is a symlink.
            status["checkout"]["conflict"].extend(
                f"{entry['destination']} (block {entry['id']})" for entry in plan.get("blocks", [])
                if entry["action"] in (ACTION_CONFLICT, ACTION_RETIRE_CONFLICT))
            if lock:
                published = [entry for entry in plan["entries"] if entry["sha256"]]
                views = [claude_view_of(entry["destination"], entry["source"]) for entry in published]
                status["checkout"]["missing"].extend(
                    view for view in views if view and local_state(os.path.join(project_root, view)) == LOCAL_ABSENT
                )
            locked = lock or {}
            status["selectionDifferences"] = selection_differences(locked, plan)
            selection_changed = bool(status["selectionDifferences"])
            sources_changed = any(item["differences"] or item["pendingUpdate"] for item in plan["sourceReport"].values())
            status["update"] = {
                "available": selection_changed or sources_changed
                or locked.get("source", {}).get("contentDigest") != plan["source"]["contentDigest"],
                "source": plan["source"],
                "changedDestinations": changed,
            }
    if skill_dir:
        provider_path = os.path.join(skill_dir, PROVIDER_CATALOG_RELATIVE_PATH)
        if os.path.isfile(provider_path):
            providers_catalog = read_json_file(provider_path, "provider catalog").get("providers", {})
            for provider in configuration.value(PROVIDERS_KEY):
                if provider in providers_catalog:
                    status["capabilities"][provider] = providers_catalog[provider]["capabilities"]
                else:
                    status["errors"].append(f"provider '{provider}' is not supported by agent-ready-setup")
    status["learningSweep"] = learning_sweep_status(project_root)
    # The last run of agent-ready sync on this checkout, or None when it never ran here.
    status["teamSync"] = team_sync.read_state(project_root) or None
    return status


def learning_sweep_status(project_root):
    """{"ok", "detail"} of the scheduled learning sweep, or None when the repository does not use it."""
    # Imported here: the CLI of learning pulls the whole learning engine.
    from agent_ready_cli_learning import schedule_state

    try:
        found = schedule_state(project_root)
    except (StateError, OSError) as problem:
        return {"ok": False, "detail": str(problem)}
    return None if found is None else {"ok": found[0], "detail": found[1]}
