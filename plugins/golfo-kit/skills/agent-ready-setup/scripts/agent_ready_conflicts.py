"""Semantic conflicts between the managed rules and what the project writes itself, reviewed with AI.

Two directions, both reported by plan (and by status, from the cache):

- update: a managed rule an apply creates or changes, against each rule of the project
  (``.agents/rules/`` without a managed equivalent) and the project's ``AGENTS.md``;
- project: a rule of the project against each managed rule already applied.

The review is harness-review.py's (same prompt and provider call) and its results go to
review-cache.py under the same check, so a pair the edit hook already reviewed is not paid
twice and the team decides on findings with ``agent-ready review``. It only reports: nothing is
ever deleted or rewritten. ``conflicts.block`` stops an apply whose update brings a conflict.

A conflict of an update is about content that is not on disk yet, so the plan keeps its findings
in the Git directory of the worktree: ``agent-ready review`` can accept or dismiss one before the
apply writes the rule, and a decision is checked against the content that was reviewed.
"""

import importlib.util
import json
import os
import subprocess
import tempfile

RULES_PREFIX = ".agents/rules/"
RULE_SUFFIX = ".md"
AGENTS_FILE = "AGENTS.md"
DIRECTION_UPDATE = "update"
DIRECTION_PROJECT = "project"
HARNESS_REVIEW_RELATIVE_PATH = "assets/common/hooks/harness-review.py"
REVIEW_CACHE_RELATIVE_PATH = "assets/common/hooks/review-cache.py"
# What the review needs from the engine; every installed engine ships both.
REVIEW_SCRIPTS = (HARNESS_REVIEW_RELATIVE_PATH, REVIEW_CACHE_RELATIVE_PATH)
# Per worktree (git rev-parse --git-path): the update conflicts of the last plan.
PENDING_GIT_PATH = "agent-ready/semantic-conflicts.json"
PENDING_FIELDS = ("id", "unit", "check", "direction", "files", "lines", "kind", "text", "reviewedFiles")


