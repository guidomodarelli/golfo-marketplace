"""agent-ready learn: the registry of what the agent learns from the instructions of the user.

record adds the evidence of one instruction and prints what happens with it; apply writes one that
record decided to learn as a rule or a skill of the project and commits it; status and list read the
registry. None of them prints the quotes of the user, which stay in .agents/learning/candidates.json.
"""

import datetime
import os
import sys

import agent_ready_learning as learning
import agent_ready_learning_apply as learning_apply
import agent_ready_learning_episodes as learning_episodes
import agent_ready_learning_promote as learning_promote
import agent_ready_learning_reorganize as learning_reorganize
import agent_ready_learning_review as learning_review
import agent_ready_learning_schedule as learning_schedule
import agent_ready_learning_session_review as session_review
import agent_ready_learning_share as learning_share
from agent_ready_cli_common import EXIT_OK, SCRIPT_DIRECTORY, find_repository_root
from agent_ready_common import StateError, serialize_json, write_text_atomically
from agent_ready_config import resolve_configuration
from agent_ready_options import CONTEXT_BUDGET_ENABLED_KEY, CONTEXT_BUDGET_RULES_BYTES_KEY

LEARNING_ENABLED_KEY = "learning.enabled"
LEARNING_MODE_KEY = "learning.mode"
LEARNING_THRESHOLD_KEY = "learning.threshold"
LEARNING_TTL_KEY = "learning.candidateTtlDays"
LEARNING_GAP_KEY = "learning.episodeGapHours"
LEARNING_SESSION_END_KEY = "learning.hooks.sessionEnd"
LEARNING_SESSION_START_KEY = "learning.hooks.sessionStart"
LEARNING_SWEEP_INTERVAL_KEY = "learning.sweep.intervalMinutes"
LEARNING_REORGANIZE_AUTO_KEY = "learning.reorganize.auto"
LEARNING_REORGANIZE_MAX_LINES_KEY = "learning.reorganize.maxRuleLines"
LEARNING_REORGANIZE_INTERVAL_KEY = "learning.reorganize.minIntervalDays"
CLI_PATH = os.path.join(SCRIPT_DIRECTORY, "agent-ready")
PROVIDERS = ("claude", "codex")
SUMMARY_LOG_LINES = 5
SUMMARY_CANDIDATES = 5
MAX_STATEMENT_CHARS_KEY = "rules.maxStatementChars"

DECISION_MESSAGES = {
    learning.DECISION_LEARN: "learn it now as a {kind} of the project: agent-ready learn apply {id}",
    learning.DECISION_PROPOSE: "learning.mode is developer-review: leave it for the developer, write nothing",
    learning.DECISION_WAIT: "keep it as a candidate until another episode repeats it ({episodes} of {threshold})",
    learning.DECISION_ALREADY_LEARNED: "already learned: nothing new to write",
    learning.DECISION_REJECTED: "the developer rejected it: write nothing (agent-ready learn accept {id} brings it back)",
}


