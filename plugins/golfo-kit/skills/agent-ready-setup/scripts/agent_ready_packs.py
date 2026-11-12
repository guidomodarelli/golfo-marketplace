"""External profile packs for agent-ready-setup.

A pack is a Git repository or a local directory with a catalog
(``agent-ready-pack.json``) and assets. This module parses the sources a manifest
declares in ``sources.packs``, downloads revisions into a per-user cache and validates catalogs. Only
``download_declared_sources`` and ``refresh_declared_sources`` use the network.
Loading a pack reads files and nothing else: no script of a pack ever runs. The
contract is documented in ``references/profiles-and-lockfile.md``.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse

from agent_ready_compatibility import require_engine, validate_compatibility
import agent_ready_blocks as managed_blocks
import agent_ready_pack_tools as pack_tools
from agent_ready_common import ProfileError, StateError, is_link, read_json_file, sha256_of_file, sha256_of_text
from agent_ready_config import LAYER_ENVIRONMENT, LAYER_FLAGS
from agent_ready_options import UPDATES_AUTO, UPDATES_MODE_KEY
from agent_ready_detection import (
    DetectionSchemaError,
    is_contained_pattern,
    validate_catalog_detection,
)

PACK_CATALOG_FILE_NAME = "agent-ready-pack.json"
PACK_SCHEMA_VERSION = 1
# version, minEngine and changes declare compatibility (agent_ready_compatibility.py).
PACK_ALLOWED_TOP_LEVEL_KEYS = ("schemaVersion", "name", "profiles", "version", "minEngine", "changes")
# clis, mcpServers and scripts are declarations: the security policy decides whether they run
# (agent_ready_pack_tools.py), never the pack.
PACK_ALLOWED_PROFILE_KEYS = ("kind", "description", "assets", "requires", "conflicts", "defaults", "tools", "detect") + pack_tools.DECLARATION_KEYS
PACK_PROFILE_KIND = "capability"
# A pack can also publish bundles: profiles that only group others through requires.
PACK_BUNDLE_KIND = "bundle"
# Tools the engine knows how to install; a pack cannot bring its own installer.
KNOWN_TOOLS = ("browser",)
# Packs add rules, skills, agents and commands as files, and managed blocks inside files of the
# project (blocks/, agent_ready_blocks.py). Hooks, settings and the AGENTS.md
# template stay under the control of the skill and the project; the tools a pack declares
# (clis, mcpServers, scripts) only run through the security policy.
PACK_ALLOWED_ASSET_DIRECTORIES = ("rules", "skills", "agents", "commands", managed_blocks.BLOCK_DIRECTORY)
PACK_FORBIDDEN_ASSET_NAMES = ("agents.md", "claude.md")

NAMESPACE_SEPARATOR = "/"
KEBAB_CASE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# golfo-kit is a source of its own (agent_ready_golfo_kit.py): a pack cannot take its name.
GOLFO_KIT_SOURCE_NAME = "golfo-kit"
GOLFO_REFERENCE = KEBAB_CASE_NAME
PACK_REFERENCE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*$")

SOURCE_TYPE_GIT = "git"
SOURCE_TYPE_PATH = "path"
GIT_SOURCE_PREFIX = "git+"
PATH_SOURCE_PREFIX = "path:"
ALLOWED_GIT_SCHEMES = ("https", "ssh")
SSH_URL_SCHEME = "ssh"
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SAFE_GIT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

# Where the mirror of an origin keeps its tags: the signature check reads the ones that point at
# the revision of a source (agent_ready_pack_signatures.py).
MIRROR_TAG_NAMESPACE = "refs/agent-ready/tags/"
TAG_REF_PREFIX = "refs/tags/"
# ls-remote lists an annotated tag twice: the tag object, and with this suffix the commit it points at.
PEELED_SUFFIX = "^{}"

SOURCE_AVAILABLE = "available"
SOURCE_MISSING = "missing"

GIT_TIMEOUT_SECONDS = 300
GIT_ERROR_MAX_CHARACTERS = 400
# Variables a Git hook may export; they would point these commands at the wrong repository.
GIT_REPOSITORY_VARIABLES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR")
REGULAR_FILE_MODES = (b"100644", b"100755")
EXECUTABLE_FILE_MODE = b"100755"
SUBMODULE_OBJECT_TYPE = b"commit"
EXCLUDED_PATHS_FILE_NAME = "excluded.json"
MATERIALIZED_TREE_DIRECTORY = "tree"
EXECUTABLE_PERMISSIONS = 0o755
URL_CREDENTIALS = re.compile(r"://[^/@\s]+@")
WINDOWS_EXTENDED_PREFIX = "\\\\?\\"



def is_pack_profile(name):
    """True for a namespaced profile, which always comes from a pack."""
    return NAMESPACE_SEPARATOR in name


def source_of_profile(name):
    """Source name of a namespaced profile."""
    return name.split(NAMESPACE_SEPARATOR, 1)[0]


# ---------------------------------------------------------------------------
# Manifest declarations
# ---------------------------------------------------------------------------

def parse_git_source(name, text, declared_ref):
    """Parse ``git+<url>``, with its ref after ``#`` or in ``ref``. Credentials never get in."""
    url, separator, fragment = text[len(GIT_SOURCE_PREFIX):].partition("#")
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as url_error:
        raise StateError(f"profile source '{name}' has an invalid URL") from url_error
    if parsed.scheme not in ALLOWED_GIT_SCHEMES or not parsed.hostname or not parsed.path.strip("/"):
        raise StateError(f"profile source '{name}' must use git+https:// or git+ssh:// with a repository path")
    if parsed.password or (parsed.username and parsed.scheme != SSH_URL_SCHEME) or parsed.query:
        raise StateError(
            f"profile source '{name}' has credentials or a query in its URL; "
            "remove them and use the Git authentication configured on the machine"
        )
    if separator and declared_ref is not None:
        raise StateError(f"profile source '{name}' declares its revision twice: use #<revision> in the URL or 'ref', not both")
    ref = declared_ref if declared_ref is not None else fragment
    if not isinstance(ref, str) or not SAFE_GIT_REF.fullmatch(ref):
        raise StateError(
            f"profile source '{name}' must declare a revision: "
            "'ref' with a branch or tag to follow, or #<full commit> at the end of its URL"
        )
    return {"name": name, "type": SOURCE_TYPE_GIT, "origin": url, "requestedRef": ref}


