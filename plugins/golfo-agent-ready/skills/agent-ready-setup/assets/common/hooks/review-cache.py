#!/usr/bin/env python3
"""Cache of the AI reviews of agent-ready-setup, one entry per reviewed unit.

A unit is what one review judges: AGENTS.md against its rules, or one pair of rules or
skills. Its key hashes everything that can change the verdict: the content of each file
with line endings normalized, the check and its version, the provider and the model, and
the engine version. An edit only invalidates the units it takes part in, and each entry
keeps its verdict and findings, so status shows the last result without the provider.

The cache is local and never reaches Git: it lives in the info directory that every
worktree of the repository shares. The decisions of the team about findings do reach
Git, in .agents/agent-ready.reviews.json: each finding has a stable id, and an accepted or
dismissed one stays quiet while its decision holds. The session hooks load this file from
.agents/hooks/ and the engine from its own skill, so both use one implementation; the Bash
scripts use its command line (enabled, defaults, lookup, store, report).
"""

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

SCHEMA_VERSION = 2
CACHE_DIRECTORY = "agent-ready"
CACHE_FILE_NAME = "reviews.json"
LOCK_DIRECTORY_NAME = "reviews.lock"
# Same path the apply writes; its generator version is the engine version of every key.
LOCK_FILE_RELATIVE_PATH = ".agents/agent-ready.lock.json"
LOCK_WAIT_SECONDS = 30
# A lock older than this belongs to a process that died; writes take milliseconds.
LOCK_STALE_SECONDS = 120
LOCK_POLL_SECONDS = 0.05
# Access denied with no lock present for this long means the directory is not writable.
LOCK_PERMISSION_SECONDS = 2
REPLACE_ATTEMPTS = 20
SECONDS_PER_HOUR = 3600
DEFAULT_SETTINGS = {"enabled": True, "cache": True, "ttl": None, "commit": False, "redundancy": True}
# With reviews.commit, every result is also saved here, to be committed, so CI and the team skip
# the reviews whose key matches. Anyone can edit a versioned file: see trusted_shared_entry().
SHARED_CACHE_RELATIVE_PATH = ".agents/agent-ready.review-cache.json"
SHARED_CACHE_LOCK_RELATIVE_PATH = ".agents/agent-ready.review-cache.lock"
SOURCE_SHARED = "shared"
# Model and reasoning effort of every AI review, the only copy: the hooks read it from here and the
# Bash scripts with `defaults`. AGENT_READY_SETUP_MERGE_MODEL and
# AGENT_READY_SETUP_MERGE_REASONING_EFFORT change them for the review of AGENTS.md.
PROVIDER_DEFAULTS = {
    "claude": {"model": "claude-sonnet-5-5", "effort": "medium"},
    "codex": {"model": "gpt-6-luna", "effort": "high"},
}
VERDICT_CONSISTENT = "consistent"
VERDICT_FINDINGS = "findings"
# Exit status of `lookup` when the unit has no current entry.
MISS_STATUS = 3
# Decisions of the team about findings: versioned with the repository, unlike the cache.
DECISIONS_RELATIVE_PATH = ".agents/agent-ready.reviews.json"
DECISIONS_SCHEMA_VERSION = 1
DECISION_ACCEPTED = "accepted"
DECISION_DISMISSED = "dismissed"
DECISION_KINDS = (DECISION_ACCEPTED, DECISION_DISMISSED)
# content: valid while the files of the finding stay as they were; pair: until someone removes it.
SCOPE_CONTENT = "content"
SCOPE_PAIR = "pair"
DECISION_SCOPES = (SCOPE_CONTENT, SCOPE_PAIR)
# A finding nobody decided on, and one whose content decision is older than its files.
STATUS_OPEN = "open"
STATUS_TO_CONFIRM = "to-confirm"
# Two rules that ask for the same thing in other words (reviews.redundancy.enabled): a warning, never a
# failure, so it neither stops an apply under conflicts.block nor fails agent-ready check.
KIND_REDUNDANCY = "redundancy"
FINDING_ID_LENGTH = 10


class CacheLockTimeout(RuntimeError):
    """Another process held the cache lock for longer than a write takes."""


class DecisionsError(ValueError):
    """The decisions file exists but is not one this version can read; nothing overwrites it."""


