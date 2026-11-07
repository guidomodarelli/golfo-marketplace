"""External profile packs for agent-ready-setup.

A pack is a Git repository or a local directory with a catalog
(``agent-ready-pack.json``) and assets. This module parses the sources a manifest
declares, downloads pinned revisions into a per-user cache and validates catalogs.
Only ``download_declared_sources`` uses the network. Loading a pack reads files and
nothing else: no script of a pack ever runs. The contract is documented in
``references/profiles-and-lockfile.md``.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse

from agent_ready_common import ProfileError, StateError, read_json_file, sha256_of_file, sha256_of_text
from agent_ready_detection import (
    DetectionSchemaError,
    is_contained_pattern,
    validate_catalog_detection,
)

PACK_CATALOG_FILE_NAME = "agent-ready-pack.json"
PACK_SCHEMA_VERSION = 1
PACK_ALLOWED_TOP_LEVEL_KEYS = ("schemaVersion", "name", "profiles")
PACK_ALLOWED_PROFILE_KEYS = ("kind", "description", "assets", "requires", "conflicts", "tools", "detect")
PACK_PROFILE_KIND = "capability"
# Tools the engine knows how to install; a pack cannot bring its own installer.
KNOWN_TOOLS = ("browser",)
# Packs add rules, skills, agents and commands. Hooks, settings, MCP registration and
# the AGENTS.md template stay under the control of the skill and the project.
PACK_ALLOWED_ASSET_DIRECTORIES = ("rules", "skills", "agents", "commands")
PACK_FORBIDDEN_ASSET_NAMES = ("agents.md", "claude.md")

NAMESPACE_SEPARATOR = "/"
KEBAB_CASE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
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
BACKGROUND_FETCH_MAX_ATTEMPTS = 3
BACKGROUND_FETCH_LOCK_MAX_AGE_SECONDS = 3600


def is_pack_profile(name):
    """True for a namespaced profile, which always comes from a pack."""
    return NAMESPACE_SEPARATOR in name


def source_of_profile(name):
    """Source name of a namespaced profile."""
    return name.split(NAMESPACE_SEPARATOR, 1)[0]


# ---------------------------------------------------------------------------
# Manifest declarations
# ---------------------------------------------------------------------------

def parse_git_source(name, text):
    """Parse ``git+<url>#<ref>``. Credentials never get into the manifest or the lock."""
    url, separator, ref = text[len(GIT_SOURCE_PREFIX):].partition("#")
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
    if not separator or not SAFE_GIT_REF.fullmatch(ref):
        raise StateError(f"profile source '{name}' must pin a revision: end its URL with #<full commit>, #<tag> or #<branch>")
    return {"name": name, "type": SOURCE_TYPE_GIT, "origin": url, "requestedRef": ref}


def parse_path_source(name, text):
    """Parse ``path:<relative path>``, resolved later from the consumer repository root."""
    path = text[len(PATH_SOURCE_PREFIX):]
    if not path or "\\" in path or path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise StateError(
            f"profile source '{name}' must use a path relative to the repository root with forward slashes; "
            "an absolute path would not exist on another machine"
        )
    return {"name": name, "type": SOURCE_TYPE_PATH, "origin": path, "requestedRef": None}


def parse_profile_sources(manifest, manifest_path):
    """Validate the ``profileSources`` of a manifest and return their declarations."""
    entries = manifest.get("profileSources", [])
    if not isinstance(entries, list):
        raise StateError(f"{manifest_path} 'profileSources' must be a list")
    declarations = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"name", "source"}:
            raise StateError(f"{manifest_path} 'profileSources' entries must have exactly 'name' and 'source'")
        name, text = entry["name"], entry["source"]
        if not isinstance(name, str) or not KEBAB_CASE_NAME.fullmatch(name) or not isinstance(text, str):
            raise StateError(f"{manifest_path} has a profile source with an invalid name; use kebab-case")
        if name in declarations:
            raise StateError(f"{manifest_path} declares the profile source '{name}' more than once")
        if text.startswith(GIT_SOURCE_PREFIX):
            declarations[name] = parse_git_source(name, text)
        elif text.startswith(PATH_SOURCE_PREFIX):
            declarations[name] = parse_path_source(name, text)
        else:
            raise StateError(f"profile source '{name}' must start with {GIT_SOURCE_PREFIX} or {PATH_SOURCE_PREFIX}")
    return [declarations[name] for name in sorted(declarations)]


