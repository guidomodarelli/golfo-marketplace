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

Subcommands: resolve, manifest, plan, finalize, status.
"""

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

MANIFEST_RELATIVE_PATH = ".agents/agent-ready.json"
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
SKILL_NAME = "agent-ready-setup"
PLUGIN_NAME = "golfo-kit"
BASE_PROFILE_NAME = "common"
STACK_PROFILE_KIND = "stack"
SCHEMA_VERSION = 1
MANAGED_BLOCK_START = "<!-- BEGIN AGENT-READY MANAGED -->"
MANAGED_BLOCK_END = "<!-- END AGENT-READY MANAGED -->"
SETTINGS_TEMPLATE_FALLBACK_STATUS = 10
SUPPORTED_UPDATE_MODES = ("pinned", "auto")
DEFAULT_UPDATE_MODE = "pinned"
SUPPORTED_PROVIDERS = ("claude", "codex")
BROWSER_TOOL_NAME = "browser"
# Exit status when the selected profiles cannot be resolved or composed.
PROFILE_ERROR_STATUS = 2
# Exit status of `status --check` when the checkout or the source drifted from the lock.
DRIFT_STATUS = 4

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
STATE_RETIRED_MODIFIED = "retired-modified"

LOCAL_ABSENT = "absent"
LOCAL_SYMLINK = "symlink"
LOCAL_NOT_A_FILE = "not-a-file"

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


class ProfileError(Exception):
    """Raised when profiles cannot be resolved or composed without ambiguity."""


class StateError(Exception):
    """Raised when the manifest or the lockfile cannot be read safely."""


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

def sha256_of_file(path):
    """Return the hex sha256 of a file with CRLF line endings normalized to LF.

    A checkout with core.autocrlf rewrites every line ending without anyone
    editing the file, so hashing raw bytes would report the whole tree as locally
    modified. A file with LF endings hashes to its plain sha256.
    """
    with open(path, "rb") as file_handle:
        content = file_handle.read()
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def sha256_of_text(text):
    """Return the hex sha256 of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def local_state(path):
    """Describe a project path: absent, symlink, not-a-file or its sha256."""
    if os.path.islink(path):
        return LOCAL_SYMLINK
    if not os.path.exists(path):
        return LOCAL_ABSENT
    if not os.path.isfile(path):
        return LOCAL_NOT_A_FILE
    return sha256_of_file(path)


def is_content_hash(value):
    """True when a local state is a content hash rather than a special marker."""
    return value not in (LOCAL_ABSENT, LOCAL_SYMLINK, LOCAL_NOT_A_FILE)


def read_json_file(path, description):
    """Read a JSON object, raising StateError with the path on failure."""
    try:
        with open(path, encoding="utf-8") as file_handle:
            content = json.load(file_handle)
    except (OSError, json.JSONDecodeError) as caught_error:
        raise StateError(f"could not read {description} {path}: {caught_error}") from caught_error
    if not isinstance(content, dict):
        raise StateError(f"{description} {path} must contain a JSON object")
    return content


