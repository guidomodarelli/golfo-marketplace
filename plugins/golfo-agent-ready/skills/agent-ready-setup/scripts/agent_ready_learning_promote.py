"""Promote what several clients learned to a profile of a pack, by pull request, and spot the learned rule
the profile now says too.

learn promote takes a candidate of learn harvest (or one learned rule of this repository) and writes it as
a rule of a profile in the clone of the pack the developer has. Without --yes it only prints the change:
the clone of the pack is not touched. With --yes it writes the rule on a new branch of that clone, commits
it, pushes the branch and opens the pull request; the branch the clone was on stays checked out. Nothing
of a client travels to the pack: the statement is the general one, and the pull request says how many
repositories learned it, never which.

Once the pack publishes the rule and a repository updates its profile, the plan finds the learned rule
that says the same as a rule of the profile (duplicates) and offers to retire it with learn retire, which
the developer confirms by running it (references/learning.md, «Promover a un pack»).
"""

import difflib
import os
import re
import shutil
import subprocess
import unicodedata

import agent_ready_learning as learning
import agent_ready_rules
from agent_ready_common import StateError, read_json_file, serialize_json, write_text_atomically
from agent_ready_learning_share import HARVEST_ID_PREFIX, harvest_path

PACK_MANIFEST = "agent-ready-pack.json"
PROFILE_RULES_DIRECTORY = "rules"
DEFAULT_PROMOTED_FILE = "rules/promoted.md"
PROMOTED_FILE_HEADER = ("# Promoted rules\n\nRules that several clients learned and the developer promoted to the "
                        "profile (agent-ready learn promote).\n")
BRANCH_PREFIX = "learn/promote-"
SLUG_WORDS = 6
WORD = re.compile(r"[a-z0-9]+")

ACTION_ADD = "add"
ACTION_UPDATE = "update"


def promote_slug(item):
    """The id of the promoted rule: its key with dashes, or the first words of its statement."""
    if item.get("key"):
        return item["key"].replace(".", "-")
    ascii_text = unicodedata.normalize("NFKD", item["statement"]).encode("ascii", "ignore").decode().lower()
    return "-".join(WORD.findall(ascii_text)[:SLUG_WORDS]) or item["id"].split("-", 1)[-1]


def harvest_candidate(candidate_id):
    path = harvest_path()
    if not os.path.exists(path):
        raise StateError(f"there is no harvest to promote {candidate_id} from: run agent-ready learn harvest first")
    report = read_json_file(path, "the last harvest")
    for candidate in report.get("candidates") or []:
        if candidate.get("id") == candidate_id:
            return {"id": candidate_id, "statement": candidate["statement"], "kind": candidate.get("kind"),
                    "key": candidate.get("key"), "paths": candidate.get("paths") or [],
                    "repositories": len(candidate.get("repositories") or [])}
    raise StateError(f"{candidate_id} is not a candidate of the last harvest ({path}); run agent-ready learn harvest "
                     "again")


def learned_item(project_root, candidate_id):
    registry = learning.read_registry(project_root)
    entry = next((item for item in registry["candidates"] if item["id"] == candidate_id), None)
    if entry is None:
        raise StateError(f"there is no entry {candidate_id} in .agents/learning/{learning.CANDIDATES_FILE_NAME}")
    if entry["status"] != learning.STATUS_LEARNED:
        raise StateError(f"{candidate_id} is {entry['status']}, not learned: only what a repository learned is promoted")
    return {"id": candidate_id, "statement": entry["statement"], "kind": entry["kind"], "key": entry.get("key"),
            "paths": entry.get("paths") or [], "repositories": 1}


def resolve_item(candidate_id, project_root):
    """What to promote: a candidate of the last harvest, or one learned entry of this repository."""
    item = harvest_candidate(candidate_id) if candidate_id.startswith(HARVEST_ID_PREFIX) \
        else learned_item(project_root, candidate_id)
    if item["kind"] != learning.KIND_RULE:
        raise StateError(f"{candidate_id} is a {item['kind']}: learn promote writes rules; copy a skill to the profile "
                         "by hand")
    return item


