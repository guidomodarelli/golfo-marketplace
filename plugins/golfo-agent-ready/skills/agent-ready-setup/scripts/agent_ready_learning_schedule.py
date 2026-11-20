"""The scheduled learning sweep: one task of the user in the scheduler of the system that runs
``agent-ready learn sweep --registered`` every ``learning.sweep.intervalMinutes`` (references/learning-episodes.md,
«Barrido programado»).

It closes the episodes nobody comes back to, so their review runs even when the chat is never used
again. The task belongs to the user and needs no administrator: a task of the current user in the Task
Scheduler of Windows (never /RU SYSTEM), a LaunchAgent in ``~/Library/LaunchAgents`` on macOS (never a
LaunchDaemon) and the crontab of the user on Linux.

There is one task per machine, shared by every repository that uses learning, like the CLIs of the
packs: each repository records itself under ``learning-schedule/projects/<key>.json`` in the cache of
the user, the task runs as often as the most frequent of them asks, and it goes away with the last one.
The task runs a small runner in the same cache that points at the engine of the last apply.

When the scheduler refuses the task (a policy of the machine, no crontab), the apply goes on: the
record of the repository keeps the reason, and status and doctor report the missing timer.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from xml.sax.saxutils import escape

from agent_ready_common import (
    StateError, acquire_directory_lock, serialize_json, sha256_of_text, skill_cache_directory, write_text_atomically,
    write_text_if_changed,
)

# Chooses the scheduler instead of the platform: schtasks, launchd, crontab or none (tests, debugging).
SCHEDULER_VARIABLE = "AGENT_READY_LEARNING_SCHEDULER"
SCHEDULER_SCHTASKS = "schtasks"
SCHEDULER_LAUNCHD = "launchd"
SCHEDULER_CRONTAB = "crontab"
SCHEDULER_NONE = "none"
SCHEDULERS = (SCHEDULER_SCHTASKS, SCHEDULER_LAUNCHD, SCHEDULER_CRONTAB, SCHEDULER_NONE)
SCHEDULE_DIRECTORY = "learning-schedule"
PROJECTS_DIRECTORY = "projects"
RUNNER_FILE = "run-sweep.py"
TASK_FILE = "task.json"
# Where the runner sends the output of the sweep when the task gives it no streams (pythonw.exe).
RUNNER_LOG_FILE = "last-sweep.log"
CACHE_VARIABLE = "XDG_CACHE_HOME"
PATH_VARIABLE = "PATH"
LOCK_DIRECTORY = "lock"
LOCK_WAIT_SECONDS = 10
LOCK_POLL_SECONDS = 0.05
PROJECT_KEY_LENGTH = 16
COMMAND_TIMEOUT_SECONDS = 30
SCHTASKS_TASK_NAME = r"\agent-ready\learning-sweep"
# schtasks accepts at most this many minutes for /SC MINUTE, as does the schema.
MAX_INTERVAL_MINUTES = 1439
LAUNCHD_LABEL = "com.golfo.agent-ready.learning-sweep"
CRONTAB_MARKER = "# agent-ready learning sweep"
MINUTES_PER_HOUR = 60
SECONDS_PER_MINUTE = 60
HOURS_PER_DAY = 24
# Python without a console window, so the task does not flash one on Windows.
WINDOWLESS_PYTHON = "pythonw.exe"

STATUS_REGISTERED = "registered"
STATUS_UNCHANGED = "unchanged"
STATUS_REMOVED = "removed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


class ScheduleError(RuntimeError):
    """The scheduler of the system refused the task, or there is none."""


# ---------------------------------------------------------------------------
# Records of the repositories
# ---------------------------------------------------------------------------

def schedule_root():
    return skill_cache_directory(SCHEDULE_DIRECTORY)


def project_key(project_root):
    return sha256_of_text(os.path.realpath(project_root))[:PROJECT_KEY_LENGTH]


def project_record_path(project_root):
    return os.path.join(schedule_root(), PROJECTS_DIRECTORY, f"{project_key(project_root)}.json")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            content = json.load(handle)
    except (OSError, ValueError):
        return None
    return content if isinstance(content, dict) else None


def read_project_record(project_root):
    return read_json(project_record_path(project_root))


def registered_projects():
    """Every repository that asked for the sweep: (record path, record), the ones still on disk first."""
    directory = os.path.join(schedule_root(), PROJECTS_DIRECTORY)
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    projects = []
    for name in names:
        path = os.path.join(directory, name)
        record = read_json(path)
        if record and isinstance(record.get("project"), str) and isinstance(record.get("intervalMinutes"), int):
            projects.append((path, record))
    return projects


class ScheduleLock:
    """One writer of the records and the task at a time: two applies may run at once."""

    def __init__(self):
        self.path = os.path.join(schedule_root(), LOCK_DIRECTORY)

    def __enter__(self):
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while not acquire_directory_lock(self.path):
            if time.monotonic() > deadline:
                raise StateError(f"the learning schedule is locked by another process ({self.path})")
            time.sleep(LOCK_POLL_SECONDS)
        return self

    def __exit__(self, *_):
        try:
            os.rmdir(self.path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Schedulers
# ---------------------------------------------------------------------------

def scheduler_name():
    """The scheduler of this machine, or the one SCHEDULER_VARIABLE names."""
    chosen = os.environ.get(SCHEDULER_VARIABLE, "").strip()
    if chosen:
        if chosen not in SCHEDULERS:
            raise ScheduleError(f"{SCHEDULER_VARIABLE} must be one of {', '.join(SCHEDULERS)}, not {chosen!r}")
        return chosen
    if sys.platform == "win32":
        return SCHEDULER_SCHTASKS
    if sys.platform == "darwin":
        return SCHEDULER_LAUNCHD
    return SCHEDULER_CRONTAB


def run_command(arguments, stdin_text=None):
    """Run a command of the scheduler; ScheduleError when it is missing. Returns the completed process."""
    executable = shutil.which(arguments[0])
    if executable is None:
        raise ScheduleError(f"{arguments[0]} is not on the PATH")
    try:
        return subprocess.run([executable, *arguments[1:]], input=stdin_text, capture_output=True, encoding="utf-8",
                              errors="replace", timeout=COMMAND_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as problem:
        raise ScheduleError(f"{arguments[0]} could not run: {problem}") from problem


def failure(completed, what):
    detail = (completed.stderr or completed.stdout or "").strip().splitlines()
    return ScheduleError(f"{what} failed (exit {completed.returncode}){': ' + detail[-1] if detail else ''}")


def schtasks_install(interval, command):
    completed = run_command(["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(interval),
                             "/TN", SCHTASKS_TASK_NAME, "/TR", subprocess.list2cmdline(command)])
    if completed.returncode != 0:
        raise failure(completed, "schtasks /Create")


def schtasks_remove():
    if not schtasks_present():
        return
    completed = run_command(["schtasks", "/Delete", "/F", "/TN", SCHTASKS_TASK_NAME])
    if completed.returncode != 0:
        raise failure(completed, "schtasks /Delete")


def schtasks_present():
    return run_command(["schtasks", "/Query", "/TN", SCHTASKS_TASK_NAME]).returncode == 0


def launchd_plist_path():
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, "Library", "LaunchAgents", f"{LAUNCHD_LABEL}.plist")


def launchd_domain():
    return f"gui/{os.getuid()}"


def launchd_plist(interval, command):
    arguments = "".join(f"\n    <string>{escape(argument)}</string>" for argument in command)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            f'  <key>Label</key>\n  <string>{LAUNCHD_LABEL}</string>\n'
            f'  <key>ProgramArguments</key>\n  <array>{arguments}\n  </array>\n'
            f'  <key>StartInterval</key>\n  <integer>{interval * SECONDS_PER_MINUTE}</integer>\n'
            '</dict>\n</plist>\n')


def launchd_install(interval, command):
    path = launchd_plist_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Unloaded first: launchd keeps the interval it read until the agent is loaded again.
    if os.path.exists(path):
        run_command(["launchctl", "bootout", launchd_domain(), path])
    write_text_atomically(path, launchd_plist(interval, command))
    completed = run_command(["launchctl", "bootstrap", launchd_domain(), path])
    if completed.returncode != 0:
        raise failure(completed, "launchctl bootstrap")


def launchd_remove():
    path = launchd_plist_path()
    if not os.path.exists(path):
        return
    run_command(["launchctl", "bootout", launchd_domain(), path])
    os.remove(path)


def launchd_present():
    return os.path.isfile(launchd_plist_path())


def crontab_lines():
    """The crontab of the user; empty when it has none."""
    completed = run_command(["crontab", "-l"])
    if completed.returncode != 0:
        # crontab -l fails when the user has no crontab yet: nothing to keep.
        if "no crontab" in (completed.stderr or "").lower():
            return []
        raise failure(completed, "crontab -l")
    return completed.stdout.splitlines()


def crontab_write(lines):
    completed = run_command(["crontab", "-"], stdin_text="".join(f"{line}\n" for line in lines))
    if completed.returncode != 0:
        raise failure(completed, "crontab -")


def crontab_schedule(interval):
    """The five fields of cron for an interval: every N minutes, or every N hours from 60 on."""
    if interval < MINUTES_PER_HOUR:
        return f"*/{interval} * * * *"
    hours = min(interval // MINUTES_PER_HOUR, HOURS_PER_DAY - 1)
    return f"0 */{hours} * * *"


def crontab_install(interval, command):
    kept = [line for line in crontab_lines() if CRONTAB_MARKER not in line]
    crontab_write(kept + [f"{crontab_schedule(interval)} {shlex.join(command)} {CRONTAB_MARKER}"])


def crontab_remove():
    lines = crontab_lines()
    kept = [line for line in lines if CRONTAB_MARKER not in line]
    if kept != lines:
        crontab_write(kept)


def crontab_present():
    return any(CRONTAB_MARKER in line for line in crontab_lines())


SCHEDULER_ACTIONS = {
    SCHEDULER_SCHTASKS: (schtasks_install, schtasks_remove, schtasks_present),
    SCHEDULER_LAUNCHD: (launchd_install, launchd_remove, launchd_present),
    SCHEDULER_CRONTAB: (crontab_install, crontab_remove, crontab_present),
    SCHEDULER_NONE: (lambda interval, command: None, lambda: None, lambda: False),
}


# ---------------------------------------------------------------------------
# The task
# ---------------------------------------------------------------------------

def python_for_task():
    """The Python of this engine; on Windows its windowless twin when it has one."""
    if sys.platform == "win32":
        windowless = os.path.join(os.path.dirname(sys.executable), WINDOWLESS_PYTHON)
        if os.path.isfile(windowless):
            return windowless
    return sys.executable


def task_file_path():
    return os.path.join(schedule_root(), TASK_FILE)


def write_runner(cli_path):
    """The runner the task starts: it runs the sweep of every registered repository with this engine.

    The scheduler starts it with an environment of its own, so the runner brings back what the apply
    saw: the cache that holds the records (XDG_CACHE_HOME) and the PATH that finds the CLI of the
    provider the review runs. pythonw.exe gives it no output streams, so it opens a log for them.
    """
    path = os.path.join(schedule_root(), RUNNER_FILE)
    cache_home = os.path.dirname(skill_cache_directory())
    write_text_if_changed(path, (
        '"""Started by the scheduled learning sweep of agent-ready-setup; the next apply rewrites it."""\n'
        "import os\nimport runpy\nimport sys\n\n"
        f"CLI = {cli_path!r}\n"
        f"LOG = {os.path.join(schedule_root(), RUNNER_LOG_FILE)!r}\n"
        f"os.environ[{CACHE_VARIABLE!r}] = {cache_home!r}\n"
        f"os.environ[{PATH_VARIABLE!r}] = os.pathsep.join(filter(None, [{os.environ.get(PATH_VARIABLE, '')!r}, "
        f"os.environ.get({PATH_VARIABLE!r})]))\n"
        "if sys.stdout is None or sys.stderr is None:\n"
        '    log = open(LOG, "w", encoding="utf-8")\n'
        "    sys.stdout = sys.stdout or log\n"
        "    sys.stderr = sys.stderr or log\n"
        'sys.argv = [CLI, "learn", "sweep", "--registered"]\n'
        'runpy.run_path(CLI, run_name="__main__")\n'))
    return path


def wanted_interval():
    """The interval of the task: the most frequent any registered repository asks for, or None."""
    intervals = [record["intervalMinutes"] for _, record in registered_projects() if record["intervalMinutes"] > 0]
    return min(min(intervals), MAX_INTERVAL_MINUTES) if intervals else None


def sync_task(cli_path):
    """Make the task match the records: installed with the wanted interval, or removed. Returns its state."""
    name = scheduler_name()
    install, remove, present = SCHEDULER_ACTIONS[name]
    task_path = task_file_path()
    interval = wanted_interval()
    if interval is None:
        remove()
        if os.path.exists(task_path):
            os.remove(task_path)
        return None
    command = [python_for_task(), write_runner(cli_path)]
    task = {"scheduler": name, "intervalMinutes": interval, "command": command}
    if read_json(task_path) != task or not present():
        install(interval, command)
        write_text_atomically(task_path, serialize_json(task))
    return task


def register(project_root, interval, cli_path):
    """Ask for the sweep of this repository (interval > 0), or stop asking (0). Never raises for the scheduler.

    Returns {"status", "detail"}: registered, unchanged, removed, failed (with the reason) or skipped.
    """
    record_path = project_record_path(project_root)
    previous = read_json(record_path)
    record = {"project": os.path.realpath(project_root), "intervalMinutes": interval}
    with ScheduleLock():
        if interval == 0:
            # Without a record there is nothing to drop, unless an earlier removal was refused and
            # left the task of the last repository behind: then it is tried again.
            if previous is None and (registered_projects() or not os.path.exists(task_file_path())):
                return {"status": STATUS_SKIPPED, "detail": "learning.sweep.intervalMinutes is 0"}
            if previous is not None:
                os.remove(record_path)
        else:
            write_text_if_changed(record_path, serialize_json(record))
        try:
            task = sync_task(cli_path)
        except (ScheduleError, OSError) as problem:
            if interval:
                write_text_atomically(record_path, serialize_json({**record, "error": str(problem)}))
            return {"status": STATUS_FAILED, "detail": str(problem)}
    if interval == 0:
        return {"status": STATUS_REMOVED, "detail": "this repository no longer asks for the scheduled sweep"}
    status = STATUS_UNCHANGED if previous == record else STATUS_REGISTERED
    return {"status": status, "detail": f"every {task['intervalMinutes']} minutes ({task['scheduler']})"}


def unregister(project_root, cli_path):
    """This repository stops asking for the sweep; the task goes with the last repository."""
    return register(project_root, 0, cli_path)


def prune_missing(cli_path):
    """Drop the records of repositories that are gone from the disk; the task follows the rest."""
    with ScheduleLock():
        gone = [path for path, record in registered_projects() if not os.path.isdir(record["project"])]
        for path in gone:
            os.remove(path)
        # A task left by a refused removal goes too, once no repository asks for it.
        if gone or (not registered_projects() and os.path.exists(task_file_path())):
            sync_task(cli_path)
    return len(gone)


def state(project_root):
    """Whether the scheduled sweep covers this repository: (ok, detail)."""
    record = read_project_record(project_root)
    if record is None:
        return False, "this repository is not registered: run agent-ready apply"
    if record.get("error"):
        return False, f"the scheduler refused the task: {record['error']}"
    try:
        name = scheduler_name()
        present = SCHEDULER_ACTIONS[name][2]()
    except ScheduleError as problem:
        return False, str(problem)
    if not present:
        return False, f"the task is not in the scheduler ({name}): run agent-ready apply"
    task = read_json(task_file_path()) or {}
    return True, f"every {task.get('intervalMinutes', record['intervalMinutes'])} minutes ({name})"
