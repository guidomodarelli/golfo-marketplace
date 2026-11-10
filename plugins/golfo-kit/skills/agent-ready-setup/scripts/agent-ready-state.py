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
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

# Shared modules load from this script's own directory and leave no bytecode beside
# the skill source, which may be a read-only snapshot.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_ready_common import (  # noqa: E402
    IncompleteEvaluationError,
    ProfileError,
    StateError,
    acquire_directory_lock,
    bash_executable,
    is_link,
    plugin_version,
    read_json_file,
    serialize_json,
    sha256_of_file,
    sha256_of_text,
    walk_files,
    write_text_atomically,
)
from agent_ready_config import (  # noqa: E402
    ConfigurationError,
    IGNORED_LOCKED,
    IGNORED_LOOSENS,
    LAYER_USER,
    PROJECT_CONFIG_RELATIVE_PATH,
    describe_ignored,
    describe_layer,
    format_value,
    load_schema,
    normalized_project_path,
    read_layer_file,
    render_reference,
    resolve_configuration,
    set_sparse,
    user_config_path,
    validate_layer,
)
from agent_ready_options import (  # noqa: E402
    CI_ENABLED_KEY,
    CI_MODE_KEY,
    CI_WARN,
    DETECTION_ENABLED_KEY,
    PROFILES_KEY,
    PROVIDERS_KEY,
    REVIEWS_CACHE_KEY,
    CONFLICTS_BLOCK_KEY,
    CONFLICTS_ENABLED_KEY,
    REVIEWS_ENABLED_KEY,
    REVIEWS_COMMIT_KEY,
    REVIEWS_TTL_KEY,
    SOURCES_ENABLED_KEY,
    SOURCES_PACKS_KEY,
    SUPPORTED_PROVIDERS,
    TOOLS_ENABLED_KEY,
    UPDATE_MODES,
    UPDATES_AUTO,
    UPDATES_MODE_KEY,
    UPDATES_PINNED,
    TRUSTED_PROJECTS_KEY,
    UPDATES_REFRESH_KEY,
)
from agent_ready_detection import (  # noqa: E402
    STACK_PROFILE_KIND,
    STATUS_AMBIGUOUS,
    STATUS_RESOLVED,
    DetectionSchemaError,
    detect_profiles,
    format_evidence_list,
    validate_catalog_detection,
)
import agent_ready_compatibility as compatibility  # noqa: E402
import agent_ready_conflicts as conflicts_review  # noqa: E402
import agent_ready_pack_clis as pack_clis  # noqa: E402
import agent_ready_pack_mcp as pack_mcp  # noqa: E402
import agent_ready_pack_tools as pack_tools  # noqa: E402
import agent_ready_golfo_kit as golfo_kit  # noqa: E402
from agent_ready_packs import (  # noqa: E402
    SOURCE_AVAILABLE,
    SOURCE_TYPE_GIT,
    download_declared_sources,
    effective_update_mode,
    is_pack_profile,
    load_pack_catalog,
    locate_source,
    pack_cache_root,
    parse_profile_sources,
    refresh_declared_sources,
    source_of_profile,
    source_update_mode_is_ignored,
)

