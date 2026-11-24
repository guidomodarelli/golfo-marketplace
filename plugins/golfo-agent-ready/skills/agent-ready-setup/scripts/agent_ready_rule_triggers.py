"""Antigravity loads a rule of .agents/rules/ only with a valid trigger in its frontmatter.

Antigravity drops, without a word, a rule whose frontmatter has no trigger or an unknown one, and it
scans only the first level of .agents/rules/: a folder below (the rules of a workspace, a folder of the
project) is reached through .agents/rules.json. The mapping with Claude Code is that a rule without
paths: is ``trigger: always_on`` and a rule with paths: is ``trigger: glob`` with the same patterns in
``globs``. This module checks a rule, writes the trigger of the rules the engine generates and builds
the .agents/rules.json the apply manages.
"""

import json
import os
import re

from agent_ready_common import is_link, sha256_of_text, write_text_atomically

FRONTMATTER_FENCE = "---"
TRIGGER_KEY = "trigger"
GLOBS_KEY = "globs"
GLOB_KEY = "glob"
DESCRIPTION_KEY = "description"
TRIGGER_ALWAYS_ON = "always_on"
TRIGGER_MODEL_DECISION = "model_decision"
TRIGGER_GLOB = "glob"
TRIGGER_MANUAL = "manual"
TRIGGERS = (TRIGGER_ALWAYS_ON, TRIGGER_MODEL_DECISION, TRIGGER_GLOB, TRIGGER_MANUAL)
# Antigravity takes the patterns of globs as one string separated by commas.
GLOBS_SEPARATOR = ", "
RULES_DIRECTORY = ".agents/rules"
RULES_INDEX_RELATIVE_PATH = ".agents/rules.json"
RULES_INDEX_ENTRIES_KEY = "entries"
RULES_INDEX_PATH_KEY = "path"
# The personal rules of each person (#169) are given to that person only: they stay out of the index,
# which every session of the repository reads.
PERSONAL_RULES_DIRECTORY = "learned/users"
RULE_SUFFIX = ".md"
ANTIGRAVITY_PROVIDER = "antigravity"
# The lock key of the managed .agents/rules.json.
RULES_INDEX_LOCK_KEY = "rulesIndex"
FIELD_LINE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9_-]*):\s*(?P<value>.*)$")
FRONTMATTER_KEYS_REPLACED = (TRIGGER_KEY, GLOBS_KEY, GLOB_KEY)


def split_frontmatter(text):
    """(header lines, body lines) of a rule, or (None, lines) when it does not start with a closed frontmatter."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[0].strip() == FRONTMATTER_FENCE:
        for index in range(1, len(lines)):
            if lines[index].strip() == FRONTMATTER_FENCE:
                return lines[1:index], lines[index + 1:]
    return None, lines


def scalar(value):
    """A one-line YAML value without its quotes or a trailing comment."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return re.split(r"\s+#", value, 1)[0].strip()


def frontmatter_fields(header):
    """{key: value} of the top-level one-line fields of a frontmatter."""
    fields = {}
    for line in header or []:
        match = FIELD_LINE.match(line)
        if match:
            fields[match.group("key")] = scalar(match.group("value"))
    return fields


def trigger_problem(text):
    """Why Antigravity would drop a rule with this text, or None when it loads it."""
    header, _ = split_frontmatter(text)
    if header is None:
        return "it has no frontmatter with a trigger"
    fields = frontmatter_fields(header)
    trigger = fields.get(TRIGGER_KEY, "")
    if not trigger:
        return "its frontmatter has no trigger"
    if trigger not in TRIGGERS:
        return f"its trigger {trigger!r} is none of {', '.join(TRIGGERS)}"
    if trigger == TRIGGER_GLOB and not (fields.get(GLOBS_KEY) or fields.get(GLOB_KEY)):
        return "its trigger glob has no globs"
    if trigger == TRIGGER_MODEL_DECISION and not fields.get(DESCRIPTION_KEY):
        return "its trigger model_decision has no description"
    return None


