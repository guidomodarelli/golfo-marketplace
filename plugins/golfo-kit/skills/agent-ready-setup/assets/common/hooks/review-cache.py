#!/usr/bin/env python3
"""Cache of the AI reviews of agent-ready-setup, one entry per reviewed unit.

A unit is what one review judges: AGENTS.md against its rules, or one pair of rules or
skills. Its key hashes everything that can change the verdict: the content of each file
with line endings normalized, the check and its version, the provider and the model, and
the engine version. An edit only invalidates the units it takes part in, and each entry
keeps its verdict and findings, so status shows the last result without the provider.

The cache is local and never reaches Git: it lives in the info directory that every
worktree of the repository shares. The session hooks load this file from .agents/hooks/
and the engine from its own skill, so both use one implementation; the Bash scripts use
its command line (enabled, lookup, store).
"""

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

SCHEMA_VERSION = 1
CACHE_DIRECTORY = "agent-ready"
CACHE_FILE_NAME = "reviews.json"
LOCK_DIRECTORY_NAME = "reviews.lock"
# Same path the apply writes; its generator version is the engine version of every key.
LOCK_FILE_RELATIVE_PATH = ".agents/agent-ready.lock.json"
LOCK_WAIT_SECONDS = 30
# A lock older than this belongs to a process that died; writes take milliseconds.
LOCK_STALE_SECONDS = 120
LOCK_POLL_SECONDS = 0.05
REPLACE_ATTEMPTS = 20
SECONDS_PER_HOUR = 3600
DEFAULT_SETTINGS = {"enabled": True, "cache": True, "ttl": None}
VERDICT_CONSISTENT = "consistent"
VERDICT_FINDINGS = "findings"
# Exit status of `lookup` when the unit has no current entry.
MISS_STATUS = 3


class CacheLockTimeout(RuntimeError):
    """Another process held the cache lock for longer than a write takes."""


def normalized_text(path):
    """The text a review saw: UTF-8 with LF line endings, so a CRLF checkout is the same unit."""
    with open(path, "rb") as file_handle:
        return file_handle.read().decode("utf-8", errors="replace").replace("\r\n", "\n")


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unit_id(check, names):
    """The unit is the check and the set of files it judges, whatever their order."""
    return f"{check}:" + "|".join(sorted(names))


def unit_key(check, version, provider, model, engine, contents):
    """Hash of everything that can change the verdict of a unit; ``contents`` maps names to text."""
    digest = hashlib.sha256()
    for part in (check, str(version), provider or "", model or "", engine or ""):
        digest.update(part.encode("utf-8") + b"\0")
    for name in sorted(contents):
        digest.update(name.encode("utf-8") + b"\0" + text_hash(contents[name]).encode("ascii") + b"\0")
    return digest.hexdigest()


def engine_version(project_root):
    """The golfo-kit version that last applied the repository, or none before the first apply."""
    try:
        with open(os.path.join(project_root, LOCK_FILE_RELATIVE_PATH), encoding="utf-8") as file_handle:
            return str(json.load(file_handle).get("generator", {}).get("version") or "none")
    except (OSError, ValueError, AttributeError):
        return "none"


def cache_path(project_root):
    """reviews.json in the info directory shared by the worktrees, or None outside Git."""
    try:
        completed = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=project_root, capture_output=True,
                                   encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    common = completed.stdout.strip()
    if completed.returncode != 0 or not common:
        return None
    return os.path.join(os.path.normpath(os.path.join(project_root, common)), "info", CACHE_DIRECTORY, CACHE_FILE_NAME)