MANIFEST_RELATIVE_PATH = PROJECT_CONFIG_RELATIVE_PATH
# The review cache lives with the hooks, which also run where the skill is not installed.
REVIEW_CACHE_RELATIVE_PATH = "assets/common/hooks/review-cache.py"
ENGINE_SKILL_DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK_RELATIVE_PATH = ".agents/agent-ready.lock.json"
PROFILE_CATALOG_RELATIVE_PATH = "assets/profiles.json"
PROVIDER_CATALOG_RELATIVE_PATH = "assets/providers.json"
CODEX_HOOKS_TEMPLATE_RELATIVE_PATH = "assets/codex/hooks.json"
CLAUDE_SETTINGS_TEMPLATE_NAME = "settings.json"
AGENTS_TEMPLATE_NAME = "agents-template.md"
CLAUDE_PROXY_RELATIVE_PATH = "assets/claude-proxy.md"
CENTRALIZATION_RELATIVE_PATH = "assets/instruction-centralization.md"
RENDERER_RELATIVE_PATH = "scripts/render-instruction-template.sh"
SETTINGS_MERGER_RELATIVE_PATH = "scripts/merge-managed-settings.py"
CODEX_HOOKS_MERGER_RELATIVE_PATH = "scripts/merge-codex-hooks.py"
# Inputs of the rendered instructions that no asset or merged template covers.
RENDERED_INSTRUCTION_INPUTS = (CLAUDE_PROXY_RELATIVE_PATH, CENTRALIZATION_RELATIVE_PATH, RENDERER_RELATIVE_PATH)
SKILL_NAME = "agent-ready-setup"
PLUGIN_NAME = "golfo-kit"
BASE_PROFILE_NAME = "common"
SCHEMA_VERSION = 1
# The schemaVersion of golfo-kit's catalog this engine reads; a newer one asks for a newer plugin.
GOLFO_CATALOG_SCHEMA_VERSION = 1
MANAGED_BLOCK_START = "<!-- BEGIN AGENT-READY MANAGED -->"
MANAGED_BLOCK_END = "<!-- END AGENT-READY MANAGED -->"
SETTINGS_TEMPLATE_FALLBACK_STATUS = 10
# Results of `check` and their exit statuses: the stable contract of a CI pipeline.
CHECK_UP_TO_DATE = "up-to-date"
CHECK_OUTDATED = "outdated"
CHECK_SOURCE_UNAVAILABLE = "source-unavailable"
CHECK_CONFIG_ERROR = "config-error"
CHECK_SKIPPED = "skipped"
FOREGROUND_SYNC_VARIABLE = "AGENT_READY_SETUP_SYNC_FOREGROUND"
# The background update stops retrying for a while after this many failures in a row.
BACKGROUND_UPDATE_MAX_FAILURES = 3
BACKGROUND_UPDATE_RETRY_AFTER_SECONDS = 3600
BACKGROUND_UPDATE_TIMEOUT_SECONDS = 1800
REPORT_MAX_LISTED_ASSETS = 10
REPORT_MAX_PROBLEM_CHARACTERS = 500
BACKUPS_LINE_PREFIX = "Local backups directory:"
BROWSER_TOOL_NAME = "browser"
# Exit status when the selected profiles cannot be resolved or composed.
PROFILE_ERROR_STATUS = 2
# Exit status of `detect` when the signals do not determine one primary stack.
DETECTION_UNRESOLVED_STATUS = 3
# Exit status of `status --check` when the checkout or the source drifted from the lock.
DRIFT_STATUS = 4
# Exit status when a profile source the selection needs is not available or not adopted.
INCOMPLETE_EVALUATION_STATUS = 5
CHECK_EXIT_STATUSES = {
    CHECK_UP_TO_DATE: 0,
    CHECK_SKIPPED: 0,
    CHECK_CONFIG_ERROR: PROFILE_ERROR_STATUS,
    CHECK_OUTDATED: DRIFT_STATUS,
    CHECK_SOURCE_UNAVAILABLE: INCOMPLETE_EVALUATION_STATUS,
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
# Catalog fields that do not change what a profile projects, so they stay out of its digest.
PROFILE_DIGEST_EXCLUDED_FIELDS = ("detect",)

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_ADOPT = "adopt"
ACTION_UNCHANGED = "unchanged"
ACTION_CONFLICT = "conflict"
ACTION_RETIRE = "retire"
ACTION_RETIRE_CONFLICT = "retire-conflict"
ACTION_DROP = "drop"

STATE_APPLIED = "applied"
STATE_CONFLICT = "conflict"
STATE_FAILED = "failed"
STATE_RETIRED_PRESERVED = "retired-preserved"

LOCAL_ABSENT = "absent"
LOCAL_SYMLINK = "symlink"
LOCAL_NOT_A_FILE = "not-a-file"

LINKED_PARENT_REASON = "a parent directory is a symlink; deleting through it would reach files outside the project"
DETACHED_VIEW_REASON = "regular file that no apply wrote; it is preserved instead of relinked"
EDITED_VIEW_REASON = "regular file with local changes; relinking the view overwrites them"
# Assets under these directories have a view under .claude/; hooks stay canonical in .agents/.
CLAUDE_VIEW_DIRECTORIES = ("rules", "agents", "commands", "skills")

ANSI_RESET = "\033[0m"
ANSI_COLORS = {
    "create": "\033[32m",
    "update": "\033[36m",
    "adopt": "\033[36m",
    "conflict": "\033[31m",
    "retire": "\033[33m",
    "retire-conflict": "\033[31m",
    "heading": "\033[1m",
    "muted": "\033[2m",
    "ok": "\033[32m",
    "warning": "\033[33m",
    "error": "\033[31m",
}
ACTION_SYMBOLS = {
    ACTION_CREATE: "+",
    ACTION_UPDATE: "~",
    ACTION_ADOPT: "~",
    ACTION_CONFLICT: "!",
    ACTION_RETIRE: "-",
    ACTION_RETIRE_CONFLICT: "!",
    ACTION_DROP: "-",
    ACTION_UNCHANGED: "=",
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def colors_enabled(stream):
    """Return True when ANSI colors are safe on ``stream``."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def paint(text, color_key, stream):
    """Wrap ``text`` in the palette color when the stream supports it."""
    if not colors_enabled(stream):
        return text
    return f"{ANSI_COLORS[color_key]}{text}{ANSI_RESET}"


def write_line(text="", stream=None):
    """Print one line to the given stream (stdout by default)."""
    target = stream or sys.stdout
    target.write(text + "\n")


# ---------------------------------------------------------------------------
# Generic file helpers
# ---------------------------------------------------------------------------

def local_state(path):
    """Describe a project path: absent, symlink, not-a-file or its sha256."""
    if os.path.islink(path):
        return LOCAL_SYMLINK
    if not os.path.exists(path):
        return LOCAL_ABSENT
    if not os.path.isfile(path):
        return LOCAL_NOT_A_FILE
    return sha256_of_file(path)


def has_linked_parent(project_root, destination):
    """True when a directory between the project root and a destination is a link."""
    parent = os.path.dirname(destination)
    while parent:
        if is_link(os.path.join(project_root, parent)):
            return True
        parent = os.path.dirname(parent)
    return False


def write_text_if_changed(path, text):
    """Write text unless the file already holds it, ignoring its line endings.

    Rewriting a CRLF checkout with LF would mark the file as modified in Git
    although its content is the same.
    """
    try:
        with open(path, encoding="utf-8") as file_handle:
            if file_handle.read() == text:
                return
    except (OSError, UnicodeDecodeError):
        pass
    write_text_atomically(path, text)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def load_profile_catalog(skill_dir):
    """Load and validate the profile catalog of the skill source.

    Content that needs a newer engine than the installed one (``minEngine``, ``schemaVersion``)
    stops here, before anything is written.
    """
    catalog_path = os.path.join(skill_dir, PROFILE_CATALOG_RELATIVE_PATH)
    try:
        catalog = read_json_file(catalog_path, "profile catalog")
    except StateError as caught_error:
        raise ProfileError(str(caught_error)) from caught_error
    label = f"the {golfo_kit.GOLFO_KIT_SOURCE_NAME} catalog"
    compatibility.require_engine(label, catalog, engine_version_of(skill_dir), GOLFO_CATALOG_SCHEMA_VERSION)
    compatibility.validate_compatibility(label, catalog)
    profiles = catalog.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ProfileError(f"profile catalog {catalog_path} has no profiles")
    try:
        validate_catalog_detection(profiles)
    except DetectionSchemaError as caught_error:
        raise ProfileError(f"profile catalog {catalog_path}: {caught_error}") from caught_error
    return catalog


def configuration_of(project_root, offline=False):
    """Effective configuration of a repository; ``offline`` is the --offline flag of this run."""
    return resolve_configuration(project_root, flags={UPDATES_REFRESH_KEY: False} if offline else None)


def declared_sources(project_root):
    """Profile sources of the manifest, in a stable order; none while sources are off."""
    configuration = configuration_of(project_root)
    if not configuration.value(SOURCES_ENABLED_KEY):
        return []
    return parse_profile_sources(configuration.value(SOURCES_PACKS_KEY), os.path.join(project_root, MANIFEST_RELATIVE_PATH))


def locked_sources_of(project_root):
    """Profile sources recorded by the last apply."""
    lock = read_lock(project_root)
    return (lock or {}).get("profileSources", {})


def load_effective_catalog(project_root, skill_dir, source_state=None):
    """Golfo's catalog plus the profiles of every source available on this machine.

    Pack profiles are namespaced, so they never replace a Golfo profile, and the global
    fields of Golfo's catalog stay as they are. Nothing here uses the network or runs
    anything from a pack. ``source_state`` holds the commits an apply just adopted.
    """
    catalog = load_profile_catalog(skill_dir)
    golfo_profile_names = set(catalog["profiles"])
    locked_sources = locked_sources_of(project_root)
    configuration = configuration_of(project_root)
    catalog["sources"] = {}
    catalog["packAssetRoots"] = {}
    catalog["sourcesEnabled"] = configuration.value(SOURCES_ENABLED_KEY)
    for declaration in declared_sources(project_root):
        name = declaration["name"]
        update_mode = effective_update_mode(configuration, declaration)
        source = locate_source(declaration, locked_sources.get(name), project_root, update_mode, (source_state or {}).get(name))
        if source["state"] == SOURCE_AVAILABLE:
            pack = load_pack_catalog(source, golfo_profile_names, engine_version_of(skill_dir))
            source["catalogDigest"] = pack["digest"]
            source["version"] = pack["version"]
            source["changes"] = pack["changes"]
            source["availableProfiles"] = sorted(pack["profiles"])
            catalog["profiles"].update(pack["profiles"])
            catalog["packAssetRoots"].update(pack["assetRoots"])
        catalog["sources"][name] = source
    return catalog


def raise_unknown_profile(catalog, name, requested_by):
    """Explain a profile that is not in the catalog, naming the source when it has one."""
    origin = f" (required by {requested_by})" if requested_by else ""
    if is_pack_profile(name):
        source_name = source_of_profile(name)
        source = catalog.get("sources", {}).get(source_name)
        if source is None and not catalog.get("sourcesEnabled", True):
            raise ProfileError(f"profile '{name}'{origin} comes from the source '{source_name}', and profile sources are off ({SOURCES_ENABLED_KEY}: false)")
        if source is None:
            raise ProfileError(f"profile '{name}'{origin} needs the source '{source_name}', which the manifest does not declare; packs cannot bring sources of their own")
        if source["state"] != SOURCE_AVAILABLE:
            raise IncompleteEvaluationError(f"profile '{name}'{origin} needs the source '{source_name}': {source['reason']}")
    known = ", ".join(sorted(catalog["profiles"]))
    raise ProfileError(f"unknown profile '{name}'{origin}; available profiles: {known}")


def split_profile_names(raw_profiles):
    """Split a comma separated profile list, keeping order and dropping blanks."""
    names = []
    for name in (raw_profiles or "").split(","):
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


def profiles_for_stack(catalog, stack):
    """Legacy --stack alias: the stack profile plus its catalog defaults."""
    defaults = catalog.get("stackDefaults", {})
    if stack not in defaults:
        known = ", ".join(sorted(defaults))
        raise ProfileError(f"unknown stack '{stack}'; expected one of: {known}")
    return list(defaults[stack])


def resolve_profiles(catalog, requested_names):
    """Expand requires in declaration order and validate conflicts.

    Returns the ordered list of profile names. The first stack profile is the
    primary stack: it provides the AGENTS.md template.
    """
    profiles = catalog["profiles"]
    resolved = []
    visiting = []

    def visit(name, requested_by):
        if name in resolved:
            return
        if name in visiting:
            cycle = " -> ".join(visiting + [name])
            raise ProfileError(f"profile dependency cycle: {cycle}")
        if name not in profiles:
            raise_unknown_profile(catalog, name, requested_by)
        visiting.append(name)
        for dependency in profiles[name].get("requires", []):
            visit(dependency, name)
        visiting.pop()
        resolved.append(name)

    if not requested_names:
        raise ProfileError("no profiles selected; pass --profiles or --stack")
    for requested_name in requested_names:
        visit(requested_name, None)

    for name in resolved:
        for conflicting_name in profiles[name].get("conflicts", []):
            if conflicting_name in resolved:
                raise ProfileError(
                    f"profiles '{name}' and '{conflicting_name}' are declared incompatible; select only one"
                )

    if not any(profiles[name].get("kind") == STACK_PROFILE_KIND for name in resolved):
        stacks = ", ".join(sorted(key for key, value in profiles.items() if value.get("kind") == STACK_PROFILE_KIND))
        raise ProfileError(f"select at least one stack profile ({stacks}); it provides the AGENTS.md template")
    return resolved


def primary_stack(catalog, resolved):
    """Return the first stack profile in resolution order."""
    for name in resolved:
        if catalog["profiles"][name].get("kind") == STACK_PROFILE_KIND:
            return name
    raise ProfileError("no stack profile resolved")


def profile_asset_root(skill_dir, catalog, name):
    """Absolute asset directory of a profile, or None when it has no assets."""
    if is_pack_profile(name):
        return catalog["packAssetRoots"].get(name)
    relative_root = catalog["profiles"][name].get("assets")
    if not relative_root:
        return None
    root = os.path.join(skill_dir, relative_root)
    if not os.path.isdir(root):
        raise ProfileError(f"profile '{name}' assets directory is missing: {root}")
    return root


def resolved_tools(catalog, resolved):
    """Tools that the selected profiles need installed."""
    tools = []
    for name in resolved:
        for tool in catalog["profiles"][name].get("tools", []):
            if tool not in tools:
                tools.append(tool)
    return tools


def compose_stack_directory(skill_dir, catalog, resolved, compose_root):
    """Return the stack tree Bash projects for the selected profiles.

    A single stack profile without extra assets uses its own directory, so the
    legacy layout is projected unchanged. Several asset profiles are copied into
    one composed tree; a relative path published by two profiles is an error.
    """
    asset_profiles = [name for name in resolved if profile_asset_root(skill_dir, catalog, name)]
    primary = primary_stack(catalog, resolved)
    if asset_profiles == [primary]:
        return profile_asset_root(skill_dir, catalog, primary)

    owners = {}
    for name in asset_profiles:
        for relative_path, _ in walk_files(profile_asset_root(skill_dir, catalog, name)):
            if relative_path == AGENTS_TEMPLATE_NAME and name != primary:
                continue
            if relative_path in owners:
                raise ProfileError(
                    f"profiles '{owners[relative_path]}' and '{name}' both publish {relative_path}; "
                    "remove one of them or split the asset into a profile they both require"
                )
            owners[relative_path] = name

    if not compose_root:
        raise ProfileError("composing several asset profiles requires --compose-dir")
    # Two repositories can pin different revisions of a pack: they must not share a tree.
    pack_digests = profile_digests(skill_dir, catalog, [name for name in resolved if is_pack_profile(name)]) if any(
        is_pack_profile(name) for name in resolved
    ) else {}
    selection_key = sha256_of_text(
        os.path.abspath(skill_dir) + "\n" + ",".join(resolved) + "\n" + json.dumps(pack_digests, sort_keys=True)
    )[:16]
    destination = os.path.join(compose_root, selection_key)
    os.makedirs(compose_root, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".compose.", dir=compose_root)
    try:
        for relative_path, owner in sorted(owners.items()):
            source = os.path.join(profile_asset_root(skill_dir, catalog, owner), relative_path)
            target = os.path.join(staging, relative_path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        os.makedirs(os.path.join(staging, "rules"), exist_ok=True)
        previous = None
        if os.path.exists(destination):
            previous = tempfile.mkdtemp(prefix=".previous.", dir=compose_root)
            os.rmdir(previous)
            os.replace(destination, previous)
        os.replace(staging, destination)
        if previous:
            shutil.rmtree(previous, ignore_errors=True)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination


# ---------------------------------------------------------------------------
# Desired assets
# ---------------------------------------------------------------------------

def destinations_for_template(relative_path, is_stack_root):
    """Managed destinations that the Bash projection writes for one template file.

    Mirrors project_asset_tree in bootstrap.sh and project_assets in
    sync-marketplace.sh. Merged files (settings.json) and the AGENTS.md
    template are handled separately and return no verbatim destination.
    """
    if relative_path in (AGENTS_TEMPLATE_NAME, CLAUDE_SETTINGS_TEMPLATE_NAME):
        return []
    if relative_path.startswith("github/"):
        return [".github/" + relative_path[len("github/"):]]
    destinations = [".agents/" + relative_path]
    if relative_path == "mcp.json" and is_stack_root:
        destinations.append(".codex/.mcp.json")
    top_directory = relative_path.split("/", 1)[0]
    if relative_path.endswith(".md") and "/" in relative_path:
        if top_directory in ("agents", "commands") or (
            top_directory == "skills" and relative_path.count("/") == 1
        ):
            skill_name = os.path.basename(relative_path)[: -len(".md")]
            destinations.append(f".agents/skills/{skill_name}/SKILL.md")
    return destinations


def template_origin(skill_dir, catalog, profile_name, absolute_path):
    """Where a template comes from, without any path of this machine."""
    if is_pack_profile(profile_name):
        source_name = source_of_profile(profile_name)
        pack_relative = os.path.relpath(absolute_path, catalog["sources"][source_name]["root"]).replace(os.sep, "/")
        return f"{source_name}:{pack_relative}"
    return os.path.relpath(absolute_path, skill_dir).replace(os.sep, "/")


def desired_assets(skill_dir, catalog, resolved):
    """Map every managed destination to its template, owning profile and hash.

    Two templates cannot share a destination, including the skill adapters generated
    for Codex and paths that differ only by case, which collide on Windows and macOS.
    """
    # Bash projects every profile tree as the stack tree, so only the base
    # assets skip the Codex MCP bridge.
    sources = [(BASE_PROFILE_NAME, os.path.join(skill_dir, catalog.get("baseAssets", "assets/common")), False)]
    for name in resolved:
        root = profile_asset_root(skill_dir, catalog, name)
        if root:
            sources.append((name, root, True))

    assets = {}
    destinations_by_folded_name = {}
    for profile_name, root, is_stack_root in sources:
        for relative_path, absolute_path in walk_files(root):
            for destination in destinations_for_template(relative_path, is_stack_root):
                previous = destinations_by_folded_name.setdefault(destination.casefold(), destination)
                if previous in assets and assets[previous]["sourcePath"] != absolute_path:
                    raise ProfileError(
                        f"profiles '{assets[previous]['profile']}' and '{profile_name}' both write {destination}; "
                        "nothing was written. Rename one of the assets"
                    )
                assets[destination] = {
                    "profile": profile_name,
                    "source": template_origin(skill_dir, catalog, profile_name, absolute_path),
                    "sourcePath": absolute_path,
                    "sha256": sha256_of_file(absolute_path),
                }
    reject_destinations_inside_files(assets, destinations_by_folded_name)
    return assets


def reject_destinations_inside_files(assets, destinations_by_folded_name):
    """A destination cannot sit under another one: one of the two could not be written."""
    for destination, entry in sorted(assets.items()):
        parent = os.path.dirname(destination)
        while parent:
            blocking = destinations_by_folded_name.get(parent.casefold())
            if blocking in assets:
                raise ProfileError(
                    f"profile '{assets[blocking]['profile']}' writes the file {blocking}, but profile "
                    f"'{entry['profile']}' needs it as a directory for {destination}; nothing was written. Rename one of the assets"
                )
            parent = os.path.dirname(parent)


def profile_digests(skill_dir, catalog, resolved):
    """Digest of each resolved profile: its asset bytes or its catalog entry."""
    digests = {}
    for name in [BASE_PROFILE_NAME] + resolved:
        if name == BASE_PROFILE_NAME:
            root = os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"))
            entry = {"kind": "base"}
        else:
            root = profile_asset_root(skill_dir, catalog, name)
            entry = {
                field: value for field, value in catalog["profiles"][name].items()
                if field not in PROFILE_DIGEST_EXCLUDED_FIELDS
            }
        lines = [json.dumps(entry, sort_keys=True)]
        if root:
            lines += [f"{relative_path}\t{sha256_of_file(absolute_path)}" for relative_path, absolute_path in walk_files(root)]
        digests[name] = {"kind": entry.get("kind", "base"), "digest": sha256_of_text("\n".join(lines))}
    return digests


# ---------------------------------------------------------------------------
# Source identity
# ---------------------------------------------------------------------------

def validate_pack_destinations(project_root, assets):
    """A pack asset cannot reach outside the project through a symlink in its path."""
    for destination, entry in sorted(assets.items()):
        if not is_pack_profile(entry["profile"]):
            continue
        for path in (destination, claude_view_of(destination, entry["source"])):
            if path and has_linked_parent(project_root, path):
                raise ProfileError(
                    f"profile '{entry['profile']}' would write {path} through a symlink, "
                    "which can leave the project; nothing was written"
                )


def source_entries(catalog, resolved, digests, locked_sources):
    """Lockfile entry of each declared source; a source without selected profiles has none."""
    entries = {}
    for name, source in sorted(catalog.get("sources", {}).items()):
        if source["state"] != SOURCE_AVAILABLE:
            # Unused by this selection and not on this machine: its last record stays.
            if name in locked_sources:
                entries[name] = locked_sources[name]
            continue
        selected = sorted(profile for profile in resolved if is_pack_profile(profile) and source_of_profile(profile) == name)
        entries[name] = {
            "type": source["type"],
            "origin": source["origin"],
            "requestedRef": source["requestedRef"],
            "resolvedCommit": source["resolvedCommit"],
            "catalogDigest": source["catalogDigest"],
            "contentDigest": sha256_of_text("\n".join(f"{profile}\t{digests[profile]['digest']}" for profile in selected)),
            "profiles": selected,
        }
        if source.get("version"):
            entries[name]["version"] = source["version"]
    return entries


def version_changes(catalog, plan_source, lock):
    """Each source whose version moves from the lock, with its declared changelog, newest first."""
    if not lock:
        return []
    changes = []
    golfo_change = compatibility.version_change(golfo_kit.GOLFO_KIT_SOURCE_NAME, (lock.get("source") or {}).get("version"),
                                                plan_source.get("version"), catalog.get("changes", []))
    if golfo_change:
        changes.append(golfo_change)
    locked_sources = lock.get("profileSources", {})
    for name, source in sorted(catalog.get("sources", {}).items()):
        if source["state"] != SOURCE_AVAILABLE:
            continue
        change = compatibility.version_change(name, (locked_sources.get(name) or {}).get("version"),
                                              source.get("version"), source.get("changes", []))
        if change:
            changes.append(change)
    return changes


def declaration_differences(declaration, locked_entry):
    """What the manifest changed in a source; it needs neither the network nor its content."""
    if not locked_entry:
        return ["not adopted yet"]
    differences = []
    if declaration.get("origin") != locked_entry.get("origin"):
        differences.append(f"origin changed to {declaration.get('origin')}")
    if declaration.get("requestedRef") != locked_entry.get("requestedRef"):
        differences.append(f"requested revision changed to {declaration.get('requestedRef')}")
    return differences


def source_differences(name, entry, lock):
    """What changed in a source since the last apply, in words.

    A digest of a selected profile counts only if the lock has that profile too, so
    selecting one more profile of the same revision is a selection change, not an update.
    """
    locked_sources = (lock or {}).get("profileSources", {})
    locked_entry = locked_sources.get(name)
    if not locked_entry:
        return ["not adopted yet"]
    differences = declaration_differences(entry, locked_entry)
    if entry.get("resolvedCommit") != locked_entry.get("resolvedCommit"):
        locked_commit = (locked_entry.get("resolvedCommit") or "none")[:12]
        differences.append(f"revision {locked_commit} -> {(entry.get('resolvedCommit') or 'none')[:12]}")
    if entry.get("catalogDigest") != locked_entry.get("catalogDigest"):
        differences.append("catalog changed")
    return differences


def changed_selected_profiles(digests, lock):
    """Selected pack profiles whose content differs from the digest in the lock."""
    locked_profiles = (lock or {}).get("profiles", {})
    return sorted(
        profile for profile, entry in digests.items()
        if is_pack_profile(profile) and profile in locked_profiles and locked_profiles[profile].get("digest") != entry["digest"]
    )


def source_report(catalog, resolved, digests, lock):
    """State of each declared source for plan and status, with its differences from the lock."""
    locked_sources = (lock or {}).get("profileSources", {})
    entries = source_entries(catalog, resolved, digests, locked_sources)
    changed_profiles = changed_selected_profiles(digests, lock)
    report = {}
    for name, source in sorted(catalog.get("sources", {}).items()):
        selected = sorted(profile for profile in resolved if is_pack_profile(profile) and source_of_profile(profile) == name)
        item = {
            "type": source["type"],
            "origin": source["origin"],
            "requestedRef": source["requestedRef"],
            "resolvedCommit": source["resolvedCommit"],
            "state": source["state"],
            "reason": source["reason"],
            "selected": selected,
            "updates": source["updates"],
            "differences": [],
            "pendingUpdate": None,
        }
        latest = source.get("latestCommit")
        if latest and source["resolvedCommit"] and latest != source["resolvedCommit"]:
            item["pendingUpdate"] = (
                f"ref {source['requestedRef']} is at {latest[:12]} and this source is pinned at "
                f"{source['resolvedCommit'][:12]}; adopt it with --update-source {name}"
            )
        if source["state"] == SOURCE_AVAILABLE:
            entry = entries[name]
            item["catalogDigest"] = entry["catalogDigest"]
            item["contentDigest"] = entry["contentDigest"]
            item["differences"] = source_differences(name, entry, lock)
            item["differences"] += [f"content of {profile} changed" for profile in changed_profiles if source_of_profile(profile) == name]
        else:
            item["differences"] = declaration_differences(source, locked_sources.get(name))
        report[name] = item
    return report


def describe_source_item(name, item):
    """One line about a declared source. Origins never carry credentials: the manifest rejects them."""
    if item["state"] != SOURCE_AVAILABLE:
        need = "needed by the selection" if item["selected"] else "not needed by this selection"
        return f"{name} ({item['type']} {item['origin']}): not available: {item['reason']} ({need})"
    details = []
    if item["type"] == SOURCE_TYPE_GIT:
        details.append(f"requested {item['requestedRef']}, commit {item['resolvedCommit'][:12]}")
    details.append(f"catalog {item['catalogDigest'][:12]}, content {item['contentDigest'][:12]}")
    details.append(f"profiles: {', '.join(item['selected']) or 'none selected'}")
    return f"{name} ({item['type']} {item['origin']}): " + "; ".join(details)


def enforce_sync_policy(project_root, skill_dir, catalog, resolved, digests):
    """An unattended sync only adopts what is in ``auto``.

    A pinned source that differs from the lock stops it, golfo-kit included: its mode is
    ``sources.golfoKit.updates``, then ``updates.mode``. A pinned golfo-kit projects the
    revision of the lock, so its content only differs when that revision cannot be fetched
    (a local source without Git); then a pack in ``auto`` waits too, because an apply writes
    the whole selection and cannot update a pack without updating golfo-kit.
    """
    lock = read_lock(project_root)
    report = source_report(catalog, resolved, digests, lock)
    for name, item in report.items():
        if item["selected"] and item["differences"] and item["updates"] != UPDATES_AUTO:
            raise IncompleteEvaluationError(
                f"profile source '{name}' is pinned and differs from the lock ({'; '.join(item['differences'])}); "
                "SessionStart does not adopt it, so this repository keeps its committed assets until someone adopts the change"
            )
    marker = golfo_kit.read_marker(skill_dir)
    projects_locked_revision = bool(marker) and marker.get("commit") == (lock or {}).get("source", {}).get("revision")
    # The content digest covers engine-owned files too (hooks, settings templates): with the revision
    # of the lock projected, a new engine is not a golfo-kit release and the sync goes on.
    if lock and not projects_locked_revision and golfo_kit.update_mode(configuration_of(project_root)) == UPDATES_PINNED:
        assets = desired_assets(skill_dir, catalog, resolved)
        golfo_assets = {destination: entry for destination, entry in assets.items() if not is_pack_profile(entry["profile"])}
        identity = source_identity(skill_dir, golfo_assets, merged_template_entries(skill_dir, catalog, resolved))
        if lock.get("source", {}).get("contentDigest") != identity["contentDigest"]:
            raise IncompleteEvaluationError(
                "this repository pins golfo-kit and has a release pending, and SessionStart cannot update a pack alone; "
                "the repository keeps its committed assets until someone adopts both"
            )


def asset_owner(entry):
    """The source an asset of a plan or a lock comes from: a pack, or golfo-kit."""
    profile = entry.get("profile") or ""
    return source_of_profile(profile) if is_pack_profile(profile) else golfo_kit.GOLFO_KIT_SOURCE_NAME


def is_engine_asset(entry):
    """An asset the installed engine projects (hooks and what connects them): never pinned, so never compared."""
    return asset_owner(entry) == golfo_kit.GOLFO_KIT_SOURCE_NAME and golfo_kit.is_engine_owned(entry.get("source") or "")


def locked_desired_sha256(locked_entry):
    """The content a source published for an asset of the lock: applied, or wanted when it ended in conflict."""
    if locked_entry.get("state") == STATE_APPLIED:
        return locked_entry.get("sha256")
    return locked_entry.get("desiredSha256")


def lock_differences(plan, lock):
    """Why a plan does not reproduce the lock, one line per source, and how many engine files differ.

    Content is compared byte for byte: the selection, the revision of golfo-kit and of each
    pack, the digest of each pack and the sha256 of every asset and merged template. The files
    of the engine follow the installed one, so they are only counted.
    """
    if not lock:
        return ["there is no lockfile to apply from; run an apply first"], 0
    differences = []
    if plan["profiles"] != lock.get("profileOrder"):
        differences.append(f"selection: the manifest resolves to {', '.join(plan['profiles'])} and the lock has "
                           f"{', '.join(lock.get('profileOrder') or []) or 'none'}")
    locked_revision = (lock.get("source") or {}).get("revision")
    if locked_revision and plan["source"].get("revision") != locked_revision:
        differences.append(f"{golfo_kit.GOLFO_KIT_SOURCE_NAME}: revision {(plan['source'].get('revision') or 'none')[:12]} "
                           f"instead of {locked_revision[:12]}")
    locked_sources = lock.get("profileSources", {})
    for name in sorted(set(locked_sources) | set(plan["profileSources"])):
        locked_entry, current = locked_sources.get(name), plan["profileSources"].get(name)
        if not current:
            differences.append(f"{name}: in the lock, but this repository no longer selects it")
        elif not locked_entry:
            differences.append(f"{name}: not in the lock")
        elif current.get("resolvedCommit") != locked_entry.get("resolvedCommit"):
            differences.append(f"{name}: revision {(current.get('resolvedCommit') or 'none')[:12]} instead of "
                               f"{(locked_entry.get('resolvedCommit') or 'none')[:12]}")
        elif current.get("contentDigest") != locked_entry.get("contentDigest"):
            differences.append(f"{name}: its content does not match the digest of the lock")
    locked_assets = lock.get("assets", {})
    desired = {entry["destination"]: entry for entry in plan["entries"] if entry["sha256"]}
    engine_changes = 0
    for destination, entry in sorted(desired.items()):
        locked_entry = locked_assets.get(destination)
        if is_engine_asset(entry):
            engine_changes += bool(locked_entry) and locked_entry.get("sha256") != entry["sha256"]
        elif not locked_entry:
            differences.append(f"{asset_owner(entry)}: {destination} is not in the lock")
        elif locked_desired_sha256(locked_entry) != entry["sha256"]:
            differences.append(f"{asset_owner(entry)}: {destination} does not match the sha256 of the lock")
    for destination, locked_entry in sorted(locked_assets.items()):
        # A retired asset the project kept (retired-preserved) is no longer published by any source.
        if destination not in desired and locked_entry.get("state") != STATE_RETIRED_PRESERVED and not is_engine_asset(locked_entry):
            differences.append(f"{asset_owner(locked_entry)}: {destination} is in the lock but not in this resolution")
    for destination, entry in sorted(plan["merged"].items()):
        if golfo_kit.is_engine_owned(entry["template"]):
            continue
        locked_entry = lock.get("merged", {}).get(destination)
        if not locked_entry or locked_entry.get("templateSha256") != entry["templateSha256"]:
            differences.append(f"{golfo_kit.GOLFO_KIT_SOURCE_NAME}: the template of {destination} does not match the lock")
        elif locked_entry.get("inputsSha256") != entry.get("inputsSha256"):
            differences.append(f"{golfo_kit.GOLFO_KIT_SOURCE_NAME}: what {destination} is rendered with (the centralization "
                               "and proxy texts) does not match the lock")
    return differences, engine_changes


def enforce_lock_reproduction(plan, lock):
    """--from-lock projects exactly the lock or nothing: stop before writing and name what differs."""
    differences, engine_changes = lock_differences(plan, lock)
    if differences:
        raise ProfileError("--from-lock cannot reproduce the lock, so nothing was changed:\n  - " + "\n  - ".join(differences))
    if engine_changes:
        write_line(f"--from-lock: {engine_changes} file(s) of the engine (hooks and their settings) follow the installed "
                   "plugin and differ from the lock; the content is the lock's.", sys.stderr)


def keep_locked_entries_of_unselected_sources(plan, lock):
    """SessionStart does not adopt a pinned source without selected profiles either: its drift stays visible."""
    locked_sources = (lock or {}).get("profileSources", {})
    for name, item in plan["sourceReport"].items():
        if item["selected"] or not item["differences"] or item["updates"] == UPDATES_AUTO:
            continue
        if name in locked_sources:
            plan["profileSources"][name] = locked_sources[name]
        else:
            plan["profileSources"].pop(name, None)


def run_quiet(command, cwd=None):
    """Run a read-only command and return its UTF-8 stdout, or None when it fails."""
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


SOURCE_KIND_GIT = "git"


def source_kind(skill_dir):
    """Where the skill source comes from: marketplace snapshot, cache or local."""
    normalized = os.path.abspath(skill_dir).replace(os.sep, "/")
    if "/plugins/marketplaces/" in normalized or "/.tmp/marketplaces/" in normalized:
        return "marketplace-snapshot"
    if "/plugins/cache/" in normalized:
        return "plugin-cache"
    return "local"


def source_revision(skill_dir):
    """Git revision of the skill source and whether it has local changes."""
    top_level = run_quiet(["git", "-C", skill_dir, "rev-parse", "--show-toplevel"])
    if not top_level:
        return None, None
    revision = run_quiet(["git", "-C", skill_dir, "rev-parse", "HEAD"])
    porcelain = run_quiet(["git", "-C", skill_dir, "status", "--porcelain", "--", "."])
    return revision, bool(porcelain)


def golfo_kit_pending(skill_dir):
    """A newer golfo-kit the installed plugin brings while the repository projects pinned content, or None."""
    marker = golfo_kit.read_marker(skill_dir)
    if not marker:
        return None
    engine_revision, _ = source_revision(marker["engineSkillDir"]) if os.path.isdir(marker["engineSkillDir"]) else (None, None)
    pinned_version, engine_version = plugin_version(skill_dir), marker.get("engineVersion")
    if engine_revision == marker["commit"]:
        return None
    # An installed plugin outside a Git checkout (the provider cache) has no revision: its version decides.
    if not engine_revision and engine_version == pinned_version:
        return None
    brings = f"{engine_version} ({engine_revision[:12]})" if engine_revision else f"{engine_version}"
    return {
        "pinnedRevision": marker["commit"], "pinnedVersion": pinned_version,
        "engineRevision": engine_revision, "engineVersion": engine_version,
        "message": (f"golfo-kit stays at {pinned_version} ({marker['commit'][:12]}); the installed plugin brings "
                    f"{brings}. Adopt it with: agent-ready update golfo-kit"),
    }


def content_version(skill_dir):
    """Version of the golfo-kit content: the ``version`` its catalog declares, else its plugin's."""
    try:
        declared = read_json_file(os.path.join(skill_dir, PROFILE_CATALOG_RELATIVE_PATH), "profile catalog").get("version")
    except StateError:
        declared = None
    return declared if isinstance(declared, str) and compatibility.semver_key(declared) else plugin_version(skill_dir)


def engine_version_of(skill_dir):
    """Version of the engine that projects ``skill_dir``: the installed one, also for pinned content."""
    marker = golfo_kit.read_marker(skill_dir)
    return marker["engineVersion"] if marker else plugin_version(skill_dir)


def source_identity(skill_dir, assets, merged_templates):
    """Identity of the resolved source; contentDigest is the immutable part.

    Pinned golfo-kit content records the Git origin and revision it came from, so the next apply
    of a pinned repository fetches exactly that content again.
    """
    digest_lines = [f"{destination}\t{entry['sha256']}" for destination, entry in sorted(assets.items())]
    digest_lines += [f"{destination}\t{entry['templateSha256']}" for destination, entry in sorted(merged_templates.items())]
    digest_lines += [
        f"{relative_path}\t{sha256_of_file(os.path.join(skill_dir, relative_path))}"
        for relative_path in RENDERED_INSTRUCTION_INPUTS
        if os.path.isfile(os.path.join(skill_dir, relative_path))
    ]
    marker = golfo_kit.read_marker(skill_dir)
    if marker:
        revision, dirty, kind = marker["commit"], False, SOURCE_KIND_GIT
    else:
        (revision, dirty), kind = source_revision(skill_dir), source_kind(skill_dir)
    identity = {
        "plugin": PLUGIN_NAME,
        "skill": SKILL_NAME,
        "version": content_version(skill_dir),
        "kind": kind,
        "revision": revision,
        "contentDigest": sha256_of_text("\n".join(digest_lines)),
    }
    origin = marker["origin"] if marker else golfo_kit_origin(skill_dir) if revision else None
    if origin:
        identity["origin"] = origin
    if marker and marker.get("requestedRef"):
        identity["requestedRef"] = marker["requestedRef"]
    if dirty:
        identity["revisionHasLocalChanges"] = True
    return identity


def golfo_kit_origin(skill_dir):
    """The marketplace a revision of this installation can be fetched from, or None."""
    try:
        return golfo_kit.engine_origin(skill_dir)
    except ProfileError:
        return None


def merged_template_entries(skill_dir, catalog, resolved):
    """Files merged with project content instead of copied verbatim."""
    primary = primary_stack(catalog, resolved)
    agents_template = os.path.join(profile_asset_root(skill_dir, catalog, primary), AGENTS_TEMPLATE_NAME)
    settings_template = os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"), CLAUDE_SETTINGS_TEMPLATE_NAME)
    codex_template = os.path.join(skill_dir, CODEX_HOOKS_TEMPLATE_RELATIVE_PATH)
    entries = {}
    for destination, template, kind in (
        ("AGENTS.md", agents_template, "managed-block"),
        (".claude/settings.json", settings_template, "merged-json"),
        (".codex/hooks.json", codex_template, "merged-json"),
    ):
        if os.path.isfile(template):
            entries[destination] = {
                "kind": kind,
                "template": os.path.relpath(template, skill_dir).replace(os.sep, "/"),
                "templateSha256": sha256_of_file(template),
            }
    if "AGENTS.md" in entries:
        entries["AGENTS.md"]["inputsSha256"] = rendered_inputs_digest(skill_dir)
    return entries


def rendered_inputs_digest(skill_dir):
    """Content the managed block of AGENTS.md is rendered with besides its template; the renderer is the engine's."""
    lines = [f"{relative_path}\t{sha256_of_file(os.path.join(skill_dir, relative_path))}"
             for relative_path in RENDERED_INSTRUCTION_INPUTS
             if not golfo_kit.is_engine_owned(relative_path) and relative_path != RENDERER_RELATIVE_PATH
             and os.path.isfile(os.path.join(skill_dir, relative_path))]
    return sha256_of_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Manifest and lockfile
# ---------------------------------------------------------------------------

def read_manifest(project_root):
    """The repository manifest (the project layer), validated, or None when there is none.

    Reading it resolves every layer, so an invalid organization, user or project file
    stops here, before anything is written.
    """
    configuration = configuration_of(project_root)
    if configuration.project_document is not None:
        parse_profile_sources(configuration.project_document.get("sources", {}).get("packs", []),
                              os.path.join(project_root, MANIFEST_RELATIVE_PATH))
    return configuration.project_document


def read_lock(project_root):
    """Read the lockfile, or None when the repository was never locked."""
    path = os.path.join(project_root, LOCK_RELATIVE_PATH)
    if not os.path.exists(path) and not os.path.islink(path):
        return None
    if os.path.islink(path):
        raise StateError(f"{path} is a symlink; Agent Ready does not follow it")
    lock = read_json_file(path, "Agent Ready lockfile")
    if not isinstance(lock.get("assets"), dict):
        raise StateError(f"{path} has no 'assets' inventory")
    return lock


_REVIEW_CACHE = None


def review_cache_module():
    """review-cache.py of this installation, loaded once; its file name is not importable directly."""
    global _REVIEW_CACHE
    if _REVIEW_CACHE is None:
        import importlib.util

        path = os.path.join(ENGINE_SKILL_DIRECTORY, REVIEW_CACHE_RELATIVE_PATH)
        specification = importlib.util.spec_from_file_location("review_cache", path)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        _REVIEW_CACHE = module
    return _REVIEW_CACHE


def review_findings(project_root, strict=False):
    """Every finding of the current reviews with its id and status, read without calling the provider.

    Returns (findings, decisions, units, stale). An entry whose files changed since its review is
    out of date: it is counted in stale, not shown, and runs again on the next edit or apply.
    ``strict`` refuses a decisions file that cannot be read instead of ignoring it.
    """
    module = review_cache_module()
    # The effective configuration, not the options of the last apply: a fresh clone shows the
    # committed reviews before anyone applies.
    try:
        commit = configuration_of(project_root).value(REVIEWS_COMMIT_KEY)
    except ConfigurationError:
        commit = None
    entries = module.ReviewCache(project_root).entries(commit=commit)
    decisions = module.Decisions(project_root)
    recorded = decisions.read(strict=strict)
    findings = []
    units = 0
    stale = 0
    for unit, entry in sorted(entries.items()):
        files = entry.get("files", {}) if isinstance(entry, dict) else {}
        # A semantic conflict with AGENTS.md is about what the project wrote there, not the managed block.
        semantic = (isinstance(entry, dict) and entry.get("check") == conflicts_review.CONFLICT_CHECK
                    and conflicts_review.AGENTS_FILE in files)
        current = (conflicts_review.current_hashes(module, project_root, files, project_owned_instructions)
                   if semantic else module.file_hashes(project_root, files))
        if files and current == files:
            units += 1
            annotated = decisions.annotate(unit, entry.get("findings", []), recorded)
            if semantic:
                for finding in annotated:
                    finding["reviewedFiles"] = current
                    if finding["decision"]:
                        finding["status"] = conflicts_review.decision_status(module, finding["decision"], current)
            findings += [dict(finding, check=entry.get("check")) for finding in annotated]
        else:
            stale += 1
    return findings, recorded, units, stale


def review_summary(project_root):
    """What status and plan show of the AI reviews: open findings and decisions to confirm."""
    module = review_cache_module()
    findings, decisions, units, stale = review_findings(project_root)
    shown = module.visible(findings)
    return {"units": units, "stale": stale, "findings": shown, "quiet": len(findings) - len(shown),
            "decisions": len(decisions)}


def record_review_settings(project_root):
    """Leave the reviews options where the hooks read them, so they follow the configuration."""
    configuration = configuration_of(project_root)
    module = review_cache_module()
    try:
        module.ReviewCache(project_root).write_settings(configuration.value(REVIEWS_ENABLED_KEY),
                                                        configuration.value(REVIEWS_CACHE_KEY),
                                                        configuration.value(REVIEWS_TTL_KEY),
                                                        configuration.value(REVIEWS_COMMIT_KEY))
    except (OSError, module.CacheLockTimeout) as caught_error:
        sys.stderr.write(f"WARNING: the review settings were not recorded: {caught_error}\n")


def build_manifest(previous, profiles, updates):
    """Manifest after an apply: the profiles it applied and, with --updates, the new mode.

    The apply never writes a default: --updates with the default value removes the key, so
    the repository follows whatever the lower layers say. What people wrote stays as is,
    because a value equal to the default may override the organization or the user.
    """
    manifest = json.loads(json.dumps(previous or {}))
    manifest[PROFILES_KEY] = list(profiles)
    if updates:
        set_sparse(manifest, UPDATES_MODE_KEY, updates, load_schema())
    return manifest


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def was_applied(lock_entry):
    """True when an apply wrote this destination, which is what makes it managed.

    A preserved project file stays in the lock without an applied base. A failed
    write also has no base, but the apply did try to own that destination.
    """
    return bool(lock_entry) and (bool(lock_entry.get("sha256")) or lock_entry.get("state") == STATE_FAILED)


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


def classify_retired(local, lock_entry):
    """Decision for a locked asset that no selected profile publishes anymore."""
    if local == LOCAL_ABSENT:
        return ACTION_DROP, "already removed"
    if not was_applied(lock_entry):
        return ACTION_DROP, "never applied by agent-ready-setup; it stays as a project file"
    if local == LOCAL_NOT_A_FILE:
        return ACTION_RETIRE_CONFLICT, "retired from the profiles but it is not a regular file"
    if local == lock_entry.get("sha256"):
        return ACTION_RETIRE, "no longer published by the selected profiles"
    return ACTION_RETIRE, "no longer published by the selected profiles; removes its local changes"


def claude_view_of(destination, source):
    """Project path of the .claude view of a managed asset, or None when it has none."""
    relative = destination[len(".agents/"):] if destination.startswith(".agents/") else ""
    if relative.split("/", 1)[0] not in CLAUDE_VIEW_DIRECTORIES or not source.endswith("/" + relative):
        return None
    return ".claude/" + relative


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


def compute_plan(project_root, skill_dir, catalog, profile_names):
    """Build the read-only plan for the selected profiles."""
    resolved = resolve_profiles(catalog, profile_names)
    assets = desired_assets(skill_dir, catalog, resolved)
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
        })
    for destination, lock_entry in sorted(locked_assets.items()):
        if destination in assets:
            continue
        local = local_state(os.path.join(project_root, destination))
        action, reason = classify_retired(local, lock_entry)
        if action == ACTION_RETIRE and has_linked_parent(project_root, destination):
            action, reason = ACTION_RETIRE_CONFLICT, LINKED_PARENT_REASON
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
    digests = profile_digests(skill_dir, catalog, resolved)
    golfo_assets = {destination: entry for destination, entry in assets.items() if not is_pack_profile(entry["profile"])}
    # Without a lockfile the first apply keeps the previous overwrite contract.
    edited_views, preserved_views = detached_views(project_root, assets, locked_assets) if lock else ([], [])
    identity = source_identity(skill_dir, golfo_assets, merged)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "profiles": resolved,
        "primaryStack": primary_stack(catalog, resolved),
        "tools": resolved_tools(catalog, resolved),
        # Packs have their own entries: an update of a pack is not an update of Golfo.
        "source": identity,
        "profileDigests": digests,
        "profileSources": source_entries(catalog, resolved, digests, (lock or {}).get("profileSources", {})),
        "sourceReport": source_report(catalog, resolved, digests, lock),
        "versionChanges": version_changes(catalog, identity, lock),
        "lockedSource": lock.get("source") if lock else None,
        "hasLock": lock is not None,
        "entries": entries,
        "editedViews": edited_views,
        "detachedViews": preserved_views,
        "merged": merged,
        # What the selected pack profiles declare besides files; the policy judges them later.
        "packToolDeclarations": pack_tools.declared_tools(catalog, resolved, source_of_profile, is_pack_profile),
    }