def serialize_json(content):
    """Deterministic JSON so the same resolution produces the same bytes."""
    return json.dumps(content, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_text_atomically(path, text):
    """Write text through a temporary sibling and an atomic rename."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if os.path.islink(path):
        raise StateError(f"{path} is a symlink; it was not overwritten")
    file_descriptor, temporary_path = tempfile.mkstemp(prefix=".agent-ready-state.", dir=directory)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as file_handle:
            file_handle.write(text)
        os.replace(temporary_path, path)
    except BaseException:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


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


def walk_files(root):
    """Yield (relative_posix_path, absolute_path) for every regular file, sorted."""
    collected = []
    for directory, directory_names, file_names in os.walk(root):
        directory_names.sort()
        for file_name in sorted(file_names):
            absolute_path = os.path.join(directory, file_name)
            relative_path = os.path.relpath(absolute_path, root).replace(os.sep, "/")
            collected.append((relative_path, absolute_path))
    return sorted(collected)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def load_profile_catalog(skill_dir):
    """Load and validate the profile catalog of the skill source."""
    catalog_path = os.path.join(skill_dir, PROFILE_CATALOG_RELATIVE_PATH)
    try:
        catalog = read_json_file(catalog_path, "profile catalog")
    except StateError as caught_error:
        raise ProfileError(str(caught_error)) from caught_error
    profiles = catalog.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ProfileError(f"profile catalog {catalog_path} has no profiles")
    return catalog


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
            origin = f" (required by {requested_by})" if requested_by else ""
            known = ", ".join(sorted(profiles))
            raise ProfileError(f"unknown profile '{name}'{origin}; available profiles: {known}")
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
    selection_key = sha256_of_text(os.path.abspath(skill_dir) + "\n" + ",".join(resolved))[:16]
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


def desired_assets(skill_dir, catalog, resolved):
    """Map every managed destination to its template, owning profile and hash."""
    # Bash projects every profile tree as the stack tree, so only the base
    # assets skip the Codex MCP bridge.
    sources = [(BASE_PROFILE_NAME, os.path.join(skill_dir, catalog.get("baseAssets", "assets/common")), False)]
    for name in resolved:
        root = profile_asset_root(skill_dir, catalog, name)
        if root:
            sources.append((name, root, True))

    assets = {}
    for profile_name, root, is_stack_root in sources:
        for relative_path, absolute_path in walk_files(root):
            for destination in destinations_for_template(relative_path, is_stack_root):
                if destination in assets and assets[destination]["profile"] != profile_name:
                    raise ProfileError(
                        f"profiles '{assets[destination]['profile']}' and '{profile_name}' both write {destination}"
                    )
                assets[destination] = {
                    "profile": profile_name,
                    "source": os.path.relpath(absolute_path, skill_dir).replace(os.sep, "/"),
                    "sourcePath": absolute_path,
                    "sha256": sha256_of_file(absolute_path),
                }
    return assets


def profile_digests(skill_dir, catalog, resolved):
    """Digest of each resolved profile: its asset bytes or its catalog entry."""
    digests = {}
    for name in [BASE_PROFILE_NAME] + resolved:
        if name == BASE_PROFILE_NAME:
            root = os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"))
            entry = {"kind": "base"}
        else:
            root = profile_asset_root(skill_dir, catalog, name)
            entry = catalog["profiles"][name]
        lines = [json.dumps(entry, sort_keys=True)]
        if root:
            lines += [f"{relative_path}\t{sha256_of_file(absolute_path)}" for relative_path, absolute_path in walk_files(root)]
        digests[name] = {"kind": entry.get("kind", "base"), "digest": sha256_of_text("\n".join(lines))}
    return digests


# ---------------------------------------------------------------------------
# Source identity
# ---------------------------------------------------------------------------

def bash_executable():
    """Bash from PATH; Windows process creation would find the WSL launcher in System32 first."""
    return shutil.which("bash") or "bash"


def run_quiet(command, cwd=None):
    """Run a read-only command and return its UTF-8 stdout, or None when it fails."""
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def plugin_version(skill_dir):
    """Version of the plugin manifest that ships the skill, if present."""
    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(skill_dir)))
    for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "plugin.json"):
        manifest_path = os.path.join(plugin_root, manifest)
        if os.path.isfile(manifest_path):
            try:
                return read_json_file(manifest_path, "plugin manifest").get("version")
            except StateError:
                return None
    return None


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


def source_identity(skill_dir, assets, merged_templates):
    """Identity of the resolved source; contentDigest is the immutable part."""
    digest_lines = [f"{destination}\t{entry['sha256']}" for destination, entry in sorted(assets.items())]
    digest_lines += [f"{destination}\t{entry['templateSha256']}" for destination, entry in sorted(merged_templates.items())]
    revision, dirty = source_revision(skill_dir)
    identity = {
        "plugin": PLUGIN_NAME,
        "skill": SKILL_NAME,
        "version": plugin_version(skill_dir),
        "kind": source_kind(skill_dir),
        "revision": revision,
        "contentDigest": sha256_of_text("\n".join(digest_lines)),
    }
    if dirty:
        identity["revisionHasLocalChanges"] = True
    return identity


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
    return entries


# ---------------------------------------------------------------------------
# Manifest and lockfile
# ---------------------------------------------------------------------------

def read_manifest(project_root):
    """Read the repository manifest, or None when the repository has none."""
    path = os.path.join(project_root, MANIFEST_RELATIVE_PATH)
    if not os.path.exists(path) and not os.path.islink(path):
        return None
    if os.path.islink(path):
        raise StateError(f"{path} is a symlink; Agent Ready does not follow it")
    manifest = read_json_file(path, "Agent Ready manifest")
    profiles = manifest.get("profiles")
    if not isinstance(profiles, list) or not all(isinstance(name, str) for name in profiles):
        raise StateError(f"{path} must declare 'profiles' as a list of names")
    updates = manifest.get("updates", DEFAULT_UPDATE_MODE)
    if updates not in SUPPORTED_UPDATE_MODES:
        raise StateError(f"{path} 'updates' must be one of {', '.join(SUPPORTED_UPDATE_MODES)}")
    return manifest


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


def build_manifest(profiles, updates, providers):
    """Manifest content: desired configuration, edited by people."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "profiles": list(profiles),
        "updates": updates,
        "providers": list(providers),
    }


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def classify_asset(destination, desired_entry, local, lock_entry, has_lock, force):
    """Three-way decision for one desired destination."""
    new_hash = desired_entry["sha256"]
    base_hash = lock_entry.get("sha256") if lock_entry else None
    if local == LOCAL_ABSENT:
        return ACTION_CREATE, "missing locally"
    if local == new_hash:
        return ACTION_UNCHANGED, "matches the template"
    if local == LOCAL_NOT_A_FILE:
        return ACTION_CONFLICT, "destination is not a regular file"
    if force:
        return ACTION_UPDATE, "forced overwrite"
    if not has_lock:
        return ACTION_ADOPT, "no lockfile yet: first apply keeps the previous overwrite contract"
    if lock_entry is None:
        return ACTION_CONFLICT, "file exists but was never applied by agent-ready-setup"
    if local == base_hash:
        return ACTION_UPDATE, "local file still matches the applied base"
    if local == LOCAL_SYMLINK:
        return ACTION_CONFLICT, "managed file was replaced by a symlink"
    return ACTION_CONFLICT, "local changes since the last apply"


