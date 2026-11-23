"""Git merge drivers for what the learning writes, so two machines integrate by rule and by id (#169b).

Git merges a text file line by line: two people who learn two rules at the end of the same file, or who
add evidence to the registry, collide although they changed different things. These drivers merge by
the unit the file is made of, against the common version:

* ``agent-ready-rules`` (rule files): by the id of each atomic rule (agent_ready_rules.py). A rule
  changed on one side takes that change; changed on both sides the same way, once; changed in two ways,
  or changed on one side and removed on the other, is a conflict of that rule only.
* ``agent-ready-candidates`` (.agents/learning/candidates.json): by the id of each entry. The evidence
  is the union of both sides; any other field takes the side that changed it, and ours when both did.
* ``agent-ready-log`` (.agents/learning/log.md): append-only. Ours, then the lines only theirs added.

Git runs a driver as ``<command> %O %A %B %P``: it writes the result into %A and exits 0, or 1 with
conflict markers in %A, the same as a conflict of git merge-file. A file that does not parse falls back
to ``git merge-file``. The repository declares which files use them in .gitattributes (the block of the
learning profile); the drivers themselves live in the local Git configuration of each machine
(``register``), because a command cannot be versioned.
"""

import json
import os
import subprocess
import sys

import agent_ready_rules
from agent_ready_common import serialize_json

# The command of the drivers, beside agent-ready in scripts/.
MERGE_DRIVER_SCRIPT = "agent-ready-merge"
DRIVER_RULES = "agent-ready-rules"
DRIVER_CANDIDATES = "agent-ready-candidates"
DRIVER_LOG = "agent-ready-log"
DRIVER_NAMES = {
    DRIVER_RULES: "agent-ready: atomic rules merged by id",
    DRIVER_CANDIDATES: "agent-ready: learning registry merged by entry",
    DRIVER_LOG: "agent-ready: append-only learning log",
}
# The decided conflicts of the team sync, as {path: {rule id: lines}} (agent_ready_sync_conflicts.py).
RESOLUTIONS_VARIABLE = "AGENT_READY_MERGE_RESOLUTIONS"
# What decided_lines answers for a rule whose decision does not hold (None is a decision: remove it).
NOT_DECIDED = object()
EXIT_MERGED = 0
EXIT_CONFLICT = 1
OURS_MARKER = "<<<<<<< ours"
SEPARATOR_MARKER = "======="
THEIRS_MARKER = ">>>>>>> theirs"
EVIDENCE_FIELD = "evidence"
CANDIDATES_FIELD = "candidates"
ID_FIELD = "id"


class Unparsable(Exception):
    """A version of the file this driver cannot read: git merge-file merges it by line."""


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def rule_segments(text):
    """(prefix, [(id, gap, body)], suffix) of a rule file, each a list of lines: the lines before the
    first rule, each rule with the lines between it and the previous one, and the lines after the last."""
    normalized = text.replace("\r\n", "\n")
    rules, findings = agent_ready_rules.parse_rule_text(normalized, "merge")
    if any(finding.level == agent_ready_rules.LEVEL_ERROR for finding in findings):
        raise Unparsable("the rule file has errors")
    if len({rule.id for rule in rules}) != len(rules):
        raise Unparsable("two rules share an id")
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rules = sorted(rules, key=lambda rule: rule.span[0])
    if not rules:
        return lines, [], []
    segments = []
    previous_end = rules[0].span[0]
    for rule in rules:
        rule_start, rule_end = rule.span
        segments.append((rule.id, lines[previous_end:rule_start], lines[rule_start:rule_end]))
        previous_end = rule_end
    return lines[:rules[0].span[0]], segments, lines[previous_end:]


def three_way(base, ours, theirs):
    """(value, conflict) of one unit: one side's change wins over the base; two different changes conflict."""
    if ours == theirs:
        return ours, False
    if ours == base:
        return theirs, False
    if theirs == base:
        return ours, False
    return None, True


def conflict_lines(ours, theirs):
    return [OURS_MARKER, *(ours or []), SEPARATOR_MARKER, *(theirs or []), THEIRS_MARKER]


def as_text(lines):
    return "\n".join(lines) + "\n" if lines else ""


