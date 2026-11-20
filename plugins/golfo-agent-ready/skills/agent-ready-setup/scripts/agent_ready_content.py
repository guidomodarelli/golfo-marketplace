"""The content agent-ready-setup projects: a content pack at a revision of its own, run by the installed engine.

The engine (this skill: scripts, hooks, settings and Codex hook templates, configuration schemas,
provider capabilities and the CI profiles) carries no content. The rules, skills, agents, commands,
the catalog of profiles and the template of AGENTS.md come from a content pack: a Git repository
with an ``agent-ready-pack.json`` that also publishes the base in ``baseAssets``. ``sources.golfo``
names it; by default it is the official one of golfo, ``sources.golfo.ref`` picks the revision to
follow and ``sources.golfo.updates`` whether a new one is adopted on its own or waits for
``agent-ready update golfo``.

A revision is fetched with Git into the user cache and composed with the installed engine into a
skill directory the rest of the engine uses as usual: the base goes where the engine reads the
common assets, each profile under ``assets/``, and the catalog to ``assets/profiles.json`` (see
compose_pack_content). Its profiles keep their names without a namespace.
"""

import sys

from agent_ready_lockfile import read_lock
from agent_ready_manifest import configuration_of
from agent_ready_output import write_line

import hashlib
import json
import os
import shutil
import tempfile

from agent_ready_common import (
    CONTENT_UNPROJECTED_DIRECTORIES,
    KEBAB_CASE_NAME,
    ProfileError,
    StateError,
    plugin_version,
    read_json_file,
)
from agent_ready_compatibility import require_engine, semver_key
from agent_ready_detection import is_contained_pattern
import agent_ready_nested as nested
from agent_ready_options import (
    SOURCES_GOLFO_REF_KEY,
    SOURCES_GOLFO_SOURCE_KEY,
    SOURCES_GOLFO_UPDATES_KEY,
    UPDATES_AUTO,
    UPDATES_PINNED,
)
from agent_ready_packs import (
    CONTENT_SOURCE_NAME,
    FULL_COMMIT,
    GIT_SOURCE_PREFIX,
    PACK_CATALOG_FILE_NAME,
    PACK_SCHEMA_VERSION,
    SAFE_GIT_REF,
    SOURCE_TYPE_GIT,
    cached_tree,
    download_commit,
    effective_update_mode,
    excluded_paths,
    last_known_commit,
    long_path,
    pack_cache_root,
    parse_git_source,
    record_latest_commit,
    resolve_remote_ref,
)

PLUGIN_RELATIVE_PATH = "plugins/golfo-agent-ready"
SKILL_RELATIVE_PATH = "plugins/golfo-agent-ready/skills/agent-ready-setup"
PLUGIN_MANIFESTS = ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json")
# Assets of the engine that a projection writes too (hooks, settings, CI files): they follow the installed
# plugin, never the revision of the content, so a new engine is not a new release of the content.
ENGINE_OWNED_ASSET_PATHS = (
    "assets/ci",
    "assets/common/hooks",
    "assets/common/settings.json",
    "assets/codex",
    "assets/config",
    "assets/formatters.json",
    "assets/git-hooks",
    "assets/providers.json",
    "assets/repo-facts.json",
)
# Parts of the installed skill that running the engine does not need.
ENGINE_SKIPPED_DIRECTORIES = ("tests", "evals", "__pycache__")
ASSETS_DIRECTORY = "assets"
MARKER_FILE_NAME = ".agent-ready-content.json"
ENGINE_DIGEST_LENGTH = 16
COMPOSED_DIRECTORY_NAME = "content"

# What a content pack declares: the fields of a pack catalog, plus the base it publishes.
CONTENT_PACK_TOP_LEVEL_KEYS = ("schemaVersion", "name", "version", "minEngine", "changes", "baseAssets", "profiles")
# The fields of a profile of the catalog (agent-ready-state.py validates their values).
CONTENT_PACK_PROFILE_KEYS = ("kind", "description", "assets", "requires", "conflicts", "defaults", "overrides",
                             "complements", "tools", "detect", nested.NESTED_KEY)