def extract_managed_block(text):
    """Text between the managed markers (inclusive), or None."""
    start = text.find(MANAGED_BLOCK_START)
    end = text.find(MANAGED_BLOCK_END)
    if start < 0 or end < start:
        return None
    return text[start:end + len(MANAGED_BLOCK_END)]


def merged_file_changes(project_root, skill_dir, plan):
    """Describe whether each merged file would change, without writing it."""
    changes = []
    catalog = load_profile_catalog(skill_dir)
    # Bootstrap exports the composed tree, the one the managed block is rendered from.
    stack_root = os.environ.get("AGENT_READY_SETUP_STACK_DIR") or profile_asset_root(skill_dir, catalog, plan["primaryStack"])

    agents_path = os.path.join(project_root, "AGENTS.md")
    renderer = [
        bash_executable(), os.path.join(skill_dir, RENDERER_RELATIVE_PATH),
        "--template", os.path.join(stack_root, AGENTS_TEMPLATE_NAME),
        "--rules-dir", os.path.join(stack_root, "rules"),
        "--common-rules-dir", os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"), "rules"),
        "--centralization", os.path.join(skill_dir, CENTRALIZATION_RELATIVE_PATH),
        "--managed-block",
    ]
    if os.path.isdir(os.path.join(project_root, ".agents/rules")):
        renderer += ["--project-rules-dir", ".agents/rules"]
    rendered_block = run_quiet(renderer, cwd=project_root)
    if not os.path.isfile(agents_path):
        changes.append(("AGENTS.md", ACTION_CREATE, "created from the stack template"))
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
            if os.path.isfile(absolute_path) and not os.path.islink(absolute_path) and sha256_of_file(absolute_path) != proxy_hash:
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