def settings_of(project_root):
    configuration = resolve_configuration(project_root)
    return {
        "enabled": configuration.value(LEARNING_ENABLED_KEY),
        "mode": configuration.value(LEARNING_MODE_KEY),
        "threshold": configuration.value(LEARNING_THRESHOLD_KEY),
        "ttl_days": configuration.value(LEARNING_TTL_KEY),
        "gap_hours": configuration.value(LEARNING_GAP_KEY),
        "session_review": configuration.value(LEARNING_SESSION_END_KEY),
        "session_start": configuration.value(LEARNING_SESSION_START_KEY),
        "sweep_interval": configuration.value(LEARNING_SWEEP_INTERVAL_KEY),
        "max_statement_chars": configuration.value(MAX_STATEMENT_CHARS_KEY),
        "reorganize_auto": configuration.value(LEARNING_REORGANIZE_AUTO_KEY),
        "reorganize_max_rule_lines": configuration.value(LEARNING_REORGANIZE_MAX_LINES_KEY),
        "reorganize_min_interval_days": configuration.value(LEARNING_REORGANIZE_INTERVAL_KEY),
        "rules_budget_bytes": (configuration.value(CONTEXT_BUDGET_RULES_BYTES_KEY)
                               if configuration.value(CONTEXT_BUDGET_ENABLED_KEY) else None),
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
    """Write one entry that record decided to learn (or, with accept, one the developer chose), register
    it and commit it."""
    project_root = find_repository_root(arguments.project)
    settings = settings_of(project_root)
    written = learning_apply.apply(project_root, arguments.id, settings, arguments.skill,
                                   accepted=arguments.learn_action == "accept")
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


def command_learn_reject(arguments):
    """Keep an entry from being learned until the developer accepts it."""
    project_root = find_repository_root(arguments.project)
    entry, sha = learning_review.reject(project_root, arguments.id, settings_of(project_root))
    if arguments.json:
        sys.stdout.write(serialize_json({"id": entry["id"], "status": entry["status"], "commit": sha}))
        return EXIT_OK
    sys.stdout.write(f"{entry['id']}  rejected (commit {sha[:12]})\n    {entry['statement']}\n")
    return EXIT_OK


def command_learn_revert(arguments):
    """Undo a learning in its rule or skill, with a commit of its own."""
    project_root = find_repository_root(arguments.project)
    entry, learned_sha, revert_sha = learning_review.revert(project_root, arguments.id, settings_of(project_root))
    if arguments.json:
        sys.stdout.write(serialize_json({"id": entry["id"], "status": entry["status"], "reverts": learned_sha,
                                         "commit": revert_sha, "restored": entry.get("supersedes")}))
        return EXIT_OK
    restored = f", {entry['supersedes']} is learned again" if entry.get("supersedes") else ""
    sys.stdout.write(f"{entry['id']}  reverted: {entry['learned']['path']} as before commit {learned_sha[:12]}"
                     f"{restored} (commit {revert_sha[:12]})\n")
    return EXIT_OK


def command_learn_keep(arguments):
    """Keep a learned rule over the new version of the managed rule it replaces."""
    project_root = find_repository_root(arguments.project)
    entry, changed, sha = learning_review.keep(project_root, arguments.id, settings_of(project_root))
    if arguments.json:
        sys.stdout.write(serialize_json({"id": entry["id"], "kept": changed, "commit": sha}))
        return EXIT_OK
    sys.stdout.write(f"{entry['id']}  kept over the new {', '.join(changed)} (commit {sha[:12]})\n"
                     f"    {entry['statement']}\n")
    return EXIT_OK


def command_learn_retire(arguments):
    """Remove a learned rule without bringing back what it replaced."""
    project_root = find_repository_root(arguments.project)
    entry, sha = learning_review.retire(project_root, arguments.id, settings_of(project_root))
    if arguments.json:
        sys.stdout.write(serialize_json({"id": entry["id"], "status": entry["status"], "commit": sha,
                                         "restores": entry["retired"].get("restores")}))
        return EXIT_OK
    restores = entry["retired"].get("restores")
    restores = f"; {restores} comes back on the next apply" if restores else ""
    sys.stdout.write(f"{entry['id']}  retired: {entry['learned']['ruleId']} removed from {entry['learned']['path']}"
                     f"{restores} (commit {sha[:12]})\n")
    return EXIT_OK


def learning_active(project_root, settings):
    """The hooks stay silent unless the learning profile is in use and learning.enabled is on."""
    return settings["enabled"] and learning_episodes.learning_selected(project_root)


def start_sweep_when_needed(project_root, settings, now, reorganize=False):
    """Start the sweep in the background when an episode waits for its review: hooks must not wait for it.

    With learning.hooks.sessionEnd off the sweep calls no provider, so it runs here and only drops the queue.
    ``reorganize`` is the end of a chat, which also reorganizes what was learned when that is due.
    """
    reorganize = reorganize and learning_reorganize.is_due(project_root, settings, now)
    if not learning_episodes.needs_sweep(project_root, now, settings["gap_hours"]) and not reorganize:
        return
    if not settings["session_review"] and not reorganize:
        session_review.sweep(project_root, settings, lambda line: None)
        return
    session_review.start_sweep(project_root, CLI_PATH, lambda: sweep_project(project_root, settings, reorganize),
                               ["--reorganize"] if reorganize else [])


def sweep_project(project_root, settings, reorganize):
    """The sweep of one repository: the queued reviews, then the reorganization when it is due."""
    session_review.sweep(project_root, settings, write_sweep_line)
    if reorganize:
        learning_reorganize.run_when_due(project_root, settings, learning_episodes.latest_provider(project_root),
                                         write_sweep_line)


def write_sweep_line(line):
    sys.stdout.write(f"[agent-ready learn sweep] {line}\n")


def command_learn_episode(arguments):
    """The episode of a session: with --touch, a message of the user arrived (the hook of the prompt);
    with --end, the chat ended (SessionEnd); with --review-now, the context is about to be compacted."""
    project_root = find_repository_root(arguments.project)
    settings = settings_of(project_root)
    hook_modes = arguments.touch or arguments.end or arguments.review_now
    if hook_modes:
        # The hooks run on every message: they stay silent unless the learning profile is in use.
        if not learning_active(project_root, settings):
            return EXIT_OK
        now = learning_episodes.current_time()
        transcript = os.path.abspath(arguments.transcript) if arguments.transcript else None
        if arguments.touch:
            session, started = learning_episodes.touch(project_root, arguments.session, now, settings["gap_hours"],
                                                       transcript, arguments.provider)
            if started and not arguments.json:
                sys.stdout.write(f"[agent-ready learn] Episode {session['episodeId']} started: record instructions of "
                                 f"the user with --session {arguments.session} --episode {session['episodeId']}.\n")
        elif arguments.end:
            learning_episodes.end(project_root, arguments.session, now, settings["gap_hours"], transcript)
        else:
            learning_episodes.review_now(project_root, arguments.session, now, transcript)
        start_sweep_when_needed(project_root, settings, now, reorganize=arguments.end)
        if not arguments.touch:
            return EXIT_OK
    elif arguments.scope_question:
        if not learning_episodes.mark_scope_question(project_root, arguments.session):
            raise StateError(f"the scope question of this episode was already asked: apply the instruction to the "
                             "current document only and record it without --explicit")
        session = learning_episodes.current(project_root, arguments.session)
    else:
        session = learning_episodes.current(project_root, arguments.session)
        if session is None and not arguments.json:
            sys.stdout.write(f"Session {arguments.session} has no episode yet: its first message opens one.\n")
            return EXIT_OK
    if arguments.json:
        sys.stdout.write(serialize_json({"session": arguments.session, "episode": session}))
    elif not hook_modes:
        asked = "asked" if session.get("scopeQuestionAsked") else "not asked"
        sys.stdout.write(f"{session['episodeId']}  since {session['episodeStartedAt']}, scope question {asked}\n")
    return EXIT_OK


def log_lines(project_root):
    path = os.path.join(project_root, learning_apply.LOG_RELATIVE_PATH)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.startswith("- ")]


