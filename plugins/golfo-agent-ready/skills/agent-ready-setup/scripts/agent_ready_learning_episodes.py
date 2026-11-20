"""Episodes of the conversations with the user, for the evidence of learning.

A long chat is not one episode: the evidence of an instruction counts distinct episodes, and one starts
with another session, another day or after learning.episodeGapHours without messages. The hook of the
prompt of the user touches the session on every message, without any process or clock running between
messages; the state lives in .git/info/agent-ready/episodes.json, local to the clone and never
versioned (references/learning-episodes.md, «Episodios»).

An episode closes when the next one starts, when the chat ends (SessionEnd) or when a sweep finds it
idle for learning.episodeGapHours. Closing it queues the review of its messages of the user in
pendingReviews, read from the transcript of the provider; a compaction (PreCompact) queues the review
of what the episode said so far, and the review of its close starts after that point.
"""

import datetime
import os
import subprocess
import uuid

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
# Transcript timestamps and the times of the hooks differ by a few seconds. The window of each review
# widens by this much, but never into the window of the review before it in the same session: a
# message counts in one episode only.
BOUNDARY_SLACK = datetime.timedelta(minutes=5)
# A review a sweep took and never acknowledged (the process died, the machine shut down) is taken
# again after this long.
REVIEW_CLAIM_TIMEOUT = datetime.timedelta(hours=1)


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


def format_time(moment):
    return moment.strftime(TIMESTAMP_FORMAT)


def review_window(session, until, closed_at, next_start=None, exact=False):
    """The transcript window of a review: (after, through), after exclusive and through inclusive.

    It starts where the previous review of the session ended (``reviewedThrough``), or BOUNDARY_SLACK
    before the episode started. It ends BOUNDARY_SLACK after ``until``, but never after ``closed_at``
    (a message written later belongs to a later episode, which starts reading where this one ends)
    nor within the slack of the next episode (``next_start``), so that adjacent episodes never read
    the same message; ``exact`` ends it at ``until`` (a compaction: the episode goes on from there).
    """
    previous = session.get("reviewedThrough")
    after = parse_time(previous) if previous else parse_time(session["episodeStartedAt"]) - BOUNDARY_SLACK
    end = parse_time(until)
    through = end if exact else max(end, min(end + BOUNDARY_SLACK, closed_at))
    if next_start is not None:
        through = max(end, min(through, next_start - BOUNDARY_SLACK))
    return after, max(after, through)


def queue_review(state, session_id, session, until, closed_at, next_start=None, exact=False):
    """Queue the review of what the user wrote in the episode since its last review, up to ``until``.

    The session remembers where the window ended, so its next review starts there. Without a
    transcript there is nothing to read: the episode closes without a review.
    """
    after, through = review_window(session, until, closed_at, next_start, exact)
    session["reviewedThrough"] = format_time(through)
    if not session.get("transcriptPath"):
        return False
    state["pendingReviews"].append({
        "id": uuid.uuid4().hex, "session": session_id, "episodeId": session["episodeId"],
        "since": session.get("reviewedUntil") or session["episodeStartedAt"], "until": until,
        "after": format_time(after), "through": format_time(through),
        "transcriptPath": session["transcriptPath"], "provider": session.get("provider") or DEFAULT_PROVIDER,
        "attempts": 0,
    })
    return True


def close(state, session_id, now, next_start=None):
    """Close the open episode of a session at ``now`` and queue its review; False when there was none to close.

    ``next_start`` is when the next episode of the session starts, when that is what closes this one.
    """
    session = state["sessions"].get(session_id)
    if session is None or session.get("closed"):
        return False
    session["closed"] = True
    queue_review(state, session_id, session, session["lastUserMessageAt"], now, next_start)
    return True


