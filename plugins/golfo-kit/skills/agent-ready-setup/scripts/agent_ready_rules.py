"""Atomic rules: parse, normalize, hash and lint the rule entries of a rule file.

A rule file stays Markdown grouped by topic. Each rule is one entry: an HTML comment with its
metadata, right above a top-level bullet with one imperative statement. Indented sub-bullets of
that bullet belong to the rule: ``Except:`` items are its exceptions, any other item a detail.

    <!-- rule id=testing/unit-runner key=testing.unit-runner -->
    - Use Vitest for unit tests.
      - Except: keep the runner the project already uses if it is not Vitest.

The comment costs no context in Claude Code, which strips HTML comments from CLAUDE.md and from
.claude/rules/; Codex reads AGENTS.md as written. references/atomic-rules.md is the format for
authors of packs, and this module its only implementation.
"""

import json
import os
import re

from agent_ready_common import sha256_of_text, walk_files

MARKER = re.compile(r"^<!--\s*rule(?:\s+(?P<attributes>.*?))?\s*-->\s*$")
# Any comment that starts like a marker, so a misspelled one is reported instead of read as prose.
MARKER_LIKE = re.compile(r"^<!--\s*rule\b")
ATTRIBUTE = re.compile(r"^(?P<name>[a-z]+)(?:=(?P<value>\S+))?$")
TOP_LEVEL_BULLET = re.compile(r"^(?:[-*+]|\d+[.)])\s+(?P<text>.*)$")
SUB_ITEM = re.compile(r"^\s+(?:[-*+]|\d+[.)])\s+(?P<text>.*)$")
# A fence closes only with the character that opened it, at least as many times, and nothing after it.
FENCE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<rest>.*)$")
FRONTMATTER_DELIMITER = "---"

ID_SEGMENT = r"[a-z0-9]+(?:-[a-z0-9]+)*"
RULE_ID = re.compile(rf"^{ID_SEGMENT}(?:/{ID_SEGMENT})*$")
# A reference to a rule of another source: <source>:<id>.
QUALIFIED_RULE_ID = re.compile(rf"^(?:{ID_SEGMENT}:)?{ID_SEGMENT}(?:/{ID_SEGMENT})*$")
DECISION_KEY = re.compile(rf"^{ID_SEGMENT}(?:\.{ID_SEGMENT})*$")
EXCEPTION_PREFIX = re.compile(r"^except:\s*", re.IGNORECASE)

ATTRIBUTE_ID = "id"
ATTRIBUTE_KEY = "key"
ATTRIBUTE_REQUIRES = "requires"
ATTRIBUTE_PATHS = "paths"
ATTRIBUTE_OVERRIDES = "overrides"
ATTRIBUTE_LOCKED = "locked"
# The order of the canonical marker, which the hash uses.
LIST_ATTRIBUTES = (ATTRIBUTE_REQUIRES, ATTRIBUTE_PATHS, ATTRIBUTE_OVERRIDES)
VALUE_ATTRIBUTES = (ATTRIBUTE_ID, ATTRIBUTE_KEY) + LIST_ATTRIBUTES
FLAG_ATTRIBUTES = (ATTRIBUTE_LOCKED,)
LIST_SEPARATOR = ","
HASH_PREFIX = "sha256:"

LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"
CODE_MARKER_SYNTAX = "marker-syntax"
CODE_MARKER_WITHOUT_RULE = "marker-without-rule"
CODE_UNTAGGED_RULE = "untagged-rule"
CODE_DUPLICATE_ID = "duplicate-id"
CODE_STATEMENT_TOO_LONG = "statement-too-long"
CODE_STATEMENT_LONG = "statement-long"
CODE_SEVERAL_DECISIONS = "several-decisions"
CODE_KEY_CONFLICT = "key-conflict"
CODE_DUPLICATE_RULE = "duplicate-rule"
CODE_UNKNOWN_REQUIRES = "unknown-requires"

DEFAULT_STATEMENT_WARN_CHARS = 200
DEFAULT_MAX_STATEMENT_CHARS = 300