def load_harness_review(engine_dir):
    """harness-review.py of the engine; its file name is not importable directly."""
    path = os.path.join(engine_dir, HARNESS_REVIEW_RELATIVE_PATH)
    specification = importlib.util.spec_from_file_location("harness_review", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def is_rule(destination):
    return destination.startswith(RULES_PREFIX) and destination.endswith(RULE_SUFFIX)


def project_rules(project_root, managed):
    """Rules under .agents/rules/ that no source manages: the project's own."""
    base = os.path.join(project_root, *RULES_PREFIX.rstrip("/").split("/"))
    found = []
    for directory, _, names in os.walk(base):
        for name in names:
            relative = os.path.relpath(os.path.join(directory, name), project_root).replace(os.sep, "/")
            if is_rule(relative) and relative not in managed and not os.path.islink(os.path.join(directory, name)):
                found.append(relative)
    return sorted(found)


def conflict_pairs(project_root, entries, locked_assets, read_text, project_owned):
    """Pairs to review, the text the review reads of each document, the text that identifies it in
    the cache, and the direction of each pair.

    ``entries`` are the plan entries; a managed rule the apply creates or changes is reviewed
    with the content it would write (its ``sourcePath``), everything else with what is on disk.
    Of ``AGENTS.md`` the review reads only what ``project_owned`` keeps (the text outside the
    managed block, which the same apply may replace); the cache still keys it by the whole file.
    """
    desired = {entry["destination"]: entry for entry in entries if entry.get("sha256") and is_rule(entry["destination"])}
    managed = set(desired) | {destination for destination in locked_assets if is_rule(destination)}
    own = project_rules(project_root, managed)
    texts = {}
    for name in own:
        texts[name] = read_text(os.path.join(project_root, name))
    changing = sorted(destination for destination, entry in desired.items() if entry["action"] in ("create", "update", "adopt"))
    applied = sorted(destination for destination, entry in desired.items()
                     if entry["action"] == "unchanged" and os.path.isfile(os.path.join(project_root, destination)))
    for destination in changing:
        texts[destination] = read_text(desired[destination]["sourcePath"])
    for destination in applied:
        texts[destination] = read_text(os.path.join(project_root, destination))
    agents_path = os.path.join(project_root, AGENTS_FILE)
    counterparts = list(own)
    identities = {}
    if os.path.isfile(agents_path) and not os.path.islink(agents_path):
        whole = read_text(agents_path)
        owned = project_owned(whole)
        if owned.strip():
            texts[AGENTS_FILE] = owned
            identities[AGENTS_FILE] = whole
            counterparts.append(AGENTS_FILE)
    directions = {}
    for managed_rule in changing:
        for counterpart in counterparts:
            directions[tuple(sorted((managed_rule, counterpart)))] = DIRECTION_UPDATE
    for own_rule in own:
        for managed_rule in applied:
            directions.setdefault(tuple(sorted((own_rule, managed_rule))), DIRECTION_PROJECT)
    return directions, texts, {name: identities.get(name, text) for name, text in texts.items()}


def engine_can_review(engine_dir):
    """True when the engine has the review scripts; a stripped copy of it cannot review."""
    return all(os.path.isfile(os.path.join(engine_dir, relative)) for relative in REVIEW_SCRIPTS)


def review_conflicts(project_root, engine_dir, cache_module, provider, directions, texts, bash, use_provider,
                     settings=None, identities=None):
    """Review the pairs that are not in the cache and return what plan reports.

    ``use_provider`` false (offline, review mode) answers from the cache only. A pair without an
    answer stays unchecked, never clean. ``settings`` are the effective reviews options (cache,
    ttl, commit) of this run. ``identities`` are the texts that key each document in the cache, when
    they differ from what the review reads.
    """
    identities = identities or texts
    harness = load_harness_review(engine_dir)
    pairs = sorted(directions)
    report = {"pairs": len(pairs), "fromCache": 0, "reviewed": 0, "unchecked": 0, "uncheckedUpdate": 0,
              "reason": None, "findings": [], "quiet": 0}
    if not pairs:
        return report
    cache = cache_module.ReviewCache(project_root, settings=settings)
    model = cache_module.PROVIDER_DEFAULTS[provider]["model"]
    effort = cache_module.PROVIDER_DEFAULTS[provider]["effort"]
    engine = cache_module.engine_version(project_root)
    known = {}
    pending = []
    for pair in pairs:
        contents = {name: identities[name] for name in pair}
        key = cache_module.unit_key(harness.CHECK, harness.CHECK_VERSION, provider, model, engine, contents)
        entry = cache.lookup(cache_module.unit_id(harness.CHECK, pair), key)
        if entry is None:
            pending.append((pair, key, contents))
        else:
            known[pair] = entry.get("findings", [])
    report["fromCache"] = len(known)
    unchecked_update = sum(directions[pair] == DIRECTION_UPDATE for pair, _, _ in pending)
    if pending and not use_provider:
        report["unchecked"], report["reason"] = len(pending), "this run uses no network"
        report["uncheckedUpdate"] = unchecked_update
    elif pending and not harness.provider_available(bash, provider):
        report["unchecked"], report["reason"] = len(pending), f"the {provider} CLI is not available"
        report["uncheckedUpdate"] = unchecked_update
    elif pending:
        reviewed = harness.review_pairs(bash, provider, model, effort, [pair for pair, _, _ in pending], texts, project_root)
        if reviewed is None:
            report["unchecked"], report["reason"] = len(pending), f"{provider} gave no valid answer"
            report["uncheckedUpdate"] = unchecked_update
        else:
            records = {}
            for pair, key, contents in pending:
                verdict = cache_module.VERDICT_FINDINGS if reviewed[pair] else cache_module.VERDICT_CONSISTENT
                records[cache_module.unit_id(harness.CHECK, pair)] = cache_module.entry_for(
                    harness.CHECK, harness.CHECK_VERSION, provider, model, engine, contents, key, verdict, reviewed[pair])
                known[pair] = reviewed[pair]
            report["reviewed"] = len(pending)
            try:
                cache.store(records)
            except (OSError, cache_module.CacheLockTimeout):
                pass
    decisions = cache_module.Decisions(project_root)
    recorded = decisions.read()
    annotated = []
    for pair in sorted(known):
        # A decision holds for the content that was reviewed, which for an update is what the
        # apply will write, not what is on disk.
        reviewed_files = {name: cache_module.text_hash(identities[name]) for name in pair}
        for finding in decisions.annotate(cache_module.unit_id(harness.CHECK, pair), known[pair], recorded):
            if finding["decision"]:
                finding["status"] = decision_status(cache_module, finding["decision"], reviewed_files)
            annotated.append(dict(finding, direction=directions[pair], check=harness.CHECK, reviewedFiles=reviewed_files))
    report["findings"] = cache_module.visible(annotated)
    report["quiet"] = len(annotated) - len(report["findings"])
    report["pending"] = [finding for finding in annotated if finding["direction"] == DIRECTION_UPDATE]
    return report


def decision_status(cache_module, decision, reviewed_files):
    """accepted or dismissed while the decision holds for the reviewed content; to-confirm once it changed."""
    if decision.get("scope") == cache_module.SCOPE_PAIR:
        return decision.get("decision")
    recorded = decision.get("files")
    if isinstance(recorded, dict) and recorded and recorded == reviewed_files:
        return decision.get("decision")
    return cache_module.STATUS_TO_CONFIRM


def pending_path(project_root):
    """The file with the update conflicts of the last plan in this worktree, or None outside Git."""
    try:
        completed = subprocess.run(["git", "rev-parse", "--git-path", PENDING_GIT_PATH], cwd=project_root,
                                   capture_output=True, encoding="utf-8", errors="replace", check=False)
    except OSError:
        return None
    located = completed.stdout.strip()
    if completed.returncode != 0 or not located:
        return None
    return os.path.normpath(os.path.join(project_root, located))


def record_pending(project_root, findings):
    """Keep the update conflicts of this plan for agent-ready review; a plan without any clears them."""
    path = pending_path(project_root)
    if not path:
        return
    kept = [{field: finding[field] for field in PENDING_FIELDS if field in finding} for finding in findings]
    temporary_path = None
    try:
        if not kept:
            if os.path.isfile(path):
                os.unlink(path)
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_descriptor, temporary_path = tempfile.mkstemp(prefix=".semantic-conflicts.", dir=os.path.dirname(path))
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as file_handle:
            json.dump({"findings": kept}, file_handle, indent=2, sort_keys=True, ensure_ascii=False)
            file_handle.write("\n")
        os.replace(temporary_path, path)
    except OSError:
        # Without the file, review accept only knows the conflicts that are already on disk.
        pass
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def pending_findings(cache_module, project_root, recorded):
    """The update conflicts of the last plan, each with its status against the team's decisions."""
    path = pending_path(project_root)
    if not path:
        return []
    try:
        with open(path, encoding="utf-8") as file_handle:
            data = json.load(file_handle)
    except (OSError, ValueError):
        return []
    findings = []
    for finding in data.get("findings", []) if isinstance(data, dict) else []:
        if not isinstance(finding, dict) or not isinstance(finding.get("id"), str):
            continue
        decision = recorded.get(finding["id"])
        status = (decision_status(cache_module, decision, finding.get("reviewedFiles") or {}) if decision
                  else cache_module.STATUS_OPEN)
        findings.append(dict(finding, status=status, decision=decision))
    return findings


def blocking_problem(report):
    """Why ``conflicts.block`` stops this apply, or None: an update conflict, or an update it could not check."""
    update = [finding for finding in report["findings"] if finding["direction"] == DIRECTION_UPDATE]
    if update:
        listed = "; ".join(f"[{finding['id']}] {' <-> '.join(finding.get('files', []))}: {finding.get('text', '')}"
                           for finding in update)
        return (f"conflicts.block: this apply brings {len(update)} semantic conflict(s) with the project, so nothing "
                f"was changed: {listed}. Change the rule, or accept or dismiss each one with "
                "agent-ready review accept <id> --reason \"...\"")
    if report["uncheckedUpdate"]:
        return (f"conflicts.block: {report['uncheckedUpdate']} pair(s) of this apply could not be checked for semantic "
                f"conflicts ({report['reason']}), so nothing was changed")
    return None