def as_lines(text):
    lines = text.split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def merge_text_by_line(base, ours, theirs):
    """git merge-file on three texts: (text, conflict)."""
    import tempfile

    directory = tempfile.mkdtemp(prefix="agent-ready-merge.")
    paths = []
    try:
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = os.path.join(directory, name)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            paths.append(path)
        result = subprocess.run(["git", "merge-file", "-L", "ours", "-L", "base", "-L", "theirs", *paths],
                                capture_output=True, check=False)
        with open(paths[0], encoding="utf-8", newline="") as handle:
            merged = handle.read()
        if result.returncode < 0 or result.returncode > 127:
            raise OSError(f"git merge-file failed: {result.stderr.decode(errors='replace').strip()}")
        return merged, result.returncode != 0
    finally:
        for path in paths:
            os.unlink(path)
        os.rmdir(directory)


def decided_lines(resolution, ours, theirs):
    """The lines a decision keeps for a rule (None removes it), or NOT_DECIDED.

    A decision holds only for the two versions the person saw: if either side changed the rule since, the
    rule conflicts again and the sync asks about the new versions."""
    if not isinstance(resolution, dict) or resolution.get("mine") != ours or resolution.get("theirs") != theirs:
        return NOT_DECIDED
    return resolution.get("lines")


def merge_rules(base_text, ours_text, theirs_text, resolutions=None):
    """(text, conflicts) of three versions of a rule file, merged rule by rule.

    ``resolutions`` holds {rule id: {"lines", "mine", "theirs"}} for the conflicts a person already decided
    (agent_ready_sync_conflicts.py): such a rule takes those lines, or leaves the file, without a conflict,
    while its two versions are still the ones the person decided about."""
    resolutions = resolutions or {}
    base_prefix, base_segments, _ = rule_segments(base_text)
    ours_prefix, ours_segments, ours_suffix = rule_segments(ours_text)
    theirs_prefix, theirs_segments, theirs_suffix = rule_segments(theirs_text)
    base_rules = {rule_id: body for rule_id, _, body in base_segments}
    ours_rules = {rule_id: body for rule_id, _, body in ours_segments}
    theirs_rules = {rule_id: body for rule_id, _, body in theirs_segments}
    conflicts = 0

    prefix_text, prefix_conflict = merge_text_by_line(as_text(base_prefix), as_text(ours_prefix),
                                                      as_text(theirs_prefix))
    conflicts += int(prefix_conflict)

    # The order is ours; a rule ours does not have (theirs added it, or ours removed it and theirs may have
    # changed it) goes after the rule that precedes it on their side, so three_way judges it too.
    order = [(rule_id, gap) for rule_id, gap, _ in ours_segments]
    previous = None
    for rule_id, gap, _ in theirs_segments:
        if rule_id not in ours_rules:
            known = [index for index, (other, _) in enumerate(order) if other == previous]
            order.insert(known[0] + 1 if known else (0 if previous is None else len(order)), (rule_id, gap))
        previous = rule_id

    lines = as_lines(prefix_text)
    for rule_id, gap in order:
        value, conflict = three_way(base_rules.get(rule_id), ours_rules.get(rule_id), theirs_rules.get(rule_id))
        if conflict and rule_id in resolutions:
            lines_kept = decided_lines(resolutions[rule_id], ours_rules.get(rule_id), theirs_rules.get(rule_id))
            if lines_kept is not NOT_DECIDED:
                value, conflict = lines_kept, False
        if conflict:
            conflicts += 1
            value = conflict_lines(ours_rules.get(rule_id), theirs_rules.get(rule_id))
        if value is not None:
            lines.extend(gap)
            lines.extend(value)
    lines.extend(ours_suffix if ours_suffix or not theirs_suffix else theirs_suffix)
    return as_text(lines), conflicts


# ---------------------------------------------------------------------------
# Learning registry
# ---------------------------------------------------------------------------

def read_registry_text(text):
    try:
        registry = json.loads(text) if text.strip() else {CANDIDATES_FIELD: []}
    except ValueError as invalid:
        raise Unparsable(f"the registry is not JSON: {invalid}") from invalid
    if not isinstance(registry, dict) or not isinstance(registry.get(CANDIDATES_FIELD, []), list):
        raise Unparsable("the registry has no candidates list")
    entries = {}
    for entry in registry.get(CANDIDATES_FIELD, []):
        if not isinstance(entry, dict) or not isinstance(entry.get(ID_FIELD), str) or entry[ID_FIELD] in entries:
            raise Unparsable("an entry of the registry has no id, or two share one")
        entries[entry[ID_FIELD]] = entry
    return registry, entries