def normalized_text(path):
    """The text a review saw: UTF-8 with LF line endings, so a CRLF checkout is the same unit."""
    with open(path, "rb") as file_handle:
        return file_handle.read().decode("utf-8", errors="replace").replace("\r\n", "\n")


# A rule file with atomic rules (#168, references/atomic-rules.md) is reviewed rule by rule: each rule
# is a document of its own, named <file>#<id>, with the titles and paragraphs of its sections, which say
# where it applies; what the file says outside its rules is the document <file>#. Changing one rule only
# invalidates the pairs of that rule, and changing a title or a paragraph the pairs of the rules under it.
# <file> alone is always the whole file, as every other review keeps it.
UNIT_SEPARATOR = "#"
RULES_DIRECTORY_SEGMENT = "rules"
RULE_DOCUMENT_SUFFIX = ".md"
RULE_ID_PATTERN = re.compile(r"(?:^|\s)id=(?P<id>\S+)")
# AGENTS.md is reviewed without the blocks the engine writes there (references/managed-agents-block.md).
INSTRUCTIONS_FILE_NAME = "AGENTS.md"
# The review of merge-instructions.sh (managed-block.sh) reads the whole AGENTS.md, managed block included.
WHOLE_INSTRUCTIONS_CHECK = "instructions"
MARKER_BEGIN_WORD = "BEGIN"
MARKER_END_WORD = "END"
MANAGED_MARKER_PATTERN = re.compile(r"<!-- (?P<word>BEGIN|END) AGENT-READY MANAGED(?:: (?P<id>.+?))? -->")
# The hooks that can stop a tool call, reviewed against the rules and skills that ask for it: one document
# per versioned settings file, named <file>#blocking-hooks (references/structural-conflicts.md, section 4).
BLOCKING_HOOKS_UNIT = "blocking-hooks"
BLOCKING_HOOK_EVENT = "PreToolUse"
HOOK_SETTINGS_FILES = (".claude/settings.json", ".codex/hooks.json")
# How a hook command names the project root before the path of its script.
PROJECT_DIRECTORY_PREFIXES = ("$CLAUDE_PROJECT_DIR", "${CLAUDE_PROJECT_DIR}", "./")
HOOK_SCRIPT_MAX_CHARACTERS = 4000
RULE_FORMAT_FILE_NAME = "rule-format.py"
_RULE_FORMAT = None


def rule_format_module():
    """rule-format.py from this same directory, the shape of a rule file that agent_ready_rules.py reads too."""
    global _RULE_FORMAT
    if _RULE_FORMAT is None:
        import importlib.util

        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), RULE_FORMAT_FILE_NAME)
        specification = importlib.util.spec_from_file_location("rule_format", path)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        _RULE_FORMAT = module
    return _RULE_FORMAT


def document_path(name):
    """The file a reviewed document comes from: a rule <file>#<id> and the rest <file># come from <file>."""
    return name.partition(UNIT_SEPARATOR)[0]


def is_rule_document(name):
    """True for a Markdown file under a rules/ folder, the only files whose rules are split apart."""
    path = document_path(name)
    return path.endswith(RULE_DOCUMENT_SUFFIX) and RULES_DIRECTORY_SEGMENT in path.split("/")[:-1]


def joined_lines(parts):
    """The non-empty parts, one after the other, without blank lines at either end."""
    return "\n".join(part for part in parts if part.strip()).strip("\n")


