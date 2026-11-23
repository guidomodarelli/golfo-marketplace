"""agent-ready sync: what the people of an office learned reaches the others, and nobody uses Git (#169c).

One run, in the ``business`` collaboration preset (agent_ready_identity.py):

1. commits what the learning left without a commit (``learn record`` writes the registry and leaves it
   to the next commit), only those files, whatever else is staged;
2. fetches the branch from ``sync.remote``;
3. merges it with the merge drivers of the learning (agent_ready_merge_drivers.py), which integrate by
   rule, by entry and by line of the log. A merge that still conflicts is aborted: the repository is
   never left half merged, and the next run tries again;
4. pushes, and when the remote rejects it because someone pushed first, fetches and merges again, up to
   ``sync.pushRetries`` times. It never forces a push.

Without network the commits stay local and go out with the first run that reaches the remote. In the
``software`` preset it does nothing: what is learned travels in the pull request of the change. The state
of the last run lives in ``.git/info/agent-ready/sync.json``, never in the repository.
"""

import datetime
import json
import os
import subprocess

import agent_ready_identity as identity
import agent_ready_learning as learning
import agent_ready_learning_apply as learning_apply
import agent_ready_learning_promotion as promotion
import agent_ready_merge_drivers as merge_drivers
import agent_ready_sync_conflicts as sync_conflicts
import agent_ready_sync_documents as documents
from agent_ready_common import acquire_directory_lock, bash_executable, write_text_atomically
from agent_ready_lockfile import read_lock

ENABLED_KEY = "sync.enabled"
REMOTE_KEY = "sync.remote"
PUSH_RETRIES_KEY = "sync.pushRetries"
# push: to the branch itself. pr: to a branch of each person, with a pull request into it, for a branch
# that only takes pull requests.
MODE_KEY = "sync.mode"
MODE_PUSH = "push"
MODE_PR = "pr"
PERSON_BRANCH_PREFIX = "agent-ready/sync/"
PULL_REQUEST_TITLE = "agent-ready sync: what {person} learned"
STATE_GIT_PATH = "info/agent-ready/sync.json"
LOCK_GIT_PATH = "info/agent-ready/sync.lock"
FOREGROUND_VARIABLE = "AGENT_READY_TEAM_SYNC_FOREGROUND"
COMMIT_SUBJECT = "sync: what was learned"
# What the learning writes and leaves to the next commit; the files the profiles project are not here.
KNOWLEDGE_PATHSPECS = (
    ":(glob).agents/rules/learned*.md",
    ":(glob).agents/rules/learned/**",
    ".agents/learning/candidates.json",
    ".agents/learning/log.md",
    ".agents/learning/reorganize.json",
)

RESULT_SYNCED = "synced"
RESULT_OFF = "off"
RESULT_SOFTWARE = "software"
RESULT_NO_REMOTE = "no-remote"
RESULT_DETACHED = "detached"
RESULT_BUSY = "busy"
RESULT_RUNNING = "running"
RESULT_OFFLINE = "offline"
RESULT_CONFLICT = "conflict"
RESULT_BLOCKED = "blocked"
RESULT_PUSH_FAILED = "push-failed"
# What needs a person: the others just wait for the next run.
FAILED_RESULTS = (RESULT_CONFLICT, RESULT_BLOCKED, RESULT_PUSH_FAILED)
REJECTED_PUSH_HINTS = ("[rejected]", "non-fast-forward", "fetch first", "rejected")


