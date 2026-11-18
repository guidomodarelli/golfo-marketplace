"""Episodes of the conversations with the user, for the evidence of learning.

A long chat is not one episode: the evidence of an instruction counts distinct episodes, and one starts
with another session, another day or after learning.episodeGapHours without messages. The hook of the
prompt of the user touches the session on every message, without any process or clock running between
messages; the state lives in .git/info/agent-ready/episodes.json, local to the clone and never
versioned (references/learning.md, «Episodios»).

An episode closes when the next one starts, when the chat ends (SessionEnd) or when a sweep finds it
idle for learning.episodeGapHours. Closing it queues the review of its messages of the user in
pendingReviews, read from the transcript of the provider; a compaction (PreCompact) queues the review
of what the episode said so far, and the review of its close starts after that point.
"""

import datetime
import os
import subprocess

from agent_ready_common import StateError, read_json_file, serialize_json, write_text_atomically
from agent_ready_learning import RegistryLock
from agent_ready_lockfile import read_lock

EPISODES_GIT_PATH = "info/agent-ready/episodes.json"
EPISODES_VERSION = 1
LEARNING_PROFILE = "learning"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
# A fixed clock in TIMESTAMP_FORMAT, so tests do not depend on the hour of the machine.
CLOCK_ENVIRONMENT_VARIABLE = "AGENT_READY_LEARNING_NOW"
# The review of an episode is given up after this many runs in which the provider failed.
REVIEW_MAX_ATTEMPTS = 3
DEFAULT_PROVIDER = "claude"


def current_time():
    """The local time of the machine, or the fixed clock of CLOCK_ENVIRONMENT_VARIABLE."""
    fixed = os.environ.get(CLOCK_ENVIRONMENT_VARIABLE)
    if not fixed:
        return datetime.datetime.now().astimezone()
    try:
        return datetime.datetime.strptime(fixed, TIMESTAMP_FORMAT)
    except ValueError as error:
        raise StateError(f"{CLOCK_ENVIRONMENT_VARIABLE}={fixed!r} is not a time like 2026-01-31T12:00:00+0000") from error