def rule_units(name, text):
    """{document: text} of one reviewed file: one per atomic rule and the rest of the file under ``<name>#``.

    Each rule keeps its comment, the frontmatter of its file and, for every title above it, that title
    and the paragraphs of its section, which say where the rule applies. A file without atomic rules, or
    with a shape this split does not recognise (a comment without an id or a bullet, a repeated id,
    which agent-ready rules lint reports), is one document under ``name``, as before.
    """
    if text is None or not is_rule_document(name) or UNIT_SEPARATOR in name:
        return {name: text}
    rule_format = rule_format_module()
    lines = text.split("\n")
    header = joined_lines(lines[:rule_format.frontmatter_end(lines)])
    # Each section is its title and its paragraphs; the first one, without a title, is the file's preamble.
    sections = [{"level": 0, "lines": []}]
    stack = [0]
    rules = []
    for block in rule_format.blocks(lines):
        line = lines[block.start]
        if block.kind == rule_format.BLOCK_MARKER:
            identifier = RULE_ID_PATTERN.search(block.marker.group("attributes") or "") if block.marker else None
            if not identifier or block.bullet is None:
                return {name: text}
            body = joined_lines([line] + lines[block.bullet:block.end])
            rules.append((f"{name}{UNIT_SEPARATOR}{identifier.group('id')}", body, list(stack)))
            continue
        heading = rule_format.HEADING.match(line) if block.kind == rule_format.BLOCK_TEXT else None
        if heading:
            level = len(heading.group("level"))
            while len(stack) > 1 and sections[stack[-1]]["level"] >= level:
                stack.pop()
            sections.append({"level": level, "lines": [line]})
            stack.append(len(sections) - 1)
            continue
        sections[stack[-1]]["lines"].append(line)
    if not rules:
        return {name: text}
    units = {}
    for unit, body, rule_stack in rules:
        if unit in units:
            return {name: text}
        context = [joined_lines(sections[section]["lines"]) for section in rule_stack]
        units[unit] = joined_lines([header] + context + [body])
    rest = [line for section in sections for line in section["lines"]]
    if any(line.strip() and not rule_format.HEADING.match(line) for line in rest):
        units[f"{name}{UNIT_SEPARATOR}"] = joined_lines([header, joined_lines(rest)])
    return units


def is_instructions_name(name):
    """True for AGENTS.md, at the root or in a folder: a review reads only what the project wrote in it."""
    return name == INSTRUCTIONS_FILE_NAME or name.endswith("/" + INSTRUCTIONS_FILE_NAME)


def owned_instructions(text):
    """What the project wrote in an AGENTS.md: without the managed block nor the sections of the stacks,
    which the engine writes and an apply replaces, and without blank lines at either end.

    Only whole lines are markers. Markers that do not pair up cannot tell a block apart, so all of the
    file is reviewed. The engine (agent_ready_review_findings.py) and the edit hook read AGENTS.md with
    this one function, so both review, and cache, the same text.
    """
    lines = text.replace("\r\n", "\n").split("\n")
    kept = []
    open_block = None
    for line in lines:
        marker = MANAGED_MARKER_PATTERN.fullmatch(line)
        if not marker:
            if open_block is None:
                kept.append(line)
            continue
        word, block_id = marker.group("word"), marker.group("id") or ""
        if word == MARKER_BEGIN_WORD and open_block is None:
            open_block = block_id
        elif word == MARKER_END_WORD and open_block == block_id:
            open_block = None
        else:
            kept = lines
            break
        # A block leaves a paragraph break, so the text around it never runs together.
        kept.append("")
    if open_block is not None:
        kept = lines
    owned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return owned + "\n" if owned else ""


def is_hooks_document(name):
    """True for the document of the hooks of a settings file that can stop a tool call."""
    return name.endswith(UNIT_SEPARATOR + BLOCKING_HOOKS_UNIT) and document_path(name) in HOOK_SETTINGS_FILES


def hook_script_path(project_root, command):
    """The project file a hook command runs, when one of its words names one; None otherwise."""
    for word in command.replace('"', "").replace("'", "").split():
        for prefix in PROJECT_DIRECTORY_PREFIXES:
            if word.startswith(prefix):
                word = word[len(prefix):].lstrip("/")
        if not word or os.path.isabs(word):
            continue
        candidate = os.path.normpath(os.path.join(project_root, word))
        inside = os.path.relpath(candidate, project_root).replace(os.sep, "/")
        if inside.startswith("../") or inside == "..":
            continue
        if os.path.isfile(candidate) and not os.path.islink(candidate):
            return inside
    return None