# Several decisions in one statement: a second sentence, or clauses chained with a semicolon.
# Inline code and parentheses are left out first, so `a.b`, "e.g. x" in parentheses or a
# semicolon inside code never count.
# A code span opens and closes with backtick runs of the same length, as in Markdown: `` `a`; `b` ``.
INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)")
PARENTHESIZED = re.compile(r"\([^()]*\)")
SENTENCE_BREAK = re.compile(r"[.!?]\s+(?=[A-Z])")
CLAUSE_CHAIN = re.compile(r";\s+\S")
ABBREVIATIONS = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf)\.", re.IGNORECASE)
WHITESPACE = re.compile(r"\s+")

RULES_DIRECTORY_NAME = "rules"
RULE_FILE_SUFFIX = ".md"
SKIPPED_DIRECTORIES = (".git", "node_modules")


class Rule:
    """One atomic rule as it is written in its file."""

    def __init__(self, path, line, metadata, statement, exceptions, details, span=None):
        self.path = path
        self.line = line
        self.id = metadata.get(ATTRIBUTE_ID)
        self.key = metadata.get(ATTRIBUTE_KEY)
        self.requires = metadata.get(ATTRIBUTE_REQUIRES, [])
        self.paths = metadata.get(ATTRIBUTE_PATHS, [])
        self.overrides = metadata.get(ATTRIBUTE_OVERRIDES, [])
        self.locked = bool(metadata.get(ATTRIBUTE_LOCKED))
        self.statement = statement
        self.exceptions = exceptions
        self.details = details
        # (first, after last) line index of the marker and its bullet in the text, for remove_rules.
        self.span = span

    def canonical(self):
        """The rule without its formatting: what two equal rules share, and what the hash covers."""
        return {
            ATTRIBUTE_ID: self.id, ATTRIBUTE_KEY: self.key, ATTRIBUTE_REQUIRES: sorted(set(self.requires)),
            ATTRIBUTE_PATHS: sorted(set(self.paths)), ATTRIBUTE_OVERRIDES: sorted(set(self.overrides)),
            ATTRIBUTE_LOCKED: self.locked, "statement": self.statement, "exceptions": self.exceptions,
            "details": self.details,
        }

    def content(self):
        """What the rule asks, without its identity: equal for two rules that decide the same."""
        return {"statement": self.statement, "exceptions": self.exceptions}

    def hash(self):
        """Hash of the normalized rule: spacing, line endings and the order of the metadata do not change it."""
        return HASH_PREFIX + sha256_of_text(json.dumps(self.canonical(), sort_keys=True, ensure_ascii=False))

    def marker(self):
        """The canonical comment of the rule."""
        parts = [f"{ATTRIBUTE_ID}={self.id}"]
        if self.key:
            parts.append(f"{ATTRIBUTE_KEY}={self.key}")
        for name in LIST_ATTRIBUTES:
            values = sorted(set(getattr(self, name)))
            if values:
                parts.append(f"{name}={LIST_SEPARATOR.join(values)}")
        if self.locked:
            parts.append(ATTRIBUTE_LOCKED)
        return f"<!-- rule {' '.join(parts)} -->"

    def to_json(self):
        """The rule as list --json and show --json print it."""
        return dict(self.canonical(), path=self.path, line=self.line, hash=self.hash())


class Finding:
    """One problem the lint found, located in its file."""

    def __init__(self, level, code, path, line, message, rule_id=None):
        self.level = level
        self.code = code
        self.path = path
        self.line = line
        self.message = message
        self.rule_id = rule_id

    def to_json(self):
        return {"level": self.level, "code": self.code, "path": self.path, "line": self.line,
                "rule": self.rule_id, "message": self.message}

    def render(self):
        where = f"{self.path}:{self.line}"
        named = f" {self.rule_id}" if self.rule_id else ""
        return f"{where}: {self.level}: [{self.code}]{named}: {self.message}"


def collapse(text):
    """Text on one line with single spaces."""
    return WHITESPACE.sub(" ", text).strip()