def parse_path_source(name, text, declared_ref):
    """Parse ``path:<relative path>``, resolved later from the consumer repository root."""
    if declared_ref is not None:
        raise StateError(f"profile source '{name}' is a local path, so it cannot declare 'ref'")
    path = text[len(PATH_SOURCE_PREFIX):]
    if not path or "\\" in path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise StateError(
            f"profile source '{name}' must use a path relative to the repository root with forward slashes; "
            "an absolute path would not exist on another machine"
        )
    return {"name": name, "type": SOURCE_TYPE_PATH, "origin": path, "requestedRef": None}


def parse_profile_sources(entries, manifest_path):
    """Validate the ``sources.packs`` of a manifest and return their declarations.

    The configuration schema already checked the fields and their types; this checks what
    a schema cannot: names, duplicates and the form of each source.
    """
    declarations = {}
    for entry in entries:
        name, text = entry["name"], entry["source"]
        if not KEBAB_CASE_NAME.fullmatch(name):
            raise StateError(f"{manifest_path} has a profile source with an invalid name '{name}'; use kebab-case")
        if name == GOLFO_KIT_SOURCE_NAME:
            raise StateError(f"{manifest_path} declares a profile source named '{name}', which is reserved for "
                             "golfo-kit itself; give the pack another name")
        if name in declarations:
            raise StateError(f"{manifest_path} declares the profile source '{name}' more than once")
        declared_ref = entry.get("ref")
        if text.startswith(GIT_SOURCE_PREFIX):
            declarations[name] = parse_git_source(name, text, declared_ref)
        elif text.startswith(PATH_SOURCE_PREFIX):
            declarations[name] = parse_path_source(name, text, declared_ref)
        else:
            raise StateError(f"profile source '{name}' must start with {GIT_SOURCE_PREFIX} or {PATH_SOURCE_PREFIX}")
        declarations[name]["updates"] = entry.get("updates")
    return [declarations[name] for name in sorted(declarations)]


def source_update_mode_is_ignored(configuration, declaration):
    """Why the update mode a source declares cannot apply, or None when it can.

    A machine override (environment or flags) beats every source. Otherwise the source
    mode is a project value of ``updates.mode``: it cannot loosen what the organization or
    the user set unless this machine approved the repository, nor change a locked key.
    """
    if not declaration or not declaration.get("updates"):
        return None
    if configuration.origin(UPDATES_MODE_KEY) in (LAYER_ENVIRONMENT, LAYER_FLAGS):
        return "the update mode of this run overrides it"
    return configuration.check_project_value(UPDATES_MODE_KEY, declaration["updates"])


