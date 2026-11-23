"""The rule conflicts of a merge the developer does, in the ``software`` collaboration preset (#169g).

In a repository of code there is no team sync: what is learned is a commit of the current branch and
travels in its pull request (agent_ready_identity.py). The merge drivers of the learning
(agent_ready_merge_drivers.py) integrate two branches that learned different rules. Two branches that
changed the same rule in different ways leave a conflict of that rule only, in the merge the developer
is doing (``git merge``, a pull, the merge of a pull request locally).

The agent explains it at the start of the session, or whenever it runs ``agent-ready sync
--conflicts``, and proposes what to keep: this branch, the other one or a statement that combines both.
``agent-ready sync --resolve`` writes the decided rule into the file and stages it when nothing else of
the file conflicts. It never commits, pulls nor pushes: the merge stays the developer's.
"""

import json
import os
import subprocess

import agent_ready_merge_drivers as drivers
import agent_ready_sync_conflicts as sync_conflicts

STATE_GIT_PATH = "info/agent-ready/branch-conflicts.json"
MERGE_HEAD = "MERGE_HEAD"
RULES_PREFIX = sync_conflicts.RULES_PREFIX
# Each-their-own makes personal rules, which a repository of code does not have.
DECISIONS = (sync_conflicts.DECISION_MINE, sync_conflicts.DECISION_THEIRS, sync_conflicts.DECISION_MERGED)


def git(project_root, *arguments):
    return subprocess.run(["git", "-C", project_root, *arguments], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))


def git_path(project_root, relative):
    path = git(project_root, "rev-parse", "--git-path", relative).stdout.strip()
    return path if os.path.isabs(path) else os.path.join(project_root, path)


def merge_head(project_root):
    """The commit being merged into this checkout, or None when no merge waits."""
    if not os.path.exists(git_path(project_root, MERGE_HEAD)):
        return None
    head = git(project_root, "rev-parse", "--verify", "--quiet", MERGE_HEAD).stdout.strip()
    return head or None


def unmerged_rule_files(project_root):
    files = git(project_root, "diff", "--name-only", "--diff-filter=U").stdout.split()
    return [path for path in files if path.startswith(RULES_PREFIX)]


def read_decisions(project_root, head):
    """{conflict id: {decision, statement}} taken for the merge of ``head``; another merge starts empty."""
    try:
        with open(git_path(project_root, STATE_GIT_PATH), encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return {}
    return state.get("decisions", {}) if isinstance(state, dict) and state.get("mergeHead") == head else {}


def write_decisions(project_root, head, decisions):
    path = git_path(project_root, STATE_GIT_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"mergeHead": head, "decisions": decisions}, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def conflicts(project_root):
    """The rules the two branches of the merge in progress changed in different ways, not decided yet."""
    head = merge_head(project_root)
    if not head:
        return []
    decided = read_decisions(project_root, head)
    found = []
    for path in unmerged_rule_files(project_root):
        found.extend(conflict for conflict in sync_conflicts.rule_conflicts(project_root, path, MERGE_HEAD)
                     if conflict["id"] not in decided)
    return found


def explanation(found):
    """What the agent tells the developer: who changed each rule and when, and what it can keep."""
    lines = ["[agent-ready] The merge in progress has rules that the two branches changed in different ways. "
             "Explain each one to the developer: who changed it and when, and the difference. Propose a version: "
             "this branch (`--keep mine`), the other branch (`--keep theirs`), or a statement that combines both, "
             "shown before it is saved (`--merged \"<statement>\"`). Run `agent-ready sync --resolve <id> "
             "<option>`; it writes the rule and stages its file. The merge commit stays the developer's."]
    for conflict in found:
        mine, theirs = conflict["mine"], conflict["theirs"]
        lines.append(f"  {conflict['id']}" + (f" (key {conflict['key']})" if conflict.get("key") else ""))
        lines.append(f"    this branch, {mine.get('by') or 'unknown'} at {mine.get('at') or '?'}: "
                     f"{mine.get('statement') or '(removed)'}")
        lines.append(f"    the other branch, {theirs.get('by') or 'unknown'} at {theirs.get('at') or '?'}: "
                     f"{theirs.get('statement') or '(removed)'}")
    return "\n".join(lines) + "\n"


def stage_text(project_root, stage, path):
    result = git(project_root, "show", f":{stage}:{path}")
    return result.stdout if result.returncode == 0 else ""


def resolve(project_root, conflict_id, decision, statement=None):
    """Write the decision into the file of the rule; returns (path, staged).

    The file is merged again from its three versions with every rule decided in this merge, so the
    decisions of the other rules of the file stay. It is staged only when no rule of it conflicts."""
    head = merge_head(project_root)
    if not head:
        raise ValueError("no merge is in progress in this checkout")
    if decision not in DECISIONS:
        raise ValueError("a repository of code has no personal rules: keep one version (--keep mine or --keep "
                         "theirs) or combine them (--merged)")
    decided = read_decisions(project_root, head)
    every = {conflict["id"]: conflict for path in unmerged_rule_files(project_root)
             for conflict in sync_conflicts.rule_conflicts(project_root, path, MERGE_HEAD)}
    conflict = every.get(conflict_id)
    if conflict is None:
        raise ValueError(f"no rule of the merge in progress has the id {conflict_id} (see agent-ready sync --conflicts)")
    if decision == sync_conflicts.DECISION_MERGED and not (statement or "").strip():
        raise ValueError("--merged needs the statement that combines both versions")
    if decision == sync_conflicts.DECISION_MERGED and \
            sync_conflicts.details_of(conflict["mine"]["lines"]) != sync_conflicts.details_of(conflict["theirs"]["lines"]):
        raise ValueError("the two versions also differ in their exceptions or details, which a combined statement "
                         "would lose: keep one (--keep mine or --keep theirs) and change it afterwards")
    decided[conflict_id] = {"decision": decision, "statement": " ".join((statement or "").split()) or None}
    write_decisions(project_root, head, decided)
    path = conflict["path"]
    resolutions = {}
    for other_id, choice in decided.items():
        other = every.get(other_id)
        if other is None or other["path"] != path:
            continue
        lines = sync_conflicts.resolution_lines(dict(other, decision=choice["decision"], statement=choice["statement"]))
        resolutions[other["ruleId"]] = {"lines": lines, "mine": other["mine"]["lines"], "theirs": other["theirs"]["lines"]}
    versions = [stage_text(project_root, stage, path) for stage in (1, 2, 3)]
    merged, left = drivers.merge_rules(*versions, resolutions)
    with open(os.path.join(project_root, path), "w", encoding="utf-8", newline="") as handle:
        handle.write(merged)
    staged = not left and git(project_root, "add", "--", path).returncode == 0
    return path, staged