def describe_source(identity):
    """One-line description of a source identity."""
    if not identity:
        return "none"
    version = identity.get("version") or "unknown version"
    revision = identity.get("revision")
    suffix = f", revision {revision[:12]}" if revision else ""
    if identity.get("revisionHasLocalChanges"):
        suffix += " with local changes"
    return f"{identity.get('plugin', PLUGIN_NAME)} {version} ({identity.get('kind', 'unknown')}{suffix}; content {identity.get('contentDigest', '')[:12]})"


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
            f"{plan['primaryStack']}; change it explicitly with --stack or --profiles.",
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


def added_dependencies(catalog, requested, resolved):
    """Profiles that the selection did not name, with the profiles that require them."""
    added = {}
    for name in resolved:
        if name not in requested:
            added[name] = sorted(other for other in resolved if name in catalog["profiles"][other].get("requires", []))
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


def semantic_conflicts(arguments, plan):
    """The AI review of managed rules against the project's own, or None when it is off."""
    configuration = configuration_of(arguments.project, arguments.offline)
    if not configuration.value(CONFLICTS_ENABLED_KEY) or not configuration.value(REVIEWS_ENABLED_KEY):
        conflicts_review.record_pending(arguments.project, [])
        return None
    if not conflicts_review.engine_can_review(ENGINE_SKILL_DIRECTORY):
        return None
    module = review_cache_module()
    lock = read_lock(arguments.project)
    directions, texts = conflicts_review.conflict_pairs(
        arguments.project, plan["entries"], (lock or {}).get("assets", {}), module.normalized_text,
        project_owned_instructions, ENGINE_SKILL_DIRECTORY)
    # Offline runs and automated reviews answer from the cache only.
    use_provider = not arguments.offline and os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") != "1"
    # The options of this run: the hooks' copy of them only changes when an apply finishes.
    settings = {"enabled": True, "cache": configuration.value(REVIEWS_CACHE_KEY),
                "ttl": configuration.value(REVIEWS_TTL_KEY), "commit": configuration.value(REVIEWS_COMMIT_KEY)}
    report = conflicts_review.review_conflicts(arguments.project, ENGINE_SKILL_DIRECTORY, module, arguments.provider,
                                               directions, texts, bash_executable(), use_provider, settings,
                                               publish=arguments.format == "protected")
    conflicts_review.record_pending(arguments.project, report.pop("pending", []))
    report["block"] = configuration.value(CONFLICTS_BLOCK_KEY)
    return report


def project_owned_instructions(text):
    """What the project wrote in AGENTS.md: the managed block is the engine's, and an update replaces it."""
    try:
        remaining = without_managed_block(text)
    except ValueError:
        # Markers that are not one pair: nothing can tell the block apart, so all of it is reviewed.
        return text
    return text if remaining is None else remaining


def describe_conflict(finding):
    direction = "this update" if finding["direction"] == conflicts_review.DIRECTION_UPDATE else "a project rule"
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


def print_plan(project_root, skill_dir, plan, provider, skip_marketplace_upgrade, configuration):
    """Human readable plan on stdout."""
    stream = sys.stdout
    write_line(paint("Agent Ready plan (read-only: nothing was written)", "heading", stream))
    write_line(f"Profiles: {', '.join(plan['profiles'])} (primary stack: {plan['primaryStack']})")
    write_line(f"Selected by: {plan['selection']}")
    for name, requirers in plan["addedDependencies"].items():
        write_line(f"Dependency added: {name} (required by {', '.join(requirers)})")
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


# ---------------------------------------------------------------------------
# Finalize (after Bash projection)
# ---------------------------------------------------------------------------

def remove_claude_view_of(project_root, destination):
    """Remove the .claude view of a retired .agents asset when it is a managed view."""
    if not destination.startswith(".agents/"):
        return None
    relative_view = ".claude/" + destination[len(".agents/"):]
    if has_linked_parent(project_root, relative_view):
        return None
    view = os.path.join(project_root, relative_view)
    asset = os.path.join(project_root, destination)
    if os.path.islink(view):
        target = os.path.normpath(os.path.join(os.path.dirname(view), os.readlink(view)))
        if target == os.path.normpath(asset):
            os.unlink(view)
            return view
        return None
    if os.path.isfile(view) and os.path.isfile(asset) and os.path.samefile(view, asset):
        os.unlink(view)
        return view
    return None


def remove_empty_parents(project_root, path):
    """Remove empty managed directories left by a retired asset."""
    stop_directories = {os.path.normpath(os.path.join(project_root, root)) for root in (".agents", ".claude", ".github", ".codex")}
    directory = os.path.dirname(path)
    while os.path.normpath(directory) not in stop_directories and directory.startswith(project_root):
        try:
            os.rmdir(directory)
        except OSError:
            return
        directory = os.path.dirname(directory)


