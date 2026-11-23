"""Conflicts of the team sync that a person decides, explained in plain words (#169f).

When two machines change the same rule in two ways, the merge drivers (agent_ready_merge_drivers.py)
leave a conflict of that rule only, and the sync aborts the merge (agent_ready_sync.py). This module
records each such rule, with both versions, who wrote each one (its ``Learned-by:``) and when, in the
state of the checkout (``.git/info/agent-ready/sync-conflicts.json``): the machine that met the
conflict is the one that has both versions, so its next session is the one that asks.

The person picks one of four decisions, which ``agent-ready sync --resolve`` stores:

* ``mine``: the version of this machine;
* ``theirs``: the version that came from the remote;
* ``merged``: a statement that combines both, which the agent shows before saving it;
* ``each``: each version stays as the personal rule of the person who taught it (rules of the team only).

The next sync repeats the merge with the decisions (the drivers read them through
``AGENT_READY_MERGE_RESOLUTIONS``), commits it, writes a ``resolve`` line in the log with who decided,
and asks nobody again. Until then the rest goes on synchronizing and nothing is lost: both versions are
in the history.
"""

import datetime
import json
import os
import re
import subprocess

import agent_ready_merge_drivers as drivers
import agent_ready_rules

STATE_GIT_PATH = "info/agent-ready/sync-conflicts.json"
RESOLUTIONS_VARIABLE = drivers.RESOLUTIONS_VARIABLE
DECISION_MINE = "mine"
DECISION_THEIRS = "theirs"
DECISION_MERGED = "merged"
DECISION_EACH = "each"
DECISIONS = (DECISION_MINE, DECISION_THEIRS, DECISION_MERGED, DECISION_EACH)
RULES_PREFIX = ".agents/rules/"
LEARNED_BY = re.compile(r"^Learned-by:\s*(?P<person>\S+)\s*$", re.M)
# How far back the history is read to find the commit that wrote one version of a rule.
RULE_HISTORY_LIMIT = 200
# A scope of the rule: paths in the frontmatter of its file, or the paths= attribute of its marker.
FRONTMATTER_PATHS = re.compile(r"\A---\n(?:(?!---\n).*\n)*?paths\s*:", re.M)
MARKER_PATHS = re.compile(r"<!--.*\bpaths=")


def git(project_root, *arguments):
    return subprocess.run(["git", "-C", project_root, *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                          env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))


def state_path(project_root):
    path = git(project_root, "rev-parse", "--git-path", STATE_GIT_PATH).stdout.strip()
    return path if os.path.isabs(path) else os.path.join(project_root, path)


def read_state(project_root):
    try:
        with open(state_path(project_root), encoding="utf-8") as handle:
            state = json.load(handle)
        return state if isinstance(state, dict) and isinstance(state.get("conflicts"), list) else {"conflicts": []}
    except (OSError, ValueError):
        return {"conflicts": []}


def write_state(project_root, state):
    path = state_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def show(project_root, revision, path):
    result = git(project_root, "show", f"{revision}:{path}")
    return result.stdout if result.returncode == 0 else ""


def person_of(author, body):
    learned_by = LEARNED_BY.search(body)
    return learned_by.group("person") if learned_by else author


def rule_body(project_root, revision, path, rule_id):
    """The lines of one rule of ``path`` at ``revision``, or None when the file or the rule is not there."""
    try:
        _, segments, _ = drivers.rule_segments(show(project_root, revision, path))
    except drivers.Unparsable:
        return None
    return next((body for segment_id, _, body in segments if segment_id == rule_id), None)


def last_change(project_root, revision, path, rule_id, lines):
    """(person, iso time) of the commit of ``revision`` that left the rule ``rule_id`` as ``lines``.

    A file holds several rules, and its last commit may have changed another one: the history is read back
    to the commit whose parent had this rule different."""
    result = git(project_root, "log", f"-{RULE_HISTORY_LIMIT}", "--format=%H%x00%aI%x00%an%x00%B%x01", revision,
                 "--", path)
    if result.returncode != 0:
        return None, None
    for entry in result.stdout.split("\x01"):
        fields = entry.strip("\n").split("\x00", 3)
        if len(fields) < 4:
            continue
        commit, moment, author, body = fields
        if rule_body(project_root, f"{commit}^", path, rule_id) != lines:
            return person_of(author, body), moment.strip()
    return None, None