def git(project_root, *arguments, extra_environment=None):
    """A Git command that never asks for credentials: a background run has nobody to answer."""
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_MERGE_AUTOEDIT="no", **(extra_environment or {}))
    return subprocess.run(["git", "-C", project_root, *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                          env=environment)


def git_path(project_root, relative):
    result = git(project_root, "rev-parse", "--git-path", relative)
    path = result.stdout.strip()
    return path if os.path.isabs(path) else os.path.join(project_root, path)


def settings_of(configuration, project_root):
    """{enabled, remote, retries, promote_after, preset} of the repository."""
    preset = identity.collaboration_preset(configuration.value(identity.COLLABORATION_PRESET_KEY),
                                           read_lock(project_root))
    lock = read_lock(project_root)
    return {"enabled": configuration.value(ENABLED_KEY), "remote": configuration.value(REMOTE_KEY),
            "retries": configuration.value(PUSH_RETRIES_KEY),
            "promote_after": configuration.value(promotion.PROMOTE_AFTER_USERS_KEY), "preset": preset,
            "scope": documents.effective_scope(configuration.value(documents.SCOPE_KEY), lock),
            "mode": configuration.value(MODE_KEY)}


def now_text():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def read_state(project_root):
    try:
        with open(git_path(project_root, STATE_GIT_PATH), encoding="utf-8") as handle:
            state = json.load(handle)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(project_root, report):
    state = read_state(project_root)
    state.update({"lastRun": report["at"], "result": report["result"], "message": report.get("message", ""),
                  "toPush": report.get("toPush", 0)})
    if report["result"] == RESULT_SYNCED:
        state["lastSynced"] = report["at"]
    write_text_atomically(git_path(project_root, STATE_GIT_PATH), json.dumps(state, indent=2, sort_keys=True) + "\n")


def in_progress(project_root):
    """True while a merge, rebase, cherry-pick or revert waits for a person in this checkout."""
    markers = ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD", "REVERT_HEAD")
    return any(os.path.exists(git_path(project_root, marker)) for marker in markers)


def commit_knowledge(project_root, subject=COMMIT_SUBJECT, pathspecs=KNOWLEDGE_PATHSPECS):
    """Commit the files of ``pathspecs`` that changed (the learning, and the documents with that scope), and
    nothing else; True when it made a commit."""
    # The files that changed, by name: a pathspec that matches nothing would make git add fail.
    pending = git(project_root, "status", "--porcelain", "-z", "--untracked-files=all", "--", *pathspecs)
    records = [record for record in pending.stdout.split("\0") if record]
    paths = []
    index = 0
    while index < len(records):
        state, path = records[index][:2], records[index][3:]
        paths.append(path)
        if "R" in state or "C" in state:
            # A rename carries its old name in the next record: it goes in the commit too.
            index += 1
            paths.append(records[index])
        index += 1
    if not paths:
        return False
    added = git(project_root, "add", "-A", "--", *paths)
    if added.returncode != 0:
        raise SyncError(RESULT_BLOCKED, f"git add failed: {added.stderr.strip()}")
    message = f"{subject}\n\n{identity.learned_by_trailer()}"
    committed = git(project_root, "commit", "--quiet", "-m", message, "--", *paths)
    if committed.returncode != 0:
        raise SyncError(RESULT_BLOCKED, f"git commit failed: {(committed.stderr or committed.stdout).strip()}")
    return True


def with_registry(project_root, operation, *arguments):
    """Run a step that writes the files of the learning while no learn record or apply holds them.

    The lock of the learning registry (agent_ready_learning.RegistryLock) is held only for the local
    steps (the commit and the merge), never while the network answers: a writer waits at most
    LOCK_WAIT_SECONDS, and a slow remote must not make it fail."""
    try:
        with learning.RegistryLock(project_root):
            return operation(project_root, *arguments)
    except learning.RegistryLockedError as locked:
        raise SyncError(RESULT_BUSY, f"the learning is writing its registry: {locked}") from locked


def promote_and_commit(project_root, threshold):
    """Promote to the team what enough people taught alike, and commit it; the promoted rule ids."""
    written = promotion.promote(project_root, threshold, datetime.date.today().isoformat())
    if written:
        commit_knowledge(project_root, "sync: promote to the team what several people learned alike")
    return written


class SyncError(Exception):
    def __init__(self, result, message):
        super().__init__(message)
        self.result = result


def remote_ref(remote, branch):
    return f"refs/remotes/{remote}/{branch}"


def fetch(project_root, remote, branch):
    """True when the remote has the branch, False when it does not have it yet; offline raises."""
    result = git(project_root, "fetch", "--quiet", remote, f"+refs/heads/{branch}:{remote_ref(remote, branch)}")
    if result.returncode == 0:
        return True
    text = result.stderr.lower()
    if "couldn't find remote ref" in text or "could not find remote ref" in text:
        return False
    raise SyncError(RESULT_OFFLINE, result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "fetch failed")


def merge(project_root, remote, branch):
    """Merge the fetched branch; a conflict is aborted and raised with its files."""
    reference = remote_ref(remote, branch)
    if git(project_root, "merge-base", "--is-ancestor", reference, "HEAD").returncode == 0:
        # Nothing to bring: what conflicted before was settled some other way.
        sync_conflicts.clear_pending(project_root)
        return
    # The drivers point to this installation: the one the last apply wrote may have left the cache.
    merge_drivers.register(project_root, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                      merge_drivers.MERGE_DRIVER_SCRIPT))
    # The conflicts a person already decided go to the drivers, which merge them as decided.
    resolutions = sync_conflicts.resolutions_file(project_root)
    # Only the decisions this merge needs are finished; the others went stale and are dropped.
    applied = sync_conflicts.applicable(project_root, reference) if resolutions else set()
    environment = {sync_conflicts.RESOLUTIONS_VARIABLE: resolutions} if resolutions else None
    result = git(project_root, "merge", "--no-edit", "--quiet", reference, extra_environment=environment)
    if result.returncode == 0:
        if resolutions:
            finish_resolutions(project_root, applied)
        # The merge went through: a conflict that waited (the other side went back) no longer exists.
        sync_conflicts.clear_pending(project_root)
        return
    if os.path.exists(git_path(project_root, "MERGE_HEAD")):
        unmerged = git(project_root, "diff", "--name-only", "--diff-filter=U").stdout.split()
        # Two uploaded files with one name are both kept, without asking anybody.
        documents.settle_inputs(project_root, unmerged, git)
        if unmerged and resolve_file_conflicts(project_root, resolutions):
            if resolutions:
                finish_resolutions(project_root, applied)
            sync_conflicts.clear_pending(project_root)
            return
    if os.path.exists(git_path(project_root, "MERGE_HEAD")):
        files = git(project_root, "diff", "--name-only", "--diff-filter=U").stdout.split()
        # Before the abort: the versions of each rule, its people and its times, for the next session.
        recorded, unexplained = sync_conflicts.record(project_root, files, reference)
        git(project_root, "merge", "--abort")
        waiting = [conflict["id"] for conflict in recorded if not conflict.get("decision")]
        if not files:
            # Git stopped without a file in conflict (a driver that failed): its own words say why.
            unexplained = [(result.stderr or result.stdout).strip().splitlines()[-1] if (result.stderr or result.stdout).strip()
                           else "git merge stopped"]
        raise SyncError(RESULT_CONFLICT, "the same part changed on two machines: " + ", ".join(waiting + unexplained)
                        + ("; the next session explains it and offers what to keep" if waiting else ""))
    raise SyncError(RESULT_BLOCKED, (result.stderr or result.stdout).strip().splitlines()[0]
                    if (result.stderr or result.stdout).strip() else "git merge failed")