def effective_update_mode(configuration, declaration=None):
    """Update mode in force: the machine override, then the source, then the configuration."""
    if declaration and declaration.get("updates") and source_update_mode_is_ignored(configuration, declaration) is None:
        return declaration["updates"]
    return configuration.value(UPDATES_MODE_KEY)


# ---------------------------------------------------------------------------
# Per-user cache
# ---------------------------------------------------------------------------

def long_path(path):
    """``path`` in the extended form Windows needs past 260 characters; unchanged elsewhere.

    The cache of a revision nests the whole repository under the commit, so deep files go past
    that limit there.
    """
    if os.name != "nt":
        return path
    absolute = os.path.abspath(path)
    return absolute if absolute.startswith(WINDOWS_EXTENDED_PREFIX) else WINDOWS_EXTENDED_PREFIX + absolute


def pack_cache_root():
    """Per-user directory of downloaded packs; nothing machine-specific lands in the project."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME") or os.path.expanduser("~"), ".cache")
    return os.path.join(base, "agent-ready-setup", "packs")


def origin_key(origin):
    """Short stable directory name of a repository."""
    return sha256_of_text(origin)[:16]


def cached_revision_directory(origin, commit):
    """Directory of one materialized revision, shared by every repository that pins it."""
    return os.path.join(pack_cache_root(), "trees", origin_key(origin), commit)


def cached_tree(origin, commit):
    """Materialized tree of a revision, or None when this machine does not have it."""
    tree = os.path.join(cached_revision_directory(origin, commit), MATERIALIZED_TREE_DIRECTORY)
    return tree if os.path.isdir(tree) else None


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------

def sanitized_git_error(completed):
    """Last part of a Git error, with any URL credentials removed."""
    text = completed.stderr.decode("utf-8", "replace").strip()
    return URL_CREDENTIALS.sub("://***@", text)[-GIT_ERROR_MAX_CHARACTERS:]


def run_git(source_name, arguments, input_bytes=None):
    """Run Git without prompts; authentication comes from what the machine already has."""
    environment = {key: value for key, value in os.environ.items() if key not in GIT_REPOSITORY_VARIABLES}
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return subprocess.run(
            ["git"] + arguments, input=input_bytes, capture_output=True,
            env=environment, timeout=GIT_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as git_error:
        raise ProfileError(f"profile source '{source_name}': git {arguments[0]} could not finish: {type(git_error).__name__}") from git_error


def resolve_remote_ref(declaration):
    """Commit a tag or branch points at right now; a tag wins over a branch of the same name."""
    name, origin, ref = declaration["name"], declaration["origin"], declaration["requestedRef"]
    peeled_tag, tag, branch = f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}", f"refs/heads/{ref}"
    completed = run_git(name, ["ls-remote", "--", origin, tag, peeled_tag, branch])
    if completed.returncode != 0:
        raise ProfileError(
            f"profile source '{name}': could not read {origin}; "
            f"check the Git authentication configured on this machine: {sanitized_git_error(completed)}"
        )
    remote_refs = {}
    for line in completed.stdout.decode("utf-8", "replace").splitlines():
        commit, _, remote_ref = line.partition("\t")
        remote_refs[remote_ref] = commit
    for candidate in (peeled_tag, tag, branch):
        if candidate in remote_refs:
            return remote_refs[candidate]
    raise ProfileError(f"profile source '{name}': {origin} has no tag or branch named '{ref}'")


def mirror_repository(origin):
    """The bare mirror that keeps the commits (and, for the signature check, the tags) of one origin."""
    return os.path.join(pack_cache_root(), "repos", origin_key(origin) + ".git")


def mirror_has_commit(name, repository, commit):
    return os.path.isdir(repository) and run_git(
        name, ["--git-dir", repository, "cat-file", "-e", f"{commit}^{{commit}}"]).returncode == 0


def fetch_signing_tags(name, origin, commit):
    """Bring into the mirror every annotated tag of the origin that points at the commit.

    Any of them can vouch for the commit (security.checks.signature), whatever ref the source
    follows: a branch whose tip is a signed release, or a full commit. Only those tags travel.
    """
    repository = mirror_repository(origin)
    if not os.path.isdir(repository):
        return
    completed = run_git(name, ["ls-remote", "--tags", "--", origin])
    if completed.returncode != 0:
        return
    refspecs = []
    for line in completed.stdout.decode("utf-8", "replace").splitlines():
        target, _, reference = line.partition("\t")
        if target != commit or not reference.endswith(PEELED_SUFFIX):
            continue
        tag = reference[len(TAG_REF_PREFIX):-len(PEELED_SUFFIX)]
        if reference.startswith(TAG_REF_PREFIX) and SAFE_GIT_REF.fullmatch(tag):
            refspecs.append(f"+{TAG_REF_PREFIX}{tag}:{MIRROR_TAG_NAMESPACE}{tag}")
    if refspecs:
        run_git(name, ["--git-dir", repository, "fetch", "--quiet", "--no-tags", "--depth", "1", "--", origin] + refspecs)


def fetch_commit(name, origin, commit):
    """Bring one commit into the bare mirror of its repository and return the mirror path."""
    repository = mirror_repository(origin)
    os.makedirs(os.path.dirname(repository), exist_ok=True)
    if not os.path.isdir(repository):
        # An empty template: this repository never runs a hook.
        completed = run_git(name, ["init", "--quiet", "--bare", "--template=", repository])
        if completed.returncode != 0:
            raise ProfileError(f"profile source '{name}': could not create its cache: {sanitized_git_error(completed)}")

    def has_commit():
        return mirror_has_commit(name, repository, commit)

    if has_commit():
        return repository
    run_git(name, ["--git-dir", repository, "fetch", "--quiet", "--no-tags", "--depth", "1", "--", origin, commit])
    if has_commit():
        return repository
    # Some servers only serve commits that a ref points at.
    completed = run_git(name, [
        "--git-dir", repository, "fetch", "--quiet", "--no-tags", "--", origin,
        "+refs/heads/*:refs/agent-ready/heads/*", f"+refs/tags/*:{MIRROR_TAG_NAMESPACE}*",
    ])
    if not has_commit():
        raise ProfileError(
            f"profile source '{name}': could not download commit {commit} from {origin}; "
            f"check the revision and the Git authentication configured on this machine: {sanitized_git_error(completed)}"
        )
    return repository


def is_writable_tree_path(path):
    """True for a tree path that stays inside the cache on every operating system."""
    if not is_contained_pattern(path) or ":" in path or any(ord(character) < 32 for character in path):
        return False
    return all(not segment.endswith((".", " ")) for segment in path.split("/"))


def read_blobs(name, repository, object_ids):
    """Raw blobs by object id. ``cat-file`` applies no filter, so content matches the commit."""
    if not object_ids:
        return {}
    completed = run_git(name, ["--git-dir", repository, "cat-file", "--batch"], input_bytes="\n".join(object_ids).encode() + b"\n")
    if completed.returncode != 0:
        raise ProfileError(f"profile source '{name}': could not read its objects: {sanitized_git_error(completed)}")
    blobs = {}
    position = 0
    for object_id in object_ids:
        header_end = completed.stdout.index(b"\n", position)
        size = int(completed.stdout[position:header_end].split()[2])
        blobs[object_id] = completed.stdout[header_end + 1:header_end + 1 + size]
        position = header_end + 1 + size + 1
    return blobs


def materialize_commit(name, origin, commit, repository):
    """Write a commit to the cache atomically; symlinks and unsafe names are only recorded."""
    revision_directory = cached_revision_directory(origin, commit)
    parent = os.path.dirname(revision_directory)
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".staging.", dir=parent)
    try:
        completed = run_git(name, ["--git-dir", repository, "ls-tree", "-r", "-z", "--full-tree", commit])
        if completed.returncode != 0:
            raise ProfileError(f"profile source '{name}': could not list commit {commit}: {sanitized_git_error(completed)}")
        regular_files = []
        excluded = []
        for record in completed.stdout.split(b"\0"):
            if not record:
                continue
            metadata, _, raw_path = record.partition(b"\t")
            mode, object_type, object_id = metadata.split()
            path = raw_path.decode("utf-8", "surrogateescape")
            if mode in REGULAR_FILE_MODES and is_writable_tree_path(path):
                regular_files.append((path, object_id.decode(), mode))
            elif object_type != SUBMODULE_OBJECT_TYPE:
                excluded.append(path)
        # On a case-insensitive file system one of these files would silently replace the other.
        folded_paths = [path.casefold() for path, _, _ in regular_files]
        excluded += [path for path, _, _ in regular_files if folded_paths.count(path.casefold()) > 1]
        regular_files = [entry for entry in regular_files if folded_paths.count(entry[0].casefold()) == 1]
        blobs = read_blobs(name, repository, sorted({object_id for _, object_id, _ in regular_files}))
        tree = os.path.join(staging, MATERIALIZED_TREE_DIRECTORY)
        os.makedirs(tree)
        for path, object_id, mode in regular_files:
            # The cache nests the whole repository under the commit: deep files pass the path
            # limit of Windows, which the extended form lifts.
            target = long_path(os.path.join(tree, *path.split("/")))
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as file_handle:
                    file_handle.write(blobs[object_id])
            except (OSError, ValueError):
                # A name this file system does not allow; it counts only if the pack consumes it.
                excluded.append(path)
                continue
            if mode == EXECUTABLE_FILE_MODE:
                os.chmod(target, EXECUTABLE_PERMISSIONS)
        with open(os.path.join(staging, EXCLUDED_PATHS_FILE_NAME), "w", encoding="utf-8") as file_handle:
            json.dump(sorted(excluded), file_handle)
        try:
            os.replace(staging, revision_directory)
        except OSError:
            # Another process materialized the same commit first; its copy is identical.
            if not cached_tree(origin, commit):
                raise
            shutil.rmtree(staging, ignore_errors=True)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def download_commit(name, origin, commit):
    """Make one commit available in the cache."""
    repository = fetch_commit(name, origin, commit)
    if not cached_tree(origin, commit):
        materialize_commit(name, origin, commit, repository)


def latest_commit_path(origin, ref):
    """Where this machine remembers the last commit seen for a ref; it is only a cache."""
    return os.path.join(pack_cache_root(), "latest", f"{origin_key(origin)}-{sha256_of_text(ref)[:16]}")


def record_latest_commit(origin, ref, commit):
    """Remember the commit a ref points at, so offline modes can report a pending update."""
    path = latest_commit_path(origin, ref)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(commit)


def last_known_commit(origin, ref):
    """Last commit seen for a ref on this machine, or None."""
    try:
        with open(latest_commit_path(origin, ref), encoding="utf-8") as file_handle:
            commit = file_handle.read().strip()
    except OSError:
        return None
    return commit if FULL_COMMIT.fullmatch(commit) else None


def revision_to_download(declaration, locked_entry, follow_ref):
    """Commit a Git source should use, using the network only to resolve a new or followed ref."""
    ref = declaration["requestedRef"]
    if FULL_COMMIT.fullmatch(ref):
        return ref
    if not follow_ref and locked_entry and locked_entry.get("requestedRef") == ref \
            and locked_entry.get("origin") == declaration["origin"] and locked_entry.get("resolvedCommit"):
        return locked_entry["resolvedCommit"]
    commit = resolve_remote_ref(declaration)
    record_latest_commit(declaration["origin"], ref, commit)
    return commit


def revision_of_ref(declaration, ref):
    """Commit of a full commit, tag or branch of a Git source, for an update that picks its revision."""
    if FULL_COMMIT.fullmatch(ref):
        return ref
    if not SAFE_GIT_REF.fullmatch(ref):
        raise ProfileError(f"profile source '{declaration['name']}': '{ref}' is not a full commit, a branch or a tag")
    commit = resolve_remote_ref(dict(declaration, requestedRef=ref))
    record_latest_commit(declaration["origin"], ref, commit)
    return commit


def require_local_source(declaration, project_root):
    """An apply needs every declared local source, also one without selected profiles."""
    root = os.path.join(project_root, *declaration["origin"].split("/"))
    if not os.path.isdir(root):
        raise ProfileError(f"profile source '{declaration['name']}': the path {declaration['origin']} does not exist from the repository root")


def download_declared_sources(declarations, locked_sources, update_names, configuration, project_root, to_ref=None,
                              from_lock=False, offline=False):
    """Resolve and download what an apply needs. Returns the commit adopted per Git source.

    A source in ``auto`` follows its ref; a pinned one keeps the lock until --update-source.
    ``to_ref`` (a tag, branch or full commit) is the revision the single source in
    ``update_names`` adopts instead of the latest of its ref. ``from_lock`` takes the commit
    of the lock for every source, whatever ref the manifest declares now, and fails for one the
    lock does not have from the same origin. ``offline`` downloads nothing: a missing revision fails.
    """
    known = {declaration["name"]: declaration for declaration in declarations}
    for name in update_names:
        if name not in known:
            raise ProfileError(f"--update-source {name}: the manifest does not declare that source")
        if known[name]["type"] == SOURCE_TYPE_GIT and FULL_COMMIT.fullmatch(known[name]["requestedRef"]):
            raise ProfileError(f"profile source '{name}' is pinned to a full commit; edit its revision in the manifest to change it")
    pins = {}
    for declaration in declarations:
        if declaration["type"] != SOURCE_TYPE_GIT:
            require_local_source(declaration, project_root)
            continue
        name = declaration["name"]
        follow_ref = name in update_names or effective_update_mode(configuration, declaration) == UPDATES_AUTO
        if from_lock:
            locked_entry = locked_sources.get(name) or {}
            if not locked_entry.get("resolvedCommit") or locked_entry.get("origin") != declaration["origin"]:
                raise ProfileError(f"--from-lock: profile source '{name}' has no revision in the lock from "
                                   f"{declaration['origin']}; apply without --from-lock to adopt it")
            commit = locked_entry["resolvedCommit"]
        elif to_ref and name in update_names:
            commit = revision_of_ref(declaration, to_ref)
        else:
            commit = revision_to_download(declaration, locked_sources.get(name), follow_ref)
        if not cached_tree(declaration["origin"], commit):
            if offline:
                raise ProfileError(f"profile source '{name}': revision {commit[:12]} is not in the cache of this machine "
                                   "and this run uses no network")
            download_commit(name, declaration["origin"], commit)
        if configuration.value(pack_tools.CHECK_SIGNATURE_KEY) and not offline:
            # A signed tag vouches for the commit it points at, as much as a signed commit does.
            fetch_signing_tags(name, declaration["origin"], commit)
        pins[name] = commit
    return pins


def refresh_declared_sources(declarations, locked_sources, with_tags=False):
    """Update the cache to know whether everything is current; the repository is not touched.

    Returns one message per source that could not be refreshed: the caller compares with
    what the cache already has and reports the limit instead of failing. ``with_tags`` also
    brings the tag of each ref, for the signature check.
    """
    failures = []
    for declaration in declarations:
        if declaration["type"] != SOURCE_TYPE_GIT:
            continue
        name, origin, ref = declaration["name"], declaration["origin"], declaration["requestedRef"]
        try:
            commits = {locked_revision(declaration, locked_sources.get(name))}
            if not FULL_COMMIT.fullmatch(ref):
                latest = resolve_remote_ref(declaration)
                record_latest_commit(origin, ref, latest)
                commits.add(latest)
            for commit in sorted(commit for commit in commits if commit):
                if not cached_tree(origin, commit):
                    download_commit(name, origin, commit)
            if with_tags:
                for commit in sorted(commit for commit in commits if commit):
                    fetch_signing_tags(name, origin, commit)
        except ProfileError as refresh_error:
            failures.append(str(refresh_error))
    return failures


def locked_revision(declaration, locked_entry):
    """Commit that needs no network to identify, or None when only a resolution can tell."""
    ref = declaration["requestedRef"]
    if FULL_COMMIT.fullmatch(ref):
        return ref
    if locked_entry and locked_entry.get("requestedRef") == ref and locked_entry.get("origin") == declaration["origin"]:
        return locked_entry.get("resolvedCommit")
    return None


# ---------------------------------------------------------------------------
# Locating a source without the network
# ---------------------------------------------------------------------------

def locate_source(declaration, locked_entry, project_root, update_mode, pinned_commit=None):
    """Where a declared source lives on this machine. It never uses the network.

    A source in ``auto`` uses the last commit seen for its ref, and a pinned one the
    lock. ``latestCommit`` lets a pinned source report that its ref moved.
    """
    located = dict(declaration, root=None, resolvedCommit=None, latestCommit=None, state=SOURCE_MISSING, reason=None, updates=update_mode)
    if declaration["type"] == SOURCE_TYPE_PATH:
        root = os.path.normpath(os.path.join(project_root, *declaration["origin"].split("/")))
        if os.path.isdir(root):
            located.update(root=root, state=SOURCE_AVAILABLE)
        else:
            located["reason"] = f"the path {declaration['origin']} does not exist from the repository root"
        return located
    locked_commit = locked_revision(declaration, locked_entry)
    latest_commit = None
    if not FULL_COMMIT.fullmatch(declaration["requestedRef"]):
        latest_commit = last_known_commit(declaration["origin"], declaration["requestedRef"])
    located["latestCommit"] = latest_commit
    preferred = (latest_commit, locked_commit) if update_mode == UPDATES_AUTO else (locked_commit, latest_commit)
    commit = pinned_commit or preferred[0] or preferred[1]
    if not commit:
        located["reason"] = (
            f"the ref '{declaration['requestedRef']}' is not resolved in the lockfile; "
            "resolving it needs the network, and only an apply uses it"
        )
        return located
    located["resolvedCommit"] = commit
    tree = cached_tree(declaration["origin"], commit)
    if tree:
        located.update(root=tree, state=SOURCE_AVAILABLE)
    else:
        located["reason"] = f"commit {commit[:12]} is not in the local cache"
    return located


# ---------------------------------------------------------------------------
# Pack catalogs
# ---------------------------------------------------------------------------

def excluded_paths(source):
    """Tree paths a Git source could not materialize as regular files."""
    if source["type"] != SOURCE_TYPE_GIT:
        return []
    path = os.path.join(cached_revision_directory(source["origin"], source["resolvedCommit"]), EXCLUDED_PATHS_FILE_NAME)
    try:
        with open(path, encoding="utf-8") as file_handle:
            return json.load(file_handle)
    except (OSError, ValueError) as read_error:
        raise ProfileError(f"profile source '{source['name']}': its cache is damaged; delete {cached_revision_directory(source['origin'], source['resolvedCommit'])}") from read_error


def validate_reference_list(source_name, profile_name, field, values):
    """``requires`` and ``conflicts`` name a Golfo profile or a namespaced profile."""
    if not isinstance(values, list):
        raise ProfileError(f"pack '{source_name}' profile '{profile_name}': '{field}' must be a list")
    for value in values:
        if not isinstance(value, str) or not (GOLFO_REFERENCE.fullmatch(value) or PACK_REFERENCE.fullmatch(value)):
            raise ProfileError(f"pack '{source_name}' profile '{profile_name}': invalid reference '{value}' in '{field}'; use <profile> or <source>/<profile>")


def validate_asset_tree(source, profile_name, asset_root, relative_root):
    """Assets stay inside the pack, in the allowed directories, without symlinks."""
    source_name, pack_root = source["name"], source["root"]
    real_pack = os.path.normcase(os.path.realpath(pack_root))
    real_assets = os.path.normcase(os.path.realpath(asset_root))
    try:
        is_inside = os.path.commonpath([real_pack, real_assets]) == real_pack
    except ValueError:
        is_inside = False
    if not is_inside:
        raise ProfileError(f"pack '{source_name}' profile '{profile_name}': its assets leave the pack through a symlink")
    for excluded in excluded_paths(source):
        if excluded == relative_root or excluded.startswith(relative_root + "/"):
            raise ProfileError(f"pack '{source_name}' profile '{profile_name}': {excluded} is a symlink or has a name that cannot be used")
    for directory, directory_names, file_names in os.walk(asset_root):
        for entry_name in directory_names + file_names:
            entry_path = os.path.join(directory, entry_name)
            relative_path = os.path.relpath(entry_path, asset_root).replace(os.sep, "/")
            if is_link(entry_path):
                raise ProfileError(f"pack '{source_name}' profile '{profile_name}': {relative_root}/{relative_path} is a symlink, which packs cannot use")
            if entry_name in file_names:
                if "/" not in relative_path or relative_path.split("/", 1)[0] not in PACK_ALLOWED_ASSET_DIRECTORIES:
                    allowed = ", ".join(PACK_ALLOWED_ASSET_DIRECTORIES)
                    raise ProfileError(f"pack '{source_name}' profile '{profile_name}': {relative_path} is outside the directories a pack can publish ({allowed})")
                block_destination = managed_blocks.destination_of(relative_path)
                if block_destination is not None:
                    # A block goes inside a file of the project (agent_ready_blocks.py).
                    managed_blocks.validate_destination(block_destination, f"{source_name}/{profile_name}")
                    continue
                if entry_name.casefold() in PACK_FORBIDDEN_ASSET_NAMES:
                    raise ProfileError(f"pack '{source_name}' profile '{profile_name}': {relative_path} would change the instructions of the project, which packs cannot do")


def validate_pack_profile(source, short_name, entry, golfo_profile_names):
    """One profile of a pack: the fields of a Golfo profile, limited to capabilities."""
    source_name = source["name"]
    if not isinstance(short_name, str) or not KEBAB_CASE_NAME.fullmatch(short_name):
        raise ProfileError(f"pack '{source_name}' has an invalid profile name '{short_name}'; use kebab-case")
    if short_name in golfo_profile_names:
        raise ProfileError(f"pack '{source_name}' cannot redefine the Golfo profile '{short_name}'; use another name")
    if not isinstance(entry, dict):
        raise ProfileError(f"pack '{source_name}' profile '{short_name}' must be an object")
    extra_keys = sorted(set(entry) - set(PACK_ALLOWED_PROFILE_KEYS))
    if extra_keys:
        raise ProfileError(f"pack '{source_name}' profile '{short_name}' has unknown keys: {', '.join(extra_keys)}")
    if entry.get("kind") not in (PACK_PROFILE_KIND, PACK_BUNDLE_KIND):
        raise ProfileError(f"pack '{source_name}' profile '{short_name}' must have kind '{PACK_PROFILE_KIND}' or "
                           f"'{PACK_BUNDLE_KIND}'; packs cannot add primary stacks")
    for field in ("requires", "conflicts", "defaults"):
        if field in entry:
            validate_reference_list(source_name, short_name, field, entry[field])
    tools = entry.get("tools", [])
    if not isinstance(tools, list) or any(tool not in KNOWN_TOOLS for tool in tools):
        raise ProfileError(f"pack '{source_name}' profile '{short_name}': 'tools' only accepts {', '.join(KNOWN_TOOLS)}")
    try:
        pack_tools.validate_declarations(entry, source["root"], is_contained_pattern)
    except pack_tools.DeclarationError as declaration_error:
        raise ProfileError(f"pack '{source_name}' profile '{short_name}': {declaration_error}") from declaration_error
    relative_root = entry.get("assets")
    if relative_root is None:
        return None
    if not isinstance(relative_root, str) or not is_contained_pattern(relative_root):
        raise ProfileError(f"pack '{source_name}' profile '{short_name}': 'assets' must be a relative directory inside the pack")
    asset_root = os.path.join(source["root"], *relative_root.split("/"))
    if not os.path.isdir(asset_root):
        raise ProfileError(f"pack '{source_name}' profile '{short_name}': assets directory {relative_root} is missing")
    validate_asset_tree(source, short_name, asset_root, relative_root)
    return asset_root


def load_pack_catalog(source, golfo_profile_names, engine_version=None):
    """Read and validate a pack. Returns its catalog digest, its namespaced profiles and what it declares.

    A pack that needs a newer engine (``minEngine``, ``schemaVersion``) stops here, before
    anything is written.
    """
    source_name = source["name"]
    catalog_path = os.path.join(source["root"], PACK_CATALOG_FILE_NAME)
    if os.path.islink(catalog_path) or not os.path.isfile(catalog_path):
        raise ProfileError(f"profile source '{source_name}' has no {PACK_CATALOG_FILE_NAME} at its root")
    try:
        catalog = read_json_file(catalog_path, "pack catalog")
    except StateError as caught_error:
        raise ProfileError(f"profile source '{source_name}': {caught_error}") from caught_error
    extra_keys = sorted(set(catalog) - set(PACK_ALLOWED_TOP_LEVEL_KEYS))
    if extra_keys:
        raise ProfileError(f"pack '{source_name}' has fields a pack cannot declare: {', '.join(extra_keys)}")
    label = f"pack '{source_name}'"
    require_engine(label, catalog, engine_version, PACK_SCHEMA_VERSION)
    if catalog.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise ProfileError(f"pack '{source_name}' must declare schemaVersion {PACK_SCHEMA_VERSION}")
    validate_compatibility(label, catalog)
    if catalog.get("name") != source_name:
        raise ProfileError(
            f"profile source '{source_name}' points to a pack named '{catalog.get('name')}'; "
            "the name in the manifest must match the catalog, because its profiles reference each other by it"
        )
    profiles = catalog.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ProfileError(f"pack '{source_name}' has no profiles")
    namespaced = {}
    asset_roots = {}
    for short_name, entry in sorted(profiles.items()):
        asset_root = validate_pack_profile(source, short_name, entry, golfo_profile_names)
        full_name = f"{source_name}{NAMESPACE_SEPARATOR}{short_name}"
        namespaced[full_name] = entry
        if asset_root:
            asset_roots[full_name] = asset_root
    try:
        validate_catalog_detection(namespaced)
    except DetectionSchemaError as caught_error:
        raise ProfileError(f"pack '{source_name}': {caught_error}") from caught_error
    return {"digest": sha256_of_file(catalog_path), "profiles": namespaced, "assetRoots": asset_roots,
            "version": catalog.get("version"), "changes": catalog.get("changes", [])}
