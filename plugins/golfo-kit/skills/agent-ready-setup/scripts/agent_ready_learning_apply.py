"""Write what the agent learned: an entry of the registry becomes a rule or a skill of the project.

A rule of the project that already decides the same key is edited in place; a managed rule that decides
it is replaced with overrides, unless it is locked; anything else is a new rule in .agents/rules/learned.md.
Nothing managed is ever written. Each learning is one commit with the trailers Learning-Id and
Learned-from, and one line of .agents/learning/log.md (references/learning.md, «Escribir lo aprendido»).
"""

import os
import re
import subprocess
import unicodedata

import agent_ready_learning as learning
import agent_ready_rules
from agent_ready_common import ProfileError, StateError, write_text_atomically
from agent_ready_lockfile import read_lock, was_applied
from agent_ready_profiles import BASE_PROFILE_NAME
from agent_ready_rule_overrides import PROJECT_RULE_SOURCE, rule_source
from agent_ready_workspaces import PATHS_LINE, WORKSPACE_RULES_DIRECTORY, frontmatter_patterns

PROJECT_RULES_RELATIVE_PATH = ".agents/rules"
PROJECT_SKILLS_RELATIVE_PATH = ".agents/skills"
LEARNED_RULES_RELATIVE_PATH = ".agents/rules/learned.md"
LOG_RELATIVE_PATH = ".agents/learning/log.md"
SKILL_FILE_NAME = "SKILL.md"
LEARNED_RULE_PREFIX = "learned/"
SLUG_WORDS = 5
LEARNED_RULES_HEADER = ("# Learned\n\nRules the agent learned from the instructions of the user "
                        "(agent-ready learn, references/learning.md of agent-ready-setup).\n")
LOG_HEADER = "# Learning log\n\nWhat the agent learned, changed or replaced, and from which instruction.\n\n"
WORD = re.compile(r"[a-z0-9]+")
LEARNED_SCOPED_PREFIX = "learned-"
FRONTMATTER_FENCE = "---"

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_SUPERSEDE = "supersede"


class LockedRuleError(StateError):
    """The instruction goes against a rule its profile marks as locked: nothing is saved."""


def slug_of(entry):
    """The last segment of the id of a learned rule: its key, or the first words of the statement."""
    if entry.get("key"):
        return entry["key"].replace(".", "-")
    ascii_text = unicodedata.normalize("NFKD", entry["statement"]).encode("ascii", "ignore").decode().lower()
    words = WORD.findall(ascii_text)[:SLUG_WORDS]
    return "-".join(words) or entry["id"]


def unique_rule_id(slug, taken):
    rule_id, suffix = LEARNED_RULE_PREFIX + slug, 2
    while rule_id in taken:
        rule_id, suffix = f"{LEARNED_RULE_PREFIX}{slug}-{suffix}", suffix + 1
    return rule_id


def repository_rules(project_root):
    """[(rule, managed, source, profile)] of the root rules of the repository: managed is what an apply
    wrote, and profile is the profile of the lock that wrote it."""
    rules_root = os.path.join(project_root, PROJECT_RULES_RELATIVE_PATH)
    files = [path for path in agent_ready_rules.rule_files(rules_root)
             if not agent_ready_rules.display_path(path, rules_root).startswith(WORKSPACE_RULES_DIRECTORY + "/")]
    try:
        rules, _ = agent_ready_rules.read_rules(files, project_root)
    except (OSError, UnicodeDecodeError) as read_error:
        raise StateError(f"could not read a rule file: {read_error}") from read_error
    assets = (read_lock(project_root) or {}).get("assets", {})
    described = []
    for rule in rules:
        asset = assets.get(rule.path)
        managed = was_applied(asset)
        profile = asset.get("profile") if managed else None
        described.append((rule, managed, rule_source(profile) if managed else PROJECT_RULE_SOURCE, profile))
    return described


def is_managed(project_root, relative_path):
    return was_applied((read_lock(project_root) or {}).get("assets", {}).get(relative_path))


def marker_of(rule_id, entry, overrides):
    attributes = [f"id={rule_id}"]
    if entry.get("key"):
        attributes.append(f"key={entry['key']}")
    if entry.get("paths"):
        if any(char.isspace() or char in ',"' for glob in entry["paths"] for char in glob):
            raise StateError(f"{entry['id']}: a glob of --paths has a space, a comma or a quote, which a rule marker "
                             "cannot hold")
        attributes.append("paths=" + ",".join(entry["paths"]))
    if overrides:
        attributes.append(f"overrides={overrides}")
    return f"<!-- rule {' '.join(attributes)} -->"


def read_text(path):
    with open(path, encoding="utf-8", newline="") as file_handle:
        return file_handle.read()