# ---------------------------------------------------------------------------
# Per-user cache
# ---------------------------------------------------------------------------

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


def fetch_commit(name, origin, commit):
    """Bring one commit into the bare mirror of its repository and return the mirror path."""
    repository = os.path.join(pack_cache_root(), "repos", origin_key(origin) + ".git")
    os.makedirs(os.path.dirname(repository), exist_ok=True)
    if not os.path.isdir(repository):
        # An empty template: this repository never runs a hook.
        completed = run_git(name, ["init", "--quiet", "--bare", "--template=", repository])
        if completed.returncode != 0:
            raise ProfileError(f"profile source '{name}': could not create its cache: {sanitized_git_error(completed)}")

    def has_commit():
        return run_git(name, ["--git-dir", repository, "cat-file", "-e", f"{commit}^{{commit}}"]).returncode == 0

    if has_commit():
        return repository
    run_git(name, ["--git-dir", repository, "fetch", "--quiet", "--no-tags", "--depth", "1", "--", origin, commit])
    if has_commit():
        return repository
    # Some servers only serve commits that a ref points at.
    completed = run_git(name, [
        "--git-dir", repository, "fetch", "--quiet", "--no-tags", "--", origin,
        "+refs/heads/*:refs/agent-ready/heads/*", "+refs/tags/*:refs/agent-ready/tags/*",
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
        blobs = read_blobs(name, repository, sorted({object_id for _, object_id, _ in regular_files}))
        tree = os.path.join(staging, MATERIALIZED_TREE_DIRECTORY)
        os.makedirs(tree)
        for path, object_id, mode in regular_files:
            target = os.path.join(tree, *path.split("/"))
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


def revision_to_download(declaration, locked_entry, update_requested):
    """Commit a Git source should use, using the network only to resolve a new or updated ref."""
    ref = declaration["requestedRef"]
    if FULL_COMMIT.fullmatch(ref):
        if update_requested:
            raise ProfileError(
                f"profile source '{declaration['name']}' is pinned to a full commit; "
                "edit its revision in the manifest to change it"
            )
        return ref
    if not update_requested and locked_entry and locked_entry.get("requestedRef") == ref \
            and locked_entry.get("origin") == declaration["origin"] and locked_entry.get("resolvedCommit"):
        return locked_entry["resolvedCommit"]
    return resolve_remote_ref(declaration)


def download_declared_sources(declarations, locked_sources, update_names):
    """Resolve and download what an apply needs. Returns the commit adopted per Git source."""
    known = {declaration["name"] for declaration in declarations}
    for name in update_names:
        if name not in known:
            raise ProfileError(f"--update-source {name}: the manifest does not declare that source")
    pins = {}
    for declaration in declarations:
        if declaration["type"] != SOURCE_TYPE_GIT:
            continue
        name = declaration["name"]
        commit = revision_to_download(declaration, locked_sources.get(name), name in update_names)
        if not cached_tree(declaration["origin"], commit):
            download_commit(name, declaration["origin"], commit)
        pins[name] = commit
    return pins


def locked_revision(declaration, locked_entry):
    """Commit that needs no network to identify, or None when only a resolution can tell."""
    ref = declaration["requestedRef"]
    if FULL_COMMIT.fullmatch(ref):
        return ref
    if locked_entry and locked_entry.get("requestedRef") == ref and locked_entry.get("origin") == declaration["origin"]:
        return locked_entry.get("resolvedCommit")
    return None


def read_attempts(attempts_path):
    """Failed background downloads of one revision; an unreadable count starts over."""
    try:
        with open(attempts_path, encoding="utf-8") as attempts_file:
            return int(attempts_file.read().strip() or 0)
    except (OSError, ValueError):
        return 0


def download_locked_sources_in_background(declarations, locked_sources):
    """Download revisions already pinned, for a machine that has never seen them.

    SessionStart runs this detached. It never resolves a ref and never adopts anything:
    a later session projects the locked revision once it is in the cache. Failures
    stop after a few attempts, so an unreachable source does not retry forever.
    """
    lock_path = os.path.join(pack_cache_root(), "background-fetch.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    try:
        if time.time() - os.path.getmtime(lock_path) > BACKGROUND_FETCH_LOCK_MAX_AGE_SECONDS:
            os.rmdir(lock_path)
    except OSError:
        pass
    try:
        os.mkdir(lock_path)
    except OSError:
        return []
    failures = []
    try:
        for declaration in declarations:
            if declaration["type"] != SOURCE_TYPE_GIT:
                continue
            name, origin = declaration["name"], declaration["origin"]
            commit = locked_revision(declaration, locked_sources.get(name))
            if not commit or cached_tree(origin, commit):
                continue
            attempts_path = os.path.join(pack_cache_root(), "attempts", f"{origin_key(origin)}-{commit}")
            attempts = read_attempts(attempts_path)
            if attempts >= BACKGROUND_FETCH_MAX_ATTEMPTS:
                failures.append(f"profile source '{name}': automatic download stopped after {attempts} attempts")
                continue
            try:
                download_commit(name, origin, commit)
            except ProfileError as download_error:
                failures.append(str(download_error))
                os.makedirs(os.path.dirname(attempts_path), exist_ok=True)
                with open(attempts_path, "w", encoding="utf-8") as attempts_file:
                    attempts_file.write(str(attempts + 1))
            else:
                if os.path.isfile(attempts_path):
                    os.unlink(attempts_path)
    finally:
        os.rmdir(lock_path)
    return failures


# ---------------------------------------------------------------------------
# Locating a source without the network
# ---------------------------------------------------------------------------

def locate_source(declaration, locked_entry, project_root, pinned_commit=None):
    """Where a declared source lives on this machine. It never uses the network."""
    located = dict(declaration, root=None, resolvedCommit=None, state=SOURCE_MISSING, reason=None)
    if declaration["type"] == SOURCE_TYPE_PATH:
        root = os.path.normpath(os.path.join(project_root, *declaration["origin"].split("/")))
        if os.path.isdir(root):
            located.update(root=root, state=SOURCE_AVAILABLE)
        else:
            located["reason"] = f"the path {declaration['origin']} does not exist from the repository root"
        return located
    commit = pinned_commit or locked_revision(declaration, locked_entry)
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
        located["reason"] = f"commit {commit[:12]} is not in the local cache; only an apply downloads it"
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


def is_link(path):
    """True for a symlink or, on Windows, a directory junction."""
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


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
    if entry.get("kind") != PACK_PROFILE_KIND:
        raise ProfileError(f"pack '{source_name}' profile '{short_name}' must have kind '{PACK_PROFILE_KIND}'; packs cannot add primary stacks")
    for field in ("requires", "conflicts"):
        if field in entry:
            validate_reference_list(source_name, short_name, field, entry[field])
    tools = entry.get("tools", [])
    if not isinstance(tools, list) or any(tool not in KNOWN_TOOLS for tool in tools):
        raise ProfileError(f"pack '{source_name}' profile '{short_name}': 'tools' only accepts {', '.join(KNOWN_TOOLS)}")
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


def load_pack_catalog(source, golfo_profile_names):
    """Read and validate a pack. Returns its catalog digest and its namespaced profiles."""
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
    if catalog.get("schemaVersion") != PACK_SCHEMA_VERSION:
        raise ProfileError(f"pack '{source_name}' must declare schemaVersion {PACK_SCHEMA_VERSION}")
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
    return {"digest": sha256_of_file(catalog_path), "profiles": namespaced, "assetRoots": asset_roots}