def command_learn_summary(arguments):
    """A few lines for the start of a session: what was learned lately and what waits. Silent when the
    learning profile is not in use or there is nothing to tell."""
    project_root = find_repository_root(arguments.project)
    settings = settings_of(project_root)
    if not learning_active(project_root, settings):
        return EXIT_OK
    # The start of a session also sweeps: the episodes other chats left idle get their review.
    start_sweep_when_needed(project_root, settings, learning_episodes.current_time())
    if not settings["session_start"]:
        return EXIT_OK
    items = learning.entries(project_root, settings["today"], settings["ttl_days"])
    waiting = [item for item in items if item["status"] == learning.STATUS_CANDIDATE]
    recent = log_lines(project_root)[-SUMMARY_LOG_LINES:]
    if not waiting and not recent:
        return EXIT_OK
    sys.stdout.write("[agent-ready learn] What this project learned from the user (references/learning.md):\n")
    for line in recent:
        sys.stdout.write(f"  {line[2:]}\n")
    if waiting:
        sys.stdout.write("  Waiting for another episode; if the user repeats one, record it again:\n")
        for item in waiting[:SUMMARY_CANDIDATES]:
            sys.stdout.write(f"    {item['id']}  {item['statement']}\n")
        if len(waiting) > SUMMARY_CANDIDATES:
            sys.stdout.write(f"    and {len(waiting) - SUMMARY_CANDIDATES} more (agent-ready learn list --status candidate)\n")
    return EXIT_OK


