"""Managed blocks: the part of a file shared with the project that one profile owns.

A profile publishes a block as ``blocks/<path in the repository>`` in its asset tree. The block
lives in that file between two marker lines that carry its id, the name of the profile:

    <!-- BEGIN AGENT-READY MANAGED: golfo -->      (Markdown)
    # BEGIN AGENT-READY MANAGED: golfo             (.gitignore, .gitattributes, YAML, TOML, shell)

Each apply replaces what is between the markers and leaves the rest of the file to the project.
Several profiles keep blocks of their own in the same file. Markers that repeat, come out of order
or nest stop every change to that file. The lockfile keeps the sha256 of each block, and a block
whose profile leaves the selection is removed; a file left empty goes away. The contract is in
``references/managed-agents-block.md``.
"""

import os
import re
import stat

from agent_ready_common import ProfileError, sha256_of_text
from agent_ready_detection import is_contained_pattern

BLOCK_DIRECTORY = "blocks"
BLOCK_PREFIX = BLOCK_DIRECTORY + "/"
MARKDOWN_SYNTAX = ("<!-- ", " -->")
HASH_SYNTAX = ("# ", "")
SYNTAX_BY_SUFFIX = {".md": MARKDOWN_SYNTAX, ".markdown": MARKDOWN_SYNTAX, ".yml": HASH_SYNTAX,
                    ".yaml": HASH_SYNTAX, ".toml": HASH_SYNTAX, ".sh": HASH_SYNTAX}
SYNTAX_BY_NAME = {".gitignore": HASH_SYNTAX, ".gitattributes": HASH_SYNTAX, ".dockerignore": HASH_SYNTAX}
BEGIN_WORD = "BEGIN"
END_WORD = "END"
MARKER_LABEL = "AGENT-READY MANAGED"
# Files whose content the engine owns some other way: the instruction files, at any depth and in
# any case, and the directories of Git and of the providers.
RESERVED_DESTINATIONS = ("AGENTS.md", "CLAUDE.md")
RESERVED_PREFIXES = (".git/", ".agents/", ".claude/", ".codex/")

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_UNCHANGED = "unchanged"
ACTION_CONFLICT = "conflict"
ACTION_RETIRE = "retire"
ACTION_RETIRE_CONFLICT = "retire-conflict"
ACTION_DROP = "drop"
STATE_APPLIED = "applied"
STATE_CONFLICT = "conflict"


class MarkerError(ValueError):
    """Markers of a file that cannot be read as blocks: nothing in it is changed."""


def destination_of(relative_path):
    """The repository path of a block template, or None for a file that is not a block."""
    if not relative_path.startswith(BLOCK_PREFIX):
        return None
    return relative_path[len(BLOCK_PREFIX):]


def comment_syntax(destination):
    name = destination.rsplit("/", 1)[-1]
    if name in SYNTAX_BY_NAME:
        return SYNTAX_BY_NAME[name]
    return SYNTAX_BY_SUFFIX.get(os.path.splitext(name)[1].lower())


def validate_destination(destination, profile):
    """Raise ProfileError for a block a profile cannot publish."""
    if not is_contained_pattern(destination) or any(ord(character) < 32 for character in destination):
        raise ProfileError(f"profile '{profile}': the block {destination} does not stay inside the repository")
    folded = destination.casefold()
    basename = folded.rsplit("/", 1)[-1]
    if basename in {name.casefold() for name in RESERVED_DESTINATIONS} or folded.startswith(RESERVED_PREFIXES):
        raise ProfileError(f"profile '{profile}': {destination} is not a file a block can go to")
    if comment_syntax(destination) is None:
        known = ", ".join(sorted(SYNTAX_BY_NAME) + sorted(SYNTAX_BY_SUFFIX))
        raise ProfileError(f"profile '{profile}': the block {destination} has no known comment syntax; "
                           f"a block goes to a file named or ending {known}")


def marker_line(destination, word, block_id):
    prefix, suffix = comment_syntax(destination)
    return f"{prefix}{word} {MARKER_LABEL}: {block_id}{suffix}"


def marker_pattern(destination):
    prefix, suffix = comment_syntax(destination)
    return re.compile(rf"{re.escape(prefix)}({BEGIN_WORD}|{END_WORD}) {re.escape(MARKER_LABEL)}: (.+?){re.escape(suffix)}")


def normalized_content(text):
    """The text of a block as it goes between its markers: Unix line ends and a final line end."""
    text = text.replace("\r\n", "\n")
    return text if not text or text.endswith("\n") else text + "\n"