def blocking_hooks_text(project_root, settings_name):
    """What the hooks of one settings file that can stop a tool call do, for a review against the rules and
    skills: the PreToolUse hooks, each with its matcher, its command and the script it runs. None when the
    file has none, or cannot be read."""
    try:
        with open(os.path.join(project_root, *settings_name.split("/")), encoding="utf-8-sig") as file_handle:
            data = json.load(file_handle)
    except (OSError, ValueError):
        return None
    hooks = data.get("hooks") if isinstance(data, dict) else None
    groups = hooks.get(BLOCKING_HOOK_EVENT) if isinstance(hooks, dict) else None
    lines = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        matcher = group.get("matcher") if isinstance(group.get("matcher"), str) and group.get("matcher") else "*"
        for hook in group.get("hooks") if isinstance(group.get("hooks"), list) else []:
            command = hook.get("command") if isinstance(hook, dict) else None
            if not isinstance(command, str) or not command.strip():
                continue
            lines.append(f"- {BLOCKING_HOOK_EVENT} hook for the tools matching `{matcher}`: runs `{command.strip()}`")
            script = hook_script_path(project_root, command)
            if not script:
                continue
            try:
                body = normalized_text(os.path.join(project_root, *script.split("/")))
            except OSError:
                continue
            if len(body) > HOOK_SCRIPT_MAX_CHARACTERS:
                body = body[:HOOK_SCRIPT_MAX_CHARACTERS] + "\n[...]"
            lines.append(f"  The script {script}:")
            lines += ["    " + line for line in body.rstrip("\n").split("\n")]
    if not lines:
        return None
    return (f"Hooks of {settings_name} that run before a tool call and can stop it (a hook that exits with "
            "status 2, or denies the call, blocks it):\n" + "\n".join(lines) + "\n")


def hook_documents(project_root):
    """{document: text} of the blocking hooks of the versioned settings files of a project."""
    documents = {}
    for settings_name in HOOK_SETTINGS_FILES:
        name = f"{settings_name}{UNIT_SEPARATOR}{BLOCKING_HOOKS_UNIT}"
        text = blocking_hooks_text(project_root, settings_name)
        if text:
            documents[name] = text
    return documents


def unit_text(project_root, name, check=None):
    """The text a document has on disk now: a rule of a file, the rest of a file split into rules, what the
    project wrote in an AGENTS.md (all of it for ``check`` WHOLE_INSTRUCTIONS_CHECK), the blocking hooks of a
    settings file, or a whole file; None when it is gone."""
    if is_hooks_document(name):
        return blocking_hooks_text(project_root, document_path(name))
    path = document_path(name)
    try:
        text = normalized_text(os.path.join(project_root, path))
    except OSError:
        return None
    if UNIT_SEPARATOR not in name:
        return owned_instructions(text) if is_instructions_name(name) and check != WHOLE_INSTRUCTIONS_CHECK else text
    return rule_units(path, text).get(name)


def unit_pairs(directions, texts):
    """The pairs of ``directions`` (pair of files: direction) between documents, with each document's text.

    A file split into rules takes part with each rule and its rest; two documents of the same file are
    never paired, as a file was never paired with itself.
    """
    split = {name: rule_units(name, text) for name, text in texts.items()}
    documents_text = {document: text for parts in split.values() for document, text in parts.items()}
    paired = {}
    for (first, second), direction in sorted(directions.items()):
        for first_document in split.get(first, {first: None}):
            for second_document in split.get(second, {second: None}):
                paired.setdefault(tuple(sorted((first_document, second_document))), direction)
    return paired, documents_text


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
    """The golfo-agent-ready version that last applied the repository, or none before the first apply."""
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


def worktree_roots(project_root):
    """Every worktree of the repository: an entry is gone only when its files are gone from all of them."""
    try:
        completed = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=project_root, capture_output=True,
                                   encoding="utf-8", errors="replace", check=False)
    except OSError:
        return [project_root]
    roots = [line[len("worktree "):] for line in completed.stdout.splitlines() if line.startswith("worktree ")]
    return roots if completed.returncode == 0 and roots else [project_root]


def worktree_key(project_root):
    """Each worktree keeps its own reviews options inside the shared cache."""
    return os.path.normcase(os.path.realpath(project_root))


