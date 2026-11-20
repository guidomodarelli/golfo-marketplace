"""The AI reviews that a session start runs again in the background, when their files changed since.

`agent-ready status` counts a review whose files changed as out of date, and before this it waited for
the next edit or apply. With ``conflicts.sessionStart.reviews`` the session hook asks first how many
there are (``--announce``, which prints one line and never calls the provider), and then reviews them
detached from the session. Each unit is reviewed with the check that reviewed it, on what its files
hold now, and stored in the local cache: the versioned one only changes with an apply.

Two sessions that start together do not review the same unit twice: the run takes a lock per project,
the second one leaves, and the first counts what is out of date again once it holds the lock. A run whose
provider gives no valid answer too often in a row waits a while before the next session start tries again.
"""

import os
import time

import agent_ready_conflicts as conflicts_review
import agent_ready_skill_overlap as skill_overlap
from agent_ready_common import (
    StateError,
    acquire_directory_lock,
    bash_executable,
    read_json_file,
    serialize_json,
    sha256_of_text,
    write_text_atomically,
)
from agent_ready_config import ConfigurationError
from agent_ready_layout import ENGINE_SKILL_DIRECTORY, review_cache_module
from agent_ready_manifest import configuration_of
from agent_ready_options import (
    REVIEWS_ENABLED_KEY,
    SESSION_START_CONFLICTS_ENABLED_KEY,
    SESSION_START_REVIEWS_KEY,
)
from agent_ready_output import write_line
from agent_ready_review_findings import stale_entries

LOG_PREFIX = "[marketplace-sync]"
# Announce exits with this status when there is nothing to review, so the hook starts no background task.
NOTHING_TO_REVIEW_STATUS = 1
REVIEWED_UNIT_SIZE = 2
# After this many runs in a row without a valid answer, the session start waits before trying again.
REFRESH_MAX_FAILURES = 3
REFRESH_RETRY_AFTER_SECONDS = 3600


def refresh_state_paths(project_root):
    """Per-user (report, lock) of the background review of one project; nothing of it lands in the project."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME") or os.path.expanduser("~"), ".cache")
    key = sha256_of_text(os.path.realpath(project_root))[:16]
    directory = os.path.join(base, "agent-ready-setup", "reviews")
    return os.path.join(directory, f"{key}.json"), os.path.join(directory, f"{key}.lock")


def refresh_lock_path(project_root):
    return refresh_state_paths(project_root)[1]


def failures_waiting(report_path):
    """True when the last runs failed too often in a row and the wait after them has not passed yet."""
    try:
        report = read_json_file(report_path, "background review report") or {}
        age = time.time() - os.path.getmtime(report_path)
    except (StateError, OSError):
        return False
    return report.get("consecutiveFailures", 0) >= REFRESH_MAX_FAILURES and age < REFRESH_RETRY_AFTER_SECONDS


def record_run(report_path, failed):
    """Count the runs in a row without a valid answer; a run that reviewed everything starts again from 0."""
    try:
        previous = read_json_file(report_path, "background review report") or {}
    except StateError:
        previous = {}
    failures = previous.get("consecutiveFailures", 0) + 1 if failed else 0
    write_text_atomically(report_path, serialize_json({"consecutiveFailures": failures}))


def refresh_enabled(project_root):
    """True when a session start reviews again what is out of date: the AI reviews, the session-start checks
    and their reviews key are on."""
    try:
        configuration = configuration_of(project_root, offline=True)
    except ConfigurationError:
        return False
    return all(configuration.value(key) for key in
               (REVIEWS_ENABLED_KEY, SESSION_START_CONFLICTS_ENABLED_KEY, SESSION_START_REVIEWS_KEY))


def checks(harness):
    """{check: reviewer} of the reviews a unit of the cache can come from."""
    return {conflicts_review.CONFLICT_CHECK: harness, skill_overlap.CHECK: skill_overlap.reviewer(harness)}


def refreshable(stale, known_checks):
    """The stale units this run can review: a pair of documents of a check it knows."""
    return {unit: entry for unit, entry in stale.items()
            if entry.get("check") in known_checks and len(entry.get("files", {})) == REVIEWED_UNIT_SIZE}


def review_stale(project_root, provider, bash):
    """Review the stale units again and store what they find. Returns (reviewed, unchecked)."""
    module = review_cache_module()
    harness = conflicts_review.load_harness_review(ENGINE_SKILL_DIRECTORY)
    reviewers = checks(harness)
    units = refreshable(stale_entries(project_root), reviewers)
    if not units:
        return 0, 0
    cache = module.ReviewCache(project_root)
    # The local cache only: a background review never changes a file of the repository.
    writer = module.ReviewCache(project_root, settings=dict(cache.settings(), commit=False))
    model = module.PROVIDER_DEFAULTS[provider]["model"]
    effort = module.PROVIDER_DEFAULTS[provider]["effort"]
    engine = module.engine_version(project_root)
    by_check = {}
    for entry in units.values():
        names = tuple(sorted(entry["files"]))
        texts = {name: module.unit_text(project_root, name) for name in names}
        if any(text is None for text in texts.values()):
            continue
        by_check.setdefault(entry["check"], {})[names] = texts
    reviewed = unchecked = 0
    for check_name, pairs in sorted(by_check.items()):
        check = reviewers[check_name]
        texts = {name: text for contents in pairs.values() for name, text in contents.items()}
        found = check.review_pairs(bash, provider, model, effort, sorted(pairs), texts, project_root)
        if found is None:
            unchecked += len(pairs)
            continue
        records = {}
        for pair, contents in pairs.items():
            key = module.unit_key(check.CHECK, check.CHECK_VERSION, provider, model, engine, contents)
            verdict = module.VERDICT_FINDINGS if found[pair] else module.VERDICT_CONSISTENT
            records[module.unit_id(check.CHECK, pair)] = module.entry_for(
                check.CHECK, check.CHECK_VERSION, provider, model, engine, contents, key, verdict, found[pair])
        writer.store(records)
        reviewed += len(pairs)
    return reviewed, unchecked


def command_refresh_reviews(arguments):
    """Announce or run the background review of the stale AI reviews of a session start."""
    project_root = arguments.project
    if not refresh_enabled(project_root):
        return NOTHING_TO_REVIEW_STATUS if arguments.announce else 0
    bash = bash_executable()
    harness = conflicts_review.load_harness_review(ENGINE_SKILL_DIRECTORY)
    report_path, lock_path = refresh_state_paths(project_root)
    if arguments.announce:
        if failures_waiting(report_path):
            return NOTHING_TO_REVIEW_STATUS
        count = len(refreshable(stale_entries(project_root), checks(harness)))
        if not count or not harness.provider_available(bash, arguments.provider):
            return NOTHING_TO_REVIEW_STATUS
        write_line(f"{LOG_PREFIX} {count} AI review(s) are out of date; reviewing them in the background with "
                   f"{arguments.provider} (conflicts.sessionStart.reviews).")
        return 0
    if not acquire_directory_lock(lock_path):
        write_line("Another background review of this project is running.")
        return 0
    try:
        if not harness.provider_available(bash, arguments.provider):
            write_line(f"The {arguments.provider} CLI is not available; the reviews stay out of date.")
            return 0
        reviewed, unchecked = review_stale(project_root, arguments.provider, bash)
        record_run(report_path, failed=bool(unchecked))
        write_line(f"Reviewed {reviewed} unit(s) again" + (f"; {unchecked} got no valid answer" if unchecked else "") + ".")
    finally:
        os.rmdir(lock_path)
    return 0