def stage_text(project_root, stage, path):
    """The text of ``path`` at a stage of the merge in progress (1 base, 2 ours, 3 theirs); "" if absent."""
    result = git(project_root, "show", f":{stage}:{path}")
    return result.stdout if result.returncode == 0 else ""


def resolve_file_conflicts(project_root, resolutions_path):
    """Finish a merge whose remaining conflicts the decisions settle, and commit it; False if one is left.

    Git does not run the merge driver when one side deleted a rule file and the other changed it, so the
    decision of such a conflict is applied here, with the same merge of rules as the driver."""
    files = git(project_root, "diff", "--name-only", "--diff-filter=U").stdout.split()
    resolutions = {}
    if resolutions_path:
        try:
            with open(resolutions_path, encoding="utf-8") as handle:
                resolutions = json.load(handle)
        except (OSError, ValueError):
            return False
    if any(path not in resolutions for path in files):
        return False
    for path in files:
        versions = [stage_text(project_root, stage, path) for stage in (1, 2, 3)]
        decided = resolutions[path].get(documents.KIND_DOCUMENT)
        if decided is not None:
            # A document the person decided: the whole version they chose, while both sides are the ones seen.
            if not documents.decision_holds(decided, versions[1], versions[2]):
                return False
            write_text_atomically(os.path.join(project_root, path), decided["text"])
            if git(project_root, "add", "--", path).returncode != 0:
                return False
            continue
        try:
            merged, conflicts = merge_drivers.merge_rules(*versions, resolutions[path])
            _, segments, _ = merge_drivers.rule_segments(merged)
        except merge_drivers.Unparsable:
            return False
        if conflicts:
            return False
        if not segments and not (versions[1] and versions[2]):
            # The side that deleted the file wins with its last rule: the file goes.
            outcome = git(project_root, "rm", "--quiet", "--cached", "--", path)
            absolute = os.path.join(project_root, path)
            if os.path.exists(absolute):
                os.remove(absolute)
        else:
            write_text_atomically(os.path.join(project_root, path), merged)
            outcome = git(project_root, "add", "--", path)
        if outcome.returncode != 0:
            return False
    return git(project_root, "commit", "--no-edit", "--quiet").returncode == 0