def now_text():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_seconds(checked_at):
    try:
        checked = datetime.datetime.strptime(checked_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None
    return (datetime.datetime.now(datetime.timezone.utc) - checked).total_seconds()


def write_json_atomically(path, data, prefix):
    """Replace ``path`` atomically with sorted, indented JSON; Windows refuses the replace while a reader
    has the file open, so retry."""
    file_descriptor, temporary_path = tempfile.mkstemp(prefix=prefix, dir=os.path.dirname(path))
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as file_handle:
            json.dump(data, file_handle, indent=2, sort_keys=True, ensure_ascii=False)
            file_handle.write("\n")
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(temporary_path, path)
                return
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(LOCK_POLL_SECONDS)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def trusted_shared_entry(local, shared):
    """Whether a shared entry may answer for its unit.

    Anyone can edit the versioned cache, so it only saves a review whose key matches: a shared
    entry that finds nothing never hides findings the local cache knows for the same unit. A
    shared entry with findings only adds what to look at, so it is always welcome.
    """
    if shared.get("findings"):
        return True
    return not (isinstance(local, dict) and local.get("findings"))


def matches_files(project_root, entry):
    """Whether the files of an entry are on disk as they were when it was reviewed."""
    files = entry.get("files", {}) if isinstance(entry, dict) else {}
    return bool(files) and file_hashes(project_root, files, entry.get("check")) == files


def file_identity(path):
    """What changes whenever the file is written (an atomic write replaces it), or None when it is absent."""
    try:
        status = os.stat(path)
    except OSError:
        return None
    return status.st_ino, status.st_mtime_ns, status.st_size


class ReviewCache:
    """Reads and writes the review cache of one repository.

    One hook reviews thousands of pairs, and the cache can weigh megabytes: the parsed files are kept while
    they stay the same file on disk, so a batch of lookups decodes each one once. A write of another process
    replaces the file, which reads it again.
    """

    def __init__(self, project_root, settings=None):
        """``settings`` are the effective reviews options when the engine resolved them; the hooks
        leave them out and use the ones the last apply recorded."""
        self.project_root = os.path.abspath(project_root)
        self.worktree = worktree_key(project_root)
        self.path = cache_path(project_root)
        self.shared_path = os.path.join(self.project_root, SHARED_CACHE_RELATIVE_PATH)
        self.overrides = settings
        self.parsed = {}

    def remembered(self, path, load):
        """``load()`` of ``path``, parsed again only when the file changed since the last time."""
        identity = file_identity(path) if path else None
        known = self.parsed.get(path)
        if identity is not None and known is not None and known[0] == identity:
            return known[1]
        data = load()
        if identity is None:
            self.parsed.pop(path, None)
        else:
            self.parsed[path] = (identity, data)
        return data

    def read(self):
        """The whole cache as last parsed; callers that change it go through load under the lock."""
        return self.remembered(self.path, self.load)

    def load(self):
        """The whole cache, read from disk; an absent or unreadable file is an empty one."""
        empty = {"schemaVersion": SCHEMA_VERSION, "settings": {}, "entries": {}}
        if not self.path:
            return empty
        try:
            with open(self.path, encoding="utf-8") as file_handle:
                data = json.load(file_handle)
        except (OSError, ValueError):
            return empty
        if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION or not isinstance(data.get("entries"), dict):
            return empty
        if not isinstance(data.get("settings"), dict):
            data["settings"] = {}
        return data

    def settings_of(self, data):
        """reviews.enabled, reviews.cache and reviews.ttl as the last apply of this worktree resolved them.

        The entries are shared by every worktree, but two worktrees can configure the reviews differently.
        """
        if self.overrides is not None:
            return {**DEFAULT_SETTINGS, **self.overrides}
        own = data["settings"].get(self.worktree)
        return {**DEFAULT_SETTINGS, **(own if isinstance(own, dict) else {})}

    def settings(self):
        return self.settings_of(self.read())

    def lookup(self, unit, key, recheck=False):
        """The entry of a unit when its key is current, the cache is on and it has not expired.

        The local cache answers first; with reviews.commit, the shared one answers what it misses.
        """
        data = self.read()
        settings = self.settings_of(data)
        if recheck or not settings.get("cache", True):
            return None
        ttl = settings.get("ttl")

        def current(entry):
            if not isinstance(entry, dict) or entry.get("key") != key:
                return False
            age = age_seconds(entry.get("checkedAt"))
            return not (ttl and (age is None or age > ttl * SECONDS_PER_HOUR))

        local = data["entries"].get(unit)
        if current(local):
            return local
        if settings.get("commit"):
            shared = self.read_shared().get(unit)
            if current(shared) and trusted_shared_entry(local, shared):
                return dict(shared, source=SOURCE_SHARED)
        return None

    def read_shared(self):
        """The shared cache as last parsed; store_shared, which changes it, goes through load_shared."""
        return self.remembered(self.shared_path, self.load_shared)

    def load_shared(self):
        """{unit: entry} of the versioned shared cache; empty when it is absent, unreadable or of another schema."""
        try:
            with open(self.shared_path, encoding="utf-8") as file_handle:
                data = json.load(file_handle)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("schemaVersion") != SCHEMA_VERSION or not isinstance(data.get("entries"), dict):
            return {}
        return {unit: entry for unit, entry in data["entries"].items() if isinstance(entry, dict)}

    def entries(self, commit=None):
        """The entries status and review list read: the local ones and, with reviews.commit, the shared
        ones the local cache lacks or has out of date, as long as they can be trusted.

        ``commit`` is the effective reviews.commit of the engine; the hooks leave it out and use the
        options of the last apply, which a fresh clone does not have yet.
        """
        data = self.read()
        entries = dict(data["entries"])
        if not (self.settings_of(data).get("commit") if commit is None else commit):
            return entries
        for unit, shared in self.read_shared().items():
            local = entries.get(unit)
            if not trusted_shared_entry(local, shared) or not matches_files(self.project_root, shared):
                continue
            if local is None or not matches_files(self.project_root, local):
                entries[unit] = dict(shared, source=SOURCE_SHARED)
        return entries

    def store(self, records):
        """Save ``{unit: entry}``; other entries of files that no longer exist go away in the same write.

        reviews.cache: false only stops reusing entries: the last result of each unit is still saved,
        so status shows it and a finding can be accepted or dismissed.
        """
        if not self.path:
            return
        stamped = {unit: dict(entry, checkedAt=entry.get("checkedAt") or now_text()) for unit, entry in records.items()}
        with self.locked():
            data = self.load()
            data["entries"].update(stamped)
            # What was just reviewed is current, even when a reviewed rule comes from the
            # template and the repository has no copy of it yet.
            self.prune(data, keep=records)
            self.write(data)
        if self.settings_of(data).get("commit"):
            self.store_shared(stamped)

    def store_shared(self, records):
        """Add ``records`` to the versioned shared cache; entries of files gone from this checkout leave it."""
        os.makedirs(os.path.dirname(self.shared_path), exist_ok=True)
        with directory_lock(os.path.join(self.project_root, SHARED_CACHE_LOCK_RELATIVE_PATH)):
            entries = self.load_shared()
            entries.update(records)
            for unit, entry in list(entries.items()):
                names = entry.get("files", {})
                if unit not in records and any(not os.path.exists(os.path.join(self.project_root, document_path(name)))
                                               for name in names):
                    del entries[unit]
            write_json_atomically(self.shared_path, {"schemaVersion": SCHEMA_VERSION, "entries": entries},
                                  ".agent-ready.review-cache.")

    def write_settings(self, enabled, cache, ttl, commit=False, redundancy=True):
        """Record the effective reviews options, so the hooks honor them without the engine."""
        if not self.path:
            return
        settings = {"enabled": bool(enabled), "cache": bool(cache), "ttl": ttl, "commit": bool(commit),
                    "redundancy": bool(redundancy)}
        if self.settings() == settings:
            return
        with self.locked():
            data = self.load()
            data["settings"][self.worktree] = settings
            self.prune(data)
            self.write(data)

    def prune(self, data, keep=()):
        """Drop entries that name a project file that is gone, except the units in ``keep``, and the options
        of worktrees that no longer exist."""
        for worktree in list(data["settings"]):
            if worktree != self.worktree and not os.path.isdir(worktree):
                del data["settings"][worktree]
        # Worktrees on other branches can have files this one lacks: their reviews stay.
        roots = worktree_roots(self.project_root)

        def gone(name):
            return not os.path.isabs(name) and not any(os.path.exists(os.path.join(root, document_path(name)))
                                                       for root in roots)

        for unit, entry in list(data["entries"].items()):
            if unit in keep:
                continue
            names = entry.get("files", {}) if isinstance(entry, dict) else {}
            if any(gone(name) for name in names):
                del data["entries"][unit]

    def write(self, data):
        write_json_atomically(self.path, data, ".reviews.")

    def locked(self):
        """Hold the lock of the cache between processes."""
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        return directory_lock(os.path.join(directory, LOCK_DIRECTORY_NAME))


@contextlib.contextmanager
def directory_lock(lock):
    """Hold ``lock``, a directory, between processes; one left by a dead process expires.

    Git never tracks an empty directory, so a lock left in the working tree never reaches a commit.
    """
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    denied_since = None
    while True:
        try:
            os.mkdir(lock)
            break
        except FileExistsError:
            denied_since = None
        except PermissionError:
            # Windows answers access denied while another process removes the lock. With no lock
            # there for a while, the directory itself is not writable: fail instead of waiting.
            if os.path.isdir(lock):
                denied_since = None
            else:
                denied_since = denied_since or time.monotonic()
                if time.monotonic() - denied_since > LOCK_PERMISSION_SECONDS:
                    raise
        try:
            if time.time() - os.path.getmtime(lock) > LOCK_STALE_SECONDS:
                os.rmdir(lock)
                continue
        except OSError:
            pass
        # Every path that waits observes the deadline and sleeps, so no failure spins.
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
# Decisions of the team about findings
# ---------------------------------------------------------------------------

def collapsed(text):
    return " ".join(str(text).split())


def finding_id(unit, finding):
    """Short and stable: the check, the files the finding involves, its kind and the lines it quotes.

    Only the files of the finding count, not every file of its unit: the review of AGENTS.md
    sees every rule, and adding an unrelated one must not change the id of a conflict. The
    quoted lines come from the files, so a review that words the same problem differently
    keeps the id; a finding without quoted lines falls back to its text.
    """
    check, _, unit_files = unit.partition(":")
    files = sorted(finding.get("files") or unit_files.split("|"))
    lines = sorted(collapsed(line) for line in finding.get("lines", []) if collapsed(line))
    basis = lines or [collapsed(finding.get("text", ""))]
    payload = "\0".join([check, "|".join(files), str(finding.get("kind", ""))] + basis)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:FINDING_ID_LENGTH]