def parse_marker(attributes_text):
    """(metadata, problems) of the attributes of a marker comment."""
    metadata = {}
    problems = []
    for token in (attributes_text or "").split():
        match = ATTRIBUTE.match(token)
        if not match:
            problems.append(f"cannot read the attribute {token!r}; write name=value or a flag")
            continue
        name, value = match.group("name"), match.group("value")
        if name in metadata:
            problems.append(f"the attribute {name} is written twice")
        elif name in FLAG_ATTRIBUTES:
            if value is not None:
                problems.append(f"{name} is a flag and takes no value")
            metadata[name] = True
        elif name in VALUE_ATTRIBUTES:
            if value is None:
                problems.append(f"the attribute {name} needs a value: {name}=<value>")
                continue
            metadata[name] = value.split(LIST_SEPARATOR) if name in LIST_ATTRIBUTES else value
        else:
            known = ", ".join(VALUE_ATTRIBUTES + FLAG_ATTRIBUTES)
            problems.append(f"unknown attribute {name}; a rule takes {known}")
    problems.extend(metadata_problems(metadata))
    return metadata, problems


def metadata_problems(metadata):
    """What is wrong with the values of a marker that was read."""
    problems = []
    rule_id = metadata.get(ATTRIBUTE_ID)
    if rule_id is None:
        problems.append("the marker has no id: <!-- rule id=<topic>/<name> -->")
    elif not RULE_ID.match(rule_id):
        problems.append(f"the id {rule_id!r} must be kebab-case segments joined by /, such as testing/unit-runner")
    key = metadata.get(ATTRIBUTE_KEY)
    if key is not None and not DECISION_KEY.match(key):
        problems.append(f"the key {key!r} must be kebab-case segments joined by dots, such as testing.unit-runner")
    for name in (ATTRIBUTE_REQUIRES, ATTRIBUTE_OVERRIDES):
        for reference in metadata.get(name, []):
            if not QUALIFIED_RULE_ID.match(reference):
                problems.append(f"{name} names {reference!r}, which is not a rule id or <source>:<id>")
    if any(not path for path in metadata.get(ATTRIBUTE_PATHS, [])):
        problems.append("paths has an empty entry")
    return problems


def strip_frontmatter(lines):
    """Index of the first line after a leading YAML frontmatter, or 0 without one."""
    if lines and lines[0].strip() == FRONTMATTER_DELIMITER:
        for index in range(1, len(lines)):
            if lines[index].strip() == FRONTMATTER_DELIMITER:
                return index + 1
    return 0


def split_items(body_lines):
    """(statement, exceptions, details) of the bullet of a rule and its indented lines."""
    statement_parts = [body_lines[0]]
    items = []
    for line in body_lines[1:]:
        sub_item = SUB_ITEM.match(line)
        if sub_item:
            items.append([sub_item.group("text")])
        elif items:
            items[-1].append(line)
        else:
            statement_parts.append(line)
    exceptions = []
    details = []
    for item in items:
        text = collapse(" ".join(item))
        if EXCEPTION_PREFIX.match(text):
            exceptions.append(EXCEPTION_PREFIX.sub("", text, count=1))
        elif text:
            details.append(text)
    return collapse(" ".join(statement_parts)), exceptions, details


def parse_rule_text(text, path):
    """(rules, findings) of the text of a rule file; the findings are the ones of a single file."""
    lines = text.replace("\r\n", "\n").split("\n")
    rules = []
    findings = []
    index = strip_frontmatter(lines)
    open_fence = None
    while index < len(lines):
        line = lines[index]
        fence = FENCE.match(line)
        if fence and open_fence is None and not (fence.group("fence")[0] == "`" and "`" in fence.group("rest")):
            open_fence = fence.group("fence")
            index += 1
            continue
        if open_fence is not None:
            if (fence and fence.group("fence")[0] == open_fence[0] and len(fence.group("fence")) >= len(open_fence)
                    and not fence.group("rest").strip()):
                open_fence = None
            index += 1
            continue
        marker = MARKER.match(line)
        if marker or MARKER_LIKE.match(line):
            index = read_entry(lines, index, marker, path, rules, findings)
            continue
        if TOP_LEVEL_BULLET.match(line):
            findings.append(Finding(LEVEL_ERROR, CODE_UNTAGGED_RULE, path, index + 1,
                                    "a top-level bullet without a <!-- rule id=... --> marker above it; "
                                    "give it an id, or write it as prose if it is not an instruction"))
        index += 1
    return rules, findings


