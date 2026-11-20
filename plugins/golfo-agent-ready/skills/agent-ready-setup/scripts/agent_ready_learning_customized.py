"""A managed rule the learning replaced, whose profile changed it since: «customized, review».

When learn apply replaces a managed rule with overrides, the entry keeps the fingerprint of that rule as
it was (its statement, exceptions and details). An update of the profile that changes the rule keeps the
learned version, since the override still holds, and the plan marks the override «customized, review»:
the developer decides whether the learned version still applies (agent-ready learn keep) or the new one of
the profile should come back (agent-ready learn retire). The plan only reads the repository: what the
profile publishes now is kept in the cache of the user, where learn keep takes it from
(references/learning.md, «Cuando el profile cambia una rule reemplazada»).
"""

import json
import os

import agent_ready_learning as learning
from agent_ready_common import StateError, read_json_file, serialize_json, sha256_of_text, skill_cache_directory, \
    write_text_atomically

CUSTOMIZED_CACHE = "learning-customized"


def rule_fingerprint(rule):
    """What a rule says, without where it is written: its statement, exceptions and details."""
    return sha256_of_text(json.dumps([rule.statement.strip(), list(rule.exceptions or []), list(rule.details or [])],
                                     ensure_ascii=False))


def seen_path(project_root):
    return skill_cache_directory(CUSTOMIZED_CACHE, sha256_of_text(os.path.realpath(project_root)) + ".json")


def recorded(project_root):
    """{reference: (entry, fingerprint)} of the managed rules the learned entries replaced."""
    try:
        registry = learning.read_registry(project_root)
    except StateError:
        # A broken registry is reported by the learn commands; the plan goes on without the mark.
        return {}
    found = {}
    for entry in registry["candidates"]:
        if entry["status"] != learning.STATUS_LEARNED:
            continue
        for reference, fingerprint in (entry.get("learned", {}).get("overridden") or {}).items():
            found[reference] = (entry, fingerprint)
    return found


def mark(project_root, published, rule_overrides):
    """Mark each override of a learned rule whose managed rule changed since it was learned.

    ``published`` is {qualified id: (profile, relative path, absolute path, rule)} of the selection
    (agent_ready_rule_overrides.selection_rules). Saves what the profile publishes now for learn keep.
    """
    known = recorded(project_root)
    seen = {}
    for override in rule_overrides:
        reference = override["replaces"]
        if reference not in known or reference not in published:
            continue
        entry, fingerprint = known[reference]
        current = rule_fingerprint(published[reference][3])
        seen[reference] = current
        if current != fingerprint:
            override["customized"] = {"learningId": entry["id"], "since": entry["learned"].get("date")}
    if seen:
        write_text_atomically(seen_path(project_root), serialize_json(seen))
    return rule_overrides


def current_versions(project_root):
    path = seen_path(project_root)
    return read_json_file(path, "the rules the last plan saw") if os.path.exists(path) else {}