def classify_retired(local, lock_entry, force):
    """Decision for a locked asset that no selected profile publishes anymore."""
    if local == LOCAL_ABSENT:
        return ACTION_DROP, "already removed"
    if force and local != LOCAL_NOT_A_FILE:
        return ACTION_RETIRE, "forced removal"
    if is_content_hash(local) and local == lock_entry.get("sha256"):
        return ACTION_RETIRE, "no longer published by the selected profiles"
    return ACTION_RETIRE_CONFLICT, "retired from the profiles but modified locally; delete it or rerun with --force"


def compute_plan(project_root, skill_dir, profile_names, force):
    """Build the read-only plan for the selected profiles."""
    catalog = load_profile_catalog(skill_dir)
    resolved = resolve_profiles(catalog, profile_names)
    assets = desired_assets(skill_dir, catalog, resolved)
    lock = read_lock(project_root)
    locked_assets = lock["assets"] if lock else {}
    entries = []
    for destination, desired_entry in sorted(assets.items()):
        local = local_state(os.path.join(project_root, destination))
        lock_entry = locked_assets.get(destination)
        action, reason = classify_asset(destination, desired_entry, local, lock_entry, lock is not None, force)
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
        action, reason = classify_retired(local, lock_entry, force)
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
    return {
        "schemaVersion": SCHEMA_VERSION,
        "profiles": resolved,
        "primaryStack": primary_stack(catalog, resolved),
        "tools": resolved_tools(catalog, resolved),
        "source": source_identity(skill_dir, assets, merged),
        "lockedSource": lock.get("source") if lock else None,
        "hasLock": lock is not None,
        "force": force,
        "entries": entries,
        "merged": merged,
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
    """CLAUDE.md files that instruction normalization would rewrite."""
    proxy_path = os.path.join(skill_dir, CLAUDE_PROXY_RELATIVE_PATH)
    listed = run_quiet(["git", "ls-files", "-co", "--exclude-standard"], cwd=project_root)
    if listed is None or not os.path.isfile(proxy_path):
        return []
    proxy_hash = sha256_of_file(proxy_path)
    drifted = []
    for relative_path in listed.splitlines():
        if os.path.basename(relative_path).lower() != "claude.md":
            continue
        absolute_path = os.path.join(project_root, relative_path)
        if os.path.isfile(absolute_path) and not os.path.islink(absolute_path) and sha256_of_file(absolute_path) != proxy_hash:
            drifted.append(relative_path)
    return drifted


def global_effects(plan, skip_marketplace_upgrade, browser_install_enabled):
    """Effects outside the repository that an apply may have, with their scope."""
    effects = []
    if not skip_marketplace_upgrade:
        effects.append(("user", "refresh the golfo-marketplace snapshot through the provider CLI before projecting"))
    if BROWSER_TOOL_NAME in plan["tools"]:
        if browser_install_enabled:
            effects.append(("user-cache", "install or reuse browser tools under ~/.local/share/agent-ready-setup/browser-tools (profile browser)"))
            effects.append(("project", "register browser MCP servers in .mcp.json and .codex/config.toml"))
        else:
            effects.append(("none", "browser tools are selected but AGENT_READY_SETUP_BROWSER_INSTALL=0 skips them"))
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


def print_plan(project_root, skill_dir, plan, provider, show_diff, skip_marketplace_upgrade, browser_install_enabled):
    """Human readable plan on stdout."""
    stream = sys.stdout
    write_line(paint("Agent Ready plan (read-only: nothing was written)", "heading", stream))
    write_line(f"Profiles: {', '.join(plan['profiles'])} (primary stack: {plan['primaryStack']})")
    write_line(f"Source:   {describe_source(plan['source'])}")
    write_line(f"Lock:     {describe_source(plan['lockedSource']) if plan['hasLock'] else 'none (first apply creates it)'}")
    write_line("")
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
    for scope, description in global_effects(plan, skip_marketplace_upgrade, browser_install_enabled):
        write_line(f"  - [{scope}] {description}")
    write_line("")
    write_line(paint("Requirements", "heading", stream))
    for command, reason, available in requirements(provider, skip_marketplace_upgrade, plan["tools"]):
        marker = paint("ok", "ok", stream) if available else paint("missing", "error", stream)
        write_line(f"  {marker:<7} {command}: {reason}")
    if show_diff:
        diff_entries = [entry for entry in plan["entries"] if entry["action"] in (ACTION_UPDATE, ACTION_ADOPT, ACTION_CONFLICT)]
        if diff_entries:
            write_line("")
            write_line(paint("Diffs (local -> template)", "heading", stream))
            for entry in diff_entries:
                write_line(render_diff(project_root, entry).rstrip("\n"))
    write_line("")
    summary = ", ".join(f"{counts[action]} {action}" for action in sorted(counts) if action != ACTION_UNCHANGED) or "no changes"
    write_line(paint(f"Summary: {summary}", "heading", stream))


def plan_for_output(plan):
    """Plan without machine-local absolute paths."""
    sanitized = dict(plan)
    sanitized["entries"] = [{key: value for key, value in entry.items() if key != "sourcePath"} for entry in plan["entries"]]
    return sanitized


# ---------------------------------------------------------------------------
# Finalize (after Bash projection)
# ---------------------------------------------------------------------------

def remove_claude_view_of(project_root, destination):
    """Remove the .claude view of a retired .agents asset when it is a managed view."""
    if not destination.startswith(".agents/"):
        return None
    view = os.path.join(project_root, ".claude", destination[len(".agents/"):])
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


def finalize(project_root, skill_dir, plan, provider_list, updates):
    """Retire assets, then write the lockfile and the manifest."""
    lock_assets = {}
    removed = []
    retire_conflicts = []
    failed = []
    conflicts = []
    previous_lock = read_lock(project_root)
    previous_assets = previous_lock["assets"] if previous_lock else {}

    for entry in plan["entries"]:
        destination = entry["destination"]
        absolute_path = os.path.join(project_root, destination)
        previous_entry = previous_assets.get(destination, {})
        if entry["action"] == ACTION_DROP:
            continue
        if entry["action"] == ACTION_RETIRE:
            if local_state(absolute_path) != entry["local"]:
                retire_conflicts.append(f"{destination} changed during synchronization; preserved")
                lock_assets[destination] = dict(previous_entry, state=STATE_RETIRED_MODIFIED)
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
            lock_assets[destination] = dict(previous_entry, state=STATE_RETIRED_MODIFIED)
            continue
        if entry["action"] == ACTION_CONFLICT:
            conflicts.append(f"{destination}: {entry['reason']}")
            lock_assets[destination] = {
                "profile": entry["profile"],
                "source": entry["source"],
                "sha256": entry["baseSha256"],
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
                "state": STATE_FAILED,
            }

    catalog = load_profile_catalog(skill_dir)
    lock = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": SKILL_NAME, "version": plugin_version(skill_dir), "stateSchemaVersion": SCHEMA_VERSION},
        "source": plan["source"],
        "profiles": profile_digests(skill_dir, catalog, plan["profiles"]),
        # The digests map is keyed by name; profileOrder keeps the resolution order.
        "profileOrder": plan["profiles"],
        "primaryStack": plan["primaryStack"],
        "providers": list(provider_list),
        "requires": {"bash": "3.2+", "git": "any", "python3": "3.8+"},
        "assets": lock_assets,
        "merged": plan["merged"],
    }
    write_text_if_changed(os.path.join(project_root, LOCK_RELATIVE_PATH), serialize_json(lock))

    manifest = read_manifest(project_root)
    manifest_providers = manifest.get("providers", list(provider_list)) if manifest else list(provider_list)
    manifest_updates = updates or (manifest.get("updates") if manifest else None) or DEFAULT_UPDATE_MODE
    desired_manifest = build_manifest(plan["profiles_requested"], manifest_updates, manifest_providers)
    if manifest is None or {key: manifest.get(key) for key in desired_manifest} != desired_manifest:
        write_text_atomically(os.path.join(project_root, MANIFEST_RELATIVE_PATH), serialize_json(desired_manifest))

    return {"removed": removed, "retireConflicts": retire_conflicts, "failed": failed, "conflicts": conflicts}


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