def scoped(project_root, path, revisions, versions):
    """True when the rule applies to some files only: paths= in its marker, or paths in its file's frontmatter."""
    if any(MARKER_PATHS.search(line) for lines in versions if lines for line in lines):
        return True
    return any(FRONTMATTER_PATHS.search(show(project_root, revision, path).replace("\r\n", "\n"))
               for revision in revisions)


def statement_of(lines):
    rules, _ = agent_ready_rules.parse_rule_text("\n".join(lines or []), "conflict")
    return (rules[0].statement, rules[0].key) if rules else (None, None)


def rule_conflicts(project_root, path, reference):
    """The rules of ``path`` that changed two ways between HEAD and ``reference``."""
    base_revision = git(project_root, "merge-base", "HEAD", reference).stdout.strip()
    versions = [show(project_root, revision, path) for revision in (base_revision, "HEAD", reference)]
    try:
        _, base_segments, _ = drivers.rule_segments(versions[0])
        _, ours_segments, _ = drivers.rule_segments(versions[1])
        _, theirs_segments, _ = drivers.rule_segments(versions[2])
    except drivers.Unparsable:
        return []
    base = {rule_id: body for rule_id, _, body in base_segments}
    ours = {rule_id: body for rule_id, _, body in ours_segments}
    theirs = {rule_id: body for rule_id, _, body in theirs_segments}
    found = []
    for rule_id in sorted(set(ours) | set(theirs)):
        _, conflict = drivers.three_way(base.get(rule_id), ours.get(rule_id), theirs.get(rule_id))
        if not conflict:
            continue
        ours_statement, key = statement_of(ours.get(rule_id))
        theirs_statement, theirs_key = statement_of(theirs.get(rule_id))
        ours_person, ours_time = last_change(project_root, "HEAD", path, rule_id, ours.get(rule_id))
        theirs_person, theirs_time = last_change(project_root, reference, path, rule_id, theirs.get(rule_id))
        found.append({
            "id": f"{path}#{rule_id}", "path": path, "ruleId": rule_id, "key": key or theirs_key,
            "personal": agent_ready_rules.PERSONAL_RULES_PATTERN.search(path) is not None,
            "scoped": scoped(project_root, path, ("HEAD", reference), (ours.get(rule_id), theirs.get(rule_id))),
            "mine": {"lines": ours.get(rule_id), "statement": ours_statement, "by": ours_person, "at": ours_time},
            "theirs": {"lines": theirs.get(rule_id), "statement": theirs_statement, "by": theirs_person,
                       "at": theirs_time},
        })
    return found


def record(project_root, files, reference):
    """Record the rule conflicts of a merge in progress; returns (recorded, files they do not explain).

    A conflict that already has a decision keeps it while the versions are the same. So does a decided
    conflict of a file the decision merged: the merge was aborted for another file, and the sync needs that
    decision again when it repeats the whole merge."""
    state = read_state(project_root)
    known = {conflict["id"]: conflict for conflict in state["conflicts"]}
    current = []
    unexplained = []
    for path in files:
        conflicts = rule_conflicts(project_root, path, reference) if path.startswith(RULES_PREFIX) else []
        if not conflicts:
            unexplained.append(path)
        for conflict in conflicts:
            previous = known.get(conflict["id"])
            if previous and previous.get("decision") and previous["mine"]["lines"] == conflict["mine"]["lines"] \
                    and previous["theirs"]["lines"] == conflict["theirs"]["lines"]:
                conflict.update({field: previous[field] for field in ("decision", "decidedBy", "statement")
                                 if field in previous})
            conflict.setdefault("detected", datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
                                .isoformat())
            current.append(conflict)
    recorded_ids = {conflict["id"] for conflict in current}
    kept = [conflict for conflict in state["conflicts"]
            if conflict.get("decision") and conflict["path"] not in files and conflict["id"] not in recorded_ids]
    state["conflicts"] = kept + current
    write_state(project_root, state)
    return current, unexplained


def pending(project_root):
    return [conflict for conflict in read_state(project_root)["conflicts"] if not conflict.get("decision")]


