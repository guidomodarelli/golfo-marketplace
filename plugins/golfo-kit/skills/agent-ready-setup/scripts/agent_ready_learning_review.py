"""What the developer decides about what the agent learned: reject a candidate or revert a learning.

The agent learns on its own from fixed rules of evidence (agent_ready_learning_apply); the developer
reviews it afterwards. reject keeps an instruction from being learned until the developer accepts it,
and revert undoes the change a learning made to its rule or skill, with a commit of its own, leaving
the later changes of the same files in place (references/learning.md, «Revisar lo aprendido»).
"""

import os
import subprocess

import agent_ready_learning as learning
import agent_ready_rules
from agent_ready_common import StateError, write_text_atomically
from agent_ready_learning_apply import (
    ACTION_CREATE,
    append_log,
    commit_paths,
    learned_file,
    read_text,
    replaced_statement,
)

# The tree of no files, which git knows without it being in the repository: what a root commit is compared to.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def git(project_root, *arguments):
    return subprocess.run(["git", *arguments], cwd=project_root, capture_output=True, text=True, check=False)


def git_bytes(project_root, *arguments, input_bytes=None):
    """git with bytes in and out: a patch passed as text would get CRLF line endings on Windows."""
    return subprocess.run(["git", *arguments], cwd=project_root, input=input_bytes, capture_output=True, check=False)


def find_entry(registry, candidate_id):
    entry = next((item for item in registry["candidates"] if item["id"] == candidate_id), None)
    if entry is None:
        raise StateError(f"no entry has the id {candidate_id} (see agent-ready learn list)")
    return entry


def reject(project_root, candidate_id, settings):
    """Mark an entry that is not learned as rejected and commit the registry; returns (entry, sha)."""
    with learning.RegistryLock(project_root):
        registry = learning.read_registry(project_root)
        learning.refresh_expiry(registry, settings["today"], settings["ttl_days"])
        entry = find_entry(registry, candidate_id)
        if entry["status"] == learning.STATUS_LEARNED:
            raise StateError(f"{candidate_id} is learned: undo it with agent-ready learn revert {candidate_id}")
        if entry["status"] == learning.STATUS_REJECTED:
            raise StateError(f"{candidate_id} is already rejected")
        if entry["status"] == learning.STATUS_SUPERSEDED:
            # Reverting the newer one gives this text back as learned: a rejection could not hold.
            raise StateError(f"{candidate_id} is superseded by {entry.get('supersededBy')} and not in force; reverting "
                             f"{entry.get('supersededBy')} would bring it back, so revert that first and then "
                             f"revert {candidate_id}")
        entry["status"] = learning.STATUS_REJECTED
        entry["rejected"] = {"date": settings["today"].isoformat()}
        learning.write_registry(project_root, registry)
        log_path = append_log(project_root, f"- {settings['today'].isoformat()} reject {entry['id']}: "
                                            f"{entry['statement']}\n")
        sha = commit_paths(project_root, [learning.candidates_path(project_root), log_path],
                           f"learn: reject {entry['statement']}\n\nLearning-Id: {entry['id']}\n")
    return entry, sha


def learning_commit(project_root, entry):
    """The sha of the commit that wrote the learning: the newest with its Learning-Id and its file."""
    result = git(project_root, "log", "--format=%H", "--fixed-strings", f"--grep=Learning-Id: {entry['id']}",
                 "--", entry["learned"]["path"])
    shas = result.stdout.split()
    if result.returncode != 0 or not shas:
        raise StateError(f"no commit with Learning-Id: {entry['id']} changed {entry['learned']['path']}; "
                         "undo it by hand")
    return shas[0]


def reverse_patch(project_root, sha, path):
    """Undo in the working tree what ``sha`` did to ``path``, keeping the later changes; nothing on conflict."""
    has_parent = git(project_root, "rev-parse", "--verify", "--quiet", f"{sha}^").returncode == 0
    diff = git_bytes(project_root, "diff", "--binary", f"{sha}^" if has_parent else EMPTY_TREE, sha, "--", path)
    if diff.returncode != 0 or not diff.stdout:
        raise StateError(f"commit {sha[:12]} has no change of {path} to undo")
    check = git_bytes(project_root, "apply", "--reverse", "--check", input_bytes=diff.stdout)
    if check.returncode != 0:
        raise StateError(f"{path} changed after commit {sha[:12]} in the lines the learning wrote: "
                         f"{check.stderr.decode(errors='replace').strip()}; nothing was reverted, undo it by hand")
    applied = git_bytes(project_root, "apply", "--reverse", input_bytes=diff.stdout)
    if applied.returncode != 0:
        raise StateError(f"could not undo {path}: {applied.stderr.decode(errors='replace').strip()}")


