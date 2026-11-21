"""Promotion of personal rules to the team: what several people of an office taught alike (#169e).

The sync (agent_ready_sync.py) brings the personal rules of the others with the rest of the repository.
After each merge, ``promote`` looks for a decision key that ``sync.promoteAfterUsers`` people (2 by
default) decide with the same statement in their personal rules (agent_ready_learning_apply.py, one
folder per person under .agents/rules/learned/users/). Such a rule becomes a rule of the team, and the
personal ones are superseded by it: their entries leave the personal files and say so in the registry
and the log.

The rule of the team takes an id derived from its key (``learned/<key>``) and its entry an id derived
from its statement, so two machines that promote at the same time write the same rule and the same
entry: the merge drivers join them by id, and nothing is duplicated. A key that a rule of the team
already decides is never promoted over it, and a person who decides the key differently keeps their
personal rule. Without a key nothing is promoted here (the deterministic comparison needs one).
"""

import collections
import os

import agent_ready_learning as learning
import agent_ready_learning_apply as learning_apply
import agent_ready_rules
from agent_ready_common import write_text_atomically

PROMOTE_AFTER_USERS_KEY = "sync.promoteAfterUsers"
ACTION_PROMOTE = "promote"


def team_rule_id(key):
    return learning_apply.LEARNED_RULE_PREFIX + key.replace(".", "-")


def personal_rules_by_key(project_root):
    """{key: {person: rule}} of the personal rules with a key, and the keys the team already decides."""
    personal = collections.defaultdict(dict)
    team_keys = set()
    for rule, _, _, _ in learning_apply.repository_rules(project_root):
        if not rule.key:
            continue
        owner = agent_ready_rules.personal_owner(rule)
        if owner:
            personal[rule.key][owner] = rule
        else:
            team_keys.add(rule.key)
    return personal, team_keys


def promotable(project_root, threshold):
    """[(key, statement, [rules])] that ``threshold`` people decide alike and the team does not decide."""
    personal, team_keys = personal_rules_by_key(project_root)
    found = []
    for key, by_person in sorted(personal.items()):
        if key in team_keys:
            continue
        alike = collections.defaultdict(list)
        for rule in by_person.values():
            alike[learning.normalized_statement(rule.statement)].append(rule)
        for rules in alike.values():
            if len(rules) >= threshold:
                found.append((key, rules[0].statement, sorted(rules, key=lambda rule: rule.path)))
    return found


def promote(project_root, threshold, today):
    """Promote what is promotable, under the lock of the registry the caller holds; the paths it wrote."""
    if threshold < 2:
        return []
    found = promotable(project_root, threshold)
    if not found:
        return []
    registry = learning.read_registry(project_root)
    written = []
    for key, statement, rules in found:
        rule_id = team_rule_id(key)
        entry = next((item for item in registry["candidates"]
                      if item["id"] == learning.candidate_id(statement)), None)
        if entry is None:
            entry = {"id": learning.candidate_id(statement), "statement": statement,
                     "kind": learning.KIND_RULE, "key": key, "created": today, "evidence": []}
            registry["candidates"].append(entry)
        personal_ids = {rule.id for rule in rules}
        personal_entries = [item for item in registry["candidates"]
                            if item.get("learned", {}).get("ruleId") in personal_ids]
        for item in personal_entries:
            for evidence in item.get("evidence") or []:
                if evidence not in entry["evidence"]:
                    entry["evidence"].append(evidence)
            item["status"] = learning.STATUS_SUPERSEDED
            item["supersededBy"] = entry["id"]
        path, text = learning_apply.appended_rule(project_root, rule_id, dict(entry, paths=[]), None)
        write_text_atomically(path, text)
        written.append(path)
        entry["status"] = learning.STATUS_LEARNED
        entry["learned"] = {"action": ACTION_PROMOTE, "ruleId": rule_id, "date": today,
                            "path": os.path.relpath(path, project_root).replace(os.sep, "/"),
                            "promotes": sorted(personal_ids),
                            "marker": {"key": key, "paths": []}}
        for rule in rules:
            rule_path = os.path.join(project_root, rule.path)
            with open(rule_path, encoding="utf-8", newline="") as handle:
                remaining = agent_ready_rules.remove_rules(handle.read(), {rule.id})
            write_text_atomically(rule_path, remaining)
            written.append(rule_path)
        people = ", ".join(sorted(agent_ready_rules.personal_owner(rule) for rule in rules))
        written.append(learning_apply.append_log(
            project_root, f"- {today} promote {entry['id']} ({rule_id}, from the personal rules of {people}): "
                          f"{statement}\n"))
    learning.write_registry(project_root, registry)
    written.append(learning.candidates_path(project_root))
    return written
