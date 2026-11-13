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
"""

import hashlib
import json
import os
import shutil
import tempfile

from agent_ready_common import ProfileError, plugin_version, read_json_file
from agent_ready_options import SOURCES_GOLFO_KIT_REF_KEY, SOURCES_GOLFO_KIT_UPDATES_KEY, UPDATES_AUTO, UPDATES_PINNED
from agent_ready_packs import (
    FULL_COMMIT,
    GOLFO_KIT_SOURCE_NAME,
    SAFE_GIT_REF,
    SOURCE_TYPE_GIT,
    cached_tree,
    download_commit,
    effective_update_mode,
    excluded_paths,
    last_known_commit,
    long_path,
    pack_cache_root,
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
    """golfo-kit as a Git source: the origin of its lock or of the engine, and the ref and mode it declares."""
    ref = configuration.value(SOURCES_GOLFO_KIT_REF_KEY)
    if ref is not None and not (FULL_COMMIT.fullmatch(ref) or SAFE_GIT_REF.fullmatch(ref)):
        raise ProfileError(f"sources.golfoKit.ref '{ref}' is not a full commit, a branch or a tag")
    # Only fetching a revision needs the origin: following the installed engine works without one.
    origin = (locked_source or {}).get("origin")
    if not origin:
        try:
            origin = engine_origin(engine_dir)
        except ProfileError:
            origin = None
    return {"name": GOLFO_KIT_SOURCE_NAME, "type": SOURCE_TYPE_GIT, "origin": origin, "requestedRef": ref,
            "updates": configuration.value(SOURCES_GOLFO_KIT_UPDATES_KEY)}


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
    if update or mode == UPDATES_AUTO:
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


def engine_digest(engine_dir):
    """Identity of the engine files a composition copies, so a new engine composes again."""
    digest = hashlib.sha256()
    for relative_path in sorted(engine_files(engine_dir)):
        digest.update(relative_path.encode("utf-8") + b"\0")
        with open(os.path.join(engine_dir, *relative_path.split("/")), "rb") as file_handle:
            digest.update(hashlib.sha256(file_handle.read()).digest())
    return digest.hexdigest()[:ENGINE_DIGEST_LENGTH]


def engine_files(engine_dir):
    """Files of the installed skill a composition takes: everything but its content and what tests need."""
    files = []
    for directory, directories, names in os.walk(engine_dir):
        relative_directory = os.path.relpath(directory, engine_dir).replace(os.sep, "/")
        directories[:] = sorted(name for name in directories if name not in ENGINE_SKIPPED_DIRECTORIES)
        for name in sorted(names):
            relative_path = name if relative_directory == "." else f"{relative_directory}/{name}"
            if relative_path == MARKER_FILE_NAME:
                continue
            in_content = relative_path.startswith(CONTENT_DIRECTORY + "/")
            if not in_content or is_engine_owned(relative_path):
                files.append(relative_path)
    return files


def is_engine_owned(relative_path):
    return any(relative_path == owned or relative_path.startswith(owned + "/") for owned in ENGINE_OWNED_ASSET_PATHS)


def copy_file(source, destination):
    os.makedirs(long_path(os.path.dirname(destination)), exist_ok=True)
    shutil.copy2(long_path(source), long_path(destination))


def compose(engine_dir, origin, commit, requested_ref):
    """Skill directory with the content of ``commit`` and the installed engine; built once per pair."""
    tree = cached_tree(origin, commit)
    content_skill = os.path.join(tree, *SKILL_RELATIVE_PATH.split("/"))
    if not os.path.isdir(os.path.join(content_skill, CONTENT_DIRECTORY)):
        raise ProfileError(f"golfo-kit: revision {commit} of {origin} has no {SKILL_RELATIVE_PATH}/{CONTENT_DIRECTORY}")
    # A file the cache could not write (a name or a path too long for this file system) would
    # leave the content incomplete: never project part of a revision.
    missing = [path for path in excluded_paths({"type": SOURCE_TYPE_GIT, "name": GOLFO_KIT_SOURCE_NAME, "origin": origin,
                                                "resolvedCommit": commit})
               if path.startswith(f"{SKILL_RELATIVE_PATH}/{CONTENT_DIRECTORY}/")]
    if missing:
        raise ProfileError(f"golfo-kit: {len(missing)} file(s) of revision {commit[:12]} could not be written to the cache "
                           f"(first: {missing[0]}); point XDG_CACHE_HOME to a shorter directory and try again")
    # A short name keeps the deepest asset under the path limit of Windows.
    identity = f"{commit}\0{engine_digest(engine_dir)}\0{requested_ref or ''}"
    pair = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:ENGINE_DIGEST_LENGTH]
    root = os.path.join(composed_root(), pair)
    skill_dir = os.path.join(root, *SKILL_RELATIVE_PATH.split("/"))
    if os.path.isfile(os.path.join(skill_dir, MARKER_FILE_NAME)):
        return skill_dir
    os.makedirs(os.path.dirname(root), exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".s", dir=os.path.dirname(root))
    try:
        staged_skill = os.path.join(staging, *SKILL_RELATIVE_PATH.split("/"))
        for manifest in PLUGIN_MANIFESTS:
            source = os.path.join(tree, *PLUGIN_RELATIVE_PATH.split("/"), *manifest.split("/"))
            if os.path.isfile(source):
                copy_file(source, os.path.join(staging, *PLUGIN_RELATIVE_PATH.split("/"), *manifest.split("/")))
        content_root = long_path(os.path.join(content_skill, CONTENT_DIRECTORY))
        for directory, _, names in os.walk(content_root):
            for name in names:
                source = os.path.join(directory, name)
                relative_path = CONTENT_DIRECTORY + "/" + os.path.relpath(source, content_root).replace(os.sep, "/")
                if not is_engine_owned(relative_path):
                    copy_file(source, os.path.join(staged_skill, *relative_path.split("/")))
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
        commit, resolution_warning = (locked_source or {}).get("revision") or None, None
    else:
        mode = effective_update_mode(configuration, declaration)
        commit, resolution_warning = target_commit(declaration, mode, locked_source, update, to_ref, offline, read_only)
    if commit is None or commit == engine_revision:
        return engine_dir, resolution_warning
    if not declaration["origin"]:
        raise ProfileError("golfo-kit: the plugin manifest of this installation declares no https repository to fetch "
                           f"revision {commit[:12]} from")
    if not cached_tree(declaration["origin"], commit):
        if (offline or resolution_warning) and read_only and not from_lock:
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
    return compose(engine_dir, declaration["origin"], commit, requested_ref), resolution_warning


def is_pinned(configuration, engine_dir, locked_source):
    """Whether golfo-kit waits for an explicit update in this repository."""
    return effective_update_mode(configuration, declaration_of(configuration, engine_dir, locked_source)) == UPDATES_PINNED
