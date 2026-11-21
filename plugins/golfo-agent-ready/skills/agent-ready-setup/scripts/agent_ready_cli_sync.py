"""agent-ready sync [--background] [--json]: one run of the team sync (agent_ready_sync.py).

--background is what the triggers use (the start of a session and each learning): the run goes on
detached from the hook, with its output in a log under the cache of the user, so the agent never waits
for the network. AGENT_READY_TEAM_SYNC_FOREGROUND=1 keeps it in the process, for the tests.
"""

import importlib.util
import os
import pathlib
import sys

import agent_ready_sync as team_sync
from agent_ready_cli_common import EXIT_FAILED, EXIT_OK, engine, find_repository_root
from agent_ready_common import serialize_json, sha256_of_text

SYNC_COMMAND = "sync"
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


def command_sync(arguments):
    project_root = find_repository_root(arguments.project)
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