def revert_rule(project_root, entry):
    """Undo a learning in its rule by the rule's id, so the rules around it do not matter: a rule the
    learning created goes away (and its learned file with it, once empty), and a rule it edited gets its
    previous statement back. A rule edited since then is left alone."""
    learned = entry["learned"]
    path = os.path.join(project_root, learned["path"])
    text = read_text(path) if os.path.exists(path) else ""
    rules, _ = agent_ready_rules.parse_rule_text(text, learned["path"])
    rule = next((item for item in rules if item.id == learned["ruleId"]), None)
    if rule is None or learning.normalized_statement(rule.statement) != learning.normalized_statement(entry["statement"]):
        raise StateError(f"{learned['path']} changed after the learning: rule {learned['ruleId']} no longer says "
                         f"what {entry['id']} wrote; nothing was reverted, undo it by hand")
    if learned["action"] != ACTION_CREATE:
        _, new_text = replaced_statement(project_root, rule, learned["previousStatement"])
        write_text_atomically(path, new_text)
        return
    marker = learned.get("marker") or {"key": entry.get("key"), "paths": sorted(entry.get("paths") or [])}
    written_marker = (marker["key"], marker["paths"],
                      sorted((learned.get("overrides") or "").split(",")) if learned.get("overrides") else [], [], False)
    if (rule.key, sorted(rule.paths), sorted(rule.overrides), sorted(rule.requires), rule.locked) != written_marker:
        # The marker apply wrote changed (locked, requires, paths...): the rule is the team's now.
        raise StateError(f"rule {rule.id} in {learned['path']} has a marker someone changed after the learning; "
                         "nothing was reverted, undo it by hand")
    if rule.exceptions or rule.details:
        # A created rule has only its statement: what is under it, someone added afterwards.
        raise StateError(f"rule {rule.id} in {learned['path']} has exceptions or details someone added after the "
                         f"learning; nothing was reverted, undo it by hand")
    new_text = agent_ready_rules.remove_rules(text, {rule.id})
    learned_path, header = learned_file(project_root, entry.get("paths") or [])
    if learned_path == learned["path"] and new_text.replace("\r\n", "\n").strip() == header.strip():
        # Only the header apply wrote is left: the file goes. Anything the team added keeps it.
        os.remove(path)
        return
    write_text_atomically(path, new_text)


def revert(project_root, candidate_id, settings):
    """Undo a learning: its rule or skill goes back to what it was before, the entry it replaced is
    learned again, and a commit records it. Returns (entry, sha of the learning, sha of the revert)."""
    with learning.RegistryLock(project_root):
        registry = learning.read_registry(project_root)
        entry = find_entry(registry, candidate_id)
        if entry["status"] != learning.STATUS_LEARNED:
            raise StateError(f"{candidate_id} is {entry['status']}, not learned: there is nothing to revert")
        sha = learning_commit(project_root, entry)
        path = entry["learned"]["path"]
        # The text this learning replaced comes back, so its entry is learned again, whatever new evidence
        # did to it since; a rejection would not hold, so it stops the revert before anything changes.
        previous = next((item for item in registry["candidates"] if item["id"] == entry.get("supersedes")), None)
        if previous is not None and previous["status"] == learning.STATUS_REJECTED:
            raise StateError(f"reverting {candidate_id} brings back the text of {previous['id']}, which the developer "
                             f"rejected: accept {previous['id']} first, or edit {path} by hand; nothing was reverted")
        if entry["learned"].get("ruleId"):
            revert_rule(project_root, entry)
        else:
            reverse_patch(project_root, sha, path)
        today = settings["today"].isoformat()
        entry["status"] = learning.STATUS_REVERTED
        entry["reverted"] = {"date": today, "commit": sha}
        if previous is not None and previous["status"] in (learning.STATUS_SUPERSEDED, learning.STATUS_CANDIDATE,
                                                           learning.STATUS_EXPIRED):
            previous["status"] = learning.STATUS_LEARNED
            previous.pop("supersededBy", None)
        learning.write_registry(project_root, registry)
        log_path = append_log(project_root, f"- {today} revert {entry['id']} ({path}, commit {sha[:12]}): "
                                            f"{entry['statement']}\n")
        revert_sha = commit_paths(project_root,
                                  [os.path.join(project_root, path), learning.candidates_path(project_root), log_path],
                                  f"learn: revert {entry['statement']}\n\nLearning-Id: {entry['id']}\n"
                                  f"Reverts: {sha}\n")
    return entry, sha, revert_sha