def personal_entry(person, conflict, statement=None):
    return {"scope": learning.SCOPE_PERSONAL, "owner": person, "statement": statement,
            "key": conflict.get("key"), "paths": []}


def personal_rule_id(person, conflict):
    return learning_apply.rule_prefix(personal_entry(person, conflict)) + conflict["ruleId"].rsplit("/", 1)[-1]


def team_rule_required_by(project_root, conflict):
    """The id of a rule that requires the team rule of ``conflict``, or None: each-their-own would remove it."""
    import agent_ready_learning_reorganize as reorganize

    found = reorganize.incoming_requires(project_root, [conflict["ruleId"]])
    return found[0].id if found else None


def personal_rule_exists(project_root, person, conflict):
    """True when the personal rules of ``person`` already have the id that each-their-own would write."""
    path = os.path.join(project_root, learning_apply.personal_file(personal_entry(person, conflict)))
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return False
    rule_id = personal_rule_id(person, conflict)
    return any(f"id={rule_id}" in line.split() for line in text.splitlines() if line.lstrip().startswith("<!--"))


def append_personal(project_root, person, conflict, statement, details=()):
    """Write one version of a decided conflict, with its exceptions and details, as the personal rule of the
    person who taught it."""
    entry = personal_entry(person, conflict, statement)
    rule_id = personal_rule_id(person, conflict)
    path, text = learning_apply.appended_rule(project_root, rule_id, entry, None)
    if details:
        newline = "\r\n" if "\r\n" in text else "\n"
        text = text + newline.join(details) + newline
    write_text_atomically(path, text)
    return path


def finish_resolutions(project_root, applied=None):
    """After the merge with the decisions: the personal rules of «each one keeps theirs», a resolve line in
    the log per decision the merge applied, and a commit with them."""
    sync_conflicts.finish(project_root,
                          lambda person, conflict, statement, details=(): append_personal(project_root, person, conflict,
                                                                                         statement, details),
                          lambda line: learning_apply.append_log(project_root, line), applied)
    commit_knowledge(project_root, "sync: what the people decided about two versions of a rule")


def to_push(project_root, remote, branch, remote_has_branch):
    """The commits of HEAD the remote does not have, as far as the last fetch knows (also offline)."""
    reference = remote_ref(remote, branch)
    if not remote_has_branch and git(project_root, "rev-parse", "--verify", "--quiet", reference).returncode != 0:
        reference = None
    arguments = ["rev-list", "--count", "HEAD"] + ([f"^{reference}"] if reference else [])
    result = git(project_root, *arguments)
    return int(result.stdout.strip() or 0) if result.returncode == 0 else 0


def push(project_root, remote, branch):
    """True when the push went out, False when the remote rejected it because it moved; errors raise."""
    result = git(project_root, "push", "--quiet", remote, f"HEAD:refs/heads/{branch}")
    if result.returncode == 0:
        return True
    if any(hint in result.stderr for hint in REJECTED_PUSH_HINTS):
        return False
    message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "git push failed"
    if "could not read" in result.stderr.lower() or "unable to access" in result.stderr.lower():
        raise SyncError(RESULT_OFFLINE, message)
    raise SyncError(RESULT_PUSH_FAILED, message)


def person_branch(person):
    """The branch of the pull request of one person in the pr mode."""
    return PERSON_BRANCH_PREFIX + learning_apply.person_slug(person)