def command_learn_sweep(arguments):
    """What the hooks start in the background: close idle episodes and record what their review finds.

    With --registered, what the scheduled task runs: the sweep of every repository that asked for it.
    """
    if arguments.registered:
        return sweep_registered()
    project_root = find_repository_root(arguments.project)
    settings = settings_of(project_root)
    if not learning_active(project_root, settings):
        return EXIT_OK
    sweep_project(project_root, settings, arguments.reorganize)
    return EXIT_OK


def sweep_registered():
    """The sweep of every registered repository; one that fails never stops the others."""
    try:
        # CI and review mode never touch the scheduler, so they leave the records as they are.
        if not schedule_blocked():
            learning_schedule.prune_missing(CLI_PATH)
    except (learning_schedule.ScheduleError, StateError, OSError) as problem:
        write_sweep_line(f"scheduled sweep: {problem}")
    for _, record in learning_schedule.registered_projects():
        project_root = record["project"]
        try:
            settings = settings_of(project_root)
            if learning_active(project_root, settings):
                # The scheduled task is the one that reorganizes when nobody closes a chat.
                sweep_project(project_root, settings, True)
        except (StateError, OSError) as problem:
            write_sweep_line(f"{project_root}: {problem}")
    return EXIT_OK


def schedule_blocked():
    """Why this run must not touch the scheduler of the machine, or None."""
    blocked = session_review.provider_blocked()
    return f"no scheduled task under {blocked}" if blocked else None


def schedule_sweep(project_root):
    """Register this repository for the scheduled sweep, or drop it, as its settings ask. What an apply runs.

    Returns {"status", "detail"} (agent_ready_learning_schedule.register); a refusal of the scheduler
    never raises: the hooks still close the episodes.
    """
    blocked = schedule_blocked()
    if blocked:
        return {"status": learning_schedule.STATUS_SKIPPED, "detail": blocked}
    settings = settings_of(project_root)
    interval = settings["sweep_interval"] if learning_active(project_root, settings) else 0
    try:
        return learning_schedule.register(project_root, interval, CLI_PATH)
    except StateError as problem:
        return {"status": learning_schedule.STATUS_FAILED, "detail": str(problem)}


def unschedule_sweep(project_root):
    """agent-ready remove: this repository stops asking for the scheduled sweep."""
    if schedule_blocked() or learning_schedule.read_project_record(project_root) is None:
        return None
    try:
        return learning_schedule.unregister(project_root, CLI_PATH)
    except StateError as problem:
        return {"status": learning_schedule.STATUS_FAILED, "detail": str(problem)}


def schedule_state(project_root):
    """What status and doctor say of the scheduled sweep: None when it does not apply, else (ok, detail)."""
    settings = settings_of(project_root)
    if not learning_active(project_root, settings) or settings["sweep_interval"] == 0 or schedule_blocked():
        return None
    return learning_schedule.state(project_root)


def command_learn_schedule(arguments):
    """Register the scheduled sweep as the settings ask, as an apply does (after changing them by hand)."""
    project_root = find_repository_root(arguments.project)
    report = schedule_sweep(project_root)
    if arguments.json:
        sys.stdout.write(serialize_json(report))
    else:
        stream = sys.stderr if report["status"] == learning_schedule.STATUS_FAILED else sys.stdout
        stream.write(f"Scheduled learning sweep: {report['status']}: {report['detail']}\n")
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
    # In developer-review mode, what the rules of evidence would learn waits for learn accept.
    proposals = [item for item in waiting if learning.decide(item, settings["mode"], settings["threshold"],
                                                             settings["ttl_days"]) == learning.DECISION_PROPOSE]
    reorganizations = learning_reorganize.plan(find_repository_root(arguments.project), settings)["proposals"]
    if arguments.json:
        sys.stdout.write(serialize_json({
            "enabled": settings["enabled"], "mode": settings["mode"], "threshold": settings["threshold"],
            "candidateTtlDays": settings["ttl_days"], "counts": counts,
            "candidates": [learning.public_view(item, settings["ttl_days"]) for item in waiting],
            "proposals": [item["id"] for item in proposals],
            "reorganizations": [item["id"] for item in reorganizations]}))
        return EXIT_OK
    state = settings["mode"] if settings["enabled"] else "off"
    sys.stdout.write(f"Learning: {state}, {settings['threshold']} episodes to learn an implicit instruction, "
                     f"candidates expire after {settings['ttl_days']} days without evidence.\n")
    sys.stdout.write("  " + ", ".join(f"{counts[status]} {status}" for status in learning.STATUSES) + "\n")
    for item in waiting:
        if item in proposals:
            continue
        episodes = learning.live_episodes(item, settings["ttl_days"])
        sys.stdout.write(f"  {item['id']}  {episodes}/{settings['threshold']} episodes  {item['statement']}\n")
    if proposals:
        sys.stdout.write("Proposals for the developer (agent-ready learn accept <id>, or reject <id>):\n")
        for item in proposals:
            sys.stdout.write(f"  {item['id']}  {item['statement']}\n")
    if reorganizations:
        sys.stdout.write(f"{len(reorganizations)} reorganizations wait for the developer: "
                         "agent-ready learn reorganize --plan\n")
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


