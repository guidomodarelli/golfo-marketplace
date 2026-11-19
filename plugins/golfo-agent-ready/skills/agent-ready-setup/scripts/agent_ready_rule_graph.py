"""The graph of the atomic rules (#168): what each rule needs, what replaces it and which skills cite it.

The edges come from the rules themselves and from the skills next to them:

- ``requires``: a rule that needs another one;
- ``overrides``: a rule that replaces another one;
- a citation ``rule:<source>:<id>`` (or ``rule:<id>``) in the text of a skill.

A reference names a rule by its id, with or without its source. Inside one set of rules (a repository or
the checkout of a pack) the ids are unique, so the graph matches a qualified reference by its id.
"""

import os
import re

from agent_ready_common import walk_files
from agent_ready_rules import ID_SEGMENT, RULE_FILE_SUFFIX, SKIPPED_DIRECTORIES, display_path

SKILLS_DIRECTORY_NAME = "skills"
SOURCE_SEPARATOR = ":"
# rule:<source>:<id> or rule:<id>, not inside a longer word such as "subrule:".
CITATION = re.compile(rf"(?<![\w/-])rule:(?:(?P<source>{ID_SEGMENT}):)?(?P<id>{ID_SEGMENT}(?:/{ID_SEGMENT})*)")
EDGE_REQUIRES = "requires"
EDGE_OVERRIDES = "overrides"
EDGE_CITES = "cites"


def referenced_id(reference):
    """The id a reference names: ``golfo:testing/unit-runner`` and ``testing/unit-runner`` name the same rule."""
    return reference.rsplit(SOURCE_SEPARATOR, 1)[-1]


def skill_files(target):
    """The text files of the skills of a target: every .md under a skills/ directory of a directory."""
    if not os.path.isdir(target):
        return []
    inside_skills = os.path.basename(os.path.normpath(target)) == SKILLS_DIRECTORY_NAME
    return [absolute_path for relative_path, absolute_path in walk_files(target)
            if relative_path.endswith(RULE_FILE_SUFFIX)
            and not any(part in SKIPPED_DIRECTORIES for part in relative_path.split("/"))
            and (inside_skills or SKILLS_DIRECTORY_NAME in relative_path.split("/")[:-1])]


def skill_citations(paths, display_root):
    """[{path, line, reference}] of every rule citation in the skill files of ``paths``."""
    citations = []
    for path in paths:
        display = display_path(path, display_root)
        with open(path, encoding="utf-8", errors="replace") as skill_file:
            for number, line in enumerate(skill_file, start=1):
                for match in CITATION.finditer(line):
                    reference = match.group(0)[len("rule:"):]
                    citations.append({"path": display, "line": number, "reference": reference})
    return citations


def rule_place(rule):
    return {"id": rule.id, "path": rule.path, "line": rule.line}


def graph(rules, citations):
    """{nodes, edges} of the rules: each edge {from, to, kind, path, line}, ``from`` a rule id or a skill path."""
    edges = []
    for rule in rules:
        for kind, references in ((EDGE_REQUIRES, rule.requires), (EDGE_OVERRIDES, rule.overrides)):
            for reference in references:
                edges.append({"from": rule.id, "to": reference, "kind": kind, "path": rule.path, "line": rule.line})
    for citation in citations:
        edges.append({"from": citation["path"], "to": citation["reference"], "kind": EDGE_CITES,
                      "path": citation["path"], "line": citation["line"]})
    edges.sort(key=lambda edge: (edge["kind"], edge["from"], edge["to"], edge["path"], edge["line"]))
    return {"nodes": sorted({rule.id for rule in rules}), "edges": edges}


def impact(rules, citations, rule_id):
    """What a change to ``rule_id`` touches: {id, rules, requiredBy, replacedBy, citedBy}, or None when the id is
    neither a rule of the set nor named by one of its references."""
    wanted = referenced_id(rule_id)
    rule_graph = graph(rules, citations)
    by_kind = {EDGE_REQUIRES: [], EDGE_OVERRIDES: [], EDGE_CITES: []}
    for edge in rule_graph["edges"]:
        if referenced_id(edge["to"]) == wanted:
            by_kind[edge["kind"]].append(edge)
    found = [rule_place(rule) for rule in rules if rule.id == wanted]
    if not found and not any(by_kind.values()):
        return None
    return {"id": wanted, "rules": found, "requiredBy": edge_places(by_kind[EDGE_REQUIRES], True),
            "replacedBy": edge_places(by_kind[EDGE_OVERRIDES], True),
            "citedBy": edge_places(by_kind[EDGE_CITES], False)}


def edge_places(edges, with_rule_id):
    """[{id?, path, line}] of where each edge is written; the id is the rule that wrote it."""
    places = []
    for edge in edges:
        place = {"id": edge["from"]} if with_rule_id else {}
        place.update(path=edge["path"], line=edge["line"])
        places.append(place)
    return places