def finalize(project_root, skill_dir, plan, updates):
    """Retire assets, then write the lockfile and the manifest."""
    lock_assets = {}
    removed = []
    retire_conflicts = []
    failed = []
    conflicts = []
    preserved_views = set(plan["detachedViews"])
    previous_lock = read_lock(project_root)
    previous_assets = previous_lock["assets"] if previous_lock else {}

    for entry in plan["entries"]:
        destination = entry["destination"]
        absolute_path = os.path.join(project_root, destination)
        previous_entry = previous_assets.get(destination, {})
        if entry["action"] == ACTION_DROP:
            continue
        if entry["action"] == ACTION_RETIRE:
            if local_state(absolute_path) != entry["local"] or has_linked_parent(project_root, destination):
                retire_conflicts.append(f"{destination} changed during synchronization; preserved")
                lock_assets[destination] = dict(previous_entry, state=STATE_RETIRED_PRESERVED)
                continue
            view = remove_claude_view_of(project_root, destination)
            if view:
                removed.append(os.path.relpath(view, project_root).replace(os.sep, "/"))
            os.unlink(absolute_path)
            remove_empty_parents(project_root, absolute_path)
            removed.append(destination)
            continue
        if entry["action"] == ACTION_RETIRE_CONFLICT:
            retire_conflicts.append(f"{destination}: {entry['reason']}")
            lock_assets[destination] = dict(previous_entry, state=STATE_RETIRED_PRESERVED)
            continue
        if entry["action"] == ACTION_CONFLICT:
            conflicts.append(f"{destination}: {entry['reason']}")
            lock_assets[destination] = {
                "profile": entry["profile"],
                "source": entry["source"],
                "sha256": entry["baseSha256"],
                # What the source wanted to write: --from-lock verifies the content against it.
                "desiredSha256": entry["sha256"],
                "state": STATE_CONFLICT,
            }
            continue
        if local_state(absolute_path) == entry["sha256"]:
            lock_assets[destination] = {
                "profile": entry["profile"],
                "source": entry["source"],
                "sha256": entry["sha256"],
                "state": STATE_APPLIED,
            }
        else:
            failed.append(destination)
            lock_assets[destination] = {
                "profile": entry["profile"],
                "source": entry["source"],
                "sha256": entry["baseSha256"],
                "desiredSha256": entry["sha256"],
                "state": STATE_FAILED,
            }

    # Whatever happened to the asset, a project file in its view stays the project's.
    for entry in plan["entries"]:
        if entry["sha256"] and entry["destination"] in lock_assets and                 claude_view_of(entry["destination"], entry["source"]) in preserved_views:
            lock_assets[entry["destination"]]["viewPreserved"] = True

    conflicts += [f"{view}: {DETACHED_VIEW_REASON}" for view in plan["detachedViews"]]

    lock = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": SKILL_NAME, "version": engine_version_of(skill_dir), "stateSchemaVersion": SCHEMA_VERSION},
        "source": plan["source"],
        "profiles": plan["profileDigests"],
        # The digests map is keyed by name; profileOrder keeps the resolution order.
        "profileOrder": plan["profiles"],
        "primaryStack": plan["primaryStack"],
        "providers": configuration_of(project_root).value(PROVIDERS_KEY),
        "requires": {"bash": "3.2+", "git": "any", "python3": "3.8+"},
        "assets": lock_assets,
        "merged": plan["merged"],
    }
    if plan["profileSources"]:
        lock["profileSources"] = plan["profileSources"]
    mcp_report = register_pack_mcp_servers(project_root, plan, previous_lock)
    if mcp_report["lock"]:
        lock["mcpServers"] = mcp_report["lock"]
    cli_report = install_pack_clis(project_root, plan, previous_lock)
    if cli_report["lock"]:
        lock["clis"] = cli_report["lock"]
    write_text_if_changed(os.path.join(project_root, LOCK_RELATIVE_PATH), serialize_json(lock))

    manifest = read_manifest(project_root)
    desired_manifest = build_manifest(manifest, plan["profiles_requested"], updates)
    if manifest != desired_manifest:
        write_text_atomically(os.path.join(project_root, MANIFEST_RELATIVE_PATH), serialize_json(desired_manifest))
    record_review_settings(project_root)
    # The update the last plan reviewed is on disk now: its conflicts are the current ones.
    conflicts_review.record_pending(project_root, [])

    return {"removed": removed, "retireConflicts": retire_conflicts, "failed": failed, "conflicts": conflicts,
            "mcpServers": mcp_report, "clis": cli_report}


def install_pack_clis(project_root, plan, previous_lock):
    """Install the CLIs of the packs that the policy allows, in the cache of the user; automated reviews install none."""
    previous = (previous_lock or {}).get("clis", {})
    if os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") == "1":
        return {"installed": [], "reused": [], "removed": [], "manual": [], "conflicts": [], "failed": [],
                "lock": previous, "path": [], "skipped": "automated reviews never install the CLIs of the packs"}
    return pack_clis.install(project_root, plan.get("packTools"), previous)


def print_pack_cli_report(report, stream):
    """What an apply installed, reused or dropped among the CLIs of the packs."""
    if not report:
        return
    if report.get("skipped"):
        write_line(f"CLIs of profile packs: unchanged ({report['skipped']}).", stream)
        return
    if report["installed"]:
        write_line(paint(f"CLIs of profile packs installed in {pack_clis.installs_root()}: {', '.join(report['installed'])}",
                         "ok", stream), stream)
    if report["reused"]:
        write_line(f"CLIs of profile packs already in the cache: {', '.join(report['reused'])}", stream)
    if report["removed"]:
        write_line(f"CLIs this repository no longer uses: {', '.join(report['removed'])}", stream)
    for note in report["manual"] + report["conflicts"]:
        write_line(paint(f"  ! {note}", "warning", stream), stream)
    for problem in report["failed"]:
        write_line(paint(f"  ! CLI not installed: {problem}", "error", stream), stream)


def register_pack_mcp_servers(project_root, plan, previous_lock):
    """Register the MCP servers of the packs that the policy allows; automated reviews change none."""
    previous = (previous_lock or {}).get("mcpServers", {})
    if os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") == "1":
        return {"registered": {}, "removed": {}, "conflicts": [], "failed": [], "lock": previous,
                "skipped": "automated reviews never change the MCP servers the providers start"}
    providers = configuration_of(project_root).value(PROVIDERS_KEY)
    return pack_mcp.register(project_root, plan.get("packTools"), previous, providers)


def print_pack_mcp_report(report, stream):
    """What an apply registered, unregistered or left alone among the MCP servers of the packs."""
    if not report:
        return
    if report.get("skipped"):
        write_line(f"MCP servers of profile packs: unchanged ({report['skipped']}).", stream)
        return
    for path, names in sorted(report["registered"].items()):
        if names:
            write_line(paint(f"MCP servers of profile packs in {path}: {', '.join(names)}", "ok", stream), stream)
    for path, names in sorted(report["removed"].items()):
        if names:
            write_line(f"Unregistered from {path}: {', '.join(names)}", stream)
    for conflict in report["conflicts"]:
        write_line(paint(f"  ! MCP server kept as the project has it: {conflict}", "warning", stream), stream)
    for problem in report["failed"]:
        write_line(paint(f"  ! {problem}", "error", stream), stream)


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


def print_finalize_report(report):
    """Report retirement, preserved conflicts and the overall result."""
    stream = sys.stdout
    if report["removed"]:
        write_line("Retired managed assets:")
        for path in report["removed"]:
            write_line(f"  - {path}")
    # The projection already reported each preserved conflict with its path.
    if report["retireConflicts"]:
        write_line(paint("Retired assets kept because they changed locally:", "warning", stream))
        for conflict in report["retireConflicts"]:
            write_line(f"  ! {conflict}")
    if report["failed"]:
        write_line(paint("Managed assets that could not be applied (see conflicts above):", "error", stream))
        for path in report["failed"]:
            write_line(f"  ! {path}")
    print_pack_mcp_report(report.get("mcpServers"), stream)
    print_pack_cli_report(report.get("clis"), stream)
    if report["failed"]:
        result = "partial: some managed assets could not be applied"
    elif report["conflicts"] or report["retireConflicts"]:
        preserved = len(report["conflicts"]) + len(report["retireConflicts"])
        result = f"applied with {preserved} preserved conflict(s)"
    else:
        result = "complete"
    write_line(f"Lockfile: {LOCK_RELATIVE_PATH} ({result})")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def selection_differences(lock, plan):
    """How the selected profiles differ from the lock, in words."""
    differences = []
    locked_order = lock.get("profileOrder")
    if locked_order != plan["profiles"]:
        differences.append(f"the lock has the profiles {', '.join(locked_order or []) or 'none'}; the selection resolves to {', '.join(plan['profiles'])}")
    locked_profiles = lock.get("profiles") or {}
    for name, entry in sorted(plan["profileDigests"].items()):
        if name in locked_profiles and locked_profiles[name] != entry:
            differences.append(f"profile {name} changed since the lock")
    return differences


def compute_status(project_root, skill_dir):
    """Read-only state: manifest, checkout versus lock, source versus lock."""
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
        "golfoKit": golfo_kit_pending(skill_dir) if skill_dir else None,
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

    profile_names = configuration.value(PROFILES_KEY) or (lock.get("profileOrder") if lock else None)
    if profile_names and skill_dir:
        try:
            catalog = load_effective_catalog(project_root, skill_dir)
            plan = compute_plan(project_root, skill_dir, catalog, profile_names)
        except IncompleteEvaluationError as caught_error:
            status["incomplete"] = str(caught_error)
        except (ProfileError, StateError) as caught_error:
            status["errors"].append(str(caught_error))
        else:
            status["sources"] = plan["sourceReport"]
            status["plan"] = plan
            status["packTools"] = pack_tools.report(plan["packToolDeclarations"], catalog, configuration)
            changed = [entry["destination"] for entry in plan["entries"]
                       if entry["action"] not in (ACTION_UNCHANGED, ACTION_DROP)]
            status["checkout"]["modified"].extend(plan["editedViews"] + plan["detachedViews"])
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


def status_has_drift(status):
    """True when the checkout or the source differs from the lock, or the selection cannot resolve."""
    if status["errors"] or status["incomplete"]:
        return True
    checkout = status["checkout"]
    if any(checkout[key] for key in ("modified", "missing", "conflict", "failed", "retiredPreserved")):
        return True
    return bool(status["update"] and status["update"]["available"]) or not status["hasLock"]


def print_pack_tools(report, stream, brief=False):
    """What the selected packs declare besides files, and what the security policy decides about each one."""
    if not report:
        return
    blocked = sum(tool["decision"] == pack_tools.DECISION_BLOCKED for tool in report["tools"])
    write_line(paint("Pack tools (what the security policy allows; an apply registers the allowed MCP servers "
                     "and installs the allowed CLIs, and does not run scripts yet)", "heading", stream), stream)
    for tool in report["tools"]:
        label = f"{pack_tools.describe_tool(tool)} [{tool['profile']}]"
        if tool["decision"] == pack_tools.DECISION_ALLOWED:
            effect = "" if tool["type"] in report.get("applies", []) else " (not installed or run yet)"
            write_line(paint(f"  + allowed: {label}{effect}", "ok", stream), stream)
        else:
            write_line(paint(f"  - blocked: {label}: {tool['reason']}", "warning", stream), stream)
    if not brief:
        write_line("  Policy:", stream)
        for key, item in report["policy"].items():
            write_line(f"    {key}: {format_value(item['value'])} ({item['origin']})", stream)
    elif blocked:
        write_line(f"  {blocked} blocked; agent-ready plan shows the policy and the layer of each value.", stream)
    write_line("", stream)


def print_review_summary(reviews, brief, stream):
    """Open findings of the AI reviews and decisions to confirm, from the cache; nothing when there is no review yet."""
    if not reviews or not (reviews["units"] or reviews["stale"]):
        return
    module = review_cache_module()
    quiet = f"; {reviews['quiet']} accepted or dismissed" if reviews.get("quiet") else ""
    if reviews["findings"]:
        write_line(paint(f"AI reviews: {len(reviews['findings'])} known finding(s) in {reviews['units']} reviewed unit(s), "
                         f"from the cache{quiet}:", "warning", stream), stream)
        if not brief:
            for finding in reviews["findings"]:
                write_line(paint(f"  {module.finding_line(finding)}", "warning", stream), stream)
            write_line(f"  Accept or dismiss one with: agent-ready review accept <id> --reason \"...\"", stream)
    else:
        write_line(paint(f"AI reviews: no known finding in {reviews['units']} reviewed unit(s){quiet}.", "ok", stream), stream)
    if reviews["stale"] and not brief:
        write_line(f"  {reviews['stale']} review(s) are out of date and run again on the next edit or apply.", stream)


def print_status(status, brief):
    """Human readable status."""
    stream = sys.stdout
    configuration = status["configuration"]
    profiles = configuration.value(PROFILES_KEY)
    if not profiles:
        hint = "" if brief else " Run /agent-ready-setup to pin this repository."
        write_line(paint(f"Agent Ready: no profiles selected in {MANIFEST_RELATIVE_PATH}.{hint}", "warning", stream))
    else:
        write_line(f"Agent Ready profiles: {', '.join(profiles)} (updates: {configuration.value(UPDATES_MODE_KEY)})")
    # SessionStart already reported what was ignored when it read the configuration.
    if not brief:
        print_ignored_configuration(configuration, stream)
    if not status["hasLock"]:
        write_line(paint("No lockfile: applied assets are not pinned yet.", "warning", stream))
    else:
        write_line(f"Locked source: {describe_source(status['lockedSource'])}")
        if status.get("golfoKit"):
            write_line(paint(status["golfoKit"]["message"], "warning", stream))
        checkout = status["checkout"]
        write_line(
            "Checkout: "
            f"{len(checkout['applied'])} applied, {len(checkout['modified'])} modified, "
            f"{len(checkout['missing'])} missing, {len(checkout['conflict'])} preserved conflicts, "
            f"{len(checkout['failed'])} failed, {len(checkout['retiredPreserved'])} retired but preserved"
        )
        if not brief:
            for key, label in (("modified", "modified"), ("missing", "missing"), ("conflict", "conflict"),
                               ("failed", "failed"), ("retiredPreserved", "retired but preserved")):
                for destination in checkout[key]:
                    write_line(f"  ! {label}: {destination}")
    for name, item in status["sources"].items():
        if item["differences"] or item["pendingUpdate"] or item["state"] != SOURCE_AVAILABLE or not brief:
            write_line(f"Profile source {describe_source_item(name, item)}")
        if item["differences"]:
            write_line(paint(f"  ! {name} differs from the lock: {'; '.join(item['differences'])}", "warning", stream))
        if item["pendingUpdate"]:
            write_line(paint(f"  ! {name}: {item['pendingUpdate']}", "warning", stream))
    if status["incomplete"]:
        write_line(paint(f"Evaluation incomplete, nothing was validated: {status['incomplete']}", "warning", stream))
    update = status["update"]
    if update:
        if update["available"]:
            hint = "" if brief else " Review it with `/agent-ready-setup plan` and apply it with `/agent-ready-setup`."
            write_line(paint(
                f"Update available: {describe_source(update['source'])}; {len(update['changedDestinations'])} asset(s) would change.{hint}",
                "warning", stream,
            ))
        else:
            write_line(paint("Source matches the lock: no update pending.", "ok", stream))
    print_review_summary(status.get("reviews"), brief, stream)
    print_pack_tools(status.get("packTools"), stream, brief=True)
    if not brief and status["capabilities"]:
        write_line("Provider capabilities:")
        for provider, capabilities in status["capabilities"].items():
            details = ", ".join(f"{name}={value['support']}" for name, value in capabilities.items())
            write_line(f"  {provider}: {details}")
    for error in status["errors"]:
        write_line(paint(f"ERROR: {error}", "error", stream))


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
    """The stack a repository without a selection starts with, or why there is none."""
    if detection["status"] == STATUS_RESOLVED:
        return detection["primaryStack"]
    selection_hint = f"select one with --stack {'|'.join(stack_names_of(catalog))} or --profiles <a,b>"
    if detection["status"] == STATUS_AMBIGUOUS:
        matches = ", ".join(f"{name} ({format_evidence_list(detection['stacks'][name])})" for name in detection["candidates"])
        raise ProfileError(f"could not detect project stack: several stacks match and none has priority: {matches}; {selection_hint}")
    raise ProfileError(f"could not detect project stack: no signal matched; {selection_hint}")