def pack_profile_root(pack_root, profile):
    """(pack name, profile name, asset root) of a profile of the pack in ``pack_root``."""
    manifest_path = os.path.join(pack_root, PACK_MANIFEST)
    if not os.path.isfile(manifest_path):
        raise StateError(f"{pack_root} is not a pack: it has no {PACK_MANIFEST}")
    manifest = read_json_file(manifest_path, "the pack manifest")
    profiles = {name: entry for name, entry in (manifest.get("profiles") or {}).items()
                if isinstance(entry, dict) and entry.get("assets")}
    if profile is None:
        if len(profiles) != 1:
            raise StateError(f"name the profile with --profile: {pack_root} has {', '.join(sorted(profiles)) or 'none'}")
        profile = next(iter(profiles))
    if profile not in profiles:
        raise StateError(f"the pack {manifest.get('name')} has no profile '{profile}' with assets; it has "
                         f"{', '.join(sorted(profiles)) or 'none'}")
    real_pack = os.path.realpath(pack_root)
    asset_root = os.path.realpath(os.path.join(pack_root, profiles[profile]["assets"]))
    if os.path.commonpath([real_pack, asset_root]) != real_pack:
        raise StateError(f"the assets of '{profile}' are outside {pack_root}")
    return manifest.get("name"), profile, asset_root


def read_text(path):
    with open(path, encoding="utf-8", newline="") as file_handle:
        return file_handle.read()


def pack_rules(pack_root):
    """Every rule of every profile of the pack: the ids of a pack are shared by all its profiles."""
    manifest = read_json_file(os.path.join(pack_root, PACK_MANIFEST), "the pack manifest")
    found = []
    for entry in (manifest.get("profiles") or {}).values():
        if not isinstance(entry, dict) or not entry.get("assets"):
            continue
        rules_root = os.path.join(pack_root, entry["assets"], PROFILE_RULES_DIRECTORY)
        for path in agent_ready_rules.rule_files(rules_root) if os.path.isdir(rules_root) else []:
            rules, _ = agent_ready_rules.parse_rule_text(read_text(path), path)
            found.extend((path, rule) for rule in rules)
    return found


def marker_of(rule_id, item):
    attributes = [f"id={rule_id}"]
    if item.get("key"):
        attributes.append(f"key={item['key']}")
    if item["paths"]:
        attributes.append("paths=" + ",".join(sorted(item["paths"])))
    return f"<!-- rule {' '.join(attributes)} -->"


