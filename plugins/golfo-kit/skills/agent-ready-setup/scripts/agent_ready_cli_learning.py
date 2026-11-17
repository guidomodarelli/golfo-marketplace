"""agent-ready learn: the registry of what the agent learns from the instructions of the user.

record adds the evidence of one instruction and prints what happens with it; apply writes one that
record decided to learn as a rule or a skill of the project and commits it; status and list read the
registry. None of them prints the quotes of the user, which stay in .agents/learning/candidates.json.
"""

import datetime
import sys

import agent_ready_learning as learning
import agent_ready_learning_apply as learning_apply
from agent_ready_cli_common import EXIT_OK, find_repository_root
from agent_ready_common import StateError, serialize_json
from agent_ready_config import resolve_configuration

LEARNING_ENABLED_KEY = "learning.enabled"
LEARNING_MODE_KEY = "learning.mode"
LEARNING_THRESHOLD_KEY = "learning.threshold"
LEARNING_TTL_KEY = "learning.candidateTtlDays"
MAX_STATEMENT_CHARS_KEY = "rules.maxStatementChars"

DECISION_MESSAGES = {
    learning.DECISION_LEARN: "learn it now as a {kind} of the project: agent-ready learn apply {id}",
    learning.DECISION_PROPOSE: "learning.mode is developer-review: leave it for the developer, write nothing",
    learning.DECISION_WAIT: "keep it as a candidate until another episode repeats it ({episodes} of {threshold})",
    learning.DECISION_ALREADY_LEARNED: "already learned: nothing new to write",
}


def settings_of(project_root):
    configuration = resolve_configuration(project_root)
    return {
        "enabled": configuration.value(LEARNING_ENABLED_KEY),
        "mode": configuration.value(LEARNING_MODE_KEY),
        "threshold": configuration.value(LEARNING_THRESHOLD_KEY),
        "ttl_days": configuration.value(LEARNING_TTL_KEY),
        "max_statement_chars": configuration.value(MAX_STATEMENT_CHARS_KEY),
        "today": datetime.date.today(),
    }


def command_learn_record(arguments):
    """Record the evidence of one instruction of the user and print the decision."""
    project_root = find_repository_root(arguments.project)
    settings = settings_of(project_root)
    if not settings["enabled"]:
        sys.stderr.write(f"{LEARNING_ENABLED_KEY} is off: nothing was recorded.\n")
        return EXIT_OK
    date = learning.parse_date(arguments.date, "--date") if arguments.date else settings["today"]
    if date > settings["today"]:
        raise StateError(f"--date {arguments.date} is in the future")
    instruction = {"statement": arguments.statement, "kind": arguments.kind, "key": arguments.key,
                   "paths": arguments.paths or None, "quote": arguments.quote, "session": arguments.session,
                   "episode": arguments.episode, "date": date, "source": arguments.source,
                   "explicit": arguments.explicit}
    entry, decision, same_key = learning.record(project_root, instruction, settings)
    episodes = learning.live_episodes(entry, settings["ttl_days"])
    if arguments.json:
        sys.stdout.write(serialize_json({"candidate": learning.public_view(entry, settings["ttl_days"]),
                                         "decision": decision, "threshold": settings["threshold"],
                                         "sameKey": [learning.public_view(item, settings["ttl_days"])
                                                     for item in same_key]}))
        return EXIT_OK
    message = DECISION_MESSAGES[decision].format(kind=entry["kind"], id=entry["id"], episodes=episodes,
                                                 threshold=settings["threshold"])
    sys.stdout.write(f"{entry['id']}  {decision}: {message}\n    {entry['statement']}\n")
    for item in same_key:
        sys.stdout.write(f"  same key {entry['key']}: {item['id']} ({item['status']}) {item['statement']}\n")
    return EXIT_OK


def command_learn_apply(arguments):
    """Write one entry that record decided to learn, register it and commit it."""
    project_root = find_repository_root(arguments.project)
    settings = settings_of(project_root)
    written = learning_apply.apply(project_root, arguments.id, settings, arguments.skill)
    learned = written["entry"]["learned"]
    if arguments.json:
        sys.stdout.write(serialize_json({"id": arguments.id, "commit": written["commit"], "learned": learned,
                                         "supersedes": written["supersedes"]}))
        return EXIT_OK
    target = learned.get("ruleId") or learned.get("skill")
    extras = "".join(f", {label} {value}" for label, value in (("overrides", learned.get("overrides")),
                                                                ("replaces", written["supersedes"])) if value)
    sys.stdout.write(f"{arguments.id}  {learned['action']}: {target} in {learned['path']}{extras} "
                     f"(commit {written['commit'][:12]})\n")
    return EXIT_OK


def read_entries(arguments):
    project_root = find_repository_root(arguments.project)
    settings = settings_of(project_root)
    return learning.entries(project_root, settings["today"], settings["ttl_days"]), settings