def episodes_path(project_root):
    result = subprocess.run(["git", "rev-parse", "--git-path", EPISODES_GIT_PATH], cwd=project_root,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise StateError(f"{project_root} is not a Git repository: episodes live in its .git/info")
    return os.path.join(project_root, result.stdout.strip())


def learning_selected(project_root):
    """True when the last apply selected the learning profile, of the official content or of a pack."""
    lock = read_lock(project_root) or {}
    return any(name == LEARNING_PROFILE or name.endswith("/" + LEARNING_PROFILE)
               for name in lock.get("profileOrder") or [])


def empty_episodes():
    return {"version": EPISODES_VERSION, "sessions": {}, "pendingReviews": []}


def read_episodes(path):
    if not os.path.exists(path):
        return empty_episodes()
    state = read_json_file(path, "learning episodes")
    if state.get("version") != EPISODES_VERSION or not isinstance(state.get("sessions"), dict):
        return empty_episodes()
    if not isinstance(state.get("pendingReviews"), list):
        state["pendingReviews"] = []
    return state


def parse_time(text):
    return datetime.datetime.strptime(text, TIMESTAMP_FORMAT)


def is_idle(session, now, gap_hours):
    """Another day of the machine or learning.episodeGapHours without messages: the episode is over."""
    last = parse_time(session["lastUserMessageAt"])
    return last.date() != now.date() or (now - last) >= datetime.timedelta(hours=gap_hours)


def is_new_episode(session, now, gap_hours):
    """An idle episode, or one already closed (the chat ended and was resumed), starts a new one."""
    return bool(session.get("closed")) or is_idle(session, now, gap_hours)


def queue_review(state, session_id, session, until):
    """Queue the review of what the user wrote in the episode since its last review, up to ``until``.

    Without a transcript there is nothing to read: the episode closes without a review.
    """
    if not session.get("transcriptPath"):
        return False
    state["pendingReviews"].append({
        "session": session_id, "episodeId": session["episodeId"],
        "since": session.get("reviewedUntil") or session["episodeStartedAt"], "until": until,
        "transcriptPath": session["transcriptPath"], "provider": session.get("provider") or DEFAULT_PROVIDER,
        "attempts": 0,
    })
    return True


def close(state, session_id):
    """Close the open episode of a session and queue its review; False when there was none to close."""
    session = state["sessions"].get(session_id)
    if session is None or session.get("closed"):
        return False
    session["closed"] = True
    queue_review(state, session_id, session, session["lastUserMessageAt"])
    return True


def close_idle(state, now, gap_hours):
    """Close every open episode idle for learning.episodeGapHours: the sweep from any hook of the repository."""
    return [session_id for session_id, session in sorted(state["sessions"].items())
            if not session.get("closed") and is_idle(session, now, gap_hours) and close(state, session_id)]


def write_episodes(path, state):
    write_text_atomically(path, serialize_json(state))


def episode_id(session_id, now):
    return f"{session_id}:{now.strftime('%Y%m%dT%H%M%S')}"


def touch(project_root, session_id, now, gap_hours, transcript=None, provider=None):
    """A message of the user arrived: (episode, started), where started tells whether it opened one.

    Opening an episode closes the one before it, and any other idle one, queueing their reviews.
    ``transcript`` and ``provider`` come from the payload of the hook: the review reads that file.
    """
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        session = state["sessions"].get(session_id)
        started = session is None or is_new_episode(session, now, gap_hours)
        if started:
            if session is not None:
                close(state, session_id)
            session = {"episodeId": episode_id(session_id, now), "episodeStartedAt": now.strftime(TIMESTAMP_FORMAT),
                       "scopeQuestionAsked": False}
            state["sessions"][session_id] = session
        session["lastUserMessageAt"] = now.strftime(TIMESTAMP_FORMAT)
        if transcript:
            session["transcriptPath"] = transcript
        if provider:
            session["provider"] = provider
        close_idle(state, now, gap_hours)
        write_episodes(path, state)
    return session, started


def end(project_root, session_id, now, gap_hours, transcript=None):
    """The chat ended (SessionEnd): close its episode, and any other idle one. False when none was open."""
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        session = state["sessions"].get(session_id)
        if session is not None and transcript:
            session["transcriptPath"] = transcript
        closed = close(state, session_id)
        close_idle(state, now, gap_hours)
        write_episodes(path, state)
    return closed


def review_now(project_root, session_id, now, transcript=None):
    """The context is about to be compacted (PreCompact): queue the review of the episode so far.

    The episode stays open; the review of its close starts where this one ends.
    """
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        session = state["sessions"].get(session_id)
        if session is None or session.get("closed"):
            return False
        if transcript:
            session["transcriptPath"] = transcript
        until = now.strftime(TIMESTAMP_FORMAT)
        queued = queue_review(state, session_id, session, until)
        if queued:
            session["reviewedUntil"] = until
        write_episodes(path, state)
    return queued


def sweep(project_root, now, gap_hours):
    """Close the idle episodes and take the queued reviews out of the state, to run them once.

    Returns the reviews taken; the caller puts back with ``requeue`` the ones that could not run.
    """
    path = episodes_path(project_root)
    if not os.path.exists(path):
        return []
    with RegistryLock(project_root):
        state = read_episodes(path)
        close_idle(state, now, gap_hours)
        taken, state["pendingReviews"] = state["pendingReviews"], []
        write_episodes(path, state)
    return taken


def requeue(project_root, reviews, count_attempt=True):
    """Put back reviews that could not run, until a failed provider reaches REVIEW_MAX_ATTEMPTS.

    ``count_attempt`` false puts them back as they were: the review did not try (CI, review mode).
    """
    increment = 1 if count_attempt else 0
    kept = [dict(review, attempts=review.get("attempts", 0) + increment) for review in reviews
            if review.get("attempts", 0) + increment < REVIEW_MAX_ATTEMPTS]
    if not kept:
        return 0
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        state["pendingReviews"].extend(kept)
        write_episodes(path, state)
    return len(kept)


def needs_sweep(project_root, now, gap_hours):
    """True when a review is queued or an idle episode with a transcript waits to be closed.

    Cheap: it only reads the state, so every hook can ask before starting the sweep in the background.
    """
    path = episodes_path(project_root)
    if not os.path.exists(path):
        return False
    try:
        state = read_episodes(path)
    except StateError:
        return False
    return bool(state["pendingReviews"]) or any(
        not session.get("closed") and session.get("transcriptPath") and is_idle(session, now, gap_hours)
        for session in state["sessions"].values())


def current(project_root, session_id):
    """The episode of a session as the hook left it, or None before its first message."""
    return read_episodes(episodes_path(project_root))["sessions"].get(session_id)


def mark_scope_question(project_root, session_id):
    """Record the one scope question of the episode; False when it was already asked."""
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        session = state["sessions"].get(session_id)
        if session is None:
            raise StateError(f"session {session_id} has no episode yet: the hook opens one with its first message")
        if session.get("scopeQuestionAsked"):
            return False
        session["scopeQuestionAsked"] = True
        write_episodes(path, state)
    return True