def decide(project_root, conflict_id, decision, person, statement=None):
    """Store the decision of a person for one conflict; returns the conflict."""
    state = read_state(project_root)
    conflict = next((item for item in state["conflicts"] if item["id"] == conflict_id), None)
    if conflict is None:
        raise ValueError(f"no conflict of the sync has the id {conflict_id} (see agent-ready sync --conflicts)")
    if decision == DECISION_MERGED and not (statement or "").strip():
        raise ValueError("--merged needs the statement that combines both versions")
    if decision == DECISION_EACH and conflict.get("personal"):
        raise ValueError("each one keeps theirs is for a rule of the team; this one is already personal")
    if decision == DECISION_EACH and conflict["mine"].get("by") and \
            conflict["mine"].get("by") == conflict["theirs"].get("by"):
        raise ValueError("both versions are from the same person, who cannot keep two of their own: keep one "
                         "(--keep mine or --keep theirs) or combine them (--merged)")
    if decision == DECISION_EACH and conflict.get("scoped"):
        raise ValueError("this rule applies to some files only, and a personal rule applies to the whole "
                         "repository: keep one (--keep mine or --keep theirs) or combine them (--merged)")
    conflict["decision"] = decision
    conflict["decidedBy"] = person
    if decision == DECISION_MERGED:
        conflict["statement"] = " ".join(statement.split())
    write_state(project_root, state)
    return conflict


def resolution_lines(conflict):
    """The lines the merge keeps for the rule of a decided conflict; None removes it from the file."""
    decision = conflict["decision"]
    if decision == DECISION_MINE:
        return conflict["mine"]["lines"]
    if decision == DECISION_THEIRS:
        return conflict["theirs"]["lines"]
    if decision == DECISION_EACH:
        return None
    marker = next((line for line in (conflict["mine"]["lines"] or conflict["theirs"]["lines"])
                   if line.lstrip().startswith("<!--")), f"<!-- rule id={conflict['ruleId']} -->")
    return [marker, f"- {conflict['statement']}"]


def resolutions_file(project_root):
    """A file with {path: {rule id: lines}} of the decided conflicts for the drivers, or None."""
    decided = [conflict for conflict in read_state(project_root)["conflicts"] if conflict.get("decision")]
    if not decided:
        return None
    resolutions = {}
    for conflict in decided:
        # With the versions the person saw: a rule that changed since conflicts again (decided_lines).
        resolutions.setdefault(conflict["path"], {})[conflict["ruleId"]] = {
            "lines": resolution_lines(conflict), "mine": conflict["mine"]["lines"],
            "theirs": conflict["theirs"]["lines"]}
    path = state_path(project_root) + ".resolutions"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(resolutions, handle, ensure_ascii=False)
    return path


def explanation(conflicts):
    """What the agent tells the person at the start of a session, with the data to say it plainly."""
    lines = ["[agent-ready sync] Two people changed the same rule in different ways. Explain each conflict to "
             "the user in plain words, without Git terms: who changed it and when, and the difference. Offer: keep "
             "the version of this machine (`--keep mine`), keep the other one (`--keep theirs`), combine both (show "
             "the combined statement and save it only after the user agrees, `--merged \"<statement>\"`), or, for "
             "a rule of the team, each one keeps their own as a personal rule (`--each-their-own`). Run "
             "`agent-ready sync --resolve <id> <option>` with what the user chooses; nobody is asked again."]
    for conflict in conflicts:
        mine, theirs = conflict["mine"], conflict["theirs"]
        lines.append(f"  {conflict['id']}" + (f" (key {conflict['key']})" if conflict.get("key") else ""))
        lines.append(f"    this machine, {mine.get('by') or 'unknown'} at {mine.get('at') or '?'}: "
                     f"{mine.get('statement') or '(removed)'}")
        lines.append(f"    the other, {theirs.get('by') or 'unknown'} at {theirs.get('at') or '?'}: "
                     f"{theirs.get('statement') or '(removed)'}")
    return "\n".join(lines) + "\n"


def finish(project_root, append_personal, append_log):
    """After the merge with the decisions: the personal rules of «each one keeps theirs», a log line per
    decision, and the decided conflicts out of the state. Returns the paths it wrote."""
    state = read_state(project_root)
    decided = [conflict for conflict in state["conflicts"] if conflict.get("decision")]
    written = []
    today = datetime.date.today().isoformat()
    for conflict in decided:
        if conflict["decision"] == DECISION_EACH:
            for side in (conflict["mine"], conflict["theirs"]):
                if side.get("statement") and side.get("by"):
                    written.append(append_personal(side["by"], conflict, side["statement"]))
        written.append(append_log(f"- {today} resolve {conflict['ruleId']} ({conflict['decision']}, decided by "
                                  f"{conflict.get('decidedBy') or 'unknown'}): two versions of the same rule\n"))
    state["conflicts"] = [conflict for conflict in state["conflicts"] if not conflict.get("decision")]
    write_state(project_root, state)
    return [path for path in written if path]
