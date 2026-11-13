"""Rules against the reality of the repository: what a rule takes for granted (``assumes`` in its
frontmatter) checked against the static signals of the project, the same kind detect reads.

A rule declares its assumptions in its frontmatter::

    ---
    assumes:
      testRunner: vitest
    ---

The facts and how each value shows in a repository live in ``assets/repo-facts.json``: the
dependencies of ``package.json``, lockfiles and config files, the ``packageManager`` field,
``.editorconfig`` and the Prettier config. A rule contradicts the repository when the repository
shows another value of the same fact and none of the one the rule assumes. Nothing is executed and
nothing is written.
"""

import configparser
import glob
import json
import os

FACTS_RELATIVE_PATH = "assets/repo-facts.json"
ASSUMES_KEY = "assumes"
FRONTMATTER_DELIMITER = "---"
PACKAGE_JSON = "package.json"
DEPENDENCY_SECTIONS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
PACKAGE_MANAGER_FIELD = "packageManager"
EDITORCONFIG = ".editorconfig"
EDITORCONFIG_ALL_FILES_SECTION = "*"
PRETTIER_FILES = (".prettierrc", ".prettierrc.json")
PRETTIER_PACKAGE_KEY = "prettier"


def load_facts(skill_dir):
    """The catalog of facts: {fact: {description, values: {value: signals}}}."""
    with open(os.path.join(skill_dir, *FACTS_RELATIVE_PATH.split("/")), encoding="utf-8") as facts_file:
        return json.load(facts_file)


def rule_assumptions(text):
    """{fact: value} the rule declares under ``assumes`` in its frontmatter; {} without one."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}
    assumptions, inside = {}, False
    for line in lines[1:]:
        if line.strip() == FRONTMATTER_DELIMITER:
            break
        if not line.startswith((" ", "\t")):
            inside = line.split(":", 1)[0].strip() == ASSUMES_KEY
            continue
        if inside and ":" in line:
            fact, value = (part.strip().strip("'\"") for part in line.split(":", 1))
            if fact and value:
                assumptions[fact] = value
    return assumptions


def read_json(path):
    """The JSON of a regular file, or None."""
    if not os.path.isfile(path) or os.path.islink(path):
        return None
    try:
        with open(path, encoding="utf-8") as json_file:
            return json.load(json_file)
    except (OSError, ValueError):
        return None


def editorconfig_values(project_root):
    """The [*] section of the root .editorconfig, lowercased; {} without one."""
    path = os.path.join(project_root, EDITORCONFIG)
    if not os.path.isfile(path) or os.path.islink(path):
        return {}
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        with open(path, encoding="utf-8") as editorconfig_file:
            parser.read_string("[__root__]\n" + editorconfig_file.read())
    except (OSError, configparser.Error):
        return {}
    if not parser.has_section(EDITORCONFIG_ALL_FILES_SECTION):
        return {}
    return {key: value.strip().lower() for key, value in parser.items(EDITORCONFIG_ALL_FILES_SECTION)}


def prettier_values(project_root, package):
    """(config, file) of the Prettier config in JSON: .prettierrc(.json) or package.json "prettier"."""
    for name in PRETTIER_FILES:
        config = read_json(os.path.join(project_root, name))
        if isinstance(config, dict):
            return config, name
    if isinstance(package, dict) and isinstance(package.get(PRETTIER_PACKAGE_KEY), dict):
        return package[PRETTIER_PACKAGE_KEY], PACKAGE_JSON
    return {}, None


def value_evidence(project_root, signals, package, editorconfig, prettier):
    """The files that show this value of a fact in the repository; [] when none does."""
    evidence = []
    dependencies = {}
    if isinstance(package, dict):
        for section in DEPENDENCY_SECTIONS:
            if isinstance(package.get(section), dict):
                dependencies.update(package[section])
    if any(name in dependencies for name in signals.get("dependencies", [])):
        evidence.append(PACKAGE_JSON)
    if isinstance(package, dict) and any(key in package for key in signals.get("packageJsonKeys", [])):
        evidence.append(PACKAGE_JSON)
    field = signals.get("packageManagerField")
    if field and isinstance(package, dict) and str(package.get(PACKAGE_MANAGER_FIELD, "")).split("@", 1)[0] == field:
        evidence.append(PACKAGE_JSON)
    for pattern in signals.get("files", []):
        evidence += [os.path.relpath(path, project_root).replace(os.sep, "/")
                     for path in sorted(glob.glob(os.path.join(glob.escape(project_root), pattern)))]
    wanted = signals.get("editorconfig")
    if wanted and editorconfig and all(editorconfig.get(key) == value for key, value in wanted.items()):
        evidence.append(EDITORCONFIG)
    wanted = signals.get("prettier")
    config, prettier_file = prettier
    if wanted and prettier_file and all(config.get(key, False if isinstance(value, bool) else None) == value
                                        for key, value in wanted.items()):
        evidence.append(prettier_file)
    return sorted(set(evidence))


def repository_facts(project_root, facts):
    """{fact: {value: [evidence files]}} of every value the repository shows."""
    package = read_json(os.path.join(project_root, PACKAGE_JSON))
    editorconfig = editorconfig_values(project_root)
    prettier = prettier_values(project_root, package)
    shown = {}
    for fact, definition in facts.items():
        for value, signals in definition["values"].items():
            evidence = value_evidence(project_root, signals, package, editorconfig, prettier)
            if evidence:
                shown.setdefault(fact, {})[value] = evidence
    return shown


def contradictions(project_root, facts, rules):
    """One finding per assumption of a rule that the repository contradicts.

    ``rules`` is [{path, profile, text}]. An assumption about a fact the catalog does not know, or a
    value it does not list, is reported too: the rule cannot be checked as written.
    """
    shown = repository_facts(project_root, facts)
    findings = []
    for rule in rules:
        for fact, assumed in sorted(rule_assumptions(rule["text"]).items()):
            definition = facts.get(fact)
            if definition is None or assumed not in definition["values"]:
                findings.append({"rule": rule["path"], "profile": rule["profile"], "fact": fact, "assumes": assumed,
                                 "unknown": True})
                continue
            values = shown.get(fact, {})
            if values and assumed not in values:
                findings.append({"rule": rule["path"], "profile": rule["profile"], "fact": fact, "assumes": assumed,
                                 "description": definition["description"],
                                 "repository": sorted(values),
                                 "evidence": sorted({path for paths in values.values() for path in paths})})
    return findings