def close_idle(state, now, gap_hours):
    """Close every open episode idle for learning.episodeGapHours: the sweep from any hook of the repository."""
    return [session_id for session_id, session in sorted(state["sessions"].items())
            if not session.get("closed") and is_idle(session, now, gap_hours) and close(state, session_id, now)]


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
            previous = session
            if previous is not None:
                close(state, session_id, now, now)
            session = {"episodeId": episode_id(session_id, now), "episodeStartedAt": now.strftime(TIMESTAMP_FORMAT),
                       "scopeQuestionAsked": False}
            # The same chat keeps its transcript and provider, and the review of this episode starts
            # where the review of the previous one ended.
            for key in ("reviewedThrough", "transcriptPath", "provider"):
                if previous is not None and previous.get(key):
                    session[key] = previous[key]
            state["sessions"][session_id] = session
        session["lastUserMessageAt"] = now.strftime(TIMESTAMP_FORMAT)
        if transcript:
            session["transcriptPath"] = transcript
        if provider:
            session["provider"] = provider
        close_idle(state, now, gap_hours)
        write_episodes(path, state)
    return session, started


def latest_provider(project_root):
    """The provider of the session with the latest message of the user, or DEFAULT_PROVIDER."""
    sessions = read_episodes(episodes_path(project_root))["sessions"].values()
    timed = [(parse_time(session["lastUserMessageAt"]), session.get("provider") or DEFAULT_PROVIDER)
             for session in sessions if session.get("lastUserMessageAt")]
    return max(timed)[1] if timed else DEFAULT_PROVIDER


def end(project_root, session_id, now, gap_hours, transcript=None):
    """The chat ended (SessionEnd): close its episode, and any other idle one. False when none was open."""
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        session = state["sessions"].get(session_id)
        if session is not None and transcript:
            session["transcriptPath"] = transcript
        closed = close(state, session_id, now)
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
        queued = queue_review(state, session_id, session, until, now, exact=True)
        if queued:
            session["reviewedUntil"] = until
        write_episodes(path, state)
    return queued


def is_claimable(review, now):
    """A review no sweep is running: never taken, or taken by a sweep that died REVIEW_CLAIM_TIMEOUT ago."""
    claimed = review.get("claimedAt")
    return not claimed or now - parse_time(claimed) >= REVIEW_CLAIM_TIMEOUT


def sweep(project_root, now, gap_hours):
    """Close the idle episodes and claim the queued reviews, to run them once.

    The reviews stay in the state, claimed, until the caller acknowledges each one (``acknowledge``)
    or puts it back (``requeue``): a sweep that dies leaves them for a later one.
    """
    path = episodes_path(project_root)
    if not os.path.exists(path):
        return []
    with RegistryLock(project_root):
        state = read_episodes(path)
        close_idle(state, now, gap_hours)
        taken = []
        for review in state["pendingReviews"]:
            if is_claimable(review, now):
                review.setdefault("id", uuid.uuid4().hex)
                review["claimedAt"] = format_time(now)
                taken.append(dict(review))
        write_episodes(path, state)
    return taken


def acknowledge(project_root, reviews):
    """Drop reviews that ran, or that will not run (learning.hooks.sessionEnd off)."""
    finished = {review["id"] for review in reviews}
    if not finished:
        return
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        state["pendingReviews"] = [review for review in state["pendingReviews"] if review.get("id") not in finished]
        write_episodes(path, state)


def requeue(project_root, reviews, count_attempt=True):
    """Release reviews that could not run, until a failed provider reaches REVIEW_MAX_ATTEMPTS.

    ``count_attempt`` false releases them as they were: the review did not try (CI, review mode).
    Returns how many stay queued.
    """
    released = {review["id"] for review in reviews}
    if not released:
        return 0
    increment = 1 if count_attempt else 0
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        kept, count = [], 0
        for review in state["pendingReviews"]:
            if review.get("id") in released:
                review.pop("claimedAt", None)
                review["attempts"] = review.get("attempts", 0) + increment
                if review["attempts"] >= REVIEW_MAX_ATTEMPTS:
                    continue
                count += 1
            kept.append(review)
        state["pendingReviews"] = kept
        write_episodes(path, state)
    return count


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
    return any(is_claimable(review, now) for review in state["pendingReviews"]) or any(
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