def parse(text, destination):
    """{id: (begin line, end line)} of the blocks of a file; MarkerError when its markers do not pair up.

    Only whole lines are markers, so a line that mentions one stays as text.
    """
    pattern = marker_pattern(destination)
    blocks, open_block = {}, None
    for index, line in enumerate(text.replace("\r\n", "\n").split("\n")):
        match = pattern.fullmatch(line)
        if not match:
            continue
        word, block_id = match.groups()
        if word == BEGIN_WORD:
            if open_block is not None:
                raise MarkerError(f"the block {block_id} starts inside the block {open_block[0]}")
            if block_id in blocks:
                raise MarkerError(f"the block {block_id} appears twice")
            open_block = (block_id, index)
        elif open_block is None or open_block[0] != block_id:
            raise MarkerError(f"the end of the block {block_id} has no start before it")
        else:
            blocks[block_id] = (open_block[1], index)
            open_block = None
    if open_block is not None:
        raise MarkerError(f"the block {open_block[0]} has no end")
    return blocks


def block_text(text, destination, block_id):
    """What the file holds between the markers of a block, or None without that block."""
    lines = text.replace("\r\n", "\n").split("\n")
    span = parse(text, destination).get(block_id)
    if span is None:
        return None
    return "".join(line + "\n" for line in lines[span[0] + 1:span[1]])


def with_block(text, destination, block_id, content):
    """The file with the block in place: replaced where it is, or added at the end."""
    lines = text.replace("\r\n", "\n").split("\n")
    span = parse(text, destination).get(block_id)
    block = [marker_line(destination, BEGIN_WORD, block_id)] + normalized_content(content).split("\n")[:-1] + \
        [marker_line(destination, END_WORD, block_id)]
    if span is not None:
        lines[span[0]:span[1] + 1] = block
        return "\n".join(lines)
    body = "\n".join(lines).rstrip("\n")
    return (body + "\n\n" if body else "") + "\n".join(block) + "\n"


def without_block(text, destination, block_id):
    """The file without the block, and without the blank line that separated it."""
    lines = text.replace("\r\n", "\n").split("\n")
    span = parse(text, destination).get(block_id)
    if span is None:
        return text
    start, end = span
    del lines[start:end + 1]
    if start > 0 and start - 1 < len(lines) and lines[start - 1] == "" and (start >= len(lines) or lines[start] == ""):
        del lines[start - 1]
    return "\n".join(lines)


def is_empty(text):
    return not text.strip()


def read_text(path):
    with open(path, encoding="utf-8", newline="") as file_handle:
        return file_handle.read()


def has_linked_directory(project_root, destination):
    """True when a directory between the repository and the file is a symlink: writing would leave it."""
    parent = os.path.dirname(destination)
    while parent:
        if os.path.islink(os.path.join(project_root, parent)):
            return True
        parent = os.path.dirname(parent)
    return False


def local_file(path):
    """(state, text): 'absent', 'symlink', 'not-a-file' or 'file' with its text."""
    if os.path.islink(path):
        return "symlink", None
    if not os.path.exists(path):
        return "absent", ""
    if not os.path.isfile(path):
        return "not-a-file", None
    return "file", read_text(path)


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def classify(project_root, desired, locked, retiring=()):
    """One entry per block: what an apply does to it, and why.

    ``desired`` is {(destination, id): {profile, source, content}} and ``locked`` the blocks of the lock,
    {destination: {id: entry}}. ``retiring`` names the files the same apply deletes first, because the
    whole-file asset there left the selection: their blocks create the file again.
    """
    entries = []
    destinations = sorted({destination for destination, _ in desired} | set(locked))
    for destination in destinations:
        state, text = local_file(os.path.join(project_root, destination))
        if destination in retiring:
            state, text = "absent", ""
        problem = None
        if has_linked_directory(project_root, destination):
            state, text, problem = "linked", None, "a directory on its path is a symlink; the file was not changed"
        elif state in ("symlink", "not-a-file"):
            problem = "the file is a symlink or not a regular file" if state == "symlink" else "it is not a regular file"
        else:
            try:
                parse(text, destination)
            except MarkerError as marker_error:
                problem = f"its markers do not pair up ({marker_error}); nothing in the file was changed"
        file_sha256 = sha256_of_text(text) if state == "file" else state
        wanted = {block_id: item for (target, block_id), item in desired.items() if target == destination}
        for block_id in sorted(set(wanted) | set(locked.get(destination, {}))):
            item, lock_entry = wanted.get(block_id), locked.get(destination, {}).get(block_id)
            entry = {"destination": destination, "id": block_id, "fileSha256": file_sha256,
                     "baseSha256": (lock_entry or {}).get("sha256")}
            current = None if problem or state != "file" else block_text(text, destination, block_id)
            entry["localSha256"] = sha256_of_text(current) if current is not None else None
            if item:
                entry.update(profile=item["profile"], source=item["source"], content=item["content"],
                             sha256=sha256_of_text(item["content"]))
                if problem:
                    entry.update(action=ACTION_CONFLICT, reason=problem)
                elif current is None:
                    entry.update(action=ACTION_CREATE, reason="adds the block" if state == "file" else "creates the file")
                elif entry["localSha256"] == entry["sha256"]:
                    entry.update(action=ACTION_UNCHANGED, reason="matches the template")
                elif entry["localSha256"] == entry["baseSha256"]:
                    entry.update(action=ACTION_UPDATE, reason="the block still matches the applied base")
                else:
                    entry.update(action=ACTION_UPDATE, reason="overwrites local changes inside the block")
            else:
                entry.update(profile=lock_entry.get("profile"), source=lock_entry.get("source"), sha256=None)
                if current is None and not problem:
                    entry.update(action=ACTION_DROP, reason="already removed")
                elif problem:
                    entry.update(action=ACTION_RETIRE_CONFLICT, reason=problem)
                else:
                    entry.update(action=ACTION_RETIRE, reason="no longer published by the selected profiles")
            entries.append(entry)
    return entries