def compute_status(project_root, skill_dir):
    """Read-only state: manifest, checkout versus lock, source versus lock."""
    manifest = read_manifest(project_root)
    lock = read_lock(project_root)
    status = {
        "manifest": manifest,
        "hasLock": lock is not None,
        "lockedSource": lock.get("source") if lock else None,
        "checkout": {"applied": [], "modified": [], "missing": [], "conflict": [], "failed": [], "retiredModified": []},
        "update": None,
        "capabilities": {},
        "errors": [],
    }
    if lock:
        for destination, entry in sorted(lock["assets"].items()):
            local = local_state(os.path.join(project_root, destination))
            state = entry.get("state", STATE_APPLIED)
            if state == STATE_FAILED:
                status["checkout"]["failed"].append(destination)
            elif state == STATE_RETIRED_MODIFIED:
                status["checkout"]["retiredModified"].append(destination)
            elif state == STATE_CONFLICT:
                status["checkout"]["conflict"].append(destination)
            elif local == LOCAL_ABSENT:
                status["checkout"]["missing"].append(destination)
            elif local != entry.get("sha256"):
                status["checkout"]["modified"].append(destination)
            else:
                status["checkout"]["applied"].append(destination)

    profile_names = manifest["profiles"] if manifest else (lock.get("profileOrder") if lock else None)
    if profile_names and skill_dir:
        try:
            plan = compute_plan(project_root, skill_dir, profile_names, False)
        except (ProfileError, StateError) as caught_error:
            status["errors"].append(str(caught_error))
        else:
            changed = [entry["destination"] for entry in plan["entries"]
                       if entry["action"] not in (ACTION_UNCHANGED, ACTION_DROP)]
            locked_digest = (lock or {}).get("source", {}).get("contentDigest")
            status["update"] = {
                "available": locked_digest != plan["source"]["contentDigest"],
                "source": plan["source"],
                "changedDestinations": changed,
            }
    if skill_dir:
        provider_path = os.path.join(skill_dir, PROVIDER_CATALOG_RELATIVE_PATH)
        if os.path.isfile(provider_path):
            providers_catalog = read_json_file(provider_path, "provider catalog").get("providers", {})
            selected = (manifest or {}).get("providers") or list(SUPPORTED_PROVIDERS)
            for provider in selected:
                if provider in providers_catalog:
                    status["capabilities"][provider] = providers_catalog[provider]["capabilities"]
                else:
                    status["errors"].append(f"provider '{provider}' is not supported by agent-ready-setup")
    return status


