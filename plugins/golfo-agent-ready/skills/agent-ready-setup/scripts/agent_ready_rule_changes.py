"""The atomic rules of a managed rule file, one by one (#168): their hashes for the lock and what an
update changes in each of them for the plan.

A file is still written whole; these functions only say which of its rules the write adds, removes or
changes, so a one-line change shows as one rule and not as the whole file.
"""

import os

import agent_ready_rule_graph
import agent_ready_rules

RULES_DESTINATION_PREFIX = ".agents/rules/"
RULE_FILE_SUFFIX = ".md"
CHANGE_ADDED = "added"
CHANGE_REMOVED = "removed"
CHANGE_CHANGED = "changed"
CHANGE_KINDS = (CHANGE_CHANGED, CHANGE_ADDED, CHANGE_REMOVED)
CHANGE_SYMBOLS = {CHANGE_CHANGED: "~", CHANGE_ADDED: "+", CHANGE_REMOVED: "-"}
IMPACT_KINDS = ("requiredBy", "replacedBy", "citedBy")
IMPACT_LABELS = (("requiredBy", "required by"), ("replacedBy", "replaced by"), ("citedBy", "cited by"))


def is_rule_destination(destination):
    """True for a managed file under .agents/rules/ that can hold atomic rules."""
    return destination.startswith(RULES_DESTINATION_PREFIX) and destination.endswith(RULE_FILE_SUFFIX)


def read_text(path):
    """The text of a file, or None when it cannot be read as UTF-8 (absent, a directory, binary)."""
    if not path or not os.path.isfile(path) or os.path.islink(path):
        return None
    try:
        with open(path, encoding="utf-8", newline="") as text_file:
            return text_file.read()
    except (OSError, UnicodeDecodeError):
        return None


def rule_hashes(text, path):
    """{id: hash} of the atomic rules of a text, or {} when it has none. A repeated id keeps the first."""
    if text is None:
        return {}
    rules, _ = agent_ready_rules.parse_rule_text(text, path)
    hashes = {}
    for rule in rules:
        hashes.setdefault(rule.id, rule.hash())
    return hashes


def rule_changes(old_text, new_text, path):
    """{changed, added, removed} ids between two versions of a rule file, or None when neither has an
    atomic rule (a file of prose: its diff is the only view)."""
    old_hashes = rule_hashes(old_text, path)
    new_hashes = rule_hashes(new_text, path)
    if not old_hashes and not new_hashes:
        return None
    return {
        CHANGE_CHANGED: sorted(rule_id for rule_id in old_hashes.keys() & new_hashes.keys()
                               if old_hashes[rule_id] != new_hashes[rule_id]),
        CHANGE_ADDED: sorted(new_hashes.keys() - old_hashes.keys()),
        CHANGE_REMOVED: sorted(old_hashes.keys() - new_hashes.keys()),
    }


def changed_rule_ids(changes):
    """The ids an update touches in a way that can break what depends on them: changed and removed."""
    return sorted(set(changes.get(CHANGE_CHANGED, [])) | set(changes.get(CHANGE_REMOVED, []))) if changes else []


def has_changes(changes):
    return bool(changes) and any(changes[kind] for kind in CHANGE_KINDS)


def current_impact(project_root, rule_ids):
    """{id: {requiredBy, replacedBy, citedBy}} of the rules and skills of the repository now, for the ids
    something depends on; an id nothing depends on is left out."""
    if not rule_ids:
        return {}
    rule_paths = agent_ready_rules.rule_files(os.path.join(project_root, ".agents", "rules"))
    skill_paths = agent_ready_rule_graph.skill_files(os.path.join(project_root, ".agents", "skills"))
    try:
        rules, _ = agent_ready_rules.read_rules(rule_paths, project_root)
        citations = agent_ready_rule_graph.skill_citations(skill_paths, project_root)
    except (OSError, UnicodeDecodeError):
        # The impact is a hint for the reader of the plan; a file it cannot read leaves it out.
        return {}
    impacts = {}
    for rule_id in rule_ids:
        report = agent_ready_rule_graph.impact(rules, citations, rule_id)
        dependents = {kind: report[kind] for kind in IMPACT_KINDS} if report else {}
        if any(dependents.values()):
            impacts[rule_id] = dependents
    return impacts


def annotate_entries(project_root, entries, actions):
    """Add ruleChanges (changed, added, removed ids) to each entry of ``actions`` that writes or retires a
    rule file with atomic rules, and ruleImpact (current_impact) for the ids it changes or removes."""
    touched = []
    for entry in entries:
        if entry["action"] not in actions or not is_rule_destination(entry["destination"]):
            continue
        old_text = read_text(os.path.join(project_root, entry["destination"]))
        new_text = read_text(entry.get("sourcePath")) if entry.get("sha256") else None
        changes = rule_changes(old_text, new_text, entry["destination"])
        if has_changes(changes):
            entry["ruleChanges"] = changes
            touched.append(entry)
    impacts = current_impact(project_root, sorted({rule_id for entry in touched
                                                   for rule_id in changed_rule_ids(entry["ruleChanges"])}))
    for entry in touched:
        entry_impact = {rule_id: impacts[rule_id] for rule_id in changed_rule_ids(entry["ruleChanges"])
                        if rule_id in impacts}
        if entry_impact:
            entry["ruleImpact"] = entry_impact


def rule_change_lines(entry):
    """The lines under a plan entry: one per kind of change, then one per dependent of a changed rule."""
    changes = entry.get("ruleChanges")
    if not changes:
        return []
    lines = [f"      {CHANGE_SYMBOLS[kind]} rule {kind}: {', '.join(changes[kind])}"
             for kind in CHANGE_KINDS if changes[kind]]
    for rule_id, dependents in sorted(entry.get("ruleImpact", {}).items()):
        for kind, label in IMPACT_LABELS:
            for place in dependents.get(kind, []):
                where = f"{place['path']}:{place['line']}"
                described = f"{place['id']} ({where})" if "id" in place else where
                lines.append(f"        ! {rule_id} is {label} {described}")
    return lines
