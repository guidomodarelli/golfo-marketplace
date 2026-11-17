"""The learning registry: instructions of the user that may become rules or skills of the project.

.agents/learning/candidates.json keeps one entry per instruction, in the canonical and general form the
agent wrote (its statement), with the evidence of each time the user gave it: the literal quote, the
session, the episode and the date. The registry counts distinct episodes, not messages, and decides from
fixed rules of evidence whether an instruction is learned now or waits for another episode
(references/learning.md). The quotes may hold data of a case, so only this file keeps them.
"""

import datetime
import os
import re
import time

from agent_ready_common import (
    StateError,
    acquire_directory_lock,
    read_json_file,
    serialize_json,
    sha256_of_text,
    skill_cache_directory,
    write_text_atomically,
)
from agent_ready_rules import DECISION_KEY

LEARNING_RELATIVE_PATH = ".agents/learning"
CANDIDATES_FILE_NAME = "candidates.json"
REGISTRY_VERSION = 1

KIND_RULE = "rule"
KIND_SKILL = "skill"
KIND_NESTED = "nested"
KINDS = (KIND_RULE, KIND_SKILL, KIND_NESTED)

SOURCE_IN_SESSION = "in-session"
SOURCE_SESSION_END = "session-end"
SOURCES = (SOURCE_IN_SESSION, SOURCE_SESSION_END)

STATUS_CANDIDATE = "candidate"
STATUS_LEARNED = "learned"
STATUS_SUPERSEDED = "superseded"
STATUS_EXPIRED = "expired"
STATUSES = (STATUS_CANDIDATE, STATUS_LEARNED, STATUS_SUPERSEDED, STATUS_EXPIRED)

MODE_AUTO = "auto"
MODE_DEVELOPER_REVIEW = "developer-review"

# What record tells the agent to do with the instruction.
DECISION_LEARN = "learn"
DECISION_PROPOSE = "propose"
DECISION_WAIT = "wait"
DECISION_ALREADY_LEARNED = "already-learned"

CANDIDATE_ID_PREFIX = "learn-"
CANDIDATE_ID_HASH_CHARS = 10
UNKNOWN_SESSION = "unknown"
LOCK_WAIT_SECONDS = 10
LOCK_POLL_SECONDS = 0.05
TRAILING_PUNCTUATION = ".;:!?,"
WHITESPACE = re.compile(r"\s+")


def candidates_path(project_root):
    return os.path.join(project_root, LEARNING_RELATIVE_PATH, CANDIDATES_FILE_NAME)


def normalized_statement(statement):
    """The form two statements are compared in: case, spacing and closing punctuation do not count."""
    return WHITESPACE.sub(" ", statement).strip().rstrip(TRAILING_PUNCTUATION).strip().casefold()


def candidate_id(statement):
    """A stable id from the first statement of the entry: a later rewording keeps it."""
    return CANDIDATE_ID_PREFIX + sha256_of_text(normalized_statement(statement))[:CANDIDATE_ID_HASH_CHARS]


def parse_date(text, label):
    try:
        return datetime.date.fromisoformat(text)
    except (TypeError, ValueError) as date_error:
        raise StateError(f"{label} must be a date as YYYY-MM-DD, not {text!r}") from date_error


def episode_of(session, date, episode):
    """The episode of one piece of evidence. Without the episode of a hook, another session or another
    day starts a new one (references/learning.md, «Episodios»)."""
    return episode or f"{session}:{date.isoformat()}"


def empty_registry():
    return {"version": REGISTRY_VERSION, "candidates": []}


def read_registry(project_root):
    """The registry of the project, or an empty one when the project has none yet."""
    path = candidates_path(project_root)
    if not os.path.exists(path):
        return empty_registry()
    registry = read_json_file(path, "learning registry")
    if registry.get("version") != REGISTRY_VERSION or not isinstance(registry.get("candidates"), list):
        raise StateError(f"learning registry {path} must have version {REGISTRY_VERSION} and a candidates list")
    for entry in registry["candidates"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("evidence"), list) \
                or entry.get("status") not in STATUSES or not entry.get("id") or not entry.get("statement"):
            raise StateError(f"learning registry {path} has an entry without id, statement, status or evidence")
    return registry


def write_registry(project_root, registry):
    write_text_atomically(candidates_path(project_root), serialize_json(registry))


class RegistryLock:
    """One writer at a time per project: two sessions may record at once. The lock lives in the cache
    of the user, never in the repository."""

    def __init__(self, project_root):
        self.path = skill_cache_directory("learning-locks", sha256_of_text(os.path.realpath(project_root)))

    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while not acquire_directory_lock(self.path):
            if time.monotonic() > deadline:
                raise StateError(f"the learning registry is locked by another process ({self.path})")
            time.sleep(LOCK_POLL_SECONDS)
        return self

    def __exit__(self, *_):
        try:
            os.rmdir(self.path)
        except OSError:
            pass


def evidence_dates(entry):
    return [parse_date(item["date"], f"the evidence of {entry['id']}") for item in entry["evidence"]]


def live_evidence(entry, ttl_days):
    """The evidence since the last time the candidate expired: going back from the newest, it stops at
    the first gap of more than ttl_days between two pieces. Repetitions that each arrive before the
    candidate expires all count, however long the whole series is. Evidence before ``liveFrom`` belongs
    to an instruction that was replaced, and never counts again."""
    first_live = entry.get("liveFrom", 0)
    dated = sorted(((date, index) for index, date in enumerate(evidence_dates(entry)) if index >= first_live),
                   reverse=True)
    live = []
    for position, (date, index) in enumerate(dated):
        if position and (dated[position - 1][0] - date).days > ttl_days:
            break
        live.append(entry["evidence"][index])
    return live


