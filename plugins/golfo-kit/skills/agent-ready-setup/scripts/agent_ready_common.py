"""Errors and file helpers shared by the agent-ready-setup state modules."""

import hashlib
import json
import os
import time

LOCK_MAX_AGE_SECONDS = 3600


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