def frontmatter_paths(text, rule_path):
    """The sorted patterns of paths: in the YAML frontmatter of a rule file, or [] without one; read as
    the workspaces read it (agent_ready_workspaces.frontmatter_patterns)."""
    lines = text.replace("\r\n", "\n").split("\n")
    end = agent_ready_rules.rule_format_module().frontmatter_end(lines)
    for index in range(1, max(end - 1, 1)):
        if PATHS_LINE.match(lines[index]):
            try:
                patterns, _ = frontmatter_patterns(lines, index, rule_path)
            except ProfileError as scope_error:
                raise StateError(str(scope_error)) from scope_error
            return sorted(patterns)
    return []


def rule_scope(project_root, rule):
    """Where a rule applies: the paths of its marker, else the paths: of its file, which Claude reads."""
    if rule.paths:
        return sorted(rule.paths)
    return frontmatter_paths(read_text(os.path.join(project_root, rule.path)), rule.path)


def learned_file(project_root, paths):
    """(relative path, header) of the file a learned rule goes to. A rule for some folders goes to a file
    of its own whose frontmatter carries paths: Claude drops the HTML marker, so only the frontmatter
    keeps the scope in its view of the rule."""
    if not paths:
        return LEARNED_RULES_RELATIVE_PATH, LEARNED_RULES_HEADER
    slug = "-".join(word for glob in sorted(paths) for word in WORD.findall(glob.lower())) or "scoped"
    globs = "".join(f'  - "{glob}"\n' for glob in sorted(paths))
    header = (f"{FRONTMATTER_FENCE}\npaths:\n{globs}{FRONTMATTER_FENCE}\n# Learned for {', '.join(sorted(paths))}\n\n"
              "Rules the agent learned from the instructions of the user (agent-ready learn, references/learning.md "
              "of agent-ready-setup).\n")
    suffix = ""
    while True:
        relative = f"{PROJECT_RULES_RELATIVE_PATH}/{LEARNED_SCOPED_PREFIX}{slug}{suffix}.md"
        path = os.path.join(project_root, relative)
        if not os.path.exists(path) or frontmatter_paths(read_text(path), relative) == sorted(paths):
            return relative, header
        suffix = f"-{int(suffix[1:] or 1) + 1}"


def appended_rule(project_root, rule_id, entry, overrides):
    """(path, new text) of the learned file of the scope of the entry, with the new rule at its end."""
    relative, header = learned_file(project_root, entry.get("paths") or [])
    if is_managed(project_root, relative):
        raise StateError(f"{relative} is managed by a profile; a learned rule never goes there")
    path = os.path.join(project_root, relative)
    text = read_text(path) if os.path.exists(path) else header
    newline = "\r\n" if "\r\n" in text else "\n"
    block = newline.join([marker_of(rule_id, entry, overrides), f"- {entry['statement']}"]) + newline
    return path, text.rstrip("\r\n") + newline + newline + block


def replaced_statement(project_root, rule, statement):
    """(path, new text) of the file of ``rule`` with its statement replaced; its marker, exceptions and
    details stay, so a rule the team wrote keeps what it says besides the decision."""
    path = os.path.join(project_root, rule.path)
    text = read_text(path)
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    index = rule.line - 1
    bullet = agent_ready_rules.rule_format_module().TOP_LEVEL_BULLET.match(lines[index])
    # The statement is the bullet and its indented continuations, blank lines between them included,
    # up to the first sub-item of the rule (rule-format.py decides where the rule ends).
    rule_end = rule.span[1]
    statement_end = index + 1
    for position in range(index + 1, rule_end):
        if agent_ready_rules.SUB_ITEM.match(lines[position]):
            break
        if lines[position].strip():
            statement_end = position + 1
    lines[index:statement_end] = [lines[index][:bullet.start("text")] + statement]
    return path, newline.join(lines)


def check_rule_text(path, text, rule_id, project_root, max_statement_chars):
    """The learned rule parses and passes the lint of one rule (atomic and short) before anything is written.
    The other rules of the repository are known ids, so a requires= of the rule finds what it names."""
    rules, findings = agent_ready_rules.parse_rule_text(text, os.path.relpath(path, project_root))
    learned = [rule for rule in rules if rule.id == rule_id]
    known_ids = {item[0].id for item in repository_rules(project_root)} | {rule.id for rule in rules}
    findings = findings + agent_ready_rules.lint_rules(learned, max_statement_chars, max_statement_chars,
                                                       known_ids=known_ids)
    errors = [finding for finding in findings if finding.level == agent_ready_rules.LEVEL_ERROR]
    if errors:
        raise StateError("the learned rule would not be a valid atomic rule, so nothing was written: "
                         + errors[0].render())


def scope(paths):
    return ", ".join(sorted(paths)) or "the whole repository"