def live_episodes(entry, ttl_days):
    """Distinct episodes of the live evidence: what expired with the candidate does not count again."""
    return len({item["episode"] for item in live_evidence(entry, ttl_days)})


def is_explicit(entry, ttl_days):
    """The user asked for it to last in some live evidence; an explicit request that expired does not."""
    return any(item.get("explicit") for item in live_evidence(entry, ttl_days))


def refresh_expiry(registry, today, ttl_days):
    """A candidate without evidence in the last ttl_days expires; learned entries never do."""
    for entry in registry["candidates"]:
        if entry["status"] != STATUS_CANDIDATE:
            continue
        dates = evidence_dates(entry)
        if not dates or (today - max(dates)).days > ttl_days:
            entry["status"] = STATUS_EXPIRED


def decide(entry, mode, threshold, ttl_days):
    """learn, propose (the developer decides, in developer-review mode), wait or already-learned."""
    if entry["status"] == STATUS_LEARNED:
        return DECISION_ALREADY_LEARNED
    if entry["status"] in (STATUS_EXPIRED, STATUS_SUPERSEDED):
        return DECISION_WAIT
    if is_explicit(entry, ttl_days) or live_episodes(entry, ttl_days) >= threshold:
        return DECISION_PROPOSE if mode == MODE_DEVELOPER_REVIEW else DECISION_LEARN
    return DECISION_WAIT


def validate_instruction(statement, kind, key, quote, max_statement_chars):
    statement = (statement or "").strip()
    if not statement:
        raise StateError("--statement is empty: write the instruction in its general form")
    if "\n" in statement:
        raise StateError("--statement has several lines: one instruction is one sentence")
    if len(statement) > max_statement_chars:
        raise StateError(f"--statement has {len(statement)} characters, over rules.maxStatementChars "
                         f"({max_statement_chars}): one instruction per statement, the rest as details")
    if kind not in KINDS:
        raise StateError(f"--kind must be one of {', '.join(KINDS)}")
    if key is not None and not DECISION_KEY.match(key):
        raise StateError(f"--key {key!r} must be lowercase segments joined by dots, such as testing.unit-runner")
    if not (quote or "").strip():
        raise StateError("--quote is empty: the evidence is what the user wrote, word for word")
    return statement


def record(project_root, instruction, settings):
    """Add the evidence of one instruction to the registry and decide what happens with it.

    instruction: statement, kind, key, paths, quote, session, episode, date (datetime.date), source and
    explicit. settings: mode, threshold, ttl_days, max_statement_chars and today (datetime.date).
    Returns (entry, decision, same_key): same_key are the other entries that decide the same key with
    another statement, which the agent reads before writing (one may be the instruction it replaces).
    """
    statement = validate_instruction(instruction["statement"], instruction["kind"], instruction.get("key"),
                                     instruction["quote"], settings["max_statement_chars"])
    session = instruction.get("session") or UNKNOWN_SESSION
    date = instruction["date"]
    evidence = {"session": session, "episode": episode_of(session, date, instruction.get("episode")),
                "date": date.isoformat(), "quote": instruction["quote"].strip(), "source": instruction["source"]}
    if instruction.get("explicit"):
        # On the evidence, not on the entry: an explicit request that expires stops counting.
        evidence["explicit"] = True
    with RegistryLock(project_root):
        registry = read_registry(project_root)
        refresh_expiry(registry, settings["today"], settings["ttl_days"])
        wanted = normalized_statement(statement)
        entry = next((item for item in registry["candidates"]
                      if normalized_statement(item["statement"]) == wanted), None)
        if entry is None:
            entry = {"id": candidate_id(statement), "statement": statement, "kind": instruction["kind"],
                     "status": STATUS_CANDIDATE, "created": date.isoformat(), "evidence": []}
            registry["candidates"].append(entry)
        for field in ("key", "paths"):
            if instruction.get(field):
                entry[field] = instruction[field]
        if evidence not in entry["evidence"]:
            if entry["status"] == STATUS_SUPERSEDED:
                # The user gives a replaced instruction again: it comes back as a candidate that counts
                # only the evidence from now on, so it can replace the newer one again.
                entry["status"] = STATUS_CANDIDATE
                entry["liveFrom"] = len(entry["evidence"])
                entry.pop("supersededBy", None)
            entry["evidence"].append(evidence)
        entry["updated"] = max(entry.get("updated", date.isoformat()), date.isoformat())
        if entry["status"] == STATUS_EXPIRED:
            # New evidence brings it back, counting only what is not expired.
            entry["status"] = STATUS_CANDIDATE
        refresh_expiry(registry, settings["today"], settings["ttl_days"])
        decision = decide(entry, settings["mode"], settings["threshold"], settings["ttl_days"])
        write_registry(project_root, registry)
    same_key = [item for item in registry["candidates"]
                if item is not entry and entry.get("key") and item.get("key") == entry["key"]
                and item["status"] in (STATUS_CANDIDATE, STATUS_LEARNED)]
    return entry, decision, same_key


def entries(project_root, today, ttl_days):
    """Every entry of the registry, with the expiry of today applied (read only: nothing is written)."""
    registry = read_registry(project_root)
    refresh_expiry(registry, today, ttl_days)
    return registry["candidates"]


def public_view(entry, ttl_days):
    """An entry without the quotes of the user: what list, status and anything outside this file show."""
    view = {field: entry[field] for field in ("id", "statement", "kind", "status", "created", "updated",
                                               "key", "paths") if field in entry}
    view["episodes"] = live_episodes(entry, ttl_days)
    view["explicit"] = is_explicit(entry, ttl_days)
    view["evidence"] = [{field: item[field] for field in ("session", "episode", "date", "source", "explicit")
                         if field in item} for item in entry["evidence"]]
    return view