CONTENT_PACK_PROFILE_KINDS = ("stack", "capability", "bundle")
# The name the engine gives the base in the lock, the blocks and the digests: no profile can take it.
RESERVED_PROFILE_NAMES = ("common",)
# CI profiles bring the files that run the CLI of this engine, so they always come from the engine.
ENGINE_PROFILE_KIND = "ci"
AGENTS_TEMPLATE_FILE_NAME = "agents-template.md"
AGENTS_SKELETON_FILE_NAME = "agents-skeleton.md"
# The base of a content pack: common rules, skills and blocks, and the AGENTS.md template. Hooks and
# settings are the engine's.
CONTENT_BASE_DIRECTORIES = ("rules", "skills", "blocks")
CONTENT_BASE_FILES = (AGENTS_TEMPLATE_FILE_NAME,)
# What a profile of a content pack publishes: what a pack can, plus the AGENTS.md skeleton of a capability.
CONTENT_PROFILE_DIRECTORIES = ("rules", "skills", "agents", "commands", "blocks", nested.NESTED_DIRECTORY)
CONTENT_PROFILE_FILES = (AGENTS_SKELETON_FILE_NAME,)
# Where a composition lays the content, beside the engine files of the installed skill: the base where
# the engine reads the common assets, and each profile under assets/ at the path it has in the pack
# (stacks/react goes to assets/stacks/react).
COMPOSED_BASE_DIRECTORY = "assets/common"
COMPOSED_PROFILES_DIRECTORY = "assets"
CATALOG_RELATIVE_PATH = "assets/profiles.json"
# Development override: the content of a local directory (a checkout of a content pack being written),
# whatever sources.golfo says. It has no revision: its files identify it, and the lock records no origin.
CONTENT_DIRECTORY_VARIABLE = "AGENT_READY_SETUP_CONTENT_DIR"
LOCAL_ORIGIN = "local"
# Files of a checkout that are not content: version control and caches.
LOCAL_SKIPPED_NAMES = (".git", "__pycache__")


class ContentPendingError(ProfileError):
    """The content pack of the repository is not on this machine and this run cannot download it.

    A run that writes nothing (a session start that hands the sync to the background) reports
    nothing from other content: the detached sync downloads it.
    """


def composed_root():
    """Per-user directory of composed skill directories, beside the pack cache, never in a project."""
    return os.path.join(os.path.dirname(pack_cache_root()), COMPOSED_DIRECTORY_NAME)


def plugin_root_of(skill_dir):
    return os.path.dirname(os.path.dirname(os.path.abspath(skill_dir)))


def declaration_of(configuration):
    """The content source as a Git source: its origin, the ref it follows and its update mode."""
    source = configuration.value(SOURCES_GOLFO_SOURCE_KEY)
    if not isinstance(source, str) or not source.startswith(GIT_SOURCE_PREFIX):
        raise ProfileError(f"sources.golfo.source '{source}' must start with {GIT_SOURCE_PREFIX}https:// or "
                           f"{GIT_SOURCE_PREFIX}ssh://")
    if "#" in source:
        raise ProfileError(f"sources.golfo.source '{source}' has a revision after '#'; put it in sources.golfo.ref")
    try:
        declared = parse_git_source(CONTENT_SOURCE_NAME, source, configuration.value(SOURCES_GOLFO_REF_KEY))
    except StateError as source_error:
        raise ProfileError(f"sources.golfo: {source_error}") from source_error
    return dict(declared, updates=configuration.value(SOURCES_GOLFO_UPDATES_KEY))


def locked_source_of(declaration, locked_source):
    """The lock entry when it comes from the repository the declaration names, else None.

    Changing ``sources.golfo.source`` is adopting other content: the lock of the previous one does not count.
    """
    return locked_source if (locked_source or {}).get("origin") == declaration["origin"] else None


def resolve_ref(declaration, ref, offline):
    """Commit of a full commit, tag or branch; offline, the last one this machine saw."""
    if FULL_COMMIT.fullmatch(ref):
        return ref
    if not SAFE_GIT_REF.fullmatch(ref):
        raise ProfileError(f"{CONTENT_SOURCE_NAME}: '{ref}' is not a full commit, a branch or a tag")
    if offline:
        return last_known_commit(declaration["origin"], ref)
    commit = resolve_remote_ref(dict(declaration, requestedRef=ref))
    record_latest_commit(declaration["origin"], ref, commit)
    return commit