def plan_rule(project_root, entry, registry):
    """What writing the entry as a rule does: {action, path, text, ruleId, overrides, supersedes}."""
    described = repository_rules(project_root)
    key = entry.get("key")
    same_key = [item for item in described if key and item[0].key == key]
    # A locked rule stops the learning wherever it is, before anything else is decided.
    for rule, _, source, _ in same_key:
        if rule.locked:
            raise LockedRuleError(f"{source}:{rule.id} decides {key} and is locked: it cannot change, so "
                                  "nothing was saved; tell the user so in one line")
    for rule, _, source, _ in same_key:
        current_scope = rule_scope(project_root, rule)
        if current_scope != sorted(entry.get("paths") or []):
            raise StateError(f"{source}:{rule.id} decides {key} for {scope(current_scope)}, and the instruction is for "
                             f"{scope(entry.get('paths') or [])}: record it with a key of its own for that scope; "
                             "nothing was written")
    own = [rule for rule, managed, _, _ in same_key if not managed]
    # A managed rule a rule of the project already replaces is not active; any other one is.
    replaced_by_project = {reference for rule in own for reference in rule.overrides}
    active = [(rule, managed, source) for rule, managed, source, _ in same_key
              if not (managed and f"{source}:{rule.id}" in replaced_by_project)]
    if own and len(active) > 1:
        names = ", ".join(f"{source}:{rule.id}" for rule, _, source in active)
        raise StateError(f"{names} all decide {key}: editing one would leave the others in force, so nothing was "
                         "written; keep one of them first")
    if own:
        rule = own[0]
        previous = next((item for item in registry["candidates"] if item is not entry
                         and item["status"] == learning.STATUS_LEARNED
                         and item.get("learned", {}).get("ruleId") == rule.id), None)
        path, text = replaced_statement(project_root, rule, entry["statement"])
        return {"action": ACTION_SUPERSEDE if previous else ACTION_UPDATE, "path": path, "text": text,
                "ruleId": rule.id, "overrides": None, "supersedes": previous["id"] if previous else None,
                # What learn revert writes back.
                "previousStatement": rule.statement}
    replaced = []
    for rule, _, source, profile in same_key:
        if profile == BASE_PROFILE_NAME:
            raise StateError(f"{source}:{rule.id} decides {key} and belongs to the core, which a rule cannot "
                             "override yet: nothing was saved")
        if rule.overrides:
            raise StateError(f"{source}:{rule.id} decides {key} and already replaces {', '.join(rule.overrides)}: "
                             "a rule that replaces another cannot be replaced, so nothing was saved")
        reference = f"{source}:{rule.id}"
        # One target, one replacement: a rule of any key that already replaces it wins, and the engine
        # would reject a second one.
        replacing = [other for other, _, _, _ in described if reference in other.overrides]
        if replacing:
            raise StateError(f"{reference} decides {key} and {replacing[0].id} ({replacing[0].path}) already "
                             "replaces it: a rule is replaced once, so nothing was saved")
        replaced.append(reference)
    # Every managed rule of the key is replaced, so none of them stays next to the learned one.
    overrides = ",".join(replaced) or None
    rule_id = unique_rule_id(slug_of(entry), {item[0].id for item in described})
    path, text = appended_rule(project_root, rule_id, entry, overrides)
    return {"action": ACTION_CREATE, "path": path, "text": text, "ruleId": rule_id, "overrides": overrides,
            "supersedes": None}


def plan_skill(project_root, entry, skill_path):
    """What recording a skill the agent wrote does; the skill must be of the project, not managed."""
    if not skill_path:
        raise StateError(f"{entry['id']} is a skill: write it under {PROJECT_SKILLS_RELATIVE_PATH}/<name>/ "
                         "and pass --skill with that directory")
    absolute = os.path.abspath(os.path.join(project_root, skill_path))
    relative = os.path.relpath(absolute, project_root).replace(os.sep, "/")
    if not relative.startswith(PROJECT_SKILLS_RELATIVE_PATH + "/") or relative.count("/") != 2:
        raise StateError(f"--skill {skill_path} must be a directory directly under {PROJECT_SKILLS_RELATIVE_PATH}/")
    if not os.path.isfile(os.path.join(absolute, SKILL_FILE_NAME)):
        raise StateError(f"--skill {skill_path} has no {SKILL_FILE_NAME}")
    if is_managed(project_root, f"{relative}/{SKILL_FILE_NAME}"):
        raise StateError(f"{relative} is managed by a profile; a learned skill never replaces it")
    return {"action": ACTION_CREATE, "path": absolute, "text": None, "skill": relative, "overrides": None,
            "supersedes": None}