def operation_line(operation):
    target = " | ".join(operation["statements"]) or f"skill {operation['skill']['name']}"
    return f"{operation['type']} {', '.join(operation['ruleIds'])} -> {target}"


def print_plan(report):
    for trigger in report["triggers"]:
        detail = {learning_reorganize.TRIGGER_LONG_RULE: f"over {trigger.get('maxRuleLines')} lines",
                  learning_reorganize.TRIGGER_TOPIC: f"topic {trigger.get('topic')}",
                  learning_reorganize.TRIGGER_CONTEXT_BUDGET: f"{trigger.get('bytes')} of {trigger.get('limitBytes')} "
                                                              "bytes of rules loaded at the start",
                  learning_reorganize.TRIGGER_CONFLICT: f"key {trigger.get('key')}"}[trigger["trigger"]]
        sys.stdout.write(f"  trigger {trigger['trigger']} ({detail}): {', '.join(trigger['ruleIds'])}\n")
    if not report["triggers"]:
        sys.stdout.write("  no trigger holds: the learned rules need no reorganization now\n")


def command_learn_reorganize(arguments):
    """Reorganize the learned rules now; --plan shows what waits, --accept and --dismiss decide a proposal."""
    project_root = find_repository_root(arguments.project)
    settings = settings_of(project_root)
    if arguments.accept:
        written = learning_reorganize.accept(project_root, arguments.accept, settings)
        if arguments.json:
            sys.stdout.write(serialize_json(written))
        else:
            sys.stdout.write(f"{arguments.accept}  accepted: {operation_line(written['operation'])} "
                             f"(commit {written['commit'][:12]})\n")
        return EXIT_OK
    if arguments.dismiss:
        proposal = learning_reorganize.dismiss(project_root, arguments.dismiss)
        if arguments.json:
            sys.stdout.write(serialize_json({"dismissed": proposal["id"]}))
        else:
            sys.stdout.write(f"{proposal['id']}  dismissed: {operation_line(proposal)}\n")
        return EXIT_OK
    if arguments.plan:
        report = learning_reorganize.plan(project_root, settings)
        if arguments.json:
            sys.stdout.write(serialize_json(report))
            return EXIT_OK
        sys.stdout.write("Reorganization of what was learned:\n")
        print_plan(report)
        for proposal in report["proposals"]:
            sys.stdout.write(f"  {proposal['id']}  {operation_line(proposal)}\n      waits: {proposal['waiting']}"
                             + (f" ({proposal['verdict']['reason']})" if proposal.get("verdict") else "") + "\n")
        if report["proposals"]:
            sys.stdout.write("Decide each one with agent-ready learn reorganize --accept <id> or --dismiss <id>.\n")
        return EXIT_OK
    report = learning_reorganize.reorganize(project_root, settings,
                                            arguments.provider or learning_episodes.latest_provider(project_root))
    if arguments.json:
        sys.stdout.write(serialize_json(report))
        return EXIT_OK
    sys.stdout.write(f"Reorganization: {report['status']}\n")
    print_plan(report)
    for written in report["applied"]:
        sys.stdout.write(f"  applied  {operation_line(written['operation'])} (commit {written['commit'][:12]})\n")
    for proposal in report["proposed"]:
        sys.stdout.write(f"  proposed {proposal['id']}  {operation_line(proposal)}: {proposal['waiting']}\n")
    for problem in report["errors"]:
        sys.stdout.write(f"  not written {problem}\n")
    return EXIT_OK