def locked_revision_of_ref(locked_source, ref):
    """The revision of the lock when it came from ``ref``, or None."""
    locked = locked_source or {}
    return locked["revision"] if locked.get("revision") and locked.get("requestedRef") == ref else None


def follow_ref(declaration, ref, locked_source, offline, read_only):
    """Commit ``ref`` points at and a warning or None.

    Without the network the answer is the last commit this machine saw, then the revision of the
    lock that came from that ref. A run that writes nothing also takes them when the remote cannot
    be reached; a run that writes stops instead.
    """
    if offline:
        known = resolve_ref(declaration, ref, True) or locked_revision_of_ref(locked_source, ref)
        if known:
            return known, None
        unknown = f"{CONTENT_SOURCE_NAME}: this machine never resolved '{ref}' and the lock has no revision of it"
        if not read_only:
            raise ProfileError(f"{unknown}; run it with network")
        raise ContentPendingError(f"{unknown}; a sync with network resolves it")
    try:
        return resolve_ref(declaration, ref, False), None
    except ProfileError as resolution_error:
        known = resolve_ref(declaration, ref, True) or locked_revision_of_ref(locked_source, ref) if read_only else None
        if not known:
            raise
        return known, (f"{CONTENT_SOURCE_NAME}: could not resolve '{ref}' ({resolution_error}); comparing with "
                       f"{known[:12]}, the last revision of it this machine knows")


def target_commit(declaration, mode, locked_source, update, to_ref, offline, read_only=False):
    """The revision whose content to project and a warning or None.

    --to wins; an update, the auto mode and the first apply follow the declared ref; pinned keeps the
    revision of the lock.
    """
    if to_ref:
        return resolve_ref(declaration, to_ref, offline), None
    locked_source = locked_source_of(declaration, locked_source)
    locked_revision = (locked_source or {}).get("revision")
    if update or mode == UPDATES_AUTO or not locked_revision:
        return follow_ref(declaration, declaration["requestedRef"], locked_source, offline, read_only)
    return locked_revision, None


def read_marker(skill_dir):
    """What a composed skill directory projects: the origin and commit of its content, and its engine."""
    path = os.path.join(skill_dir, MARKER_FILE_NAME)
    if not os.path.isfile(path):
        return None
    return read_json_file(path, "content marker")


def engine_digest(engine_dir):
    """Identity of the engine files a composition copies, so a new engine composes again.

    The CI catalog of the engine (``assets/ci/profiles.json``) is one of those files. The manifests of the
    engine plugin, which are not under the skill, count too.
    """
    digest = hashlib.sha256()
    for manifest in PLUGIN_MANIFESTS:
        manifest_path = os.path.join(plugin_root_of(engine_dir), *manifest.split("/"))
        if os.path.isfile(manifest_path):
            with open(manifest_path, "rb") as file_handle:
                digest.update(manifest.encode("utf-8") + b"\0" + hashlib.sha256(file_handle.read()).digest())
    for relative_path in sorted(engine_files(engine_dir)):
        digest.update(relative_path.encode("utf-8") + b"\0")
        with open(os.path.join(engine_dir, *relative_path.split("/")), "rb") as file_handle:
            digest.update(hashlib.sha256(file_handle.read()).digest())
    return digest.hexdigest()[:ENGINE_DIGEST_LENGTH]


def engine_files(engine_dir):
    """Files of the installed skill a composition takes: all of them but what only tests and evals need."""
    files = []
    for directory, directories, names in os.walk(engine_dir):
        relative_directory = os.path.relpath(directory, engine_dir).replace(os.sep, "/")
        directories[:] = sorted(name for name in directories if name not in ENGINE_SKIPPED_DIRECTORIES)
        for name in sorted(names):
            relative_path = name if relative_directory == "." else f"{relative_directory}/{name}"
            if relative_path != MARKER_FILE_NAME:
                files.append(relative_path)
    return files


def is_engine_owned(relative_path):
    return any(relative_path == owned or relative_path.startswith(owned + "/") for owned in ENGINE_OWNED_ASSET_PATHS)


def copy_file(source, destination):
    os.makedirs(long_path(os.path.dirname(destination)), exist_ok=True)
    shutil.copy2(long_path(source), long_path(destination))