def status_has_drift(status):
    """True when the checkout or the source differs from the lock."""
    checkout = status["checkout"]
    if any(checkout[key] for key in ("modified", "missing", "conflict", "failed", "retiredModified")):
        return True
    return bool(status["update"] and status["update"]["available"]) or not status["hasLock"]


def print_status(status, brief):
    """Human readable status."""
    stream = sys.stdout
    manifest = status["manifest"]
    if manifest is None:
        write_line(paint("Agent Ready: no manifest (.agents/agent-ready.json); run /agent-ready-setup to pin this repository.", "warning", stream))
    else:
        write_line(f"Agent Ready profiles: {', '.join(manifest['profiles'])} (updates: {manifest.get('updates', DEFAULT_UPDATE_MODE)})")
    if not status["hasLock"]:
        write_line(paint("No lockfile: applied assets are not pinned yet.", "warning", stream))
    else:
        write_line(f"Locked source: {describe_source(status['lockedSource'])}")
        checkout = status["checkout"]
        write_line(
            "Checkout: "
            f"{len(checkout['applied'])} applied, {len(checkout['modified'])} modified, "
            f"{len(checkout['missing'])} missing, {len(checkout['conflict'])} preserved conflicts, "
            f"{len(checkout['failed'])} failed, {len(checkout['retiredModified'])} retired but modified"
        )
        if not brief:
            for key, label in (("modified", "modified"), ("missing", "missing"), ("conflict", "conflict"),
                               ("failed", "failed"), ("retiredModified", "retired but modified")):
                for destination in checkout[key]:
                    write_line(f"  ! {label}: {destination}")
    update = status["update"]
    if update:
        if update["available"]:
            write_line(paint(
                f"Update available: {describe_source(update['source'])}; {len(update['changedDestinations'])} asset(s) would change. "
                "Review it with `/agent-ready-setup plan` and apply it with `/agent-ready-setup`.",
                "warning", stream,
            ))
        else:
            write_line(paint("Source matches the lock: no update pending.", "ok", stream))
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

