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
import difflib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import types

# Shared modules load from this script's own directory and leave no bytecode beside
# the skill source, which may be a read-only snapshot.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_ready_common import (  # noqa: E402
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
    run_quiet,
    serialize_json,
    sha256_of_file,
    text_bytes,
    walk_files,
    write_text_atomically,
    write_text_if_changed,
)
from agent_ready_lockfile import (  # noqa: E402
    LOCK_RELATIVE_PATH,
    SCHEMA_VERSION,
    STATE_APPLIED,
    STATE_CONFLICT,
    STATE_FAILED,
    STATE_RETIRED_PRESERVED,
    read_lock,
    was_applied,
)
from agent_ready_background import command_background_update, command_update_report  # noqa: E402
import agent_ready_removal as removal  # noqa: E402
from agent_ready_desired_assets import (  # noqa: E402
    compose_stack_directory,
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
from agent_ready_layout import (  # noqa: E402
    AGENTS_SKELETON_NAME,
    CENTRALIZATION_RELATIVE_PATH,
    CLAUDE_PROXY_RELATIVE_PATH,
    ENGINE_SKILL_DIRECTORY,
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
    MANIFEST_RELATIVE_PATH,
    PROFILE_CATALOG_RELATIVE_PATH,
    PROVIDER_CATALOG_RELATIVE_PATH,
    RENDERER_RELATIVE_PATH,
    claude_view_of,
    review_cache_module,
)
from agent_ready_profiles import (  # noqa: E402
    ASSET_REFERENCE_SEPARATOR,
    CI_PROFILE_KIND,
    DEFAULTS_KEY,
    load_effective_catalog,
    load_profile_catalog,
    locked_sources_of,
    primary_stack,
    profiles_for_stack,
    resolve_profiles,
    resolve_project_profiles,
    resolved_tools,
    split_profile_names,
)
from agent_ready_source_identity import (  # noqa: E402
    agents_template_path,
    enforce_lock_reproduction,
    enforce_sync_policy,
    golfo_blocks,
    keep_locked_entries_of_unselected_sources,
    merged_template_entries,
    source_entries,
    source_identity,
    source_report,
    validate_pack_destinations,
    version_changes,
)
from agent_ready_actions import (  # noqa: E402
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
from agent_ready_finalize import (  # noqa: E402
    finalize,
    machine_report,
    machine_report_lines,
    print_finalize_report,
    print_machine_report,
    waiting_instruction_files,
    without_waiting_sections,
)
from agent_ready_manifest import (  # noqa: E402
    configuration_of,
    declared_sources,
    print_ignored_configuration,
    read_manifest,
)
from agent_ready_review_findings import project_owned_instructions, review_summary  # noqa: E402
from agent_ready_status import (  # noqa: E402
    conflict_inputs_changed,
    describe_source,
    describe_source_item,
    pack_tools_report,
    print_pack_tools,
    print_review_summary,
    print_status,
    selection_differences,
    status_has_drift,
)
from agent_ready_output import ANSI_COLORS, paint, write_line  # noqa: E402
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
    DETECTION_WORKSPACES_KEY,
    CONTEXT_BUDGET_BYTES_KEY,
    CONTEXT_BUDGET_ENABLED_KEY,
    CONTEXT_BUDGET_RULES_BYTES_KEY,
    REPO_REALITY_ENABLED_KEY,
    HOOK_CONFLICTS_ENABLED_KEY,
    PERMISSION_CONFLICTS_ENABLED_KEY,
    PROVIDER_PARITY_ENABLED_KEY,
    ENVIRONMENT_CONFLICTS_ENABLED_KEY,
    CI_JOB_CONFLICTS_ENABLED_KEY,
    COMPETING_TOOLS_ENABLED_KEY,
    COMPETING_SKILLS_ENABLED_KEY,
    EDIT_CONFLICTS_ENABLED_KEY,
    SESSION_START_CONFLICTS_ENABLED_KEY,
    EXCLUDED_DEFAULTS_KEY,
    WORKSPACES_KEY,
    PROFILES_KEY,
    PROVIDERS_KEY,
    REVIEWS_CACHE_KEY,
    CONFLICTS_BLOCK_KEY,
    CONFLICTS_ENABLED_KEY,
    REVIEWS_ENABLED_KEY,
    REVIEWS_COMMIT_KEY,
    REVIEWS_TTL_KEY,
    SUPPORTED_PROVIDERS,
    TOOLS_ENABLED_KEY,
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
import agent_ready_repo_facts as repo_facts  # noqa: E402
import agent_ready_settings_conflicts as settings_conflicts  # noqa: E402
import agent_ready_skill_overlap as skill_overlap  # noqa: E402
import agent_ready_pack_mcp as pack_mcp  # noqa: E402
import agent_ready_parity as parity  # noqa: E402
import agent_ready_pack_scripts as pack_scripts  # noqa: E402
import agent_ready_blocks as managed_blocks  # noqa: E402
import agent_ready_nested as nested  # noqa: E402
import agent_ready_workspaces as workspace_selection  # noqa: E402
import agent_ready_pack_tools as pack_tools  # noqa: E402
import agent_ready_content as content_source  # noqa: E402
from agent_ready_packs import (  # noqa: E402
    KEBAB_CASE_NAME,
    PACK_CATALOG_FILE_NAME,
    SOURCE_AVAILABLE,
    SOURCE_TYPE_GIT,
    download_declared_sources,
    effective_update_mode,
    is_pack_profile,
    pack_cache_root,
    refresh_declared_sources,
    source_of_profile,
)

# Infers the provider of a run from the environment and the installation path.
PROVIDER_RESOLVER_RELATIVE_PATH = "scripts/resolve-provider.sh"
SETTINGS_MERGER_RELATIVE_PATH = "scripts/merge-managed-settings.py"
CODEX_HOOKS_MERGER_RELATIVE_PATH = "scripts/merge-codex-hooks.py"
PLUGIN_NAME = "golfo-kit"
SETTINGS_TEMPLATE_FALLBACK_STATUS = 10
# Results of `check` and their exit statuses: the stable contract of a CI pipeline.
CHECK_UP_TO_DATE = "up-to-date"
CHECK_OUTDATED = "outdated"
CHECK_SOURCE_UNAVAILABLE = "source-unavailable"
CHECK_CONFIG_ERROR = "config-error"
CHECK_SKIPPED = "skipped"
CHECK_CONFLICTS = "conflicts"
BROWSER_TOOL_NAME = "browser"
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
# Plan
# ---------------------------------------------------------------------------


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


def composed_workspace_assets(skill_dir, catalog, resolved, workspaces):
    """(profiles only workspaces select, workspace rules, shared texts, desired assets) of a selection.

    It raises ProfileError for what an apply cannot compose: an override of a root asset, two profiles of
    a workspace that publish one rule, two assets with one destination.
    """
    workspace_profiles = workspace_selection.added_profiles(resolved, workspaces)
    workspace_rules = workspace_rule_files(skill_dir, catalog, workspaces)
    shared_texts = workspace_shared_texts(skill_dir, catalog, workspaces, workspace_profiles, workspace_rules)
    assets = desired_assets(skill_dir, catalog, resolved, workspace_rules, workspace_profiles, shared_texts)
    return workspace_profiles, workspace_rules, shared_texts, assets


def check_workspace_composition(project_root, skill_dir, catalog, resolved, workspaces):
    """Raise ProfileError when an apply could not project these workspaces: their assets
    (composed_workspace_assets), the destinations of their packs and their blocks. agent-ready workspaces
    add runs it before it writes the manifest."""
    _, workspace_rules, _, assets = composed_workspace_assets(skill_dir, catalog, resolved, workspaces)
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
    workspace_profiles, workspace_rules, _, assets = composed_workspace_assets(skill_dir, catalog, resolved, workspaces)
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
    }


def declared_pack_tools(catalog, resolved):
    """pack_tools.declared_tools, with a conflict between two declarations as a ProfileError."""
    try:
        return pack_tools.declared_tools(catalog, resolved, source_of_profile, is_pack_profile)
    except pack_tools.DeclarationError as declaration_error:
        raise ProfileError(str(declaration_error)) from declaration_error


def extract_managed_block(text):
    """Text between the managed markers (inclusive), or None."""
    start = text.find(MANAGED_BLOCK_START)
    end = text.find(MANAGED_BLOCK_END)
    if start < 0 or end < start:
        return None
    return text[start:end + len(MANAGED_BLOCK_END)]


def render_instructions(skill_dir, catalog, stack_root, project_rules_root, managed_block_only):
    """AGENTS.md as render-instruction-template.sh writes it, or only its managed block; None on failure.

    The new file takes the skeleton of the composed tree when a profile publishes one, as the
    instruction normalization does.
    """
    renderer = [
        bash_executable(), os.path.join(skill_dir, RENDERER_RELATIVE_PATH),
        "--template", agents_template_path(skill_dir, catalog),
        "--rules-dir", os.path.join(stack_root, "rules"),
        "--common-rules-dir", os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"), "rules"),
        "--centralization", os.path.join(skill_dir, CENTRALIZATION_RELATIVE_PATH),
    ]
    if managed_block_only:
        renderer.append("--managed-block")
    else:
        skeleton = os.path.join(stack_root, AGENTS_SKELETON_NAME)
        if os.path.isfile(skeleton):
            renderer += ["--skeleton", skeleton]
    if project_rules_root:
        renderer += ["--project-rules-dir", project_rules_root]
    try:
        completed = subprocess.run(renderer, capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    return completed.stdout if completed.returncode == 0 else None


def merged_file_changes(project_root, skill_dir, plan, source_state=None):
    """Describe whether each merged file would change, without writing it."""
    # The effective catalog: composing the tree needs the asset roots of the pack profiles too.
    catalog = load_effective_catalog(project_root, skill_dir, source_state)
    # Bootstrap exports the composed tree, the one the managed block is rendered from; without it the
    # tree is composed in a temporary directory, so a plan still writes nothing of its own.
    stack_root = os.environ.get("AGENT_READY_SETUP_STACK_DIR")
    if stack_root:
        return merged_file_changes_from(project_root, skill_dir, plan, catalog, stack_root)
    with tempfile.TemporaryDirectory(prefix="agent-ready-plan-compose.") as compose_root:
        stack_root = compose_stack_directory(skill_dir, catalog, plan["profiles"], compose_root)
        return merged_file_changes_from(project_root, skill_dir, plan, catalog, stack_root)


def merged_file_changes_from(project_root, skill_dir, plan, catalog, stack_root):
    """merged_file_changes with the stack tree the managed block is rendered from."""
    changes = []

    agents_path = os.path.join(project_root, "AGENTS.md")
    project_rules_root = os.path.join(project_root, ".agents", "rules")
    rendered_block = render_instructions(skill_dir, catalog, stack_root,
                                         project_rules_root if os.path.isdir(project_rules_root) else None,
                                         managed_block_only=True)
    if not os.path.isfile(agents_path):
        changes.append(("AGENTS.md", ACTION_CREATE, "created from the base template"))
    else:
        with open(agents_path, encoding="utf-8") as file_handle:
            current_block = extract_managed_block(file_handle.read())
        if current_block is None:
            changes.append(("AGENTS.md", ACTION_UPDATE, "no managed block yet; the instruction review migrates it"))
        elif rendered_block is None:
            changes.append(("AGENTS.md", ACTION_CONFLICT, "managed block could not be rendered"))
        elif extract_managed_block(rendered_block) != current_block:
            changes.append(("AGENTS.md", ACTION_UPDATE, "managed block changes; project content is preserved"))
        else:
            changes.append(("AGENTS.md", ACTION_UNCHANGED, "managed block is current"))

    for destination, merger, extra_arguments in (
        (".claude/settings.json", SETTINGS_MERGER_RELATIVE_PATH, ["--allow-nested-template-match"]),
        (".codex/hooks.json", CODEX_HOOKS_MERGER_RELATIVE_PATH, []),
    ):
        entry = plan["merged"].get(destination)
        if not entry:
            continue
        template = os.path.join(skill_dir, entry["template"])
        current = os.path.join(project_root, destination)
        if not os.path.isfile(current):
            changes.append((destination, ACTION_CREATE, "created from the template"))
            continue
        command = [sys.executable, os.path.join(skill_dir, merger)] + extra_arguments + [template, current]
        try:
            completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", check=False)
        except OSError as caught_error:
            changes.append((destination, ACTION_CONFLICT, f"merge preview failed: {caught_error}"))
            continue
        merged_text = completed.stdout
        if completed.returncode == SETTINGS_TEMPLATE_FALLBACK_STATUS:
            with open(template, encoding="utf-8") as file_handle:
                merged_text = file_handle.read()
        elif completed.returncode != 0:
            changes.append((destination, ACTION_CONFLICT, "invalid JSON; it is preserved"))
            continue
        with open(current, encoding="utf-8") as file_handle:
            current_text = file_handle.read()
        if merged_text == current_text:
            changes.append((destination, ACTION_UNCHANGED, "managed entries are current"))
        else:
            changes.append((destination, ACTION_UPDATE, "managed entries change; custom entries are preserved"))
    return changes


def claude_proxy_drift(project_root, skill_dir):
    """CLAUDE.md files that instruction normalization would rewrite or create."""
    proxy_path = os.path.join(skill_dir, CLAUDE_PROXY_RELATIVE_PATH)
    listed = run_quiet(["git", "ls-files", "-co", "--exclude-standard"], cwd=project_root)
    if listed is None or not os.path.isfile(proxy_path):
        return []
    proxy_hash = sha256_of_file(proxy_path)
    listed_paths = listed.splitlines()
    existing_proxies = {path.casefold() for path in listed_paths if os.path.basename(path).lower() == "claude.md"}
    drifted = []
    # The root always needs its proxy, and so does every AGENTS.md: it is what loads the instructions.
    required_proxies = {"CLAUDE.md"}
    for relative_path in listed_paths:
        file_name = os.path.basename(relative_path).lower()
        if file_name == "agents.md":
            required_proxies.add(os.path.join(os.path.dirname(relative_path), "CLAUDE.md").replace(os.sep, "/"))
        elif file_name == "claude.md":
            absolute_path = os.path.join(project_root, relative_path)
            if not os.path.isfile(absolute_path) or os.path.islink(absolute_path):
                continue
            # A nested CLAUDE.md is the import alone; the root one is the whole proxy (instruction-normalization.sh).
            if os.path.dirname(relative_path):
                normalized = nested.is_bare_proxy(absolute_path)
            else:
                normalized = sha256_of_file(absolute_path) == proxy_hash
            if not normalized:
                drifted.append(relative_path)
    for proxy in sorted(required_proxies):
        if proxy.casefold() not in existing_proxies and not os.path.lexists(os.path.join(project_root, proxy)):
            drifted.append(proxy)
    return drifted


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
        project_owned_instructions, ENGINE_SKILL_DIRECTORY, is_pack_profile, instructions_with_applied, nested_files)
    # Offline runs and automated reviews answer from the cache only.
    use_provider = not arguments.offline and os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") != "1"
    # The options of this run: the hooks' copy of them only changes when an apply finishes.
    settings = {"enabled": True, "cache": configuration.value(REVIEWS_CACHE_KEY),
                "ttl": configuration.value(REVIEWS_TTL_KEY), "commit": configuration.value(REVIEWS_COMMIT_KEY)}
    report = conflicts_review.review_conflicts(arguments.project, ENGINE_SKILL_DIRECTORY, module, arguments.provider,
                                               directions, texts, bash_executable(), use_provider, settings,
                                               publish=arguments.format == "protected")
    conflicts_review.record_pending(arguments.project, report.pop("pending", []), check=conflicts_review.CONFLICT_CHECK)
    report["block"] = configuration.value(CONFLICTS_BLOCK_KEY)
    levels = conflicts_review.document_levels(plan["entries"], nested_files)
    for finding in report["findings"]:
        finding["levels"] = [levels.get(name, conflicts_review.ROOT_LEVEL) for name in finding.get("files", [])]
    return report


def nested_instruction_files(plan):
    """The nested AGENTS.md files the apply writes blocks to: the ones of the workspaces and of the nested
    targets."""
    return sorted({entry["destination"] for entry in plan.get("blocks", [])
                   if entry["destination"].endswith(conflicts_review.NESTED_AGENTS_SUFFIX)})


def describe_conflict(finding):
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
    if report["findings"]:
        write_line("  Accept or dismiss one with: agent-ready review accept <id> --reason \"...\"")
    if report["unchecked"]:
        write_line(paint(f"  Check incomplete: {report['unchecked']} of {report['pairs']} pairs were not reviewed "
                         f"({report['reason']}).", "warning", stream))
    elif not report["findings"]:
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


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


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
    return status


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def source_report_without_selection(catalog):
    """Readable state of each declared source when no selection could be evaluated."""
    report = {}
    for name, source in sorted(catalog.get("sources", {}).items()):
        if source["state"] == SOURCE_AVAILABLE:
            report[name] = f"available ({source['type']} {source['origin']})"
        else:
            report[name] = f"not available ({source['type']} {source['origin']}): {source['reason']}"
    return report


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


def rejecting_ci_profiles(catalog, names):
    """A selection, or the error of resolve_profiles when it names a CI profile."""
    for name in names:
        if catalog["profiles"].get(name, {}).get("kind") == CI_PROFILE_KIND:
            resolve_profiles(catalog, [name])
    return names


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


def print_configuration_values(configuration, indent="  "):
    """Every option with its effective value and the layer it comes from."""
    values = {key: format_value(configuration.value(key)) or "-" for key in configuration.schema.leaves}
    key_width = max(len(key) for key in values)
    value_width = max(len(value) for value in values.values())
    for key in sorted(values):
        write_line(f"{indent}{key:<{key_width}}  {values[key]:<{value_width}}  ({configuration.origin(key)})")


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


# How many profiles the context warning names as the ones that add the most.
CONTEXT_LARGEST_PROFILES = 3
# The entry point that registers the browser MCP servers; its SERVER_ALIASES is their roster.
BROWSER_SETUP_RELATIVE_PATH = "scripts/setup-browser-tools.py"
RULES_DESTINATION_PREFIX = ".agents/rules/"
# The owner the reports give to the rules the project wrote itself.
PROJECT_RULES_PROFILE = "project"


def loaded_at_start(text):
    """True when Claude loads a rule at the start of a session: it has no paths: in its frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return True
    for line in lines[1:]:
        if line.strip() == "---":
            return True
        if line.startswith("paths:"):
            return False
    return True


def context_budget(project_root, skill_dir, catalog, plan, configuration):
    """What the selection adds to the context of every session, in bytes, and the profiles that add most.

    AGENTS.md is the file the apply would write: the managed block rendered by
    render-instruction-template.sh, as for the plan diff, and the stack sections the plan places with
    the same block functions as the apply. Claude also loads every rule without paths: at the start,
    managed or the project's own; a rule the apply retires does not count. MCP servers are the ones the
    apply registers: the browser's when its tools are enabled, and the pack servers the policy allows.
    """
    rules, project_rules = projected_rules(project_root, plan)
    rules_by_profile, rule_files = {}, 0
    for rule in rules:
        if loaded_at_start(rule["text"]):
            rule_files += 1
            rules_by_profile[rule["profile"]] = rules_by_profile.get(rule["profile"], 0) + text_bytes(rule["text"])

    agents_text, sections_by_profile = projected_agents_md(project_root, skill_dir, catalog, plan, project_rules)
    browser_servers = len(browser_mcp_servers(skill_dir)) if (
        BROWSER_TOOL_NAME in plan["tools"] and configuration.value(TOOLS_ENABLED_KEY)) else 0
    pack_servers, _ = pack_mcp.desired_servers(plan.get("packTools"))
    agents_bytes, rules_bytes = text_bytes(agents_text), sum(rules_by_profile.values())
    agents_limit = configuration.value(CONTEXT_BUDGET_BYTES_KEY)
    rules_limit = configuration.value(CONTEXT_BUDGET_RULES_BYTES_KEY)
    return {
        "agentsMd": {"bytes": agents_bytes, "limitBytes": agents_limit, "exceeded": agents_bytes > agents_limit,
                     "largest": largest_profiles(sections_by_profile)},
        "rulesLoadedAtStart": {"bytes": rules_bytes, "files": rule_files, "limitBytes": rules_limit,
                               "exceeded": rules_limit is not None and rules_bytes > rules_limit,
                               "largest": largest_profiles(rules_by_profile)},
        "mcpServers": browser_servers + len(pack_servers),
    }


def browser_mcp_servers(skill_dir):
    """The MCP servers the browser setup registers, read from its own roster.

    The setup needs Python 3.11 and exits before registering anything on an older one, so there the
    roster is empty, as the registration would be.
    """
    specification = importlib.util.spec_from_file_location(
        "agent_ready_browser_setup", os.path.join(skill_dir, BROWSER_SETUP_RELATIVE_PATH))
    module = importlib.util.module_from_spec(specification)
    try:
        specification.loader.exec_module(module)
    except SystemExit:
        return ()
    return tuple(module.SERVER_ALIASES)


def projected_rules(project_root, plan):
    """([{path, profile, text}], {path: text}) of the rules in .agents/rules after the apply.

    The first list holds every rule: the managed ones (the local file when the apply keeps it for a
    conflict, the template otherwise) and the project's own, with profile "project". The second
    holds only the project's own.
    """
    # The rules the apply writes or deletes. A dropped or retire-conflict entry leaves its file, which
    # stays as the project's own.
    managed_destinations = {entry["destination"] for entry in plan["entries"]
                            if entry["sha256"] or entry["action"] == ACTION_RETIRE}
    rules = []
    for entry in plan["entries"]:
        destination = entry["destination"]
        if not entry["sha256"] or not destination.startswith(RULES_DESTINATION_PREFIX) or not destination.endswith(".md"):
            continue
        # A conflict keeps the local file: that file is the one the agents load, not the template.
        local_path = os.path.join(project_root, destination)
        kept_local = entry["action"] == ACTION_CONFLICT and os.path.isfile(local_path) and not is_link(local_path)
        with open(local_path if kept_local else entry["sourcePath"], encoding="utf-8", errors="replace") as rule_file:
            rules.append({"path": destination, "profile": entry["profile"], "text": rule_file.read(),
                          "workspace": entry.get("workspace")})
    project_rules = project_owned_rules(project_root, managed_destinations)
    rules += [{"path": RULES_DESTINATION_PREFIX + path, "profile": PROJECT_RULES_PROFILE, "text": text}
              for path, text in sorted(project_rules.items())]
    return rules, project_rules


def repo_reality_report(project_root, skill_dir, plan):
    """The assumptions of the rules that the repository contradicts. Read-only."""
    rules, _ = projected_rules(project_root, plan)
    facts = repo_facts.load_facts(skill_dir)
    findings = repo_facts.contradictions(project_root, facts, [rule for rule in rules if not rule.get("workspace")])
    # A rule of a workspace is checked against that folder: its package.json, its configuration files.
    for path in sorted({rule["workspace"] for rule in rules if rule.get("workspace")}):
        workspace_rules = [rule for rule in rules if rule.get("workspace") == path]
        for finding in repo_facts.contradictions(os.path.join(project_root, *path.split("/")), facts, workspace_rules):
            if "evidence" in finding:
                finding["evidence"] = [f"{path}/{evidence}" for evidence in finding["evidence"]]
            findings.append(finding)
    return findings


def repo_reality_lines(findings):
    """One line per rule the repository contradicts."""
    lines = []
    for finding in findings:
        if finding.get("unknown"):
            lines.append(f"  ~ {finding['rule']} ({finding['profile']}) assumes {finding['fact']}: {finding['assumes']}, "
                         f"which {repo_facts.FACTS_RELATIVE_PATH} does not know; it is not checked")
            continue
        lines.append(f"  ! {finding['rule']} ({finding['profile']}) assumes {finding['description']} {finding['assumes']}, "
                     f"but the repository uses {', '.join(finding['repository'])} ({', '.join(finding['evidence'])})")
    return lines


def print_repo_reality(findings):
    """Print the lines of repo_reality_lines."""
    for line in repo_reality_lines(findings):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def parity_report(project_root, skill_dir, plan, configuration, with_user=True):
    """What each provider sees and the variables and CI jobs that collide. Read-only.

    ``with_user`` False leaves the user's own hooks out of the comparison.
    """
    report = {}
    providers = configuration.value(PROVIDERS_KEY)
    if configuration.value(PROVIDER_PARITY_ENABLED_KEY) and {parity.PROVIDER_CLAUDE, parity.PROVIDER_CODEX} <= set(providers):
        rules, _ = projected_rules(project_root, plan)
        scoped = sum(1 for rule in rules if not loaded_at_start(rule["text"]))
        report["views"] = parity.provider_views(len(rules), scoped, plan["entries"])
        report["hookDifferences"] = parity.hook_differences(project_root, skill_dir, with_user)
    if configuration.value(ENVIRONMENT_CONFLICTS_ENABLED_KEY):
        report["environment"] = parity.environment_variables(plan.get("packToolDeclarations", []), project_root)
    if configuration.value(CI_JOB_CONFLICTS_ENABLED_KEY):
        block_destinations = {block["destination"] for block in plan.get("blocks", []) if block.get("content")}
        report["ciJobs"] = parity.duplicated_ci_jobs(project_root, plan["entries"], block_destinations)
    return report


def competing_skills_report(arguments, plan, catalog, configuration):
    """The AI review of the skills that compete for the same request, or None when it is off."""
    if not configuration.value(COMPETING_SKILLS_ENABLED_KEY) or not configuration.value(REVIEWS_ENABLED_KEY):
        conflicts_review.record_pending(arguments.project, [], check=skill_overlap.CHECK)
        return None
    if not conflicts_review.engine_can_review(ENGINE_SKILL_DIRECTORY):
        return None
    module = review_cache_module()
    directions, texts = skill_overlap.skill_pairs(arguments.project, plan["entries"], catalog, is_pack_profile,
                                                  module.normalized_text)
    if not directions:
        conflicts_review.record_pending(arguments.project, [], check=skill_overlap.CHECK)
        return None
    use_provider = not arguments.offline and os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") != "1"
    settings = {"enabled": True, "cache": configuration.value(REVIEWS_CACHE_KEY),
                "ttl": configuration.value(REVIEWS_TTL_KEY), "commit": configuration.value(REVIEWS_COMMIT_KEY)}
    check = skill_overlap.reviewer(conflicts_review.load_harness_review(ENGINE_SKILL_DIRECTORY))
    report = conflicts_review.review_conflicts(arguments.project, ENGINE_SKILL_DIRECTORY, module, arguments.provider,
                                               directions, texts, bash_executable(), use_provider, settings,
                                               publish=arguments.format == "protected", check=check,
                                               pending_directions=(skill_overlap.DIRECTION_SKILLS,))
    # The skills an apply brings are not on disk yet: all their findings, decided ones included, wait
    # here, so agent-ready review can accept or dismiss one before the apply and keep that decision.
    conflicts_review.record_pending(arguments.project, report.pop("pending", []), check=skill_overlap.CHECK)
    return report


def competing_skills_lines(report):
    """The skills that compete, with the requests both take and how they differ."""
    lines = []
    if not report:
        return lines
    module = review_cache_module()
    for finding in report["findings"]:
        requests = "; ".join(f'"{request}"' for request in finding.get("lines", []))
        lines.append(f"  {module.finding_line(finding)} (competing skills"
                     f"{': ' + requests if requests else ''})")
    if report.get("unchecked"):
        lines.append(f"  Competing skills: {report['unchecked']} pair(s) not reviewed ({report['reason']})")
    return lines


def print_competing_skills(report):
    """Print the lines of competing_skills_lines."""
    for line in competing_skills_lines(report):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def competing_tools_lines(findings):
    """One line per pair of tools that give the same capability."""
    lines = []
    kinds = {pack_tools.TOOL_CLI: "CLI", pack_tools.TOOL_MCP_SERVER: "MCP server"}
    for finding in findings:
        first, second = finding["tools"]
        lines.append(f"  ~ {kinds[first['type']]} {first['name']} ({first['profile']}) and {kinds[second['type']]} "
                     f"{second['name']} ({second['profile']}) both provide {', '.join(finding['capabilities'])}: the "
                     f"agent picks either; keep one, or declare complements if they go together")
    return lines


def print_competing_tools(findings):
    """Print the lines of competing_tools_lines."""
    for line in competing_tools_lines(findings):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def parity_report_lines(report):
    """What each provider sees, and one line per hook, variable or CI job that collides."""
    lines = []
    views = report.get("views")
    if views:
        claude, codex = views[parity.PROVIDER_CLAUDE], views[parity.PROVIDER_CODEX]
        lines.append(f"Providers: Claude Code sees {claude['rules']} rules ({claude['rulesForPathsOnly']} only for their "
                     f"paths), {claude['skills']} skills, {claude['subagents']} subagents and {claude['commands']} commands; "
                     f"Codex sees {codex['rules']} rules in AGENTS.md and {codex['skills']} skills")
    for difference in report.get("hookDifferences", []):
        lines.append(f"  ~ {difference['provider']} runs the {difference['event']} hook `{difference['command']}` "
                     f"({difference['file']}) and {difference['missing']} does not")
    for variable in report.get("environment", []):
        profiles = ", ".join(variable["profiles"])
        if variable.get("sources"):
            lines.append(f"  ~ variable {variable['name']} is asked by the sources {', '.join(variable['sources'])} "
                         f"({profiles}): check they mean the same")
        else:
            lines.append(f"  ~ variable {variable['name']} ({profiles}) is already listed in {variable['file']}: "
                         "check the project uses it for the same")
    for job in report.get("ciJobs", []):
        lines.append(f"  ~ {job['file']} already runs the Agent Ready check; the managed {', '.join(job['managed'])} "
                     "runs it again")
    return lines


def print_parity_report(report):
    """Print the lines of parity_report_lines."""
    for line in parity_report_lines(report):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def settings_conflicts_lines(report):
    """One line per permission, hook or formatter that collides across the layers."""
    lines = []
    for conflict in report.get("permissions", []):
        lines.append(f"  ! permission {conflict['pattern']}: allowed in {', '.join(conflict['allow'])} and denied in "
                     f"{', '.join(conflict['deny'])}; Claude Code applies the deny")
    for hook in report.get("duplicatedHooks", []):
        lines.append(f"  ~ {hook['provider']} hook {hook['event']} `{hook['command']}` is registered in "
                     f"{' and '.join(hook['files'])}: it runs once per registration")
    for clash in report.get("formatters", []):
        first, second = clash["hooks"]
        lines.append(f"  ~ {clash['provider']} {clash['event']} runs two formatters that can rewrite the same files: "
                     f"{first['formatter']} ({first['file']}) and {second['formatter']} ({second['file']})")
    return lines


def print_settings_conflicts(report):
    """Print the lines of settings_conflicts_lines."""
    for line in settings_conflicts_lines(report):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def project_owned_rules(project_root, managed_destinations):
    """{relative path: text} of the rules in .agents/rules that no profile manages, now or before."""
    rules_root = os.path.join(project_root, ".agents", "rules")
    rules = {}
    for relative_path, absolute_path in (walk_files(rules_root) if os.path.isdir(rules_root) else []):
        if (not relative_path.endswith(".md") or is_link(absolute_path)
                or RULES_DESTINATION_PREFIX + relative_path in managed_destinations):
            continue
        with open(absolute_path, encoding="utf-8", errors="replace") as rule_file:
            rules[relative_path] = rule_file.read()
    return rules


def projected_agents_md(project_root, skill_dir, catalog, plan, project_rules):
    """(text, {profile: bytes of its section}) of AGENTS.md after the apply, without writing it."""
    with tempfile.TemporaryDirectory(prefix="agent-ready-context.") as work_root:
        # Only the project's own rules: the ones the apply retires are gone when it renders the block.
        rules_copy = os.path.join(work_root, "project-rules")
        for relative_path, rule_text in project_rules.items():
            destination = os.path.join(rules_copy, relative_path)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "w", encoding="utf-8", newline="") as rule_file:
                rule_file.write(rule_text)
        stack_root = os.environ.get("AGENT_READY_SETUP_STACK_DIR") or compose_stack_directory(
            skill_dir, catalog, plan["profiles"], os.path.join(work_root, "stack"))
        current = current_instructions(project_root, skill_dir)
        project_rules_root = rules_copy if project_rules else None
        if current is not None and extract_managed_block(current) is not None:
            rendered = render_instructions(skill_dir, catalog, stack_root, project_rules_root, managed_block_only=True)
            text = current.replace(extract_managed_block(current), extract_managed_block(rendered or "") or "", 1)
        elif current is not None:
            # Without a block yet, the instruction review adds it after the project's content.
            rendered = render_instructions(skill_dir, catalog, stack_root, project_rules_root, managed_block_only=True)
            text = current.rstrip("\n") + "\n\n" + (rendered or "")
        else:
            text = render_instructions(skill_dir, catalog, stack_root, project_rules_root, managed_block_only=False) or ""
    destination = managed_blocks.INSTRUCTION_SECTIONS_DESTINATION
    sections_by_profile = {}
    for block in plan.get("blocks", []):
        if block["destination"] != destination or block.get("action") == ACTION_CONFLICT:
            continue
        try:
            if block.get("content") is None:
                text = managed_blocks.without_block(text, destination, block["id"])
                continue
            text = managed_blocks.with_block(text, destination, block["id"], block["content"])
            # The whole section, markers included, whatever the file held before.
            size = text_bytes(managed_blocks.with_block("", destination, block["id"], block["content"]))
            sections_by_profile[block["profile"]] = sections_by_profile.get(block["profile"], 0) + size
        except managed_blocks.MarkerError:
            continue
    return text, sections_by_profile


def current_instructions(project_root, skill_dir):
    """The instructions the apply starts AGENTS.md from, or None for a new one.

    The file conflicts_review.project_instructions finds, the same discovery as the instruction
    normalization: AGENTS.md, or a root CLAUDE.md (or its only case variant) that is not the proxy.
    """
    name = conflicts_review.project_instructions(project_root, skill_dir)
    if name is None:
        return None
    with open(os.path.join(project_root, name), encoding="utf-8", errors="replace") as instructions_file:
        return instructions_file.read()


def largest_profiles(bytes_by_profile):
    """The profiles that add the most bytes, largest first."""
    ordered = sorted(bytes_by_profile.items(), key=lambda item: (-item[1], item[0]))[:CONTEXT_LARGEST_PROFILES]
    return [{"profile": profile, "bytes": size} for profile, size in ordered]


def print_context_budget(context):
    """The context the selection adds to every session, and a warning when it passes the threshold."""
    agents, rules = context["agentsMd"], context["rulesLoadedAtStart"]
    write_line(f"Context at the start of a session: AGENTS.md ~{agents['bytes']} bytes; {rules['files']} rules "
               f"without paths: ~{rules['bytes']} bytes; MCP servers: {context['mcpServers']}")
    if agents["exceeded"]:
        write_line(paint(f"  ! AGENTS.md passes {agents['limitBytes']} bytes ({CONTEXT_BUDGET_BYTES_KEY}): Codex cuts the "
                         f"combined AGENTS.md there.{largest_suffix(agents['largest'])} Move content to rules or skills.",
                         "warning", sys.stdout))
    if rules["exceeded"]:
        write_line(paint(f"  ! The rules without paths pass {rules['limitBytes']} bytes ({CONTEXT_BUDGET_RULES_BYTES_KEY}): "
                         f"Claude loads them in every session.{largest_suffix(rules['largest'])} Give them paths: or move "
                         "them to skills.", "warning", sys.stdout))


def largest_suffix(largest):
    """' Largest: a (n), b (m).' for a warning, or nothing when no profile adds to it."""
    if not largest:
        return ""
    return " Largest: " + ", ".join(f"{item['profile']} ({item['bytes']})" for item in largest) + "."


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


def structural_conflicts(project_root, skill_dir, plan, catalog, configuration, with_context=True, with_machine=True):
    """The checks of the profiles that need no AI, on a plan: what plan, conflicts and check report.

    ``with_context`` adds the context budget, which only informs: status leaves it out.
    ``with_machine`` False leaves out what comes from this machine (shadowing, the user's servers and
    settings): a pack check runs on its author's machine, not on a consumer's.
    """
    report = {}
    if with_context and configuration.value(CONTEXT_BUDGET_ENABLED_KEY):
        report["context"] = context_budget(project_root, skill_dir, catalog, plan, configuration)
    if with_machine:
        report["machine"] = machine_report(project_root, plan, configuration)
    if configuration.value(REPO_REALITY_ENABLED_KEY):
        report["repoReality"] = repo_reality_report(project_root, skill_dir, plan)
    report["parity"] = parity_report(project_root, skill_dir, plan, configuration, with_user=with_machine)
    if configuration.value(COMPETING_TOOLS_ENABLED_KEY):
        report["competingTools"] = pack_tools.competing_tools(plan.get("packToolDeclarations", []), catalog)
    report["settingsConflicts"] = settings_conflicts.report(
        project_root, skill_dir, configuration.value(HOOK_CONFLICTS_ENABLED_KEY),
        configuration.value(PERMISSION_CONFLICTS_ENABLED_KEY), with_user=with_machine)
    return report


def structural_conflict_lines(report):
    """One line per structural conflict. What only informs is left out: the context budget, what each
    provider sees, the servers left to the user and an assumption the catalog cannot check."""
    lines = machine_report_lines({"shadowed": (report.get("machine") or {}).get("shadowed", [])})
    lines += repo_reality_lines([finding for finding in report.get("repoReality", []) if not finding.get("unknown")])
    lines += settings_conflicts_lines(report.get("settingsConflicts") or {})
    lines += parity_report_lines({key: value for key, value in (report.get("parity") or {}).items() if key != "views"})
    lines += competing_tools_lines(report.get("competingTools") or [])
    return lines


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