def copy_tree(source_root, destination_root):
    """Copy a root of the content into the composition, without the evals of its rules (never projected)."""
    for directory, directories, names in os.walk(long_path(source_root)):
        if os.path.normcase(directory) == os.path.normcase(long_path(source_root)):
            directories[:] = [name for name in directories if name not in CONTENT_UNPROJECTED_DIRECTORIES]
        for name in names:
            source = os.path.join(directory, name)
            relative_path = os.path.relpath(source, long_path(source_root))
            copy_file(source, os.path.join(destination_root, relative_path))


def local_files(directory):
    """Relative paths of the files of a local content directory, without version control or caches."""
    files = []
    for current, directories, names in os.walk(directory):
        directories[:] = sorted(name for name in directories if name not in LOCAL_SKIPPED_NAMES)
        relative_directory = os.path.relpath(current, directory).replace(os.sep, "/")
        for name in sorted(names):
            path = os.path.join(current, name)
            relative_path = name if relative_directory == "." else f"{relative_directory}/{name}"
            if os.path.islink(path):
                raise ProfileError(f"{CONTENT_SOURCE_NAME}: {CONTENT_DIRECTORY_VARIABLE} has the symlink {relative_path}, "
                                   "which a content pack cannot use")
            files.append(relative_path)
    return files


def local_digest(directory):
    """Identity of a local content directory: every file and its sha256."""
    digest = hashlib.sha256()
    for relative_path in local_files(directory):
        digest.update(relative_path.encode("utf-8") + b"\0")
        with open(os.path.join(directory, *relative_path.split("/")), "rb") as file_handle:
            digest.update(hashlib.sha256(file_handle.read()).digest())
    return digest.hexdigest()


def local_content_dir():
    """The directory of the development override, or None."""
    directory = os.environ.get(CONTENT_DIRECTORY_VARIABLE)
    if not directory:
        return None
    if not os.path.isabs(directory) or not os.path.isfile(os.path.join(directory, PACK_CATALOG_FILE_NAME)):
        raise ProfileError(f"{CONTENT_SOURCE_NAME}: {CONTENT_DIRECTORY_VARIABLE} must be the absolute path of a content "
                           f"pack, with {PACK_CATALOG_FILE_NAME} at its root: {directory}")
    return directory


def compose(engine_dir, origin, commit, requested_ref, tree=None):
    """Skill directory with the content of ``commit`` (or of the local ``tree``) and the installed engine.

    Built once per pair of content and engine.
    """
    if tree is None:
        tree = cached_tree(origin, commit)
        # A file the cache could not write (a name or a path too long for this file system, a symlink)
        # would leave the content incomplete: never project part of a revision.
        missing = excluded_paths({"type": SOURCE_TYPE_GIT, "name": CONTENT_SOURCE_NAME, "origin": origin,
                                  "resolvedCommit": commit})
        if missing:
            raise ProfileError(f"{CONTENT_SOURCE_NAME}: {len(missing)} file(s) of revision {commit[:12]} could not be "
                               f"written to the cache (first: {missing[0]}); a content pack cannot use symlinks, and a "
                               "long path needs XDG_CACHE_HOME in a shorter directory")
        content_identity = commit
    else:
        content_identity = local_digest(tree)
    if not os.path.isfile(os.path.join(tree, PACK_CATALOG_FILE_NAME)):
        raise ProfileError(f"{CONTENT_SOURCE_NAME}: revision {commit} of {origin} has no {PACK_CATALOG_FILE_NAME} at its "
                           "root, so sources.golfo.source does not point to a content pack")
    # A short name keeps the deepest asset under the path limit of Windows. The origin counts: the same
    # commit from a fork or a mirror is another source, and the marker and the lock name it.
    identity = f"{content_identity}\0{engine_digest(engine_dir)}\0{requested_ref or ''}\0{origin}"
    pair = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:ENGINE_DIGEST_LENGTH]
    root = os.path.join(composed_root(), pair)
    skill_dir = os.path.join(root, *SKILL_RELATIVE_PATH.split("/"))
    if os.path.isfile(os.path.join(skill_dir, MARKER_FILE_NAME)):
        return skill_dir
    os.makedirs(os.path.dirname(root), exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".s", dir=os.path.dirname(root))
    try:
        staged_skill = os.path.join(staging, *SKILL_RELATIVE_PATH.split("/"))
        # A content pack has no plugin of its own: the composition carries the engine's manifests.
        for manifest in PLUGIN_MANIFESTS:
            source = os.path.join(plugin_root_of(engine_dir), *manifest.split("/"))
            if os.path.isfile(source):
                copy_file(source, os.path.join(staging, *PLUGIN_RELATIVE_PATH.split("/"), *manifest.split("/")))
        label = f"revision {commit[:12]} of {origin}" if commit else f"{tree} ({CONTENT_DIRECTORY_VARIABLE})"
        compose_pack_content(engine_dir, tree, staged_skill, label)
        for relative_path in engine_files(engine_dir):
            copy_file(os.path.join(engine_dir, *relative_path.split("/")), os.path.join(staged_skill, *relative_path.split("/")))
        marker = {"origin": origin, "commit": commit, "requestedRef": requested_ref,
                  "engineVersion": plugin_version(engine_dir), "engineSkillDir": os.path.abspath(engine_dir)}
        with open(os.path.join(staged_skill, MARKER_FILE_NAME), "w", encoding="utf-8", newline="\n") as file_handle:
            json.dump(marker, file_handle, indent=2, sort_keys=True)
            file_handle.write("\n")
        try:
            os.replace(staging, root)
        except OSError:
            # Another process composed the same pair first; its copy is identical.
            if not os.path.isfile(os.path.join(skill_dir, MARKER_FILE_NAME)):
                raise
            shutil.rmtree(staging, ignore_errors=True)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return skill_dir