def file_hashes(project_root, names, check=None):
    """{name: hash of what ``check`` reads of it now}, None for a file that is gone."""
    hashes = {}
    for name in names:
        text = unit_text(project_root, name, check)
        hashes[name] = None if text is None else text_hash(text)
    return hashes


class Decisions:
    """Accepted and dismissed findings of one repository, in .agents/agent-ready.reviews.json."""

    def __init__(self, project_root):
        self.project_root = os.path.abspath(project_root)
        self.path = os.path.join(self.project_root, DECISIONS_RELATIVE_PATH)

    def read(self, strict=False):
        """{id: decision}. A missing file has none; an unreadable one too, unless ``strict``.

        The hooks stay lenient, so a broken file never blocks a session; the CLI is strict,
        so it never overwrites decisions it could not read.
        """
        try:
            with open(self.path, encoding="utf-8") as file_handle:
                data = json.load(file_handle)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as caught_error:
            if strict:
                raise DecisionsError(f"{DECISIONS_RELATIVE_PATH} is not valid JSON: {caught_error}") from caught_error
            return {}
        if (not isinstance(data, dict) or data.get("schemaVersion") != DECISIONS_SCHEMA_VERSION
                or not isinstance(data.get("decisions"), dict)):
            if strict:
                raise DecisionsError(f"{DECISIONS_RELATIVE_PATH} needs schemaVersion {DECISIONS_SCHEMA_VERSION} "
                                     "and a decisions object")
            return {}
        return {identifier: decision for identifier, decision in data["decisions"].items() if isinstance(decision, dict)}

    def write(self, decisions):
        """Replace the file atomically; with no decision left the file goes away."""
        if not decisions:
            if os.path.exists(self.path):
                os.unlink(self.path)
            return
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(prefix=".agent-ready.reviews.", dir=directory)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as file_handle:
                json.dump({"schemaVersion": DECISIONS_SCHEMA_VERSION, "decisions": decisions}, file_handle,
                          indent=2, sort_keys=True, ensure_ascii=False)
                file_handle.write("\n")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def update(self, change):
        """Read the decisions, apply ``change`` (decisions -> new decisions) and write them, under a lock.

        Two sessions deciding at the same time would otherwise each write their own copy and
        lose the other one's decision.
        """
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with directory_lock(self.path[:-len(".json")] + ".lock"):
            changed = change(self.read(strict=True))
            self.write(changed)
            return changed

    def status(self, decision):
        """accepted or dismissed while the decision holds; to-confirm once a content decision is older than its files."""
        if decision.get("scope") == SCOPE_PAIR:
            return decision.get("decision")
        recorded = decision.get("files", {})
        if isinstance(recorded, dict) and recorded and file_hashes(self.project_root, recorded, decision.get("check")) == recorded:
            return decision.get("decision")
        return STATUS_TO_CONFIRM

    def annotate(self, unit, findings, decisions=None):
        """Each finding with its id, its status and the decision about it, if any."""
        decisions = self.read() if decisions is None else decisions
        annotated = []
        for finding in findings:
            identifier = finding_id(unit, finding)
            decision = decisions.get(identifier)
            annotated.append(dict(finding, id=identifier, unit=unit,
                                  status=self.status(decision) if decision else STATUS_OPEN,
                                  decision=decision))
        return annotated


