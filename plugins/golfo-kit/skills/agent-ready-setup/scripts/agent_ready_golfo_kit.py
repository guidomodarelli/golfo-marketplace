"""golfo-kit as a source: its content at a revision of its own, projected by the installed engine.

The content of golfo-kit (catalog, base, stacks, capabilities, their rules, skills, agents,
commands and instruction templates) can be pinned like a pack: ``sources.golfoKit`` declares an
optional ``ref`` and ``updates`` mode. A pinned repository keeps projecting the revision of its
lock whatever the marketplace publishes; adding a profile or recreating an asset changes nothing
else.

The engine is never pinned. Its scripts, its hooks (which update themselves on every sync), the
settings and Codex hook templates that wire them, the configuration schemas and the provider
capabilities always come from the installed skill. A pinned revision is fetched with Git from the
marketplace repository into the user cache and composed with that engine into a skill directory
the rest of the engine uses as usual.

``sources.golfoKit.source`` takes the content from another Git repository instead: a pack
(``agent-ready-pack.json``) that also publishes the base in ``baseAssets``. Its profiles keep their
names without a namespace, and the composition lays its files where the engine reads the content of
the marketplace (see compose_pack_content).
"""

import hashlib
import json
import os
import shutil
import tempfile

from agent_ready_common import KEBAB_CASE_NAME, ProfileError, StateError, plugin_version, read_json_file
from agent_ready_compatibility import semver_key
from agent_ready_detection import is_contained_pattern
import agent_ready_nested as nested
from agent_ready_options import (
    SOURCES_GOLFO_KIT_REF_KEY,
    SOURCES_GOLFO_KIT_SOURCE_KEY,
    SOURCES_GOLFO_KIT_UPDATES_KEY,
    UPDATES_AUTO,
    UPDATES_PINNED,
)
from agent_ready_packs import (
    FULL_COMMIT,
    GIT_SOURCE_PREFIX,
    GOLFO_KIT_SOURCE_NAME,
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

PLUGIN_RELATIVE_PATH = "plugins/golfo-kit"
SKILL_RELATIVE_PATH = "plugins/golfo-kit/skills/agent-ready-setup"
PLUGIN_MANIFESTS = ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json")
# Paths of the skill that belong to the engine: they follow the installed plugin, never the pin.
ENGINE_OWNED_ASSET_PATHS = (
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
CONTENT_DIRECTORY = "assets"
MARKER_FILE_NAME = ".agent-ready-golfo-kit.json"
ENGINE_DIGEST_LENGTH = 16

# Where the content comes from: the skill of the marketplace, or a pack that sources.golfoKit.source names.
LAYOUT_MARKETPLACE = "marketplace"
LAYOUT_PACK = "pack"
# What a content pack declares: the fields of a pack catalog, plus the base it publishes.
CONTENT_PACK_TOP_LEVEL_KEYS = ("schemaVersion", "name", "version", "minEngine", "changes", "baseAssets", "profiles")
# The fields of a profile of the golfo-kit catalog (agent-ready-state.py validates their values).
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
# Where a composition lays the content of a pack, beside the engine files of the installed skill: the
# base where the engine reads the common assets, and each profile under assets/ at the path it has in
# the pack, as in the marketplace (stacks/react goes to assets/stacks/react).
COMPOSED_BASE_DIRECTORY = "assets/common"
COMPOSED_PROFILES_DIRECTORY = "assets"
CATALOG_RELATIVE_PATH = "assets/profiles.json"
# The content of the installed skill, which a content pack replaces in a composition.
INSTALLED_CONTENT_PATHS = (CATALOG_RELATIVE_PATH, "assets/stacks", "assets/profiles") + tuple(
    f"{COMPOSED_BASE_DIRECTORY}/{entry}" for entry in CONTENT_BASE_DIRECTORIES + CONTENT_BASE_FILES)


def composed_root():
    """Per-user directory of composed skill directories, beside the pack cache, never in a project."""
    return os.path.join(os.path.dirname(pack_cache_root()), "golfo-kit")


def plugin_root_of(skill_dir):
    return os.path.dirname(os.path.dirname(os.path.abspath(skill_dir)))


def engine_origin(engine_dir):
    """Git URL of the marketplace that publishes golfo-kit, from the repository of its manifest."""
    for manifest in PLUGIN_MANIFESTS:
        path = os.path.join(plugin_root_of(engine_dir), manifest)
        if os.path.isfile(path):
            repository = read_json_file(path, "plugin manifest").get("repository")
            if isinstance(repository, str) and repository.startswith("https://"):
                return repository
    raise ProfileError("golfo-kit: the plugin manifest of this installation declares no https repository to fetch its content from")


def declaration_of(configuration, engine_dir, locked_source):
    """golfo-kit as a Git source: the origin of its lock or of the engine, and the ref and mode it declares.

    With ``sources.golfoKit.source`` the origin is that repository, whatever the lock says, and its
    content is a pack (``layout``).
    """
    ref = configuration.value(SOURCES_GOLFO_KIT_REF_KEY)
    source = configuration.value(SOURCES_GOLFO_KIT_SOURCE_KEY)
    if source is not None:
        if not source.startswith(GIT_SOURCE_PREFIX):
            raise ProfileError(f"sources.golfoKit.source '{source}' must start with {GIT_SOURCE_PREFIX}https:// or "
                               f"{GIT_SOURCE_PREFIX}ssh://")
        try:
            declared = parse_git_source(GOLFO_KIT_SOURCE_NAME, source, ref)
        except StateError as source_error:
            raise ProfileError(f"sources.golfoKit.source: {source_error}") from source_error
        return dict(declared, layout=LAYOUT_PACK, updates=configuration.value(SOURCES_GOLFO_KIT_UPDATES_KEY))
    if ref is not None and not (FULL_COMMIT.fullmatch(ref) or SAFE_GIT_REF.fullmatch(ref)):
        raise ProfileError(f"sources.golfoKit.ref '{ref}' is not a full commit, a branch or a tag")
    # Only fetching a revision needs the origin: following the installed engine works without one. The
    # origin of a lock that came from a content pack is not the marketplace's.
    locked = locked_source or {}
    origin = locked.get("origin") if locked.get("layout", LAYOUT_MARKETPLACE) == LAYOUT_MARKETPLACE else None
    if not origin:
        try:
            origin = engine_origin(engine_dir)
        except ProfileError:
            origin = None
    return {"name": GOLFO_KIT_SOURCE_NAME, "type": SOURCE_TYPE_GIT, "origin": origin, "requestedRef": ref,
            "layout": LAYOUT_MARKETPLACE, "updates": configuration.value(SOURCES_GOLFO_KIT_UPDATES_KEY)}


class ContentPendingError(ProfileError):
    """The content pack of the repository is not on this machine and this run cannot download it.

    A run that writes nothing (a session start that hands the sync to the background) reports
    nothing from other content: the detached sync downloads it.
    """


def locked_source_of(declaration, locked_source):
    """The lock entry when it comes from the content the declaration names, else None.

    The lock of a marketplace revision says nothing about a content pack, and the other way around:
    changing ``sources.golfoKit.source`` is adopting other content.
    """
    locked = locked_source or {}
    locked_layout = locked.get("layout", LAYOUT_MARKETPLACE)
    if locked_layout != declaration["layout"]:
        return None
    if declaration["layout"] == LAYOUT_PACK and locked.get("origin") != declaration["origin"]:
        return None
    return locked_source


def resolve_ref(declaration, ref, offline):
    """Commit of a full commit, tag or branch; offline, the last one this machine saw."""
    if FULL_COMMIT.fullmatch(ref):
        return ref
    if not SAFE_GIT_REF.fullmatch(ref):
        raise ProfileError(f"golfo-kit: '{ref}' is not a full commit, a branch or a tag")
    if not declaration["origin"]:
        raise ProfileError(f"golfo-kit: the plugin manifest of this installation declares no https repository to resolve '{ref}' in")
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
        unknown = f"golfo-kit: this machine never resolved '{ref}' and the lock has no revision of it"
        if not read_only:
            raise ProfileError(f"{unknown}; run it with network")
        return None, f"{unknown}; comparing with the installed one until a run with network resolves it"
    try:
        return resolve_ref(declaration, ref, False), None
    except ProfileError as resolution_error:
        known = resolve_ref(declaration, ref, True) or locked_revision_of_ref(locked_source, ref) if read_only else None
        if not known:
            raise
        return known, (f"golfo-kit: could not resolve '{ref}' ({resolution_error}); comparing with {known[:12]}, "
                       "the last revision of it this machine knows")


def target_commit(declaration, mode, locked_source, update, to_ref, offline, read_only=False):
    """The revision whose content to project, or None for the installed engine, and a warning or None.

    --to wins; an update or the auto mode follow the declared ref (without one, the installed
    engine); pinned keeps the revision of the lock, and the first apply takes the engine's.
    """
    if to_ref:
        return resolve_ref(declaration, to_ref, offline), None
    locked_source = locked_source_of(declaration, locked_source)
    # A content pack has no installed copy to start from: its first apply adopts its ref.
    first_of_pack = declaration["layout"] == LAYOUT_PACK and not (locked_source or {}).get("revision")
    if update or mode == UPDATES_AUTO or first_of_pack:
        if not declaration["requestedRef"]:
            return None, None
        return follow_ref(declaration, declaration["requestedRef"], locked_source, offline, read_only)
    return (locked_source or {}).get("revision") or None, None


def read_marker(skill_dir):
    """What a composed skill directory pins, or None for an installed one."""
    path = os.path.join(skill_dir, MARKER_FILE_NAME)
    if not os.path.isfile(path):
        return None
    return read_json_file(path, "golfo-kit content marker")


def engine_catalog_inputs(engine_dir):
    """What a composition of a content pack takes from the catalog of the engine: its schema and CI profiles."""
    engine_catalog = read_json_file(os.path.join(engine_dir, *CATALOG_RELATIVE_PATH.split("/")), "profile catalog")
    ci_profiles = {name: entry for name, entry in sorted(engine_catalog.get("profiles", {}).items())
                   if entry.get("kind") == ENGINE_PROFILE_KIND}
    return {"schemaVersion": engine_catalog.get("schemaVersion"), "ciProfiles": ci_profiles}


def engine_digest(engine_dir, layout=LAYOUT_MARKETPLACE):
    """Identity of the engine files a composition copies, so a new engine composes again.

    A content pack also takes the CI profiles and the schema of the engine catalog, which is not copied,
    and the manifests of the engine plugin: they count too.
    """
    digest = hashlib.sha256()
    digest.update(layout.encode("utf-8") + b"\0")
    if layout == LAYOUT_PACK:
        digest.update(json.dumps(engine_catalog_inputs(engine_dir), sort_keys=True).encode("utf-8") + b"\0")
        for manifest in PLUGIN_MANIFESTS:
            manifest_path = os.path.join(plugin_root_of(engine_dir), *manifest.split("/"))
            if os.path.isfile(manifest_path):
                with open(manifest_path, "rb") as file_handle:
                    digest.update(manifest.encode("utf-8") + b"\0" + hashlib.sha256(file_handle.read()).digest())
    for relative_path in sorted(engine_files(engine_dir, layout)):
        digest.update(relative_path.encode("utf-8") + b"\0")
        with open(os.path.join(engine_dir, *relative_path.split("/")), "rb") as file_handle:
            digest.update(hashlib.sha256(file_handle.read()).digest())
    return digest.hexdigest()[:ENGINE_DIGEST_LENGTH]


def engine_files(engine_dir, layout=LAYOUT_MARKETPLACE):
    """Files of the installed skill a composition takes: everything but its content and what tests need.

    With the content of the marketplace, only the engine-owned assets come from the installed skill.
    A content pack only brings its catalog, its base and its profiles, so everything else does.
    """
    files = []
    for directory, directories, names in os.walk(engine_dir):
        relative_directory = os.path.relpath(directory, engine_dir).replace(os.sep, "/")
        directories[:] = sorted(name for name in directories if name not in ENGINE_SKIPPED_DIRECTORIES)
        for name in sorted(names):
            relative_path = name if relative_directory == "." else f"{relative_directory}/{name}"
            if relative_path == MARKER_FILE_NAME:
                continue
            if layout == LAYOUT_PACK:
                if not is_installed_content(relative_path):
                    files.append(relative_path)
                continue
            in_content = relative_path.startswith(CONTENT_DIRECTORY + "/")
            if not in_content or is_engine_owned(relative_path):
                files.append(relative_path)
    return files


def is_installed_content(relative_path):
    return any(relative_path == content or relative_path.startswith(content + "/") for content in INSTALLED_CONTENT_PATHS)


def is_engine_owned(relative_path):
    return any(relative_path == owned or relative_path.startswith(owned + "/") for owned in ENGINE_OWNED_ASSET_PATHS)


def copy_file(source, destination):
    os.makedirs(long_path(os.path.dirname(destination)), exist_ok=True)
    shutil.copy2(long_path(source), long_path(destination))


def compose(engine_dir, origin, commit, requested_ref, layout=LAYOUT_MARKETPLACE):
    """Skill directory with the content of ``commit`` and the installed engine; built once per pair."""
    tree = cached_tree(origin, commit)
    content_skill = os.path.join(tree, *SKILL_RELATIVE_PATH.split("/"))
    if layout == LAYOUT_PACK:
        if not os.path.isfile(os.path.join(tree, PACK_CATALOG_FILE_NAME)):
            raise ProfileError(f"golfo-kit: revision {commit} of {origin} has no {PACK_CATALOG_FILE_NAME} at its root, "
                               "so sources.golfoKit.source does not point to a content pack")
        content_prefix = ""
    else:
        if not os.path.isdir(os.path.join(content_skill, CONTENT_DIRECTORY)):
            raise ProfileError(f"golfo-kit: revision {commit} of {origin} has no {SKILL_RELATIVE_PATH}/{CONTENT_DIRECTORY}")
        content_prefix = f"{SKILL_RELATIVE_PATH}/{CONTENT_DIRECTORY}/"
    # A file the cache could not write (a name or a path too long for this file system, a symlink)
    # would leave the content incomplete: never project part of a revision.
    missing = [path for path in excluded_paths({"type": SOURCE_TYPE_GIT, "name": GOLFO_KIT_SOURCE_NAME, "origin": origin,
                                                "resolvedCommit": commit})
               if path.startswith(content_prefix)]
    if missing:
        raise ProfileError(f"golfo-kit: {len(missing)} file(s) of revision {commit[:12]} could not be written to the cache "
                           f"(first: {missing[0]}); a content source cannot use symlinks, and a long path needs "
                           "XDG_CACHE_HOME in a shorter directory")
    # A short name keeps the deepest asset under the path limit of Windows. The origin counts: the same
    # commit from a fork or a mirror is another source, and the marker and the lock name it.
    identity = f"{commit}\0{engine_digest(engine_dir, layout)}\0{requested_ref or ''}\0{origin}"
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
        manifest_root = plugin_root_of(engine_dir) if layout == LAYOUT_PACK else os.path.join(tree, *PLUGIN_RELATIVE_PATH.split("/"))
        for manifest in PLUGIN_MANIFESTS:
            source = os.path.join(manifest_root, *manifest.split("/"))
            if os.path.isfile(source):
                copy_file(source, os.path.join(staging, *PLUGIN_RELATIVE_PATH.split("/"), *manifest.split("/")))
        if layout == LAYOUT_PACK:
            compose_pack_content(engine_dir, tree, staged_skill, f"revision {commit[:12]} of {origin}")
        else:
            content_root = long_path(os.path.join(content_skill, CONTENT_DIRECTORY))
            for directory, _, names in os.walk(content_root):
                for name in names:
                    source = os.path.join(directory, name)
                    relative_path = CONTENT_DIRECTORY + "/" + os.path.relpath(source, content_root).replace(os.sep, "/")
                    if not is_engine_owned(relative_path):
                        copy_file(source, os.path.join(staged_skill, *relative_path.split("/")))
        for relative_path in engine_files(engine_dir, layout):
            copy_file(os.path.join(engine_dir, *relative_path.split("/")), os.path.join(staged_skill, *relative_path.split("/")))
        marker = {"origin": origin, "commit": commit, "requestedRef": requested_ref, "layout": layout,
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
    return ProfileError(f"golfo-kit: the content pack at {label} {message}")


def require_tree(label, tree, relative_root, what, directories, files):
    """``relative_root`` is a directory of the pack with only the entries it can publish."""
    if not isinstance(relative_root, str) or not is_contained_pattern(relative_root):
        raise content_pack_error(label, f"declares {what} outside the pack; use a relative directory inside it")
    root = os.path.join(tree, *relative_root.split("/"))
    if not os.path.isdir(root):
        raise content_pack_error(label, f"has no directory {relative_root} for {what}")
    for entry in sorted(os.listdir(root)):
        is_directory = os.path.isdir(os.path.join(root, entry))
        if (is_directory and entry not in directories) or (not is_directory and entry not in files):
            allowed = ", ".join([f"{name}/" for name in directories] + list(files))
            raise content_pack_error(label, f"publishes {relative_root}/{entry} in {what}, which can only have {allowed}")
    return root


def copy_tree(source_root, destination_root):
    for directory, _, names in os.walk(long_path(source_root)):
        for name in names:
            source = os.path.join(directory, name)
            relative_path = os.path.relpath(source, long_path(source_root))
            copy_file(source, os.path.join(destination_root, relative_path))


def engine_asset_names(engine_dir):
    """Names under assets/ that the engine keeps in a composition: a profile of a pack cannot take them."""
    installed_content = {path.split("/")[1] for path in INSTALLED_CONTENT_PATHS if path.count("/") == 1}
    return {name for name in os.listdir(os.path.join(engine_dir, CONTENT_DIRECTORY)) if name not in installed_content}


def compose_pack_content(engine_dir, tree, staged_skill, label):
    """Lay the content of a pack where the engine reads golfo-kit's, with the catalog the engine expects.

    The base goes to ``assets/common`` beside the hooks and settings of the engine, each profile to
    ``assets/<its assets>``, and the catalog to ``assets/profiles.json`` with those paths and
    the CI profiles of the engine.
    """
    try:
        catalog = read_json_file(os.path.join(tree, PACK_CATALOG_FILE_NAME), "content pack catalog")
    except StateError as catalog_error:
        raise content_pack_error(label, str(catalog_error)) from catalog_error
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
    engine_inputs = engine_catalog_inputs(engine_dir)
    composed = {key: catalog[key] for key in ("version", "minEngine", "changes") if key in catalog}
    composed.update({"schemaVersion": engine_inputs["schemaVersion"], "baseAssets": COMPOSED_BASE_DIRECTORY,
                     "profiles": {}})
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
            if top_level in engine_asset_names(engine_dir):
                raise content_pack_error(label, f"puts the assets of '{name}' in {top_level}/, a name the engine uses; "
                                                "move them to another directory of the pack")
            translated["assets"] = f"{COMPOSED_PROFILES_DIRECTORY}/{entry['assets']}"
            copy_tree(asset_root, os.path.join(staged_skill, *translated["assets"].split("/")))
        composed["profiles"][name] = translated
    for name, entry in engine_inputs["ciProfiles"].items():
        if name in composed["profiles"]:
            raise content_pack_error(label, f"profile '{name}' takes the name of a CI profile of the engine")
        composed["profiles"][name] = entry
    copy_tree(base_root, os.path.join(staged_skill, *COMPOSED_BASE_DIRECTORY.split("/")))
    catalog_path = os.path.join(staged_skill, *CATALOG_RELATIVE_PATH.split("/"))
    os.makedirs(long_path(os.path.dirname(catalog_path)), exist_ok=True)
    with open(long_path(catalog_path), "w", encoding="utf-8", newline="\n") as file_handle:
        json.dump(composed, file_handle, indent=2, sort_keys=True, ensure_ascii=False)
        file_handle.write("\n")


def update_mode(configuration):
    """Update mode in force for golfo-kit: its own ``sources.golfoKit.updates``, then ``updates.mode``."""
    return effective_update_mode(configuration, {"name": GOLFO_KIT_SOURCE_NAME,
                                                 "updates": configuration.value(SOURCES_GOLFO_KIT_UPDATES_KEY)})


def content_skill_dir(configuration, engine_dir, engine_revision, locked_source, update=False, to_ref=None,
                      offline=False, read_only=False, from_lock=False):
    """The skill directory whose content an apply, plan or status uses, and a warning or None.

    The installed engine directory when golfo-kit follows it; a composed one when the content
    comes from another revision. Offline, a revision this machine never downloaded falls back to
    the engine with a warning only for a run that writes nothing (plan, status, a session start
    that hands the sync to the background); a run that writes stops instead, so it never
    replaces the pinned content with the installed one. ``from_lock`` takes the revision of the
    lock whatever the mode, and never falls back: it reproduces the lock or fails.
    """
    declaration = declaration_of(configuration, engine_dir, locked_source)
    if from_lock:
        if locked_source and locked_source_of(declaration, locked_source) is None:
            raise ProfileError("golfo-kit: the lock comes from other content than the one sources.golfoKit declares "
                               "(source changed); run an apply without --from-lock to adopt it")
        commit, resolution_warning = (locked_source or {}).get("revision") or None, None
    else:
        mode = effective_update_mode(configuration, declaration)
        commit, resolution_warning = target_commit(declaration, mode, locked_source, update, to_ref, offline, read_only)
    is_pack = declaration["layout"] == LAYOUT_PACK
    if commit is None or (commit == engine_revision and not is_pack):
        if is_pack:
            unknown = (f"golfo-kit: sources.golfoKit.source needs the content at a revision, and none of "
                       f"{declaration['origin']} is known on this machine yet")
            if read_only and not from_lock:
                raise ContentPendingError(f"{unknown}; a sync with network downloads it")
            raise ProfileError(f"{unknown}; run it with network")
        return engine_dir, resolution_warning
    if not declaration["origin"]:
        raise ProfileError("golfo-kit: the plugin manifest of this installation declares no https repository to fetch "
                           f"revision {commit[:12]} from")
    if not cached_tree(declaration["origin"], commit):
        if (offline or resolution_warning) and read_only and not from_lock:
            if is_pack:
                # The installed engine has other content: compare with nothing until the content is here.
                raise ContentPendingError(f"golfo-kit: the content pack {declaration['origin']} at {commit[:12]} is not "
                                          "in the cache of this machine yet; a sync with network downloads it")
            return engine_dir, (f"golfo-kit {commit[:12]} is not in the cache of this machine yet; comparing with the "
                                f"installed one until a run with network downloads it")
        if offline:
            raise ProfileError(f"golfo-kit {commit[:12]} is not in the cache of this machine and this run uses no "
                               f"network; nothing was changed: run it with network to download that revision")
        download_commit(GOLFO_KIT_SOURCE_NAME, declaration["origin"], commit)
    # The lock records the ref it came from; reproducing it keeps that ref too.
    if from_lock:
        requested_ref = (locked_source or {}).get("requestedRef")
    else:
        requested_ref = to_ref or declaration["requestedRef"] or (locked_source or {}).get("requestedRef")
    return compose(engine_dir, declaration["origin"], commit, requested_ref, declaration["layout"]), resolution_warning


def is_pinned(configuration, engine_dir, locked_source):
    """Whether golfo-kit waits for an explicit update in this repository."""
    return effective_update_mode(configuration, declaration_of(configuration, engine_dir, locked_source)) == UPDATES_PINNED