def read_entry(lines, index, marker, path, rules, findings):
    """Read the rule whose marker is at ``index``; return the index of the line after it."""
    line_number = index + 1
    if not marker:
        findings.append(Finding(LEVEL_ERROR, CODE_MARKER_SYNTAX, path, line_number,
                                "the rule marker is not closed on its line: <!-- rule id=... -->"))
        return index + 1
    metadata, problems = parse_marker(marker.group("attributes"))
    rule_id = metadata.get(ATTRIBUTE_ID)
    for problem in problems:
        findings.append(Finding(LEVEL_ERROR, CODE_MARKER_SYNTAX, path, line_number, problem, rule_id))
    bullet_index = index + 1
    while bullet_index < len(lines) and not lines[bullet_index].strip():
        bullet_index += 1
    bullet = TOP_LEVEL_BULLET.match(lines[bullet_index]) if bullet_index < len(lines) else None
    if not bullet:
        findings.append(Finding(LEVEL_ERROR, CODE_MARKER_WITHOUT_RULE, path, line_number,
                                "the marker must be followed by a top-level bullet with the statement", rule_id))
        return index + 1
    body = [bullet.group("text")]
    cursor = bullet_index + 1
    while cursor < len(lines):
        current = lines[cursor]
        if current.strip() and current[:1] in (" ", "\t"):
            body.append(current)
            cursor += 1
            continue
        # A blank line belongs to the rule only when an indented line follows it.
        if not current.strip():
            following = cursor + 1
            while following < len(lines) and not lines[following].strip():
                following += 1
            if following < len(lines) and lines[following][:1] in (" ", "\t"):
                cursor = following
                continue
        break
    if not problems:
        statement, exceptions, details = split_items(body)
        rules.append(Rule(path, bullet_index + 1, metadata, statement, exceptions, details, (index, cursor)))
    return cursor


def decisions_in(statement):
    """How many decisions a statement chains, by sentences and semicolons outside code and parentheses."""
    plain = INLINE_CODE.sub("code", statement)
    previous = None
    while previous != plain:
        previous, plain = plain, PARENTHESIZED.sub("", plain)
    plain = ABBREVIATIONS.sub("abbreviation", plain)
    return 1 + len(SENTENCE_BREAK.findall(plain.strip())) + len(CLAUSE_CHAIN.findall(plain))


def lint_rules(rules, warn_chars=DEFAULT_STATEMENT_WARN_CHARS, max_chars=DEFAULT_MAX_STATEMENT_CHARS):
    """Findings of a set of rules read together: each rule alone, and the set (ids, keys, requires)."""
    findings = []
    for rule in rules:
        length = len(rule.statement)
        if length > max_chars:
            findings.append(Finding(LEVEL_ERROR, CODE_STATEMENT_TOO_LONG, rule.path, rule.line,
                                    f"the statement has {length} characters, over rules.maxStatementChars "
                                    f"({max_chars}); move the reason or the exceptions to sub-bullets", rule.id))
        elif length > warn_chars:
            findings.append(Finding(LEVEL_WARNING, CODE_STATEMENT_LONG, rule.path, rule.line,
                                    f"the statement has {length} characters, over rules.statementWarnChars "
                                    f"({warn_chars})", rule.id))
        if decisions_in(rule.statement) > 1:
            findings.append(Finding(LEVEL_ERROR, CODE_SEVERAL_DECISIONS, rule.path, rule.line,
                                    "the statement chains several instructions (more than one sentence, or clauses "
                                    "joined with ';'); split it into one rule per decision", rule.id))
    findings.extend(set_findings(rules))
    return findings