def resolve_selection(arguments, catalog):
    """Requested profiles and their origin: flags, then the manifest, then initial detection."""
    if getattr(arguments, "profiles", None):
        return split_profile_names(arguments.profiles), SELECTION_PROFILES_FLAG
    if getattr(arguments, "stack", None):
        return profiles_for_stack(catalog, arguments.stack), SELECTION_STACK_FLAG
    configuration = configuration_of(arguments.project)
    if configuration.value(PROFILES_KEY):
        return configuration.value(PROFILES_KEY), SELECTION_MANIFEST
    if not configuration.value(DETECTION_ENABLED_KEY):
        raise ProfileError(f"detection is off ({DETECTION_ENABLED_KEY}: false): select the profiles with --stack or --profiles")
    detection = detect_profiles(catalog["profiles"], arguments.project)
    return profiles_for_stack(catalog, stack_from_initial_detection(catalog, detection)), SELECTION_DETECTION


def command_resolve(arguments):
    """Print the resolution as key<TAB>value lines for Bash."""
    # A manifest that cannot be read stops the apply even when flags pick the
    # profiles: it may declare a pinned repository that must not be written.
    read_manifest(arguments.project)
    catalog = load_effective_catalog(arguments.project, arguments.skill_dir, read_source_state(arguments))
    requested, selection = resolve_selection(arguments, catalog)
    resolved = resolve_profiles(catalog, requested)
    validate_pack_destinations(arguments.project, desired_assets(arguments.skill_dir, catalog, resolved))
    if arguments.source_mode == SOURCE_MODE_SYNC:
        enforce_sync_policy(arguments.project, arguments.skill_dir, catalog, resolved, profile_digests(arguments.skill_dir, catalog, resolved))
    stack_dir = compose_stack_directory(arguments.skill_dir, catalog, resolved, arguments.compose_dir)
    if selection == SELECTION_DETECTION:
        detection = detect_profiles(catalog["profiles"], arguments.project)
        primary = detection["primaryStack"]
        write_line(f"Detected stack: {primary} ({format_evidence_list(detection['stacks'][primary])})", sys.stderr)
    write_line(f"profiles\t{','.join(resolved)}")
    write_line(f"requested\t{','.join(requested)}")
    write_line(f"selection\t{selection}")
    write_line(f"primary\t{primary_stack(catalog, resolved)}")
    write_line(f"stack_dir\t{stack_dir}")
    write_line(f"tools\t{','.join(resolved_tools(catalog, resolved))}")
    return 0


def approval_hint(project_root):
    """The exact command that approves a repository on this machine."""
    script = os.path.abspath(__file__)
    return f'approve it with: python3 "{script}" trust --project "{project_root}"'


def print_ignored_configuration(configuration, stream):
    """Warn about every value a layer could not set, and about ignored source update modes."""
    hint = approval_hint(configuration.project_root)
    for item in configuration.ignored:
        write_line(paint(f"WARNING: {describe_ignored(item, hint)}", "warning", stream), stream)
    for declaration in declared_sources(configuration.project_root):
        reason = source_update_mode_is_ignored(configuration, declaration)
        if reason is None:
            continue
        item = {"key": f"{SOURCES_PACKS_KEY}[{declaration['name']}].updates", "value": declaration["updates"],
                "layer": "project", "reason": reason}
        if reason in (IGNORED_LOCKED, IGNORED_LOOSENS):
            message = describe_ignored(item, hint)
        else:
            message = f"{item['key']}={declaration['updates']} was ignored: {reason}"
        write_line(paint(f"WARNING: {message}", "warning", stream), stream)


def automatic_sources(configuration):
    """Names of the sources whose effective update mode is auto: golfo-kit, then the declared packs."""
    names = [golfo_kit.GOLFO_KIT_SOURCE_NAME] if golfo_kit.update_mode(configuration) == UPDATES_AUTO else []
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
    with commas) and the derived line ``auto_sources``: golfo-kit and the declared sources in auto.
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
        for failure in refresh_declared_sources(declarations, locked_sources):
            write_line(f"WARNING: comparing with the local cache: {failure}", sys.stderr)
        return 0
    pins = download_declared_sources(declarations, locked_sources, arguments.update_source or [],
                                     configuration_of(arguments.project), arguments.project, to_ref=arguments.to,
                                     from_lock=arguments.from_lock, offline=arguments.offline)
    if arguments.state_file:
        write_text_atomically(arguments.state_file, serialize_json(pins))
    return 0


def golfo_kit_content_dir(project_root, skill_dir, offline=False, read_only=True):
    """Skill directory with the golfo-kit content this repository uses, for a run that writes nothing.

    Offline, a pinned revision missing from the cache falls back to ``skill_dir`` with a warning.
    """
    lock = read_lock(project_root)
    engine_revision, _ = source_revision(skill_dir)
    content_dir, warning = golfo_kit.content_skill_dir(
        configuration_of(project_root, offline), skill_dir, engine_revision, (lock or {}).get("source"),
        offline=offline, read_only=read_only,
    )
    if warning:
        write_line(f"WARNING: {warning}", sys.stderr)
    return content_dir


def command_golfo_kit_source(arguments):
    """Print the composed skill directory when the golfo-kit content of this run is not the engine's; see agent_ready_golfo_kit."""
    lock = read_lock(arguments.project)
    # A revision of the lock that is the HEAD of the installed engine stays with it, local changes
    # included: that is a checkout of the skill under development, not another revision to fetch.
    engine_revision, _ = source_revision(arguments.skill_dir)
    content_dir, warning = golfo_kit.content_skill_dir(
        configuration_of(arguments.project, arguments.offline), arguments.skill_dir,
        engine_revision, (lock or {}).get("source"),
        update=arguments.update, to_ref=arguments.to, offline=arguments.offline, read_only=arguments.read_only,
        from_lock=arguments.from_lock,
    )
    if warning:
        write_line(f"WARNING: {warning}", sys.stderr)
    # Nothing when the installed engine brings the content; a forward-slash path that Bash on
    # every system can use when it comes from a composed directory.
    if content_dir != arguments.skill_dir:
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
        if arguments.format == "json":
            write_line(serialize_json({"complete": False, "requestedProfiles": requested, "selection": selection,
                                       "incomplete": str(incomplete_error)}).rstrip("\n"))
            return INCOMPLETE_EVALUATION_STATUS
        print_incomplete_plan(arguments.project, arguments.skill_dir, selection, requested, incomplete_error)
        return INCOMPLETE_EVALUATION_STATUS
    if arguments.source_mode == SOURCE_MODE_SYNC:
        enforce_sync_policy(arguments.project, arguments.skill_dir, catalog, plan["profiles"], plan["profileDigests"])
        keep_locked_entries_of_unselected_sources(plan, read_lock(arguments.project))
    tools_report = pack_tools.report(plan["packToolDeclarations"], catalog,
                                     configuration_of(arguments.project, arguments.offline))
    if tools_report:
        plan["packTools"] = tools_report
    conflicts = semantic_conflicts(arguments, plan)
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


