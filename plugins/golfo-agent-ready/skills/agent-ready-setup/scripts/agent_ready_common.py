"""Errors and file helpers shared by the agent-ready-setup state modules."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

LOCK_MAX_AGE_SECONDS = 3600
# What local_state says of a project path that is not a regular file.
LOCAL_ABSENT = "absent"
LOCAL_SYMLINK = "symlink"
LOCAL_NOT_A_FILE = "not-a-file"
# The names of packs, of their profiles and of nested targets.
KEBAB_CASE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ProfileError(Exception):
    """Raised when profiles cannot be resolved or composed without ambiguity."""


class IncompleteEvaluationError(ProfileError):
    """Raised when a read-only evaluation lacks a source it needs; it validates nothing."""


class StateError(Exception):
    """Raised when the manifest or the lockfile cannot be read safely."""


def sha256_of_file(path):
    """Return the hex sha256 of a file with CRLF line endings normalized to LF.

    A checkout with core.autocrlf rewrites every line ending without anyone
    editing the file, so hashing raw bytes would report the whole tree as locally
    modified. A file with LF endings hashes to its plain sha256.
    """
    with open(path, "rb") as file_handle:
        content = file_handle.read()
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def skill_cache_directory(*parts):
    """A directory of agent-ready-setup in the per-user cache (XDG_CACHE_HOME, else ~/.cache)."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME") or os.path.expanduser("~"), ".cache")
    return os.path.join(base, "agent-ready-setup", *parts)


def sha256_of_text(text):
    """Return the hex sha256 of UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json_file(path, description):
    """Read a JSON object, raising StateError with the path on failure."""
    try:
        with open(path, encoding="utf-8") as file_handle:
            content = json.load(file_handle)
    except (OSError, ValueError) as caught_error:
        raise StateError(f"could not read {description} {path}: {caught_error}") from caught_error
    if not isinstance(content, dict):
        raise StateError(f"{description} {path} must contain a JSON object")
    return content


def acquire_directory_lock(lock_path):
    """Take a lock between processes; one left behind by a dead process expires."""
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    try:
        if time.time() - os.path.getmtime(lock_path) > LOCK_MAX_AGE_SECONDS:
            os.rmdir(lock_path)
    except OSError:
        pass
    try:
        os.mkdir(lock_path)
    except OSError:
        return False
    return True


def is_link(path):
    """True for a symlink or, on Windows, a directory junction."""
    return os.path.islink(path) or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


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


# Top-level directories of a root of content (the base, or the assets of a profile of the official
# content or of a pack) that only check that content: the evals of its rules, which run-evals reads
# from <root>/evals/. The engine accepts them and never projects them. A skill keeps its own evals/:
# those are part of the skill and are projected with it.
CONTENT_UNPROJECTED_DIRECTORIES = ("evals",)


def is_unprojected_content(relative_path):
    """Whether a path relative to a root of content lies in one of its CONTENT_UNPROJECTED_DIRECTORIES."""
    return "/" in relative_path and relative_path.split("/", 1)[0] in CONTENT_UNPROJECTED_DIRECTORIES


def walk_content_files(root):
    """Like walk_files, for a root of content: without its top-level CONTENT_UNPROJECTED_DIRECTORIES."""
    return [(relative_path, absolute_path) for relative_path, absolute_path in walk_files(root)
            if not is_unprojected_content(relative_path)]


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
        if os.path.isfile(path):
            # Replacing a file keeps its mode: an executable script stays executable.
            os.chmod(temporary_path, os.stat(path).st_mode & 0o7777)
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


def plugin_version(skill_dir):
    """Version of the plugin manifest that ships the skill, if present.

    The skill can be reached through a symlink (``~/.claude/skills/agent-ready-setup`` pointing at a
    checkout, as Local Testing in the repository AGENTS.md sets it up): the manifest is next to its target.
    """
    plugin_root = os.path.dirname(os.path.dirname(os.path.realpath(skill_dir)))
    for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "plugin.json"):
        manifest_path = os.path.join(plugin_root, manifest)
        if os.path.isfile(manifest_path):
            try:
                return read_json_file(manifest_path, "plugin manifest").get("version")
            except StateError:
                return None
    return None


def bash_executable():
    """Bash from PATH; Windows process creation would find the WSL launcher in System32 first."""
    return shutil.which("bash") or "bash"


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


def run_quiet(command, cwd=None):
    """Run a read-only command and return its UTF-8 stdout, or None when it fails."""
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


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


def text_bytes(text):
    """Size of a text in UTF-8, the encoding every instruction file is written in."""
    return len(text.encode("utf-8"))


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