def content_pack_error(label, message):
    return ProfileError(f"{CONTENT_SOURCE_NAME}: the content pack at {label} {message}")


def require_tree(label, tree, relative_root, what, directories, files):
    """``relative_root`` is a directory of the pack with only the entries it can publish."""
    if not isinstance(relative_root, str) or not is_contained_pattern(relative_root):
        raise content_pack_error(label, f"declares {what} outside the pack; use a relative directory inside it")
    root = os.path.join(tree, *relative_root.split("/"))
    if not os.path.isdir(root):
        raise content_pack_error(label, f"has no directory {relative_root} for {what}")
    for entry in sorted(os.listdir(root)):
        is_directory = os.path.isdir(os.path.join(root, entry))
        if is_directory and entry in CONTENT_UNPROJECTED_DIRECTORIES:
            # Evals of the rules, next to them: accepted and never projected (walk_content_files).
            continue
        if (is_directory and entry not in directories) or (not is_directory and entry not in files):
            allowed = ", ".join([f"{name}/" for name in directories] + list(files))
            raise content_pack_error(label, f"publishes {relative_root}/{entry} in {what}, which can only have {allowed}")
    return root


def engine_asset_names(engine_dir):
    """Names under assets/ that the engine keeps in a composition: a profile of a pack cannot take them."""
    return set(os.listdir(os.path.join(engine_dir, ASSETS_DIRECTORY)))