def command_learn_export(arguments):
    """What this repository learned, without the quotes of the user, for its client to review and share."""
    project_root = find_repository_root(arguments.project)
    name = arguments.name or os.path.basename(os.path.normpath(project_root))
    document = learning_share.export(project_root, name, datetime.date.today())
    if not arguments.output:
        sys.stdout.write(serialize_json(document))
        return EXIT_OK
    write_text_atomically(os.path.abspath(arguments.output), serialize_json(document))
    sys.stdout.write(f"Exported {len(document['learned'])} learned instructions of {name} to {arguments.output}: "
                     "it holds the statements only, never what the user wrote; review it before sharing it.\n")
    return EXIT_OK


def command_learn_harvest(arguments):
    """Group what several repositories learned, as candidates for a pack. Reads only what was learned."""
    configuration = resolve_configuration(os.path.abspath(arguments.project))
    repositories = arguments.repos
    if repositories is None:
        repositories = configuration.value(learning_share.HARVEST_REPOS_KEY)
    if not repositories and not arguments.exports:
        raise StateError(f"no repository to harvest: pass --repos, --export, or list them in "
                         f"{learning_share.HARVEST_REPOS_KEY} of the user configuration")
    threshold = arguments.threshold or configuration.value(learning_share.HARVEST_THRESHOLD_KEY)
    if threshold < 2:
        raise StateError("--threshold must be 2 or more: harvest looks for what several repositories learned")
    report = learning_share.harvest(repositories, arguments.exports or [], threshold, arguments.provider,
                                    configuration.value(MAX_STATEMENT_CHARS_KEY),
                                    datetime.datetime.now().astimezone())
    if arguments.json:
        sys.stdout.write(serialize_json(report))
        return EXIT_OK
    sys.stdout.write(f"Harvest of {len(report['sources'])} sources, {threshold} repositories to propose:\n")
    for source in report["sources"]:
        where = source.get("path") or source.get("export")
        sys.stdout.write(f"  {source['name']}  {source['status']}, {source['learned']} learned  ({where})\n")
    if report.get("reviewProblem"):
        sys.stdout.write(f"  {report['reviewProblem']}: {report['review']}\n")
    if not report["candidates"]:
        sys.stdout.write("Nothing that several repositories learned.\n")
        return EXIT_OK
    sys.stdout.write("Candidates for a pack (general statements, without data of a client):\n")
    for candidate in report["candidates"]:
        sys.stdout.write(f"  {candidate['id']}  {candidate['kind']}  in {', '.join(candidate['repositories'])}\n"
                         f"      {candidate['statement']}\n")
    return EXIT_OK


def command_learn_promote(arguments):
    """Write a harvest candidate (or a learned rule) as a rule of a profile of a pack, by pull request."""
    project_root = None
    if not arguments.id.startswith(learning_share.HARVEST_ID_PREFIX):
        project_root = find_repository_root(arguments.project)
    configuration = resolve_configuration(os.path.abspath(project_root or arguments.project))
    item = learning_promote.resolve_item(arguments.id, project_root)
    pack_root = os.path.abspath(arguments.to)
    change = learning_promote.plan(item, pack_root, arguments.profile, arguments.file,
                                   configuration.value(MAX_STATEMENT_CHARS_KEY))
    written = None
    if arguments.yes:
        written = learning_promote.write(change, pack_root, not arguments.no_pr)
        learning_promote.record_promotion(change, written, datetime.date.today())
    if arguments.json:
        report = {field: change[field] for field in ("id", "statement", "pack", "profile", "file", "action", "ruleId",
                                                     "rule", "diff")}
        sys.stdout.write(serialize_json(dict(report, written=written)))
        return EXIT_OK
    verb = "add" if change["action"] == learning_promote.ACTION_ADD else "change the statement of"
    sys.stdout.write(f"Promote {change['id']} to {change['pack']}/{change['profile']}: {verb} {change['rule']} in "
                     f"{change['file']}\n    {change['statement']}\n\n{change['diff']}")
    if written is None:
        sys.stdout.write(f"\nNothing was written in {arguments.to}. Run it again with --yes to commit it on a branch "
                         "and open the pull request.\n")
    elif written["pullRequest"]:
        sys.stdout.write(f"\nCommitted on {written['branch']} ({written['commit'][:12]}); pull request: "
                         f"{written['pullRequest']}\n")
    else:
        sys.stdout.write(f"\nCommitted on {written['branch']} ({written['commit'][:12]}); push it and open the pull "
                         "request when you are ready.\n")
    return EXIT_OK