def now_text():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_seconds(checked_at):
    try:
        checked = datetime.datetime.strptime(checked_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None
    return (datetime.datetime.now(datetime.timezone.utc) - checked).total_seconds()


class ReviewCache:
    """Reads and writes the review cache of one repository."""

    def __init__(self, project_root):
        self.project_root = project_root
        self.path = cache_path(project_root)

    def read(self):
        """The whole cache; an absent or unreadable file is an empty one."""
        empty = {"schemaVersion": SCHEMA_VERSION, "settings": dict(DEFAULT_SETTINGS), "entries": {}}
        if not self.path:
            return empty
        try:
            with open(self.path, encoding="utf-8") as file_handle:
                data = json.load(file_handle)
        except (OSError, ValueError):
            return empty
        if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION or not isinstance(data.get("entries"), dict):
            return empty
        data["settings"] = {**DEFAULT_SETTINGS, **(data.get("settings") if isinstance(data.get("settings"), dict) else {})}
        return data

    def settings(self):
        """reviews.enabled, reviews.cache and reviews.ttl as the last apply resolved them."""
        return self.read()["settings"]

    def lookup(self, unit, key, recheck=False):
        """The entry of a unit when its key is current, the cache is on and it has not expired."""
        data = self.read()
        settings = data["settings"]
        if recheck or not settings.get("cache", True):
            return None
        entry = data["entries"].get(unit)
        if not isinstance(entry, dict) or entry.get("key") != key:
            return None
        ttl = settings.get("ttl")
        age = age_seconds(entry.get("checkedAt"))
        if ttl and (age is None or age > ttl * SECONDS_PER_HOUR):
            return None
        return entry

    def store(self, records):
        """Save ``{unit: entry}``; other entries of files that no longer exist go away in the same write."""
        if not self.path or not self.settings().get("cache", True):
            return
        with self.locked():
            data = self.read()
            for unit, entry in records.items():
                data["entries"][unit] = dict(entry, checkedAt=entry.get("checkedAt") or now_text())
            # What was just reviewed is current, even when a reviewed rule comes from the
            # template and the repository has no copy of it yet.
            self.prune(data, keep=records)
            self.write(data)

    def write_settings(self, enabled, cache, ttl):
        """Record the effective reviews options, so the hooks honor them without the engine."""
        if not self.path:
            return
        settings = {"enabled": bool(enabled), "cache": bool(cache), "ttl": ttl}
        if self.read()["settings"] == settings:
            return
        with self.locked():
            data = self.read()
            data["settings"] = settings
            self.write(data)

    def prune(self, data, keep=()):
        """Drop entries that name a project file that is gone, except the units in ``keep``."""
        for unit, entry in list(data["entries"].items()):
            if unit in keep:
                continue
            names = entry.get("files", {}) if isinstance(entry, dict) else {}
            if any(not os.path.isabs(name) and not os.path.exists(os.path.join(self.project_root, name)) for name in names):
                del data["entries"][unit]

    def write(self, data):
        """Replace the file atomically; Windows refuses the replace while a reader has it open, so retry."""
        directory = os.path.dirname(self.path)
        file_descriptor, temporary_path = tempfile.mkstemp(prefix=".reviews.", dir=directory)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as file_handle:
                json.dump(data, file_handle, indent=2, sort_keys=True, ensure_ascii=False)
                file_handle.write("\n")
            for attempt in range(REPLACE_ATTEMPTS):
                try:
                    os.replace(temporary_path, self.path)
                    return
                except PermissionError:
                    if attempt == REPLACE_ATTEMPTS - 1:
                        raise
                    time.sleep(LOCK_POLL_SECONDS)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @contextlib.contextmanager
    def locked(self):
        """Hold the lock between processes; one left by a dead process expires."""
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        lock = os.path.join(directory, LOCK_DIRECTORY_NAME)
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                os.mkdir(lock)
                break
            # Windows answers access denied while another process is removing the same directory.
            except (FileExistsError, PermissionError):
                try:
                    if time.time() - os.path.getmtime(lock) > LOCK_STALE_SECONDS:
                        os.rmdir(lock)
                        continue
                except OSError:
                    continue
                if time.monotonic() > deadline:
                    raise CacheLockTimeout(f"{lock} has been held for more than {LOCK_WAIT_SECONDS} seconds") from None
                time.sleep(LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            try:
                os.rmdir(lock)
            except OSError:
                pass


def entry_for(check, version, provider, model, engine, contents, key, verdict, findings, extra=None):
    """A cache entry: what was reviewed, with which provider and engine, and what it found."""
    entry = {
        "key": key,
        "check": check,
        "checkVersion": version,
        "provider": provider,
        "model": model,
        "engine": engine,
        "files": {name: text_hash(text) for name, text in sorted(contents.items())},
        "verdict": verdict,
        "findings": findings,
    }
    if extra:
        entry.update(extra)
    return entry


# ---------------------------------------------------------------------------
# Command line for the Bash scripts
# ---------------------------------------------------------------------------

def unit_arguments(arguments):
    """(unit, key, contents, engine) of the files given with --file NAME PATH."""
    contents = {name: normalized_text(path) for name, path in arguments.file}
    engine = engine_version(arguments.project)
    key = unit_key(arguments.check, arguments.version, arguments.provider, arguments.model, engine, contents)
    return unit_id(arguments.check, contents), key, contents, engine


def command_lookup(arguments):
    unit, key, _, _ = unit_arguments(arguments)
    entry = ReviewCache(arguments.project).lookup(unit, key, recheck=arguments.recheck)
    if entry is None:
        return MISS_STATUS
    sys.stdout.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 0


def command_store(arguments):
    unit, key, contents, engine = unit_arguments(arguments)
    with open(arguments.result, encoding="utf-8") as file_handle:
        result = json.load(file_handle)
    findings = result.get("findings", [])
    extra = {name: value for name, value in result.items() if name not in ("findings", "verdict")}
    verdict = VERDICT_FINDINGS if findings else VERDICT_CONSISTENT
    entry = entry_for(arguments.check, arguments.version, arguments.provider, arguments.model, engine, contents, key,
                      verdict, findings, extra)
    try:
        ReviewCache(arguments.project).store({unit: entry})
    except (OSError, CacheLockTimeout) as caught_error:
        # A review that could not be cached runs again next time; it never fails the caller.
        sys.stderr.write(f"WARNING: the review result was not cached: {caught_error}\n")
    return 0


def command_enabled(arguments):
    """Exit 0 while the AI reviews are on, 1 when reviews.enabled is false."""
    return 0 if ReviewCache(arguments.project).settings().get("enabled", True) else 1


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    enabled = subparsers.add_parser("enabled", help="exit 0 while the AI reviews are on")
    enabled.add_argument("--project", default=".")
    enabled.set_defaults(handler=command_enabled)
    for name, handler in (("lookup", command_lookup), ("store", command_store)):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--project", default=".")
        subparser.add_argument("--check", required=True, help="id of the review, such as instructions")
        subparser.add_argument("--version", required=True, type=int, help="version of its prompt")
        subparser.add_argument("--provider", required=True)
        subparser.add_argument("--model", default="")
        subparser.add_argument("--file", action="append", nargs=2, default=[], metavar=("NAME", "PATH"),
                               help="name and path of a reviewed file; repeatable")
        if name == "lookup":
            subparser.add_argument("--recheck", action="store_true", help="ignore the cached entry")
        else:
            subparser.add_argument("--result", required=True, help="JSON with findings and any extra fields to keep")
        subparser.set_defaults(handler=handler)
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    arguments.project = os.path.abspath(arguments.project)
    return arguments.handler(arguments)


if __name__ == "__main__":
    sys.exit(main())