def compose_pack_content(engine_dir, tree, staged_skill, label):
    """Lay the content of a pack where the engine reads it, with the catalog the engine expects.

    The base goes to ``assets/common`` beside the hooks and settings of the engine, each profile to
    ``assets/<its assets>``, and the catalog to ``assets/profiles.json`` with those paths. The CI
    profiles come from the catalog of the engine (``assets/ci/profiles.json``).
    """
    try:
        catalog = read_json_file(os.path.join(tree, PACK_CATALOG_FILE_NAME), "content pack catalog")
    except StateError as catalog_error:
        raise content_pack_error(label, str(catalog_error)) from catalog_error
    # A catalog for a newer engine (schemaVersion, minEngine) asks for that engine before its format is judged.
    require_engine(f"{CONTENT_SOURCE_NAME}: the content pack at {label}", catalog, plugin_version(engine_dir), PACK_SCHEMA_VERSION)
    extra_keys = sorted(set(catalog) - set(CONTENT_PACK_TOP_LEVEL_KEYS))
    if extra_keys:
        raise content_pack_error(label, f"has fields a content pack cannot declare: {', '.join(extra_keys)}")
    if catalog.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise content_pack_error(label, f"must declare schemaVersion {PACK_SCHEMA_VERSION}")
    if not isinstance(catalog.get("name"), str) or not KEBAB_CASE_NAME.fullmatch(catalog["name"]):
        raise content_pack_error(label, "must declare its name in kebab-case")
    if not semver_key(catalog.get("version")):
        raise content_pack_error(label, "must declare the semver version of its content in version")
    if "baseAssets" not in catalog:
        raise content_pack_error(label, "declares no baseAssets: a content source publishes the base every repository gets")
    base_root = require_tree(label, tree, catalog["baseAssets"], "baseAssets", CONTENT_BASE_DIRECTORIES, CONTENT_BASE_FILES)
    if not os.path.isfile(os.path.join(base_root, AGENTS_TEMPLATE_FILE_NAME)):
        raise content_pack_error(label, f"has no {catalog['baseAssets']}/{AGENTS_TEMPLATE_FILE_NAME}, the template of AGENTS.md")
    profiles = catalog.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise content_pack_error(label, "has no profiles")
    composed = {key: catalog[key] for key in ("schemaVersion", "version", "minEngine", "changes") if key in catalog}
    composed.update({"baseAssets": COMPOSED_BASE_DIRECTORY, "profiles": {}})
    reserved_directories = engine_asset_names(engine_dir)
    for name, entry in sorted(profiles.items()):
        if not isinstance(name, str) or not KEBAB_CASE_NAME.fullmatch(name):
            raise content_pack_error(label, f"has an invalid profile name '{name}'; use kebab-case")
        if not isinstance(entry, dict):
            raise content_pack_error(label, f"profile '{name}' must be an object")
        if name in RESERVED_PROFILE_NAMES:
            raise content_pack_error(label, f"declares a profile named '{name}', the name the engine gives the base; "
                                            "use another name")
        if entry.get("kind") == ENGINE_PROFILE_KIND:
            raise content_pack_error(label, f"declares the CI profile '{name}': CI profiles come with the engine")
        if entry.get("kind") not in CONTENT_PACK_PROFILE_KINDS:
            raise content_pack_error(label, f"profile '{name}' must have kind {', '.join(repr(kind) for kind in CONTENT_PACK_PROFILE_KINDS)}")
        extra_keys = sorted(set(entry) - set(CONTENT_PACK_PROFILE_KEYS))
        if extra_keys:
            raise content_pack_error(label, f"profile '{name}' has unknown keys: {', '.join(extra_keys)}")
        translated = dict(entry)
        if "assets" in entry:
            asset_root = require_tree(label, tree, entry["assets"], f"the assets of '{name}'",
                                      CONTENT_PROFILE_DIRECTORIES, CONTENT_PROFILE_FILES)
            top_level = entry["assets"].split("/", 1)[0]
            if top_level in reserved_directories:
                raise content_pack_error(label, f"puts the assets of '{name}' in {top_level}/, a name the engine uses; "
                                                "move them to another directory of the pack")
            translated["assets"] = f"{COMPOSED_PROFILES_DIRECTORY}/{entry['assets']}"
            copy_tree(asset_root, os.path.join(staged_skill, *translated["assets"].split("/")))
        composed["profiles"][name] = translated
    copy_tree(base_root, os.path.join(staged_skill, *COMPOSED_BASE_DIRECTORY.split("/")))
    catalog_path = os.path.join(staged_skill, *CATALOG_RELATIVE_PATH.split("/"))
    os.makedirs(long_path(os.path.dirname(catalog_path)), exist_ok=True)
    with open(long_path(catalog_path), "w", encoding="utf-8", newline="\n") as file_handle:
        json.dump(composed, file_handle, indent=2, sort_keys=True, ensure_ascii=False)
        file_handle.write("\n")


def update_mode(configuration):
    """Update mode in force for the content: its own ``sources.golfo.updates``, then ``updates.mode``."""
    return effective_update_mode(configuration, {"name": CONTENT_SOURCE_NAME,
                                                 "updates": configuration.value(SOURCES_GOLFO_UPDATES_KEY)})