def register(subparsers, new_subparser):
    """Add learn record|apply|accept|reject|revert|keep|retire|status|list|episode|summary|sweep|schedule|reorganize|
    export|harvest|promote to the CLI parser."""
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
    accept_action = new_subparser(
        actions, "accept", "The developer learns an entry the rules of evidence did not, or a proposal of developer-review.",
        "  agent-ready learn accept learn-5db4a07240", command_learn_apply)
    reject_action = new_subparser(
        actions, "reject", "The developer keeps an entry from being learned until it is accepted.",
        "  agent-ready learn reject learn-5db4a07240", command_learn_reject)
    revert_action = new_subparser(
        actions, "revert", "Undo a learning in its rule or skill, keeping later changes, with a commit of its own.",
        "  agent-ready learn revert learn-5db4a07240", command_learn_revert)
    keep_action = new_subparser(
        actions, "keep", "Keep a learned rule over the new version of the profile rule it replaces "
                         "(«customized, review» in the plan).",
        "  agent-ready learn keep learn-5db4a07240", command_learn_keep)
    retire_action = new_subparser(
        actions, "retire", "Remove a learned rule and its overrides without bringing back what it replaced: the "
                           "rule of the profile comes back on the next apply.",
        "  agent-ready learn retire learn-5db4a07240", command_learn_retire)
    for action in (apply_action, accept_action, reject_action, revert_action, keep_action, retire_action):
        action.add_argument("id", help="id of the entry, as record and list print it")
        if action in (apply_action, accept_action):
            action.add_argument("--skill", help="the directory of the skill the agent wrote, for an entry of kind skill")
        action.add_argument("--json", action="store_true", help="print the result as JSON")
    status_action = new_subparser(actions, "status", "The settings of learning and what waits for a repetition.",
                                  "  agent-ready learn status\n  agent-ready learn status --json", command_learn_status)
    status_action.add_argument("--json", action="store_true", help="print the result as JSON")
    list_action = new_subparser(actions, "list", "Every entry of the registry, without the quotes of the user.",
                                "  agent-ready learn list\n  agent-ready learn list --status learned --json",
                                command_learn_list)
    list_action.add_argument("--status", choices=learning.STATUSES, help="only the entries of this status")
    list_action.add_argument("--json", action="store_true", help="print the result as JSON")
    episode_action = new_subparser(
        actions, "episode", "The episode of a session, which the evidence of an instruction counts.",
        "  agent-ready learn episode --session 3f2a\n  agent-ready learn episode --session 3f2a --scope-question",
        command_learn_episode)
    episode_action.add_argument("--session", required=True, help="session of the provider")
    episode_modes = episode_action.add_mutually_exclusive_group()
    episode_modes.add_argument("--touch", action="store_true",
                               help="a message of the user arrived now; prints a line only when it opens an episode")
    episode_modes.add_argument("--scope-question", action="store_true",
                               help="record the one scope question of the episode; fails when it was already asked")
    episode_modes.add_argument("--end", action="store_true",
                               help="the chat ended: close its episode and review it in the background")
    episode_modes.add_argument("--review-now", action="store_true",
                               help="the context is about to be compacted: review the episode so far in the background")
    episode_action.add_argument("--transcript", help="transcript of the session, from the payload of the hook")
    episode_action.add_argument("--provider", choices=PROVIDERS, help="provider of the session, which reviews it")
    episode_action.add_argument("--json", action="store_true", help="print the result as JSON")
    summary_action = new_subparser(
        actions, "summary", "What was learned lately and what waits, in a few lines for the start of a session.",
        "  agent-ready learn summary", command_learn_summary)
    sweep_action = new_subparser(
        actions, "sweep", "Close the idle episodes and review the messages of the user of the closed ones.",
        "  agent-ready learn sweep\n  agent-ready learn sweep --registered", command_learn_sweep)
    sweep_action.add_argument("--registered", action="store_true",
                              help="sweep every repository registered for the scheduled sweep (what the task runs)")
    sweep_action.add_argument("--reorganize", action="store_true",
                              help="also reorganize what was learned, when learning.reorganize.minIntervalDays allows it")
    # The task runs it from any directory; without --registered the command finds the repository itself.
    sweep_action.set_defaults(needs_repository=False)
    schedule_action = new_subparser(
        actions, "schedule", "Register the scheduled sweep as learning.sweep.intervalMinutes asks, as an apply does.",
        "  agent-ready learn schedule\n  agent-ready learn schedule --json", command_learn_schedule)
    schedule_action.add_argument("--json", action="store_true", help="print the result as JSON")
    reorganize_action = new_subparser(
        actions, "reorganize", "Consolidate, split or turn into skills the learned rules: the equivalent changes "
                               "are applied, the rest wait for the developer.",
        "  agent-ready learn reorganize --plan\n  agent-ready learn reorganize\n"
        "  agent-ready learn reorganize --accept reorg-1a2b3c4d5e", command_learn_reorganize)
    reorganize_modes = reorganize_action.add_mutually_exclusive_group()
    reorganize_modes.add_argument("--plan", action="store_true",
                                  help="show the triggers and the proposals that wait, without a model or a change")
    reorganize_modes.add_argument("--accept", metavar="ID", help="the developer applies a proposal")
    reorganize_modes.add_argument("--dismiss", metavar="ID", help="the developer drops a proposal")
    reorganize_action.add_argument("--provider", choices=PROVIDERS,
                                   help="provider that reviews (default: the one of the latest session)")
    reorganize_action.add_argument("--json", action="store_true", help="print the result as JSON")
    export_action = new_subparser(
        actions, "export", "Write what this repository learned, without the quotes of the user, for its client to "
                           "review and hand to the developer.",
        "  agent-ready learn export --output learned.json", command_learn_export)
    export_action.add_argument("--output", help="file to write (default: print it)")
    export_action.add_argument("--name", help="name of the repository in the export (default: its folder)")
    harvest_action = new_subparser(
        actions, "harvest", "Group what several repositories learned as candidates for a pack, reading only what "
                            "was learned and skipping the ones with learning.share off.",
        "  agent-ready learn harvest --repos ../client-a ../client-b\n"
        "  agent-ready learn harvest --repos ../client-a --export client-c.json --json", command_learn_harvest)
    harvest_action.add_argument("--repos", nargs="+", metavar="PATH",
                                help=f"cloned repositories to read (default: {learning_share.HARVEST_REPOS_KEY})")
    harvest_action.add_argument("--export", dest="exports", action="append", metavar="FILE",
                                help="an export of agent-ready learn export a client handed over; repeatable")
    harvest_action.add_argument("--threshold", type=int,
                                help=f"repositories that must have learned it (default: "
                                     f"{learning_share.HARVEST_THRESHOLD_KEY})")
    harvest_action.add_argument("--provider", choices=PROVIDERS, default="claude",
                                help="provider that groups and generalizes the statements (default: claude)")
    harvest_action.add_argument("--json", action="store_true", help="print the result as JSON")
    # It reads other repositories: it runs from anywhere.
    harvest_action.set_defaults(needs_repository=False)
    promote_action = new_subparser(
        actions, "promote", "Write a candidate of learn harvest, or a learned rule, as a rule of a profile in the clone "
                            "of a pack; with --yes, on a new branch with a pull request.",
        "  agent-ready learn promote harvest-1a2b3c4d5e --to ../my-pack --profile base\n"
        "  agent-ready learn promote harvest-1a2b3c4d5e --to ../my-pack --profile base --yes", command_learn_promote)
    promote_action.add_argument("id", help="a harvest-... id of the last harvest, or a learn-... id of this repository")
    promote_action.add_argument("--to", required=True, metavar="PACK",
                                help="the clone of the pack (the folder with agent-ready-pack.json)")
    promote_action.add_argument("--profile", help="the profile of the pack (default: its only profile with assets)")
    promote_action.add_argument("--file", default=learning_promote.DEFAULT_PROMOTED_FILE,
                                help="the rule file of the profile for a new rule (default: %(default)s)")
    promote_action.add_argument("--yes", action="store_true",
                                help="write it: commit on a new branch of the pack, push it and open the pull request")
    promote_action.add_argument("--no-pr", action="store_true", help="with --yes, commit on the branch only")
    promote_action.add_argument("--json", action="store_true", help="print the result as JSON")
    promote_action.set_defaults(needs_repository=False)