def command_status(arguments):
    """Print the read-only status."""
    status = compute_status(arguments.project, arguments.skill_dir)
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
    update = status["update"]
    if update and update["available"]:
        plan = status["plan"]
        locked_digest = (status["lockedSource"] or {}).get("contentDigest")
        if locked_digest != plan["source"]["contentDigest"]:
            problems.append(f"golfo-kit: the lock has {describe_source(status['lockedSource'])}; the source is {describe_source(plan['source'])}")
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
    # A repository that pins golfo-kit is checked against the content of its revision, like an apply.
    locked_source = (read_lock(project_root) or {}).get("source")
    golfo_kit.declaration_of(configuration, skill_dir, locked_source)  # an invalid declaration is a configuration error
    engine_revision, _ = source_revision(skill_dir)
    try:
        content_dir, missing_content = golfo_kit.content_skill_dir(
            configuration, skill_dir, engine_revision, locked_source, offline=offline, read_only=True,
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
    if unavailable:
        status = CHECK_SOURCE_UNAVAILABLE
    elif problems:
        status = CHECK_OUTDATED
    else:
        status = CHECK_UP_TO_DATE
    return {"status": status, "ci": ci, "problems": problems, "unavailable": unavailable}


def print_check_text(result):
    """Readable result of the check; the text is not a contract, the exit status is."""
    stream = sys.stdout
    headlines = {
        CHECK_UP_TO_DATE: ("up to date", "ok"),
        CHECK_OUTDATED: ("updates pending", "warning"),
        CHECK_SOURCE_UNAVAILABLE: ("source not available", "error"),
        CHECK_CONFIG_ERROR: ("configuration error", "error"),
        CHECK_SKIPPED: ("skipped", "muted"),
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


# ---------------------------------------------------------------------------
# Background update
# ---------------------------------------------------------------------------

def update_state_paths(project_root):
    """Per-user report and lock of one project; nothing machine-specific lands in it."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME") or os.path.expanduser("~"), ".cache")
    key = sha256_of_text(os.path.realpath(project_root))[:16]
    directory = os.path.join(base, "agent-ready-setup", "updates")
    return os.path.join(directory, f"{key}.json"), os.path.join(directory, f"{key}.lock")


def read_update_report(report_path):
    """Last background update of a project, or an empty report."""
    try:
        return read_json_file(report_path, "background update report")
    except StateError:
        return {}


def lock_for_comparison(project_root):
    """The lock before or after an update; an unreadable one compares as empty."""
    try:
        return read_lock(project_root) or {}
    except StateError:
        return {}


def assets_needing_attention(lock):
    """Assets an update could not leave as published: the next session must hear about them."""
    labels = {STATE_CONFLICT: "preserved conflict", STATE_FAILED: "could not be applied", STATE_RETIRED_PRESERVED: "retired but preserved"}
    return [
        f"{labels[entry.get('state')]}: {destination}"
        for destination, entry in sorted(lock.get("assets", {}).items())
        if entry.get("state") in labels
    ]


def summarize_lock_changes(before, after):
    """What an update changed, from the two lockfiles."""
    assets_before, assets_after = before.get("assets", {}), after.get("assets", {})
    changes = {
        "created": sorted(set(assets_after) - set(assets_before)),
        "updated": sorted(
            destination for destination in set(assets_after) & set(assets_before)
            if assets_after[destination].get("sha256") != assets_before[destination].get("sha256")
        ),
        "retired": sorted(set(assets_before) - set(assets_after)),
        "sources": [],
    }
    sources_before, sources_after = before.get("profileSources", {}), after.get("profileSources", {})
    for name in sorted(set(sources_before) | set(sources_after)):
        old_entry, new_entry = sources_before.get(name, {}), sources_after.get(name, {})
        if old_entry.get("resolvedCommit") != new_entry.get("resolvedCommit") or old_entry.get("contentDigest") != new_entry.get("contentDigest"):
            old_revision = (old_entry.get("resolvedCommit") or old_entry.get("contentDigest") or "none")[:12]
            new_revision = (new_entry.get("resolvedCommit") or new_entry.get("contentDigest") or "removed")[:12]
            changes["sources"].append(f"{name} {old_revision} -> {new_revision}")
    source_before, source_after = before.get("source", {}), after.get("source", {})
    if source_before.get("contentDigest") != source_after.get("contentDigest"):
        changes["sources"].append(f"golfo-kit {source_before.get('version') or 'none'} -> {source_after.get('version') or 'unknown'}")
    return changes


def locally_changed_assets(project_root, lock):
    """Managed files that differ from what the lock recorded, or that someone deleted."""
    return sorted(
        destination for destination, entry in lock.get("assets", {}).items()
        if entry.get("sha256") and local_state(os.path.join(project_root, destination)) != entry["sha256"]
    )


def terminate_process_tree(process):
    """Stop a process and its children: an orphan could keep writing after the lock is released."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        process.kill()


def run_sync(command, project_root, environment, timeout_seconds):
    """Run the foreground sync in its own process group. Returns (output, exit status)."""
    try:
        process = subprocess.Popen(
            command, cwd=project_root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", start_new_session=True,
        )
    except OSError as start_error:
        return f"ERROR: the sync could not start: {type(start_error).__name__}\n", 1
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
        return output, process.returncode
    except subprocess.TimeoutExpired:
        terminate_process_tree(process)
        output, _ = process.communicate()
        return f"{output}ERROR: the sync did not finish in {timeout_seconds} seconds and was stopped\n", 1


def command_background_update(arguments):
    """Run the sync detached from the session and leave its result for the next one."""
    report_path, lock_path = update_state_paths(arguments.project)
    if not acquire_directory_lock(lock_path):
        write_line("Another background update of this project is running.")
        return 0
    try:
        previous = read_update_report(report_path)
        failures = previous.get("consecutiveFailures", 0)
        age = time.time() - os.path.getmtime(report_path) if os.path.exists(report_path) else None
        if failures >= BACKGROUND_UPDATE_MAX_FAILURES and age is not None and age < BACKGROUND_UPDATE_RETRY_AFTER_SECONDS:
            write_line(f"{failures} background updates failed in a row; the next attempt waits {BACKGROUND_UPDATE_RETRY_AFTER_SECONDS} seconds.")
            return 0
        before = lock_for_comparison(arguments.project)
        changed_before = locally_changed_assets(arguments.project, before)
        environment = dict(os.environ)
        environment[FOREGROUND_SYNC_VARIABLE] = "1"
        command = [bash_executable(), arguments.hook, "--provider", arguments.provider]
        output, return_code = run_sync(command, arguments.project, environment, BACKGROUND_UPDATE_TIMEOUT_SECONDS)
        write_line(output.rstrip("\n"))
        problems = [line.strip() for line in output.splitlines() if line.startswith(("ERROR:", "WARNING:", "Evaluation incomplete:"))]
        if return_code != 0 and not problems:
            problems = [f"the sync exited with status {return_code}"]
        after = lock_for_comparison(arguments.project)
        changes = summarize_lock_changes(before, after)
        # The lock keeps its hash when a sync overwrites a local edit: only the checkout shows it.
        still_changed = set(locally_changed_assets(arguments.project, after))
        changes["restored"] = sorted(
            destination for destination in changed_before
            if destination not in still_changed and destination in after.get("assets", {})
            and destination not in changes["updated"]
        )
        backup_line = next((line.strip() for line in output.splitlines() if line.startswith(BACKUPS_LINE_PREFIX)), None)
        if backup_line:
            changes["backups"] = backup_line
        report = {
            "reported": False,
            "consecutiveFailures": failures + 1 if problems else 0,
            "changes": changes,
            "attention": assets_needing_attention(after),
            "problems": problems,
        }
        write_text_atomically(report_path, serialize_json(report))
    finally:
        os.rmdir(lock_path)
    return 0


def describe_update_changes(changes):
    """Readable lines of what a background update changed; nothing when it changed nothing."""
    counts = [f"{len(changes[key])} {key}" for key in ("created", "updated", "restored", "retired") if changes.get(key)]
    if not counts and not changes.get("sources"):
        return []
    details = ", ".join(counts + changes.get("sources", []))
    lines = [f"[marketplace-sync] The last background update changed the repository: {details}. Review it with git diff and commit it."]
    for key in ("created", "updated", "restored", "retired"):
        listed = changes.get(key, [])[:REPORT_MAX_LISTED_ASSETS]
        lines += [f"  {key}: {destination}" for destination in listed]
    if changes.get("backups"):
        lines.append(f"  {changes['backups']}")
    return lines


def command_update_report(arguments):
    """Show the result of the last background update once, in the next session."""
    report_path, _ = update_state_paths(arguments.project)
    report = read_update_report(report_path)
    if not report or report.get("reported"):
        return 0
    for line in describe_update_changes(report.get("changes", {})):
        write_line(line)
    for problem in report.get("problems", []) + report.get("attention", []):
        write_line(f"[marketplace-sync] The last background update reported: {problem[:REPORT_MAX_PROBLEM_CHARACTERS]}")
    report["reported"] = True
    write_text_atomically(report_path, serialize_json(report))
    return 0


# ---------------------------------------------------------------------------
# Removal
# ---------------------------------------------------------------------------

REMOVAL_REMOVE = "remove"
REMOVAL_EDIT = "edit"
REMOVAL_KEEP = "keep"
REMOVAL_SYMBOLS = {REMOVAL_REMOVE: "-", REMOVAL_EDIT: "~", REMOVAL_KEEP: "="}
REMOVAL_COLORS = {REMOVAL_REMOVE: "retire", REMOVAL_EDIT: "update", REMOVAL_KEEP: "muted"}
# What each entry is, in the order a removal runs: the lockfile goes last, so an
# interrupted removal can run again and finish.
REMOVAL_KINDS = ("pack-mcp", "pack-cli", "browser", "git-config", "git-hook", "review-cache", "view", "asset", "instructions", "settings", "state",
                 "config")
# Not a project path: the CLIs live in the cache of the user, shared by the repositories of the machine.
PACK_CLI_REMOVAL_LABEL = "CLIs of profile packs (cache of the user)"
# Same values as asset-sync-common.sh, which writes them.
HARD_LINK_VIEWS_MANIFEST = ".claude/.agent-ready-hard-link-views"
GIT_HOOK_SECTION = "hook.agent-ready-relink"
GIT_HOOK_COMMAND = "sh .agents/hooks/relink-hard-link-views.sh"
GIT_HOOK_FILE_NAME = "post-index-change"
GIT_HOOK_MARKER = "# agent-ready-setup: relinks .claude hard-link views detached by git."
# Same place as review-cache.py, which writes it: the info directory every worktree shares.
REVIEW_CACHE_INFO_PATH = "info/agent-ready/reviews.json"
# Same values as setup-browser-tools.py, which registers the servers.
BROWSER_SERVERS_MARKER = "/agent-ready-setup/browser-tools/"
BROWSER_REGISTRATION_FILES = (".mcp.json", ".codex/config.toml")
BROWSER_METADATA_RELATIVE_PATH = ".agents/browser-tools.json"
UNREGISTER_BROWSER_RELATIVE_PATH = "scripts/unregister-browser-servers.py"
MANAGED_ROOT_DIRECTORIES = (".agents", ".claude", ".codex", ".github")
CHANGED_DURING_REMOVAL_REASON = "changed while removing; it was kept"
# Same directories as SYNC_LOCK_DIRECTORY in bootstrap.sh and the session hook, and as
# MERGE_LOCK_DIRECTORY in managed-block.sh, which the detached instruction review holds.
SYNC_LOCK_RELATIVE_PATH = ".agents/.agent-ready-assets.lock"
INSTRUCTIONS_LOCK_RELATIVE_PATH = ".agents/.agent-ready-instructions.lock"
REMOVAL_LOCKS = (
    (SYNC_LOCK_RELATIVE_PATH, "an apply or a session sync is running"),
    (INSTRUCTIONS_LOCK_RELATIVE_PATH, "an AGENTS.md review is running"),
)
AMBIGUOUS_MARKERS_REASON = "its managed block markers are not one pair of whole lines; remove the block by hand"
# Kinds the lockfile inventories: while one of them is left, the lockfile stays for the next run.
LOCK_INVENTORIED_KINDS = ("asset", "view")
INVENTORY_KEPT_REASON = "kept because a managed path could not be removed; run agent-ready remove again"


def removal_entry(path, action, reason, kind, local=None):
    """One line of the removal plan; ``local`` is the state it had, checked again before acting."""
    return {"path": path, "action": action, "reason": reason, "kind": kind, "local": local}


def view_mirrors(project_root, view, asset, base_hash):
    """True when a .claude path is a view an apply made of an .agents path."""
    view_path = os.path.join(project_root, view)
    asset_path = os.path.join(project_root, asset)
    if os.path.islink(view_path):
        target = os.path.normpath(os.path.join(os.path.dirname(view_path), os.readlink(view_path)))
        return target == os.path.normpath(asset_path)
    if not os.path.isfile(view_path):
        return False
    if os.path.isfile(asset_path) and os.path.samefile(view_path, asset_path):
        return True
    # A hard link that git detached still holds what the apply wrote.
    return base_hash is not None and sha256_of_file(view_path) == base_hash


def asset_removal_entries(project_root, locked_assets):
    """Managed assets go unless they changed since the last apply; project files always stay."""
    entries = []
    for destination, lock_entry in sorted(locked_assets.items()):
        local = local_state(os.path.join(project_root, destination))
        action, reason = classify_retired(local, lock_entry)
        if action == ACTION_DROP:
            if local != LOCAL_ABSENT:
                entries.append(removal_entry(destination, REMOVAL_KEEP, reason, "asset"))
            continue
        if has_linked_parent(project_root, destination):
            entries.append(removal_entry(destination, REMOVAL_KEEP, LINKED_PARENT_REASON, "asset"))
        elif action == ACTION_RETIRE_CONFLICT:
            entries.append(removal_entry(destination, REMOVAL_KEEP, "not a regular file", "asset"))
        elif local != lock_entry.get("sha256"):
            entries.append(removal_entry(destination, REMOVAL_KEEP,
                                         "changed since the last apply; delete it by hand if you no longer need it", "asset"))
        else:
            entries.append(removal_entry(destination, REMOVAL_REMOVE, "published by agent-ready-setup", "asset", local))
    return entries


def view_removal_entries(project_root, locked_assets):
    """Every .claude view of an .agents path: of managed assets and of the project's own rules."""
    entries = []
    for directory in CLAUDE_VIEW_DIRECTORIES:
        root = os.path.join(project_root, ".claude", directory)
        if is_link(root) or not os.path.isdir(root):
            continue
        for current, _, file_names in os.walk(root):
            for file_name in sorted(file_names):
                view = os.path.relpath(os.path.join(current, file_name), project_root).replace(os.sep, "/")
                asset = ".agents/" + view[len(".claude/"):]
                if has_linked_parent(project_root, view):
                    continue
                if view_mirrors(project_root, view, asset, locked_assets.get(asset, {}).get("sha256")):
                    entries.append(removal_entry(view, REMOVAL_REMOVE, f"view of {asset}", "view",
                                                 local_state(os.path.join(project_root, view))))
    return entries


def without_managed_block(text):
    """AGENTS.md text without its managed block, or None when it has no block.

    Like managed-block.sh, only whole lines are markers, so a line that mentions one stays.
    Raises ValueError when the markers are not exactly one pair in order.
    """
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == MANAGED_BLOCK_START]
    ends = [index for index, line in enumerate(lines) if line == MANAGED_BLOCK_END]
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1 or starts[0] > ends[0]:
        raise ValueError(AMBIGUOUS_MARKERS_REASON)
    before = "\n".join(lines[:starts[0]]).rstrip()
    after = "\n".join(lines[ends[0] + 1:]).lstrip("\n").rstrip()
    remaining = "\n\n".join(part for part in (before, after) if part)
    return remaining + "\n" if remaining else ""


def normalized_lines(text):
    """Text compared without line endings or trailing spaces."""
    return [line.rstrip() for line in text.replace("\r\n", "\n").strip().split("\n")]


def template_skeleton(skill_dir, lock):
    """What the AGENTS.md template puts outside the managed block, or None when it is unknown."""
    template = ((lock or {}).get("merged") or {}).get("AGENTS.md", {}).get("template")
    path = os.path.join(skill_dir, template) if template else None
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as file_handle:
        try:
            return without_managed_block(file_handle.read())
        except ValueError:
            return None


def instruction_removal_entries(project_root, skill_dir, lock):
    """The managed block of AGENTS.md goes; the file goes too when nothing of the project is left."""
    path = os.path.join(project_root, "AGENTS.md")
    local = local_state(path)
    if local in (LOCAL_ABSENT, LOCAL_NOT_A_FILE):
        return []
    if local == LOCAL_SYMLINK:
        return [removal_entry("AGENTS.md", REMOVAL_KEEP, "a symlink; remove its managed block by hand", "instructions")]
    with open(path, encoding="utf-8") as file_handle:
        try:
            remaining = without_managed_block(file_handle.read())
        except ValueError:
            return [removal_entry("AGENTS.md", REMOVAL_KEEP, AMBIGUOUS_MARKERS_REASON, "instructions")]
    if remaining is None:
        return []
    skeleton = template_skeleton(skill_dir, lock)
    if remaining.strip() and (skeleton is None or normalized_lines(remaining) != normalized_lines(skeleton)):
        return [removal_entry("AGENTS.md", REMOVAL_EDIT, "removes the managed block; the project's content stays",
                              "instructions", local)]
    entries = [removal_entry("AGENTS.md", REMOVAL_REMOVE, "only holds the managed block and the template", "instructions", local)]
    proxy = os.path.join(project_root, "CLAUDE.md")
    proxy_local = local_state(proxy)
    if proxy_local == sha256_of_file(os.path.join(skill_dir, CLAUDE_PROXY_RELATIVE_PATH)):
        entries.append(removal_entry("CLAUDE.md", REMOVAL_REMOVE, "proxy of AGENTS.md", "instructions", proxy_local))
    return entries


def without_managed_entries(document, template):
    """A Claude settings or Codex hooks document without the permissions and hooks its template manages."""
    result = json.loads(json.dumps(document))
    managed_rules = template.get("permissions", {}).get("allow", [])
    permissions = result.get("permissions")
    if isinstance(permissions, dict) and isinstance(permissions.get("allow"), list):
        permissions["allow"] = [rule for rule in permissions["allow"] if rule not in managed_rules]
        if not permissions["allow"]:
            del permissions["allow"]
        if not permissions:
            del result["permissions"]
    managed_commands = {handler.get("command") for groups in template.get("hooks", {}).values()
                        for group in groups for handler in group.get("hooks", [])}
    hooks = result.get("hooks")
    if not isinstance(hooks, dict):
        return result
    for event in list(hooks):
        if not isinstance(hooks[event], list):
            continue
        kept_groups = []
        for group in hooks[event]:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if isinstance(handlers, list) and handlers:
                handlers = [handler for handler in handlers
                            if not (isinstance(handler, dict) and handler.get("command") in managed_commands)]
                if not handlers:
                    continue
                group = dict(group, hooks=handlers)
            kept_groups.append(group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if not hooks:
        del result["hooks"]
    return result


def serialize_settings(document):
    """Settings in the format merge-managed-settings.py writes them."""
    return json.dumps(document, indent=2) + "\n"


def settings_templates(skill_dir):
    """Merged JSON files and the template each one is merged from."""
    base_assets = load_profile_catalog(skill_dir).get("baseAssets", "assets/common")
    return (
        (".claude/settings.json", os.path.join(skill_dir, base_assets, CLAUDE_SETTINGS_TEMPLATE_NAME)),
        (".codex/hooks.json", os.path.join(skill_dir, CODEX_HOOKS_TEMPLATE_RELATIVE_PATH)),
    )


def settings_without_managed_entries(project_root, destination, template_path):
    """(current document, document without the managed entries), or None when it cannot be read."""
    try:
        with open(os.path.join(project_root, destination), encoding="utf-8") as file_handle:
            current = json.load(file_handle)
        with open(template_path, encoding="utf-8") as file_handle:
            template = json.load(file_handle)
    except (OSError, ValueError):
        return None
    if not isinstance(current, dict):
        return None
    return current, without_managed_entries(current, template)


def settings_removal_entries(project_root, skill_dir):
    """Managed hooks and permissions leave the merged JSON files; custom entries stay."""
    entries = []
    for destination, template_path in settings_templates(skill_dir):
        local = local_state(os.path.join(project_root, destination))
        if local in (LOCAL_ABSENT, LOCAL_NOT_A_FILE):
            continue
        if local == LOCAL_SYMLINK:
            entries.append(removal_entry(destination, REMOVAL_KEEP, "a symlink; remove its agent-ready hooks by hand", "settings"))
            continue
        documents = settings_without_managed_entries(project_root, destination, template_path)
        if documents is None:
            entries.append(removal_entry(destination, REMOVAL_KEEP, "invalid JSON; remove its agent-ready hooks by hand", "settings"))
        elif documents[1] == documents[0]:
            continue
        elif not documents[1]:
            entries.append(removal_entry(destination, REMOVAL_REMOVE, "only holds agent-ready hooks and permissions", "settings", local))
        else:
            entries.append(removal_entry(destination, REMOVAL_EDIT,
                                         "removes the agent-ready hooks and permissions; custom entries stay", "settings", local))
    return entries


def pack_mcp_removal_entries(project_root, lock):
    """The provider configurations that hold MCP servers of profile packs, from the lock."""
    managed = (lock or {}).get("mcpServers", {})
    return [removal_entry(path, REMOVAL_EDIT, "unregisters the MCP servers of profile packs; the project's own stay", "pack-mcp")
            for path in pack_mcp.managed_files(project_root, managed)]


def pack_cli_removal_entries(project_root, lock):
    """The CLIs of profile packs this repository uses, from the lock; the cache keeps what other repositories use."""
    if not (lock or {}).get("clis"):
        return []
    return [removal_entry(PACK_CLI_REMOVAL_LABEL, REMOVAL_EDIT,
                          "stops using the CLIs of profile packs; the ones no other repository uses are deleted",
                          "pack-cli")]


def browser_removal_entries(project_root):
    """Browser MCP servers that agent-ready registered, and the metadata of this machine."""
    entries = []
    for destination in BROWSER_REGISTRATION_FILES:
        path = os.path.join(project_root, destination)
        if os.path.isfile(path) and not os.path.islink(path):
            with open(path, encoding="utf-8", errors="replace") as file_handle:
                if BROWSER_SERVERS_MARKER in file_handle.read():
                    entries.append(removal_entry(destination, REMOVAL_EDIT,
                                                 "unregisters the browser MCP servers agent-ready added; other servers stay", "browser"))
    if os.path.isfile(os.path.join(project_root, BROWSER_METADATA_RELATIVE_PATH)):
        entries.append(removal_entry(BROWSER_METADATA_RELATIVE_PATH, REMOVAL_REMOVE, "browser tools metadata of this machine", "browser"))
    gitignore = os.path.join(project_root, ".gitignore")
    if os.path.isfile(gitignore) and not os.path.islink(gitignore):
        with open(gitignore, encoding="utf-8", errors="replace") as file_handle:
            if BROWSER_METADATA_RELATIVE_PATH in file_handle.read().splitlines():
                entries.append(removal_entry(".gitignore", REMOVAL_EDIT, "drops the line that ignored the browser metadata", "browser"))
    return entries


def git_path(project_root, relative):
    """Absolute path of a file inside the Git directory, or None outside a Git worktree."""
    located = run_quiet(["git", "rev-parse", "--git-path", relative], cwd=project_root)
    return os.path.normpath(os.path.join(project_root, located)) if located else None


def display_path(project_root, path):
    """Path relative to the project, with forward slashes."""
    return os.path.relpath(path, project_root).replace(os.sep, "/")


def other_worktree_using_agent_ready(project_root):
    """Another worktree of the same repository with a lockfile: it shares the Git config and hooks."""
    listed = run_quiet(["git", "worktree", "list", "--porcelain"], cwd=project_root) or ""
    here = os.path.normcase(os.path.realpath(project_root))
    for line in listed.splitlines():
        if not line.startswith("worktree "):
            continue
        worktree = line[len("worktree "):]
        if os.path.normcase(os.path.realpath(worktree)) != here and os.path.isfile(os.path.join(worktree, LOCK_RELATIVE_PATH)):
            return worktree
    return None


def local_removal_entries(project_root):
    """Git hooks and files of agent-ready-setup that the lockfile does not list."""
    entries = []
    # Only the repository config: the setup registers the hook there, and removing it never touches the user's.
    if run_quiet(["git", "config", "--local", "--get", f"{GIT_HOOK_SECTION}.command"], cwd=project_root) == GIT_HOOK_COMMAND:
        entries.append(removal_entry(f"git config {GIT_HOOK_SECTION}", REMOVAL_REMOVE,
                                     "relinks .claude hard-link views after git operations", "git-config"))
    hook = git_path(project_root, f"hooks/{GIT_HOOK_FILE_NAME}")
    if hook and os.path.isfile(hook) and not os.path.islink(hook):
        with open(hook, encoding="utf-8", errors="replace") as file_handle:
            if GIT_HOOK_MARKER in file_handle.read():
                entries.append(removal_entry(display_path(project_root, hook), REMOVAL_REMOVE,
                                             "relinks .claude hard-link views after git operations", "git-hook", local_state(hook)))
    review_cache = git_path(project_root, REVIEW_CACHE_INFO_PATH)
    if review_cache and os.path.isfile(review_cache) and not os.path.islink(review_cache):
        entries.append(removal_entry(display_path(project_root, review_cache), REMOVAL_REMOVE,
                                     "cache of the AI reviews", "review-cache", local_state(review_cache)))
    sharing_worktree = other_worktree_using_agent_ready(project_root)
    if sharing_worktree:
        # The Git config and the hooks directory belong to every worktree of the repository.
        for entry in entries:
            entry.update(action=REMOVAL_KEEP, local=None,
                         reason=f"shared with the worktree {sharing_worktree}, which still uses agent-ready-setup")
    for path, reason in ((os.path.join(project_root, HARD_LINK_VIEWS_MANIFEST), "list of .claude hard-link views"),
                         (os.path.join(project_root, review_cache_module().SHARED_CACHE_RELATIVE_PATH),
                          "shared cache of the AI reviews (reviews.commit)"),
                         (conflicts_review.pending_path(project_root), "semantic conflicts of the last plan")):
        if path and os.path.isfile(path) and not os.path.islink(path):
            entries.append(removal_entry(display_path(project_root, path), REMOVAL_REMOVE, reason, "state", local_state(path)))
    return entries


def config_removal_entries(project_root):
    """The manifest and the lockfile, which make agent-ready-setup manage the repository."""
    entries = []
    for relative, reason in ((MANIFEST_RELATIVE_PATH, "agent-ready-setup configuration of the repository"),
                             (LOCK_RELATIVE_PATH, "lockfile of the managed assets")):
        local = local_state(os.path.join(project_root, relative))
        if local == LOCAL_ABSENT:
            continue
        if local in (LOCAL_SYMLINK, LOCAL_NOT_A_FILE):
            entries.append(removal_entry(relative, REMOVAL_KEEP, "not a regular file", "config"))
        else:
            entries.append(removal_entry(relative, REMOVAL_REMOVE, reason, "config", local))
    return entries


def plan_removal(project_root, skill_dir):
    """What `agent-ready remove` deletes, edits and keeps, without writing anything.

    It reads only the lockfile and the files themselves, not the configuration, so a
    repository with an invalid manifest can still be cleaned.
    """
    lock = read_lock(project_root)
    locked_assets = lock["assets"] if lock else {}
    entries = (
        pack_mcp_removal_entries(project_root, lock)
        + pack_cli_removal_entries(project_root, lock)
        + browser_removal_entries(project_root)
        + local_removal_entries(project_root)
        + view_removal_entries(project_root, locked_assets)
        + asset_removal_entries(project_root, locked_assets)
        + instruction_removal_entries(project_root, skill_dir, lock)
        + settings_removal_entries(project_root, skill_dir)
        + config_removal_entries(project_root)
    )
    for entry in entries:
        # A directory linked to ~/.claude or another shared place leads outside the repository.
        if entry["action"] != REMOVAL_KEEP and entry["kind"] not in ("git-config", "git-hook", "pack-cli") \
                and has_linked_parent(project_root, entry["path"]):
            entry.update(action=REMOVAL_KEEP, reason=LINKED_PARENT_REASON, local=None)
    entries.sort(key=lambda entry: (REMOVAL_KINDS.index(entry["kind"]), entry["path"]))
    return {"entries": entries, "changes": sum(entry["action"] != REMOVAL_KEEP for entry in entries)}


def unchanged_since_plan(project_root, entry):
    """True when a file still has the state the plan saw."""
    return entry["local"] is None or local_state(os.path.join(project_root, entry["path"])) == entry["local"]


def remove_managed_roots_if_empty(project_root):
    """Drop .agents, .claude, .codex and .github when the removal left them empty."""
    for directory in MANAGED_ROOT_DIRECTORIES:
        path = os.path.join(project_root, directory)
        if os.path.isdir(path) and not is_link(path):
            try:
                os.rmdir(path)
            except OSError:
                pass


def unregister_pack_mcp_servers(project_root, report):
    """Drop every MCP server of the packs that the lock records; the project's own servers stay."""
    lock = read_lock(project_root) or {}
    result = pack_mcp.unregister_all(project_root, lock.get("mcpServers", {}))
    for path, names in result["removed"].items():
        if names:
            report["edited"].append(path)
    report["failed"] += result["failed"]


def uninstall_pack_clis(project_root, report):
    """This repository stops using the CLIs of the packs; the cache deletes the ones no repository uses."""
    try:
        pack_clis.uninstall_all(project_root)
    except (pack_clis.InstallError, OSError) as problem:
        report["failed"].append(f"CLIs of profile packs: {problem}")
        return
    report["edited"].append(PACK_CLI_REMOVAL_LABEL)


def unregister_browser_servers(project_root, skill_dir, report):
    """Run the dedicated entry point once; it knows how to edit the TOML of Codex."""
    command = [sys.executable, os.path.join(skill_dir, UNREGISTER_BROWSER_RELATIVE_PATH), "--project", project_root]
    completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", check=False)
    # One "<removed|edited><TAB><path>" line per file the entry point changed.
    for line in completed.stdout.splitlines():
        outcome, _, changed_path = line.partition("\t")
        if outcome in ("removed", "edited") and changed_path:
            report[outcome].append(changed_path)
    if completed.returncode != 0:
        problem = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "the browser servers could not be removed"
        report["failed"].append(problem)


def apply_removal_entry(project_root, skill_dir, entry, report):
    """Carry out one removal or edit, after checking that the file did not change."""
    path = os.path.join(project_root, entry["path"])
    if entry["kind"] == "git-config":
        if subprocess.call(["git", "config", "--remove-section", GIT_HOOK_SECTION], cwd=project_root,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            report["removed"].append(entry["path"])
        else:
            report["failed"].append(f"{entry['path']}: git config --remove-section failed")
        return
    if not unchanged_since_plan(project_root, entry):
        report["kept"].append(f"{entry['path']}: {CHANGED_DURING_REMOVAL_REASON}")
        return
    if entry["action"] == REMOVAL_REMOVE:
        os.unlink(path)
        if entry["kind"] in ("view", "asset"):
            # Only the folders that assets created; the Git directory keeps its own.
            remove_empty_parents(project_root, path)
        elif entry["kind"] == "review-cache":
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
        report["removed"].append(entry["path"])
        return
    if entry["kind"] == "instructions":
        # Read and close before replacing: Windows refuses to replace an open file.
        with open(path, encoding="utf-8") as file_handle:
            current = file_handle.read()
        write_text_atomically(path, without_managed_block(current))
    else:
        template_path = dict(settings_templates(skill_dir))[entry["path"]]
        write_text_atomically(path, serialize_settings(settings_without_managed_entries(project_root, entry["path"], template_path)[1]))
    report["edited"].append(entry["path"])


def apply_removal(project_root, skill_dir, plan):
    """Remove agent-ready-setup from the repository following a plan; returns what happened."""
    report = {"removed": [], "edited": [], "kept": [], "failed": []}
    report["kept"] += [f"{entry['path']}: {entry['reason']}" for entry in plan["entries"] if entry["action"] == REMOVAL_KEEP]
    browser_done = False
    pack_mcp_done = False
    inventory_left = False
    for entry in plan["entries"]:
        if entry["action"] == REMOVAL_KEEP:
            continue
        if entry["kind"] == "pack-mcp":
            if not pack_mcp_done:
                failures_before = len(report["failed"])
                unregister_pack_mcp_servers(project_root, report)
                pack_mcp_done = True
                # The lock is the only record of which servers are the packs': it stays for a retry.
                inventory_left = inventory_left or len(report["failed"]) > failures_before
            continue
        if entry["kind"] == "pack-cli":
            failures_before = len(report["failed"])
            uninstall_pack_clis(project_root, report)
            # The lock says which CLIs the repository used: it stays for a retry.
            inventory_left = inventory_left or len(report["failed"]) > failures_before
            continue
        if entry["kind"] == "browser":
            if not browser_done:
                unregister_browser_servers(project_root, skill_dir, report)
                browser_done = True
            continue
        if entry["kind"] == "config" and inventory_left:
            # Without the lockfile, the next run would not know which files are still managed.
            report["kept"].append(f"{entry['path']}: {INVENTORY_KEPT_REASON}")
            continue
        try:
            apply_removal_entry(project_root, skill_dir, entry, report)
        except OSError as caught_error:
            report["failed"].append(f"{entry['path']}: {caught_error}")
            inventory_left = inventory_left or entry["kind"] in LOCK_INVENTORIED_KINDS
    return report


def remove_from_repository(project_root, skill_dir):
    """Plan again and remove holding the locks of apply, the session hook and the AGENTS.md review.

    Without them, a projection or a review already running would write the assets, the
    lockfile or AGENTS.md back after the removal reported success.
    """
    held = []
    agents_directory = os.path.join(project_root, ".agents")
    try:
        if not is_link(agents_directory):
            os.makedirs(agents_directory, exist_ok=True)
            for relative, running in REMOVAL_LOCKS:
                try:
                    os.mkdir(os.path.join(project_root, relative))
                except FileExistsError:
                    raise StateError(f"{running} ({relative} exists); run agent-ready remove again when it finishes, "
                                     "or delete that directory if no agent-ready process is running") from None
                held.append(relative)
        report = apply_removal(project_root, skill_dir, plan_removal(project_root, skill_dir))
    finally:
        for relative in reversed(held):
            try:
                os.rmdir(os.path.join(project_root, relative))
            except OSError:
                pass
    remove_managed_roots_if_empty(project_root)
    return report


def print_removal_plan(plan, stream):
    """Text plan: one line per path with what happens to it and why."""
    for entry in plan["entries"]:
        symbol = REMOVAL_SYMBOLS[entry["action"]]
        label = paint(f"{symbol} {entry['action']:<6}", REMOVAL_COLORS[entry["action"]], stream)
        write_line(f"  {label} {entry['path']}  ({entry['reason']})", stream)


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
        group.add_argument("--profiles", help="comma separated profiles, e.g. frontend,browser")
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

    golfo_kit_parser = subparsers.add_parser("golfo-kit-source", help="skill directory with the golfo-kit content of this run")
    add_common(golfo_kit_parser)
    golfo_kit_parser.add_argument("--update", action="store_true", help="adopt the latest revision of its ref, or of the installed engine")
    golfo_kit_parser.add_argument("--to", help="adopt this tag, branch or full commit")
    golfo_kit_parser.add_argument("--offline", action="store_true", help="use no network: only revisions already in the cache")
    golfo_kit_parser.add_argument("--from-lock", action="store_true", help="the revision of the lock, whatever the mode")
    golfo_kit_parser.add_argument("--read-only", action="store_true",
                                  help="the run writes nothing: offline, a missing revision compares with the installed one")
    golfo_kit_parser.set_defaults(handler=command_golfo_kit_source)

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
    plan_parser.add_argument("--format", choices=("text", "json", "protected"), default="text",
                             help="json is for scripts; protected lists the destinations an apply preserves")
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

    status_parser = subparsers.add_parser("status", help="read-only status")
    add_common(status_parser, needs_skill=False)
    status_parser.add_argument("--skill-dir", help="resolved source, to detect pending updates")
    status_parser.add_argument("--brief", action="store_true", help="summary lines only")
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