def run_gh(project_root, *arguments):
    """gh through bash, which finds the CLI the session finds (a shim without an extension too, on Windows)."""
    return subprocess.run([bash_executable(), "-c", 'exec gh "$@"', "gh", *arguments], cwd=project_root,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def ensure_pull_request(project_root, head, base, person):
    """The pull request of ``head`` into ``base``, opened with gh when there is none; (url or None, message)."""
    if run_gh(project_root, "--version").returncode != 0:
        return None, f"pushed to {head}; open a pull request into {base} (gh is not installed)"
    listed = run_gh(project_root, "pr", "list", "--head", head, "--base", base, "--state", "open", "--json", "url",
                    "--jq", ".[0].url")
    if listed.returncode == 0 and listed.stdout.strip():
        return listed.stdout.strip(), f"pushed to {head}, in its open pull request {listed.stdout.strip()}"
    created = run_gh(project_root, "pr", "create", "--head", head, "--base", base,
                     "--title", PULL_REQUEST_TITLE.format(person=person),
                     "--body", "What was learned and the documents of the office, from agent-ready sync.")
    if created.returncode == 0 and created.stdout.strip():
        url = created.stdout.strip().splitlines()[-1]
        return url, f"pushed to {head}, in the new pull request {url}"
    reason = (created.stderr or created.stdout).strip().splitlines()[-1:] or ["gh pr create failed"]
    return None, f"pushed to {head}; the pull request into {base} could not be opened: {reason[0]}"


def push_to_person_branch(project_root, remote, branch, person):
    """The pr mode: the branch of this person takes the commits, merged with what another machine of the same
    person pushed there; never forced. Returns the message of the run."""
    head = person_branch(person)
    if fetch(project_root, remote, head):
        with_registry(project_root, merge, remote, head)
    if not push(project_root, remote, head):
        raise SyncError(RESULT_PUSH_FAILED, f"{head} moved while this machine pushed; the next run merges it")
    return ensure_pull_request(project_root, head, branch, person)[1]


def synchronize(project_root, settings):
    """The steps of one run; returns the report without the time."""
    if not settings["enabled"]:
        return {"result": RESULT_OFF}
    if settings["preset"] == identity.PRESET_SOFTWARE:
        return {"result": RESULT_SOFTWARE}
    branch = git(project_root, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if not branch:
        return {"result": RESULT_DETACHED, "message": "the checkout is not on a branch"}
    remote = settings["remote"]
    if git(project_root, "remote", "get-url", remote).returncode != 0:
        return {"result": RESULT_NO_REMOTE, "message": f"the repository has no remote {remote}"}
    if in_progress(project_root):
        return {"result": RESULT_BUSY, "message": "a merge or rebase of this checkout waits for a person"}
    pathspecs = KNOWLEDGE_PATHSPECS
    if settings.get("scope") == documents.SCOPE_DOCUMENTS:
        pathspecs = KNOWLEDGE_PATHSPECS + documents.DOCUMENT_PATHSPECS
    committed = with_registry(project_root, commit_knowledge, COMMIT_SUBJECT, pathspecs)
    remote_has_branch = False
    try:
        for _ in range(settings["retries"] + 1):
            remote_has_branch = fetch(project_root, remote, branch)
            if remote_has_branch:
                with_registry(project_root, merge, remote, branch)
            # With the personal rules of everybody here, what several people taught alike goes to the team.
            if with_registry(project_root, promote_and_commit, settings["promote_after"]):
                committed = True
            if to_push(project_root, remote, branch, remote_has_branch) == 0:
                return {"result": RESULT_SYNCED, "committed": committed, "toPush": 0}
            if settings.get("mode") == MODE_PR:
                # The branch only takes pull requests: what this machine has goes to the one of its person.
                message = push_to_person_branch(project_root, remote, branch, identity.read_identity()["id"])
                return {"result": RESULT_SYNCED, "committed": committed, "toPush": 0, "message": message}
            if push(project_root, remote, branch):
                fetch(project_root, remote, branch)
                return {"result": RESULT_SYNCED, "committed": committed, "toPush": 0}
        raise SyncError(RESULT_PUSH_FAILED, f"the remote kept moving after {settings['retries']} retries")
    except SyncError as stopped:
        return {"result": stopped.result, "message": str(stopped), "committed": committed,
                "toPush": to_push(project_root, remote, branch, remote_has_branch)}


def run(project_root, settings):
    """One run under the lock of the checkout, recorded in the state of the last run."""
    lock_path = git_path(project_root, LOCK_GIT_PATH)
    if not acquire_directory_lock(lock_path):
        return {"result": RESULT_RUNNING, "at": now_text(), "message": "another sync of this checkout is running"}
    try:
        report = synchronize(project_root, settings)
    except SyncError as stopped:
        report = {"result": stopped.result, "message": str(stopped)}
    finally:
        try:
            os.rmdir(lock_path)
        except OSError:
            pass
    report["at"] = now_text()
    if report["result"] not in (RESULT_OFF, RESULT_SOFTWARE):
        write_state(project_root, report)
    return report


def describe(state):
    """One line for agent-ready status, or None when sync never ran here."""
    if not state:
        return None
    result = state.get("result")
    last = state.get("lastSynced")
    since = f", last synced {last}" if last else ""
    if result == RESULT_SYNCED:
        return f"Sync: up to date ({state.get('lastRun')})"
    waiting = state.get("toPush") or 0
    pending = f", {waiting} commit{'s' if waiting != 1 else ''} waiting to go out" if waiting else ""
    return f"Sync: {result}{pending}{since}: {state.get('message', '')}".rstrip(": ")
