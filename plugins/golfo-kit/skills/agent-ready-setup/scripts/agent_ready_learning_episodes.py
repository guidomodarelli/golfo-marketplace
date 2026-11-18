"""Episodes of the conversations with the user, for the evidence of learning.

A long chat is not one episode: the evidence of an instruction counts distinct episodes, and one starts
with another session, another day or after learning.episodeGapHours without messages. The hook of the
prompt of the user touches the session on every message, without any process or clock running between
messages; the state lives in .git/info/agent-ready/episodes.json, local to the clone and never
versioned (references/learning.md, «Episodios»).
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


def read_episodes(path):
    if not os.path.exists(path):
        return {"version": EPISODES_VERSION, "sessions": {}}
    state = read_json_file(path, "learning episodes")
    if state.get("version") != EPISODES_VERSION or not isinstance(state.get("sessions"), dict):
        return {"version": EPISODES_VERSION, "sessions": {}}
    return state


def parse_time(text):
    return datetime.datetime.strptime(text, TIMESTAMP_FORMAT)


def is_new_episode(session, now, gap_hours):
    """Another day of the machine or learning.episodeGapHours without messages start a new episode."""
    last = parse_time(session["lastUserMessageAt"])
    return last.date() != now.date() or (now - last) >= datetime.timedelta(hours=gap_hours)


def episode_id(session_id, now):
    return f"{session_id}:{now.strftime('%Y%m%dT%H%M%S')}"


def touch(project_root, session_id, now, gap_hours):
    """A message of the user arrived: (episode, started), where started tells whether it opened one."""
    path = episodes_path(project_root)
    with RegistryLock(project_root):
        state = read_episodes(path)
        session = state["sessions"].get(session_id)
        started = session is None or is_new_episode(session, now, gap_hours)
        if started:
            session = {"episodeId": episode_id(session_id, now), "episodeStartedAt": now.strftime(TIMESTAMP_FORMAT),
                       "scopeQuestionAsked": False}
            state["sessions"][session_id] = session
        session["lastUserMessageAt"] = now.strftime(TIMESTAMP_FORMAT)
        write_text_atomically(path, serialize_json(state))
    return session, started


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
        write_text_atomically(path, serialize_json(state))
    return True