def content_skill_dir(configuration, engine_dir, locked_source, update=False, to_ref=None, offline=False,
                      read_only=False, from_lock=False):
    """The composed skill directory whose content an apply, plan or status uses, and a warning or None.

    Offline, a revision this machine never downloaded stops a run that writes nothing with
    ContentPendingError (a session start hands the download to the background sync) and any other run
    with an error: there is no other content to compare with. ``from_lock`` takes the revision of the
    lock whatever the mode, and never falls back: it reproduces the lock or fails.

    With the development override (``AGENT_READY_SETUP_CONTENT_DIR``) the content is that directory,
    as it is now: no ref, mode or revision of the lock applies.
    """
    local_directory = local_content_dir()
    if local_directory:
        return compose(engine_dir, LOCAL_ORIGIN, None, None, tree=local_directory), None
    declaration = declaration_of(configuration)
    if from_lock:
        if locked_source and locked_source_of(declaration, locked_source) is None:
            raise ProfileError(f"{CONTENT_SOURCE_NAME}: the lock comes from other content than the one sources.golfo "
                               "declares (source changed); run an apply without --from-lock to adopt it")
        commit, resolution_warning = (locked_source or {}).get("revision"), None
        if not commit:
            raise ProfileError(f"{CONTENT_SOURCE_NAME}: the lock records no revision of the content to reproduce")
    else:
        mode = effective_update_mode(configuration, declaration)
        commit, resolution_warning = target_commit(declaration, mode, locked_source, update, to_ref, offline, read_only)
    if not cached_tree(declaration["origin"], commit):
        if (offline or resolution_warning) and read_only and not from_lock:
            raise ContentPendingError(f"{CONTENT_SOURCE_NAME}: the content pack {declaration['origin']} at {commit[:12]} "
                                      "is not in the cache of this machine yet; a sync with network downloads it")
        if offline:
            raise ProfileError(f"{CONTENT_SOURCE_NAME}: {commit[:12]} is not in the cache of this machine and this run "
                               "uses no network; nothing was changed: run it with network to download that revision")
        download_commit(CONTENT_SOURCE_NAME, declaration["origin"], commit)
    # The lock records the ref it came from; reproducing it keeps that ref too.
    if from_lock:
        requested_ref = (locked_source or {}).get("requestedRef")
    else:
        requested_ref = to_ref or declaration["requestedRef"]
    return compose(engine_dir, declaration["origin"], commit, requested_ref), resolution_warning


def locked_content_dir(engine_dir, locked_source):
    """The composed skill directory of the content the lock records, without reading the configuration.

    A removal identifies what the setup generated from the content that generated it, even with an
    invalid manifest. With the development override it is that directory; without a revision to
    fetch (or when it cannot be fetched) it raises ProfileError.
    """
    local_directory = local_content_dir()
    if local_directory:
        return compose(engine_dir, LOCAL_ORIGIN, None, None, tree=local_directory)
    locked = locked_source or {}
    origin, commit = locked.get("origin"), locked.get("revision")
    if not origin or not commit:
        raise ProfileError(f"{CONTENT_SOURCE_NAME}: the lock records no revision of the content to read")
    if not cached_tree(origin, commit):
        download_commit(CONTENT_SOURCE_NAME, origin, commit)
    return compose(engine_dir, origin, commit, locked.get("requestedRef"))


def is_pinned(configuration):
    """Whether the content waits for an explicit update in this repository."""
    return effective_update_mode(configuration, declaration_of(configuration)) == UPDATES_PINNED


def engine_version_of(skill_dir):
    """Version of the engine that projects ``skill_dir``: the installed one, whatever the content."""
    marker = read_marker(skill_dir)
    return marker["engineVersion"] if marker else plugin_version(skill_dir)


def content_dir_of(project_root, skill_dir, offline=False, read_only=True):
    """Skill directory with the content this repository uses, composed with the engine ``skill_dir``.

    Offline, a revision missing from the cache raises ContentPendingError for a run that writes nothing.
    """
    lock = read_lock(project_root)
    content_dir, warning = content_skill_dir(
        configuration_of(project_root, offline), skill_dir, (lock or {}).get("source"),
        offline=offline, read_only=read_only,
    )
    if warning:
        write_line(f"WARNING: {warning}", sys.stderr)
    return content_dir