def updated_statement(text, rule, statement):
    """``text`` with the statement of ``rule`` replaced; its marker, exceptions and details stay."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    index = rule.line - 1
    bullet = agent_ready_rules.rule_format_module().TOP_LEVEL_BULLET.match(lines[index])
    statement_end = index + 1
    for position in range(index + 1, rule.span[1]):
        if agent_ready_rules.SUB_ITEM.match(lines[position]):
            break
        if lines[position].strip():
            statement_end = position + 1
    lines[index:statement_end] = [lines[index][:bullet.start("text")] + statement]
    return newline.join(lines)


def plan(item, pack_root, profile, file_name, max_statement_chars):
    """The change in the pack, without writing it: the file, the action, the rule id and the new text."""
    pack_name, profile, asset_root = pack_profile_root(pack_root, profile)
    existing = pack_rules(pack_root)
    profile_rules = [(path, rule) for path, rule in existing
                     if os.path.commonpath([os.path.realpath(path), asset_root]) == asset_root]
    wanted = (learning.normalized_statement(item["statement"]), tuple(sorted(item["paths"])))
    for _path, rule in profile_rules:
        if (learning.normalized_statement(rule.statement), tuple(sorted(rule.paths))) == wanted:
            raise StateError(f"{pack_name}:{rule.id} of '{profile}' already says it: there is nothing to promote")
    same_key = [(path, rule) for path, rule in profile_rules if item.get("key") and rule.key == item["key"]]
    if len(same_key) > 1:
        raise StateError(f"'{profile}' has {len(same_key)} rules with the key {item['key']}; leave one before promoting")
    if same_key:
        path, rule = same_key[0]
        if rule.locked:
            raise StateError(f"{pack_name}:{rule.id} is locked: a promotion never changes it")
        if sorted(rule.paths) != sorted(item["paths"]):
            raise StateError(f"{pack_name}:{rule.id} has the key {item['key']} for another scope "
                             f"({', '.join(rule.paths) or 'the whole repository'}); promote it by hand")
        action, rule_id, before = ACTION_UPDATE, rule.id, read_text(path)
        after = updated_statement(before, rule, item["statement"])
    else:
        taken = {rule.id for _, rule in existing}
        base_id, suffix = promote_slug(item), 2
        rule_id = base_id
        while rule_id in taken:
            rule_id, suffix = f"{base_id}-{suffix}", suffix + 1
        path = os.path.join(asset_root, *file_name.split("/"))
        if os.path.commonpath([os.path.realpath(os.path.dirname(path)), asset_root]) != asset_root \
                or not file_name.startswith(PROFILE_RULES_DIRECTORY + "/") or not file_name.endswith(".md"):
            raise StateError(f"--file must be a .md file under {PROFILE_RULES_DIRECTORY}/ of the profile: {file_name}")
        before = read_text(path) if os.path.exists(path) else ""
        text = before or PROMOTED_FILE_HEADER
        newline = "\r\n" if "\r\n" in text else "\n"
        block = newline.join([marker_of(rule_id, item), f"- {item['statement']}"]) + newline
        action, after = ACTION_ADD, text.rstrip("\r\n") + newline + newline + block
    relative = os.path.relpath(path, pack_root).replace(os.sep, "/")
    rules, findings = agent_ready_rules.parse_rule_text(after, relative)
    promoted = [rule for rule in rules if rule.id == rule_id]
    known_ids = {rule.id for _, rule in existing} | {rule.id for rule in rules}
    findings = findings + agent_ready_rules.lint_rules(promoted, max_statement_chars, max_statement_chars,
                                                       known_ids=known_ids)
    errors = [finding for finding in findings if finding.level == agent_ready_rules.LEVEL_ERROR]
    if errors:
        raise StateError("the promoted rule would not be a valid atomic rule, so nothing was written: "
                         + errors[0].render())
    diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile=f"a/{relative}", tofile=f"b/{relative}"))
    return {"id": item["id"], "statement": item["statement"], "pack": pack_name, "profile": profile,
            "file": relative, "action": action, "ruleId": rule_id, "rule": f"{pack_name}:{rule_id}",
            "repositories": item["repositories"], "diff": diff, "path": path, "text": after, "new": not before}


def git(pack_root, *arguments):
    result = subprocess.run(["git", *arguments], cwd=pack_root, capture_output=True, text=True, check=False)
    return result.returncode, (result.stdout or "").strip(), (result.stderr or result.stdout or "").strip()


def require_git(pack_root, *arguments):
    code, output, problem = git(pack_root, *arguments)
    if code != 0:
        raise StateError(f"`git {' '.join(arguments[:2])}` failed in {pack_root}: {problem}")
    return output


def pull_request_body(change):
    learned_by = (f"{change['repositories']} client repositories learned it"
                  if change["repositories"] > 1 else "one client repository learned it")
    verb = "Adds" if change["action"] == ACTION_ADD else "Changes the statement of"
    return (f"{verb} the rule `{change['rule']}` of the profile `{change['profile']}`:\n\n"
            f"> {change['statement']}\n\n"
            f"{learned_by} (agent-ready learn harvest, `{change['id']}`). The statement is the general one, without "
            "data of any client.\n\nBefore merging: bump the version of the pack. Once a repository updates the "
            "profile, its plan shows the learned rule that says the same as a duplicate to retire.\n")


def write(change, pack_root, open_pull_request):
    """Write the change on a new branch of the clone, commit it, push it and open the pull request."""
    require_git(pack_root, "rev-parse", "--is-inside-work-tree")
    if require_git(pack_root, "status", "--porcelain"):
        raise StateError(f"{pack_root} has uncommitted changes: commit or stash them before promoting")
    code, original, _ = git(pack_root, "symbolic-ref", "--quiet", "--short", "HEAD")
    original = original if code == 0 else require_git(pack_root, "rev-parse", "HEAD")
    branch = BRANCH_PREFIX + change["ruleId"].replace("/", "-")
    if git(pack_root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0:
        raise StateError(f"the branch {branch} already exists in {pack_root}: delete it or merge its pull request first")
    require_git(pack_root, "switch", "--quiet", "-c", branch)
    back = ["switch", "--quiet", "--discard-changes"] + ([original] if code == 0 else ["--detach", original])
    try:
        os.makedirs(os.path.dirname(change["path"]), exist_ok=True)
        write_text_atomically(change["path"], change["text"])
        require_git(pack_root, "add", "--", change["file"])
        require_git(pack_root, "commit", "--quiet", "-m",
                    f"feat({change['profile']}): promote {change['statement']}\n\nPromoted-from: {change['id']}\n",
                    "--", change["file"])
        commit = require_git(pack_root, "rev-parse", "HEAD")
    except StateError:
        # Nothing half done stays: the clone goes back to where it was and the empty branch goes away.
        git(pack_root, "reset", "--quiet", "--", change["file"])
        if change["new"] and os.path.exists(change["path"]):
            os.remove(change["path"])
        git(pack_root, *back)
        git(pack_root, "branch", "--quiet", "-D", branch)
        raise
    # The clone goes back to the branch the developer had checked out; the rule lives on the new branch.
    require_git(pack_root, *back)
    result = {"branch": branch, "commit": commit, "pullRequest": None}
    if not open_pull_request:
        return result
    push_code, _, push_problem = git(pack_root, "push", "--quiet", "-u", "origin", branch)
    if push_code != 0:
        raise StateError(f"the rule is committed on {branch} ({commit[:12]}) but the push failed: {push_problem}; push "
                         "it and open the pull request by hand")
    created = subprocess.run([shutil.which("gh") or "gh", "pr", "create", "--head", branch, "--title",
                              f"Promote: {change['statement']}", "--body-file", "-"],
                             input=pull_request_body(change), cwd=pack_root, capture_output=True, text=True,
                             encoding="utf-8", check=False)
    if created.returncode != 0:
        raise StateError(f"{branch} is pushed but `gh pr create` failed: {(created.stderr or created.stdout).strip()}; "
                         "open the pull request by hand")
    result["pullRequest"] = created.stdout.strip().splitlines()[-1] if created.stdout.strip() else None
    return result


def record_promotion(change, written, today):
    """Mark the harvest candidate as promoted, so the next harvest report shows where it went."""
    if not change["id"].startswith(HARVEST_ID_PREFIX) or not os.path.exists(harvest_path()):
        return
    report = read_json_file(harvest_path(), "the last harvest")
    for candidate in report.get("candidates") or []:
        if candidate.get("id") == change["id"]:
            candidate["promoted"] = {"rule": change["rule"], "profile": change["profile"], "branch": written["branch"],
                                     "pullRequest": written["pullRequest"], "date": today.isoformat()}
    write_text_atomically(harvest_path(), serialize_json(report))


def duplicates(project_root, published):
    """The learned rules of the repository that say what a rule of the selected profiles says now.

    ``published`` is {qualified id: (profile, relative path, absolute path, rule)} of the selection
    (agent_ready_rule_overrides.selection_rules). Same statement (case, spacing and the final period aside)
    and the same scope; the learned rule can then go with learn retire.
    """
    try:
        registry = learning.read_registry(project_root)
    except StateError:
        return []
    by_statement = {}
    for qualified, (profile, _relative, _absolute, rule) in published.items():
        by_statement.setdefault((learning.normalized_statement(rule.statement), tuple(sorted(rule.paths))),
                                (qualified, profile))
    found = []
    for entry in registry["candidates"]:
        learned = entry.get("learned") or {}
        if entry["status"] != learning.STATUS_LEARNED or not learned.get("ruleId"):
            continue
        match = by_statement.get((learning.normalized_statement(entry["statement"]),
                                  tuple(sorted(entry.get("paths") or []))))
        if match:
            found.append({"learningId": entry["id"], "rule": learned["ruleId"], "path": learned["path"],
                          "duplicates": match[0], "profile": match[1]})
    return found