def diff_text(project_root, entry):
    """(before, after) of the block of one entry, for the plan."""
    state, text = local_file(os.path.join(project_root, entry["destination"]))
    before = (block_text(text, entry["destination"], entry["id"]) or "") if state == "file" else ""
    return before, entry.get("content") or ""


# ---------------------------------------------------------------------------
# Apply and remove
# ---------------------------------------------------------------------------

def write_atomically(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temporary = f"{path}.agent-ready-block.{os.getpid()}"
    with open(temporary, "w", encoding="utf-8", newline="") as file_handle:
        file_handle.write(text)
    if os.path.isfile(path):
        # An executable script stays executable.
        os.chmod(temporary, stat.S_IMODE(os.stat(path).st_mode))
    os.replace(temporary, path)


def apply(project_root, entries):
    """Write the blocks of the plan; returns {lock, changed, removed, conflicts}.

    Each file is read again first: one that changed since the plan keeps its content, and so do
    its blocks in the lock.
    """
    result = {"lock": {}, "changed": [], "removed": [], "conflicts": []}
    by_destination = {}
    for entry in entries:
        by_destination.setdefault(entry["destination"], []).append(entry)
    for destination, file_entries in sorted(by_destination.items()):
        path = os.path.join(project_root, destination)
        state, text = local_file(path)
        if has_linked_directory(project_root, destination):
            state, text = "linked", None
        current_sha256 = sha256_of_text(text) if state == "file" else state
        unchanged_since_plan = current_sha256 == file_entries[0]["fileSha256"]
        updated = text if state == "file" else ""
        for entry in file_entries:
            keep = {"profile": entry["profile"], "source": entry["source"]}
            if entry["action"] in (ACTION_CONFLICT, ACTION_RETIRE_CONFLICT) or not unchanged_since_plan:
                reason = entry["reason"] if unchanged_since_plan else "the file changed during synchronization"
                result["conflicts"].append(f"{destination} (block {entry['id']}): {reason}")
                if entry["baseSha256"] or entry["sha256"]:
                    result["lock"].setdefault(destination, {})[entry["id"]] = dict(
                        keep, sha256=entry["baseSha256"], desiredSha256=entry["sha256"], state=STATE_CONFLICT)
                continue
            if entry["action"] == ACTION_DROP:
                continue
            if entry["action"] == ACTION_RETIRE:
                updated = without_block(updated, destination, entry["id"])
                continue
            if entry["action"] != ACTION_UNCHANGED:
                updated = with_block(updated, destination, entry["id"], entry["content"])
            result["lock"].setdefault(destination, {})[entry["id"]] = dict(keep, sha256=entry["sha256"],
                                                                           state=STATE_APPLIED)
        if not unchanged_since_plan or updated == (text if state == "file" else ""):
            continue
        if is_empty(updated) and state == "file":
            os.unlink(path)
            result["removed"].append(destination)
        elif not is_empty(updated):
            write_atomically(path, updated)
            result["changed"].append(destination)
    return result


def remove_all(project_root, locked):
    """Take every block of the lock out of its file; a file left empty goes away.

    Returns (changed, removed, problems). A file whose markers do not pair up is not touched.
    """
    changed, removed, problems = [], [], []
    for destination, blocks in sorted(locked.items()):
        path = os.path.join(project_root, destination)
        state, text = local_file(path)
        if state != "file":
            continue
        try:
            updated = text
            for block_id in sorted(blocks):
                updated = without_block(updated, destination, block_id)
        except MarkerError as marker_error:
            problems.append(f"{destination}: its markers do not pair up ({marker_error}); it was not changed")
            continue
        if updated == text:
            continue
        if is_empty(updated):
            os.unlink(path)
            removed.append(destination)
        else:
            write_atomically(path, updated)
            changed.append(destination)
    return changed, removed, problems