def requested_profile_names(arguments, catalog):
    """Profiles from --profiles, the legacy --stack alias, or the manifest."""
    if getattr(arguments, "profiles", None):
        return split_profile_names(arguments.profiles)
    if getattr(arguments, "stack", None):
        return profiles_for_stack(catalog, arguments.stack)
    manifest = read_manifest(arguments.project)
    if manifest:
        return list(manifest["profiles"])
    raise ProfileError("no profiles selected: pass --profiles or --stack, or add .agents/agent-ready.json")


def command_resolve(arguments):
    """Print the resolution as key<TAB>value lines for Bash."""
    # A manifest that cannot be read stops the apply even when flags pick the
    # profiles: it may declare a pinned repository that must not be written.
    read_manifest(arguments.project)
    catalog = load_profile_catalog(arguments.skill_dir)
    requested = requested_profile_names(arguments, catalog)
    resolved = resolve_profiles(catalog, requested)
    desired_assets(arguments.skill_dir, catalog, resolved)
    stack_dir = compose_stack_directory(arguments.skill_dir, catalog, resolved, arguments.compose_dir)
    write_line(f"profiles\t{','.join(resolved)}")
    write_line(f"requested\t{','.join(requested)}")
    write_line(f"primary\t{primary_stack(catalog, resolved)}")
    write_line(f"stack_dir\t{stack_dir}")
    write_line(f"tools\t{','.join(resolved_tools(catalog, resolved))}")
    return 0


def command_manifest(arguments):
    """Print the manifest as key<TAB>value lines, or nothing without one."""
    manifest = read_manifest(arguments.project)
    if manifest is None:
        return 0
    write_line(f"profiles\t{','.join(manifest['profiles'])}")
    write_line(f"updates\t{manifest.get('updates', DEFAULT_UPDATE_MODE)}")
    return 0