def command_learn_status(arguments):
    """How many entries are in each status, the settings that decide, and what waits for a repetition."""
    items, settings = read_entries(arguments)
    counts = {status: sum(1 for item in items if item["status"] == status) for status in learning.STATUSES}
    waiting = [item for item in items if item["status"] == learning.STATUS_CANDIDATE]
    if arguments.json:
        sys.stdout.write(serialize_json({
            "enabled": settings["enabled"], "mode": settings["mode"], "threshold": settings["threshold"],
            "candidateTtlDays": settings["ttl_days"], "counts": counts,
            "candidates": [learning.public_view(item, settings["ttl_days"]) for item in waiting]}))
        return EXIT_OK
    state = settings["mode"] if settings["enabled"] else "off"
    sys.stdout.write(f"Learning: {state}, {settings['threshold']} episodes to learn an implicit instruction, "
                     f"candidates expire after {settings['ttl_days']} days without evidence.\n")
    sys.stdout.write("  " + ", ".join(f"{counts[status]} {status}" for status in learning.STATUSES) + "\n")
    for item in waiting:
        episodes = learning.live_episodes(item, settings["ttl_days"])
        sys.stdout.write(f"  {item['id']}  {episodes}/{settings['threshold']} episodes  {item['statement']}\n")
    return EXIT_OK


def command_learn_list(arguments):
    """Every entry, or those of one status, without the quotes."""
    items, settings = read_entries(arguments)
    if arguments.status:
        items = [item for item in items if item["status"] == arguments.status]
    if arguments.json:
        sys.stdout.write(serialize_json({"entries": [learning.public_view(item, settings["ttl_days"])
                                                     for item in items]}))
        return EXIT_OK
    if not items:
        sys.stdout.write("Nothing learned or waiting.\n")
        return EXIT_OK
    for item in items:
        key = f"  key={item['key']}" if item.get("key") else ""
        episodes = learning.live_episodes(item, settings["ttl_days"])
        sys.stdout.write(f"{item['id']}  {item['status']}  {item['kind']}  {episodes} episodes{key}\n"
                         f"    {item['statement']}\n")
    return EXIT_OK


def register(subparsers, new_subparser):
    """Add learn record|apply|status|list to the CLI parser."""
    learn = new_subparser(subparsers, "learn", "Record and read what the agent learns from the user.",
                          "  agent-ready learn status\n  agent-ready learn list --status candidate", None,
                          with_project=False)
    actions = learn.add_subparsers(dest="learn_action", metavar="<action>", required=True)
    record_action = new_subparser(
        actions, "record", "Record one instruction of the user and print whether to learn it now.",
        "  agent-ready learn record --kind rule --statement 'Put the case number in the header of every record.'"
        " \\\n    --quote 'de ahora en más, el número de expediente va en el encabezado' --explicit",
        command_learn_record)
    record_action.add_argument("--statement", required=True,
                               help="the instruction in its general form, one sentence, without data of the case")
    record_action.add_argument("--kind", required=True, choices=learning.KINDS,
                               help="rule (a preference or a restriction), skill (a procedure of several steps) "
                                    "or nested (only for one folder)")
    record_action.add_argument("--quote", required=True, help="what the user wrote, word for word")
    record_action.add_argument("--key", help="the decision the instruction takes, such as records.header")
    record_action.add_argument("--paths", action="append",
                               help="a glob of the folder the instruction is for; repeatable")
    record_action.add_argument("--explicit", action="store_true",
                               help="the user asked for it to last («always», «from now on», «never»)")
    record_action.add_argument("--session", help=f"session of the provider (default: {learning.UNKNOWN_SESSION})")
    record_action.add_argument("--episode", help="episode the hook of the session reported (default: the session "
                                                 "and the date)")
    record_action.add_argument("--date", help="date of the message, as YYYY-MM-DD (default: today)")
    record_action.add_argument("--source", choices=learning.SOURCES, default=learning.SOURCE_IN_SESSION,
                               help="in-session (the agent, while working) or session-end (the review at the end)")
    record_action.add_argument("--json", action="store_true", help="print the result as JSON")
    apply_action = new_subparser(
        actions, "apply", "Write an instruction record decided to learn as a rule or skill of the project, and commit it.",
        "  agent-ready learn apply learn-5db4a07240\n"
        "  agent-ready learn apply learn-0c1d2e3f4a --skill .agents/skills/records",
        command_learn_apply)
    apply_action.add_argument("id", help="id of the entry, as record and list print it")
    apply_action.add_argument("--skill", help="the directory of the skill the agent wrote, for an entry of kind skill")
    apply_action.add_argument("--json", action="store_true", help="print the result as JSON")
    status_action = new_subparser(actions, "status", "The settings of learning and what waits for a repetition.",
                                  "  agent-ready learn status\n  agent-ready learn status --json", command_learn_status)
    status_action.add_argument("--json", action="store_true", help="print the result as JSON")
    list_action = new_subparser(actions, "list", "Every entry of the registry, without the quotes of the user.",
                                "  agent-ready learn list\n  agent-ready learn list --status learned --json",
                                command_learn_list)
    list_action.add_argument("--status", choices=learning.STATUSES, help="only the entries of this status")
    list_action.add_argument("--json", action="store_true", help="print the result as JSON")