def log_line(date, action, entry, written):
    target = written.get("ruleId") or written.get("skill")
    replaced = f", replaces {written['supersedes']}" if written.get("supersedes") else ""
    overrides = f", overrides {written['overrides']}" if written.get("overrides") else ""
    return f"- {date} {action} {entry['id']} ({target}{overrides}{replaced}): {entry['statement']}\n"


def commit(project_root, paths, entry, episodes):
    """One commit with only the files of this learning, whatever else is staged."""
    message = (f"learn: {entry['statement']}\n\nLearning-Id: {entry['id']}\n"
               f"Learned-from: {', '.join(episodes)}\n")
    return commit_paths(project_root, paths, message)


def commit_paths(project_root, paths, message):
    """Commit only ``paths`` (also the ones removed) with ``message``, whatever else is staged; the sha."""
    relative = [os.path.relpath(path, project_root).replace(os.sep, "/") for path in paths]
    for command in (["git", "add", "-A", "--", *relative],
                    ["git", "commit", "--quiet", "-m", message, "--", *relative], ["git", "rev-parse", "HEAD"]):
        result = subprocess.run(command, cwd=project_root, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise StateError(f"agent-ready learn wrote the files but `{' '.join(command[:2])}` failed: "
                             f"{(result.stderr or result.stdout).strip()}; commit them by hand")
    return result.stdout.strip()


def append_log(project_root, line):
    """Add one line to .agents/learning/log.md, creating it with its header; returns its path."""
    log_path = os.path.join(project_root, LOG_RELATIVE_PATH)
    log_text = read_text(log_path) if os.path.exists(log_path) else LOG_HEADER
    write_text_atomically(log_path, log_text + line)
    return log_path


def apply(project_root, candidate_id, settings, skill_path=None, accepted=False):
    """Write one entry that record decided to learn, register it and commit it. Returns what was written.

    ``accepted`` is learn accept: the developer decides, so the rules of evidence and learning.mode do
    not stop it; what the entry may never do (locked, managed, scope) still does."""
    with learning.RegistryLock(project_root):
        registry = learning.read_registry(project_root)
        learning.refresh_expiry(registry, settings["today"], settings["ttl_days"])
        entry = next((item for item in registry["candidates"] if item["id"] == candidate_id), None)
        if entry is None:
            raise StateError(f"no entry has the id {candidate_id} (see agent-ready learn list)")
        if entry["status"] == learning.STATUS_SUPERSEDED:
            raise StateError(f"{candidate_id} was replaced by {entry.get('supersededBy')}: only new evidence "
                             "of the user brings it back")
        if entry["status"] == learning.STATUS_LEARNED:
            raise StateError(f"{candidate_id} is not learned: it is already learned")
        decision = learning.decide(entry, settings["mode"], settings["threshold"], settings["ttl_days"])
        if not accepted and decision != learning.DECISION_LEARN:
            reasons = {learning.DECISION_ALREADY_LEARNED: "it is already learned",
                       learning.DECISION_PROPOSE: "learning.mode is developer-review: the developer decides",
                       learning.DECISION_WAIT: "it waits for another episode, or it expired",
                       learning.DECISION_REJECTED: "the developer rejected it; learn accept brings it back"}
            raise StateError(f"{candidate_id} is not learned: {reasons[decision]}")
        if entry["kind"] == learning.KIND_SKILL:
            written = plan_skill(project_root, entry, skill_path)
        else:
            if entry["kind"] == learning.KIND_NESTED and not entry.get("paths"):
                raise StateError(f"{candidate_id} is only for one folder: record it with --paths")
            written = plan_rule(project_root, entry, registry)
            check_rule_text(written["path"], written["text"], written["ruleId"], project_root,
                            settings["max_statement_chars"])
            write_text_atomically(written["path"], written["text"])
        today = settings["today"].isoformat()
        entry["status"] = learning.STATUS_LEARNED
        entry["learned"] = {field: written[field] for field in ("action", "ruleId", "skill", "overrides",
                                                                "previousStatement") if written.get(field)}
        entry["learned"]["date"] = today
        if accepted:
            entry["learned"]["accepted"] = True
        entry["learned"]["path"] = os.path.relpath(written["path"], project_root).replace(os.sep, "/")
        if written["supersedes"]:
            entry["supersedes"] = written["supersedes"]
            previous = next(item for item in registry["candidates"] if item["id"] == written["supersedes"])
            previous["status"] = learning.STATUS_SUPERSEDED
            previous["supersededBy"] = entry["id"]
        learning.write_registry(project_root, registry)
        log_path = append_log(project_root, log_line(today, written["action"] + (" (accepted)" if accepted else ""),
                                                     entry, written))
        episodes = sorted({item["episode"] for item in learning.live_evidence(entry, settings["ttl_days"])})
        written["commit"] = commit(project_root, [written["path"], learning.candidates_path(project_root), log_path],
                                   entry, episodes)
    written["entry"] = entry
    return written