def quoted(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def trigger_lines(patterns):
    """The frontmatter lines of the trigger of a rule loaded for ``patterns`` (paths:), or always."""
    if not patterns:
        return [f"{TRIGGER_KEY}: {TRIGGER_ALWAYS_ON}"]
    return [f"{TRIGGER_KEY}: {TRIGGER_GLOB}", f"{GLOBS_KEY}: {quoted(GLOBS_SEPARATOR.join(patterns))}"]


def with_trigger_lines(header, patterns):
    """``header`` without its trigger, globs and glob lines, with the trigger of ``patterns`` first."""
    kept = [line for line in header
            if not (FIELD_LINE.match(line) and FIELD_LINE.match(line).group("key") in FRONTMATTER_KEYS_REPLACED)]
    return trigger_lines(patterns) + kept


def project_rule_files(project_root):
    """The .md files under .agents/rules/ of the project (relative to it, POSIX), without the personal rules
    and without following a linked folder."""
    root = os.path.join(project_root, *RULES_DIRECTORY.split("/"))
    if not os.path.isdir(root) or is_link(root):
        return []
    found = []
    for directory, directory_names, file_names in os.walk(root):
        relative_directory = os.path.relpath(directory, root).replace(os.sep, "/")
        directory_names[:] = sorted(name for name in directory_names
                                    if not is_link(os.path.join(directory, name))
                                    and not is_personal(f"{relative_directory}/{name}".lstrip("./")))
        for name in sorted(file_names):
            if name.endswith(RULE_SUFFIX):
                relative = name if relative_directory == "." else f"{relative_directory}/{name}"
                found.append(f"{RULES_DIRECTORY}/{relative}")
    return found


def is_personal(relative_to_rules):
    return relative_to_rules == PERSONAL_RULES_DIRECTORY or relative_to_rules.startswith(PERSONAL_RULES_DIRECTORY + "/")


def nested_rule_directories(rule_paths):
    """The folders below .agents/rules/ that hold rules, which Antigravity does not scan on its own."""
    directories = set()
    for path in rule_paths:
        if not path.startswith(RULES_DIRECTORY + "/") or not path.endswith(RULE_SUFFIX):
            continue
        directory = os.path.dirname(path).replace(os.sep, "/")
        if directory != RULES_DIRECTORY and not is_personal(directory[len(RULES_DIRECTORY) + 1:]):
            directories.add(directory)
    return sorted(directories)


def rules_index_text(directories):
    """The .agents/rules.json that sends Antigravity to each of ``directories``, or None without any."""
    if not directories:
        return None
    entries = [{RULES_INDEX_PATH_KEY: directory} for directory in directories]
    return json.dumps({RULES_INDEX_ENTRIES_KEY: entries}, indent=2) + "\n"


def loaded_rule_files(rule_paths):
    """The rules Antigravity reads: the first level of .agents/rules/ and the folders of the index."""
    reachable = set(nested_rule_directories(rule_paths)) | {RULES_DIRECTORY}
    return [path for path in rule_paths if os.path.dirname(path).replace(os.sep, "/") in reachable]


def sync_rules_index(project_root, providers, previous):
    """Write, update or remove .agents/rules.json after the projection; returns (report, lock entry).

    With Antigravity among ``providers`` the file lists the folders of .agents/rules/ that hold rules
    (nested_rule_directories of what is on disk now). It is managed while it is what the last apply
    wrote (``previous``, the lock entry with its sha256): a .agents/rules.json of the project is never
    touched, and the report says which folders Antigravity misses. Without Antigravity, or without any
    nested folder, the managed file goes away.
    """
    path = os.path.join(project_root, *RULES_INDEX_RELATIVE_PATH.split("/"))
    current = None
    if os.path.lexists(path):
        if is_link(path) or not os.path.isfile(path):
            return {"conflict": f"{RULES_INDEX_RELATIVE_PATH} is not a regular file; it was not changed"}, None
        with open(path, encoding="utf-8", newline="") as index_file:
            current = index_file.read()
    managed = current is not None and bool(previous) and sha256_of_text(current) == previous.get("sha256")
    desired = None
    directories = []
    if ANTIGRAVITY_PROVIDER in providers:
        directories = nested_rule_directories(project_rule_files(project_root))
        desired = rules_index_text(directories)
    if desired is None:
        if managed:
            os.unlink(path)
            return {"removed": True}, None
        return {}, None
    if current is not None and not managed and current != desired:
        return {"conflict": f"{RULES_INDEX_RELATIVE_PATH} belongs to the project, so it was not changed; Antigravity "
                            f"reads the rules of {', '.join(directories)} only if it lists them"}, None
    if current != desired:
        write_text_atomically(path, desired)
    return {"written": directories}, {"sha256": sha256_of_text(desired)}


def remove_rules_index(project_root, previous):
    """Remove the managed .agents/rules.json, as agent-ready remove does; True when it was removed."""
    path = os.path.join(project_root, *RULES_INDEX_RELATIVE_PATH.split("/"))
    if not previous or is_link(path) or not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8", newline="") as index_file:
        if sha256_of_text(index_file.read()) != previous.get("sha256"):
            return False
    os.unlink(path)
    return True