def set_findings(rules):
    """Findings that need the whole set: repeated ids, keys decided twice, equal rules, unknown requires."""
    findings = []
    first_by_id = {}
    for rule in rules:
        first = first_by_id.setdefault(rule.id, rule)
        if first is not rule:
            findings.append(Finding(LEVEL_ERROR, CODE_DUPLICATE_ID, rule.path, rule.line,
                                    f"the id is already used at {first.path}:{first.line}", rule.id))
    first_by_key = {}
    first_by_statement = {}
    for rule in rules:
        if rule.key:
            first = first_by_key.setdefault(rule.key, rule)
            if first is not rule:
                if first.content() == rule.content():
                    findings.append(Finding(LEVEL_WARNING, CODE_DUPLICATE_RULE, rule.path, rule.line,
                                            f"decides {rule.key} with the same content as {first.id} "
                                            f"({first.path}:{first.line}); keep one of them", rule.id))
                else:
                    findings.append(Finding(LEVEL_ERROR, CODE_KEY_CONFLICT, rule.path, rule.line,
                                            f"decides {rule.key}, which {first.id} ({first.path}:{first.line}) "
                                            "already decides differently; keep one, or replace the other "
                                            "with overrides", rule.id))
                continue
        normalized = rule.statement.lower()
        first = first_by_statement.setdefault(normalized, rule)
        if first is not rule:
            findings.append(Finding(LEVEL_WARNING, CODE_DUPLICATE_RULE, rule.path, rule.line,
                                    f"has the same statement as {first.id} ({first.path}:{first.line})", rule.id))
    for rule in rules:
        for required in rule.requires:
            if ":" not in required and required not in first_by_id:
                findings.append(Finding(LEVEL_ERROR, CODE_UNKNOWN_REQUIRES, rule.path, rule.line,
                                        f"requires {required}, which no rule of this set has as its id; "
                                        "name a rule of another source as <source>:<id>", rule.id))
    return findings


def rule_files(target):
    """The rule files of a target: a file itself, or every .md under a rules/ directory of a directory."""
    if os.path.isfile(target):
        return [target]
    if not os.path.isdir(target):
        return []
    inside_rules = os.path.basename(os.path.normpath(target)) == RULES_DIRECTORY_NAME
    return [absolute_path for relative_path, absolute_path in walk_files(target)
            if relative_path.endswith(RULE_FILE_SUFFIX)
            and not any(part in SKIPPED_DIRECTORIES for part in relative_path.split("/"))
            and (inside_rules or RULES_DIRECTORY_NAME in relative_path.split("/")[:-1])]


def display_path(path, display_root):
    """``path`` relative to ``display_root`` when it is inside it, else the absolute path.

    On Windows a path on another drive has no relative form, and relpath raises ValueError.
    """
    try:
        relative = os.path.relpath(path, display_root)
    except ValueError:
        relative = None
    if relative is None or relative.startswith(".."):
        return path.replace(os.sep, "/")
    return relative.replace(os.sep, "/")


def read_rules(paths, display_root):
    """(rules, findings) of every rule file of ``paths``, with paths shown relative to ``display_root``."""
    rules = []
    findings = []
    for path in paths:
        display = display_path(path, display_root)
        with open(path, encoding="utf-8") as file_handle:
            file_rules, file_findings = parse_rule_text(file_handle.read(), display)
        rules.extend(file_rules)
        findings.extend(file_findings)
    return rules, findings


def remove_rules(text, rule_ids):
    """The text of a rule file without the rules whose id is in ``rule_ids``: marker, bullet and sub-bullets.

    The neighbours, the prose and the line endings of the file stay as they are, so the other rules keep
    their hash. A blank line left doubled by the removal is dropped.
    """
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    rules, _ = parse_rule_text(text, "")
    removed = set()
    for rule in rules:
        if rule.id in rule_ids:
            removed.update(range(*rule.span))
    kept = []
    for index, line in enumerate(lines):
        if index in removed:
            continue
        if not line.strip() and kept and not kept[-1].strip() and index - 1 in removed:
            continue
        kept.append(line)
    return newline.join(kept)