def decision_for(finding, kind, reason, scope, by, project_root):
    """The record of a decision about an annotated finding; content decisions keep the hashes of its files."""
    files = finding.get("files", [])
    return {
        "decision": kind,
        "scope": scope,
        "reason": reason,
        "by": by,
        "at": now_text(),
        "check": finding.get("check"),
        "kind": finding.get("kind"),
        "text": finding.get("text", ""),
        "files": file_hashes(project_root, files, finding.get("check")) if scope == SCOPE_CONTENT else {name: None for name in files},
    }


def visible(annotated):
    """The findings to show: open ones and decisions to confirm; accepted and dismissed stay quiet."""
    return [finding for finding in annotated if finding["status"] in (STATUS_OPEN, STATUS_TO_CONFIRM)]


def is_redundancy(finding):
    """True for two rules that say the same thing: a warning that never stops nor fails anything."""
    return isinstance(finding, dict) and finding.get("kind") == KIND_REDUNDANCY


def finding_line(finding):
    """One line of a hook or a report: `!` for an open finding, `?` for a decision to confirm."""
    names = finding.get("files", [])
    where = f"{' <-> '.join(names)}: " if len(names) > 1 else ""
    if is_redundancy(finding):
        where += f"{KIND_REDUNDANCY}: "
    if finding["status"] == STATUS_TO_CONFIRM:
        decision = finding["decision"]
        return (f"? [{finding['id']}] {where}{finding.get('text', '')} "
                f"({decision.get('decision')} before the files changed: {decision.get('reason')})")
    return f"! [{finding['id']}] {where}{finding.get('text', '')}"


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
    # ASCII escapes: the Bash scripts read this with jq, whatever the code page of a Windows console.
    sys.stdout.write(json.dumps(entry, ensure_ascii=True) + "\n")
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