def command_plan(arguments):
    """Compute the plan; print it, save it, or list protected destinations."""
    catalog = load_profile_catalog(arguments.skill_dir)
    requested = requested_profile_names(arguments, catalog)
    plan = compute_plan(arguments.project, arguments.skill_dir, requested, arguments.force)
    plan["profiles_requested"] = requested
    if arguments.save:
        write_text_atomically(arguments.save, serialize_json(plan))
    if arguments.format == "protected":
        # Non-regular destinations stay with the projection, which already
        # preserves them and reports the structural conflict.
        for entry in plan["entries"]:
            if entry["action"] in (ACTION_CONFLICT, ACTION_RETIRE_CONFLICT) and entry["local"] != LOCAL_NOT_A_FILE:
                write_line(entry["destination"])
    elif arguments.format == "json":
        sys.stdout.write(serialize_json(plan_for_output(plan)))
    else:
        print_plan(
            arguments.project, arguments.skill_dir, plan, arguments.provider, not arguments.no_diff,
            os.environ.get("AGENT_READY_SETUP_MARKETPLACE_UPGRADED") == "1",
            os.environ.get("AGENT_READY_SETUP_BROWSER_INSTALL", "1") == "1",
        )
    return 0


def command_finalize(arguments):
    """Retire assets and write the lockfile from a saved pre-apply plan."""
    plan = read_json_file(arguments.plan, "saved plan")
    providers = split_profile_names(arguments.providers) or list(SUPPORTED_PROVIDERS)
    report = finalize(arguments.project, arguments.skill_dir, plan, providers, arguments.updates)
    print_finalize_report(report)
    return 0


def command_status(arguments):
    """Print the read-only status."""
    status = compute_status(arguments.project, arguments.skill_dir)
    if arguments.format == "json":
        sys.stdout.write(serialize_json(status))
    else:
        print_status(status, arguments.brief)
    if arguments.check and status_has_drift(status):
        return DRIFT_STATUS
    return 0


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

    resolve_parser = subparsers.add_parser("resolve", help="resolve and compose profiles")
    add_common(resolve_parser)
    add_selection(resolve_parser)
    resolve_parser.add_argument("--compose-dir", help="cache directory for composed stack trees")
    resolve_parser.set_defaults(handler=command_resolve)

    manifest_parser = subparsers.add_parser("manifest", help="print the repository manifest")
    add_common(manifest_parser, needs_skill=False)
    manifest_parser.set_defaults(handler=command_manifest)

    plan_parser = subparsers.add_parser("plan", help="read-only plan")
    add_common(plan_parser)
    add_selection(plan_parser)
    plan_parser.add_argument("--force", action="store_true", help="plan overwriting local changes")
    plan_parser.add_argument("--format", choices=("text", "json", "protected"), default="text")
    plan_parser.add_argument("--save", help="also save the full plan as JSON to this path")
    plan_parser.add_argument("--no-diff", action="store_true", help="omit unified diffs from the text plan")
    plan_parser.add_argument("--provider", default="claude", choices=SUPPORTED_PROVIDERS)
    plan_parser.set_defaults(handler=command_plan)

    finalize_parser = subparsers.add_parser("finalize", help="retire assets and write the lockfile")
    add_common(finalize_parser)
    finalize_parser.add_argument("--plan", required=True, help="plan saved before the projection")
    finalize_parser.add_argument("--updates", choices=SUPPORTED_UPDATE_MODES, help="manifest update mode")
    finalize_parser.add_argument("--providers", default=",".join(SUPPORTED_PROVIDERS))
    finalize_parser.set_defaults(handler=command_finalize)

    status_parser = subparsers.add_parser("status", help="read-only status")
    add_common(status_parser, needs_skill=False)
    status_parser.add_argument("--skill-dir", help="resolved source, to detect pending updates")
    status_parser.add_argument("--format", choices=("text", "json"), default="text")
    status_parser.add_argument("--brief", action="store_true", help="summary lines only")
    status_parser.add_argument("--check", action="store_true", help=f"exit {DRIFT_STATUS} when anything drifted")
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
    except ProfileError as caught_error:
        sys.stderr.write(f"ERROR: agent-ready profiles: {caught_error}\n")
        return PROFILE_ERROR_STATUS
    except StateError as caught_error:
        sys.stderr.write(f"ERROR: agent-ready state: {caught_error}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
