"""agent-ready sync [--background] [--json]: one run of the team sync (agent_ready_sync.py).

--background is what the triggers use (the start of a session and each learning): the run goes on
detached from the hook, with its output in a log under the cache of the user, so the agent never waits
for the network. AGENT_READY_TEAM_SYNC_FOREGROUND=1 keeps it in the process, for the tests.
"""

import importlib.util
import os
import pathlib
import sys

import agent_ready_identity as identity
import agent_ready_sync as team_sync
import agent_ready_sync_conflicts as sync_conflicts
from agent_ready_cli_common import EXIT_FAILED, EXIT_OK, engine, find_repository_root
from agent_ready_common import StateError, serialize_json, sha256_of_text

SYNC_COMMAND = "sync"
MAX_STATEMENT_CHARS_KEY = "rules.maxStatementChars"
CLI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent-ready")
RUN_DETACHED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-detached.py")
LOG_DIRECTORY = ("agent-ready-setup", "team-sync")


def log_path(project_root):
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME") or os.path.expanduser("~"), ".cache")
    return os.path.join(base, *LOG_DIRECTORY, f"{sha256_of_text(os.path.realpath(project_root))[:16]}.log")


def settings_for(project_root):
    return team_sync.settings_of(engine().configuration_of(project_root), project_root)


def start_in_background(project_root):
    """Start a run detached from this process, unless the settings say it would do nothing."""
    settings = settings_for(project_root)
    if not settings["enabled"] or settings["preset"] == team_sync.identity.PRESET_SOFTWARE:
        return False
    # Without the remote there is nothing to synchronize: no process is started for it.
    if team_sync.git(project_root, "remote", "get-url", settings["remote"]).returncode != 0:
        return False
    if os.environ.get(team_sync.FOREGROUND_VARIABLE) == "1":
        team_sync.run(project_root, settings)
        return True
    specification = importlib.util.spec_from_file_location("run_detached", RUN_DETACHED_PATH)
    run_detached = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(run_detached)
    run_detached.run_detached([sys.executable, CLI_PATH, SYNC_COMMAND, "--project", project_root],
                              pathlib.Path(log_path(project_root)))
    return True


def print_report(report):
    result = report["result"]
    lines = {
        team_sync.RESULT_SYNCED: "Sync: up to date with the remote.",
        team_sync.RESULT_OFF: "Sync: off (sync.enabled is false); nothing was committed, fetched or pushed.",
        team_sync.RESULT_SOFTWARE: "Sync: nothing to do in the software preset; what is learned goes in the pull "
                                   "request of the change.",
    }
    line = lines.get(result) or f"Sync: {result}: {report.get('message', '')}"
    if report.get("committed"):
        line += " Committed what the learning had pending."
    if report.get("toPush"):
        line += f" {report['toPush']} commit(s) wait to go out."
    sys.stdout.write(line.rstrip() + "\n")


def decision_of(arguments):
    """(decision, statement) that --resolve asks for, or a usage error."""
    chosen = [option for option, given in ((arguments.keep, arguments.keep), (sync_conflicts.DECISION_MERGED,
                                                                              arguments.merged is not None or
                                                                              arguments.merged_file is not None),
                                           (sync_conflicts.DECISION_EACH, arguments.each_their_own)) if given]
    if len(chosen) != 1:
        raise StateError("--resolve needs exactly one of --keep mine|theirs, --merged \"<statement>\", "
                         "--merged-file <file> and --each-their-own")
    return chosen[0], arguments.merged


def command_conflicts(project_root, as_json):
    """The conflicts that wait for a person: what the start of a session explains."""
    waiting = sync_conflicts.pending(project_root)
    if as_json:
        sys.stdout.write(serialize_json({"conflicts": waiting}))
    elif waiting:
        sys.stdout.write(sync_conflicts.explanation(waiting))
    return EXIT_OK


def check_combined_rule(project_root, lines):
    """A combined statement makes a rule that passes the lint of the project: atomic and short enough."""
    import agent_ready_rules

    maximum = engine().configuration_of(project_root).value(MAX_STATEMENT_CHARS_KEY)
    rules, findings = agent_ready_rules.parse_rule_text("\n".join(lines) + "\n", "combined")
    findings = findings + agent_ready_rules.lint_rules(rules, maximum, maximum)
    errors = [finding for finding in findings if finding.level == agent_ready_rules.LEVEL_ERROR
              and finding.code != agent_ready_rules.CODE_UNKNOWN_REQUIRES]
    if errors:
        raise ValueError("the combined statement would not be a valid rule, so nothing was decided: "
                         + errors[0].render())


def command_resolve(project_root, arguments):
    """Store what the person decided and synchronize with it."""
    decision, statement = decision_of(arguments)
    text = None
    if arguments.merged_file:
        try:
            with open(arguments.merged_file, encoding="utf-8") as handle:
                text = handle.read()
        except OSError as unreadable:
            raise StateError(f"--merged-file {arguments.merged_file} cannot be read: {unreadable}") from unreadable
    try:
        conflict = sync_conflicts.decide(
            project_root, arguments.resolve, decision, identity.read_identity()["id"], statement,
            lambda person, item: team_sync.personal_rule_exists(project_root, person, item),
            lambda item: team_sync.team_rule_required_by(project_root, item),
            lambda lines: check_combined_rule(project_root, lines), text)
    except ValueError as invalid:
        raise StateError(str(invalid)) from invalid
    sys.stdout.write(f"Decided {conflict['id']}: {decision}.\n")
    report = team_sync.run(project_root, settings_for(project_root))
    print_report(report)
    return EXIT_FAILED if report["result"] in team_sync.FAILED_RESULTS else EXIT_OK


def command_sync(arguments):
    project_root = find_repository_root(arguments.project)
    if arguments.conflicts:
        return command_conflicts(project_root, arguments.json)
    if arguments.resolve:
        return command_resolve(project_root, arguments)
    if arguments.background:
        start_in_background(project_root)
        return EXIT_OK
    report = team_sync.run(project_root, settings_for(project_root))
    if arguments.json:
        sys.stdout.write(serialize_json(report))
    else:
        print_report(report)
    return EXIT_FAILED if report["result"] in team_sync.FAILED_RESULTS else EXIT_OK


def register(subparsers, new_subparser):
    """Add sync to the CLI parser."""
    sync = new_subparser(subparsers, SYNC_COMMAND,
                         "Commit what was learned, bring what the others learned and push it, without Git.",
                         "  agent-ready sync\n  agent-ready sync --json\n  agent-ready sync --background",
                         command_sync)
    sync.add_argument("--json", action="store_true", help="print the report of the run as JSON")
    sync.add_argument("--background", action="store_true",
                      help="run detached, with its output in a log of the cache (what the hooks use)")
    sync.add_argument("--conflicts", action="store_true",
                      help="print the conflicts that wait for a person, explained (what the start of a session shows)")
    sync.add_argument("--resolve", metavar="ID", help="decide one conflict (an id that --conflicts prints) and sync")
    sync.add_argument("--keep", choices=(sync_conflicts.DECISION_MINE, sync_conflicts.DECISION_THEIRS),
                      help="with --resolve: keep the version of this machine or the other one")
    sync.add_argument("--merged", metavar="STATEMENT",
                      help="with --resolve: the statement that combines both, once the user agreed with it")
    sync.add_argument("--merged-file", metavar="FILE",
                      help="with --resolve, for a document: the file with the whole document that combines both, "
                           "once the user agreed with it")
    sync.add_argument("--each-their-own", action="store_true",
                      help="with --resolve, for a rule of the team: each version stays personal for who taught it")