def evidence_identity(item):
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def merge_entry(base, ours, theirs):
    """One entry of the registry: the evidence of both sides, and each other field by three_way."""
    if ours is None or theirs is None:
        # Removed on one side: the registry never removes an entry, so keep the one that is left.
        return ours if ours is not None else theirs
    merged = {}
    base = base or {}
    for field in sorted(set(ours) | set(theirs)):
        if field == EVIDENCE_FIELD:
            seen, union = set(), []
            for item in list(ours.get(field) or []) + list(theirs.get(field) or []):
                identity = evidence_identity(item)
                if identity not in seen:
                    seen.add(identity)
                    union.append(item)
            merged[field] = sorted(union, key=lambda item: (str(item.get("date", "")), evidence_identity(item)))
            continue
        value, conflict = three_way(base.get(field), ours.get(field), theirs.get(field))
        value = ours.get(field) if conflict else value
        if value is not None:
            merged[field] = value
    return merged


def merge_candidates(base_text, ours_text, theirs_text):
    """(text, 0) of three versions of candidates.json, merged entry by entry: it never conflicts."""
    _, base_entries = read_registry_text(base_text)
    ours_registry, ours_entries = read_registry_text(ours_text)
    _, theirs_entries = read_registry_text(theirs_text)
    order = list(ours_entries) + [entry_id for entry_id in theirs_entries if entry_id not in ours_entries]
    merged = dict(ours_registry)
    merged[CANDIDATES_FIELD] = [merge_entry(base_entries.get(entry_id), ours_entries.get(entry_id),
                                            theirs_entries.get(entry_id)) for entry_id in order]
    return serialize_json(merged), 0


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

def merge_log(base_text, ours_text, theirs_text):
    """(text, 0) of the log: ours, then each line theirs added that ours does not have."""
    ours_lines = ours_text.replace("\r\n", "\n").split("\n")
    base_lines = set(base_text.replace("\r\n", "\n").split("\n"))
    present = set(ours_lines)
    added = [line for line in theirs_text.replace("\r\n", "\n").split("\n")
             if line.strip() and line not in base_lines and line not in present]
    while ours_lines and ours_lines[-1] == "":
        ours_lines.pop()
    return "\n".join(ours_lines + added) + "\n", 0


MERGERS = {DRIVER_RULES: merge_rules, DRIVER_CANDIDATES: merge_candidates, DRIVER_LOG: merge_log}


def read(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def resolutions_for(path):
    """The decided conflicts of ``path`` (the %P of git), from the file the sync names, or {}."""
    source = os.environ.get(RESOLUTIONS_VARIABLE)
    if not source or not path:
        return {}
    try:
        with open(source, encoding="utf-8") as handle:
            return json.load(handle).get(path.replace(os.sep, "/"), {})
    except (OSError, ValueError):
        return {}


def run(driver, base_path, ours_path, theirs_path, path=None):
    """Merge the three files of git into ``ours_path``; EXIT_MERGED or EXIT_CONFLICT."""
    base, ours, theirs = read(base_path), read(ours_path), read(theirs_path)
    try:
        if driver == DRIVER_RULES:
            merged, conflicts = merge_rules(base, ours, theirs, resolutions_for(path))
        else:
            merged, conflicts = MERGERS[driver](base, ours, theirs)
    except Unparsable:
        merged, conflicted = merge_text_by_line(base, ours, theirs)
        conflicts = int(conflicted)
    with open(ours_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(merged)
    return EXIT_CONFLICT if conflicts else EXIT_MERGED


# ---------------------------------------------------------------------------
# Registration in the local Git configuration
# ---------------------------------------------------------------------------

def quoted(path):
    """A path for the shell git runs the driver with, with forward slashes."""
    return '"' + path.replace("\\", "/").replace('"', '\\"') + '"'


def driver_command(script_path, driver):
    return f"{quoted(sys.executable)} {quoted(script_path)} {driver} %O %A %B %P"


def register(project_root, script_path):
    """Write the drivers into .git/config of the repository; returns the names that changed.

    Outside a Git repository there is nothing to write."""
    changed = []
    inside = subprocess.run(["git", "-C", project_root, "rev-parse", "--git-dir"], capture_output=True, check=False)
    if inside.returncode != 0:
        return changed
    for driver, description in DRIVER_NAMES.items():
        for field, value in (("name", description), ("driver", driver_command(script_path, driver))):
            key = f"merge.{driver}.{field}"
            current = subprocess.run(["git", "-C", project_root, "config", "--local", "--get", key],
                                     capture_output=True, text=True, check=False).stdout.strip()
            if current != value:
                subprocess.run(["git", "-C", project_root, "config", "--local", key, value], check=True,
                               capture_output=True)
                if driver not in changed:
                    changed.append(driver)
    return changed