def command_report(arguments):
    """Print the findings of --result to show, with their ids; accepted and dismissed ones stay quiet."""
    unit = unit_id(arguments.check, [name for name, _ in arguments.file])
    with open(arguments.result, encoding="utf-8") as file_handle:
        findings = json.load(file_handle).get("findings", [])
    for finding in visible(Decisions(arguments.project).annotate(unit, findings)):
        # ASCII escapes would garble the text here, so print it as UTF-8 whatever the code page.
        sys.stdout.buffer.write(f"  {finding_line(finding)}\n".encode("utf-8"))
    return 0


def command_enabled(arguments):
    """Exit 0 while the AI reviews are on, 1 when reviews.enabled is false."""
    return 0 if ReviewCache(arguments.project).settings().get("enabled", True) else 1


def command_defaults(arguments):
    """Print the default model and reasoning effort of the provider, separated by a space."""
    defaults = PROVIDER_DEFAULTS[arguments.provider]
    sys.stdout.write(f"{defaults['model']} {defaults['effort']}\n")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    enabled = subparsers.add_parser("enabled", help="exit 0 while the AI reviews are on")
    enabled.add_argument("--project", default=".")
    enabled.set_defaults(handler=command_enabled)
    defaults = subparsers.add_parser("defaults", help="default model and reasoning effort of a provider")
    defaults.add_argument("--provider", required=True, choices=sorted(PROVIDER_DEFAULTS))
    defaults.add_argument("--project", default=".")
    defaults.set_defaults(handler=command_defaults)
    for name, handler in (("lookup", command_lookup), ("store", command_store), ("report", command_report)):
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
            subparser.add_argument("--result", required=True, help="JSON with the findings (and, for store, any extra fields to keep)")
        subparser.set_defaults(handler=handler)
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)
    arguments.project = os.path.abspath(arguments.project)
    return arguments.handler(arguments)


if __name__ == "__main__":
    sys.exit(main())
