"""The runner of the scripts that profile packs declare, on the events of the security policy.

- ``install`` runs in an apply the first time a script is applied and again whenever its digest
  changes, or after it failed;
- ``post-apply`` runs at the end of every apply;
- ``session-start`` runs from the session hook, in the background, and only the exact script the
  lock recorded (``security.checks.lockDigest``): a pack changed since the last apply waits for
  the next one.

Each script runs with its declared interpreter and timeout, from the root of the project, with
the CLIs of the packs first on the PATH. Its output goes to a private log in the Git directory
(``agent-ready/scripts``); the engine never prints the environment. A script that fails or times
out is reported, and the apply does not count as complete.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time

from agent_ready_common import acquire_directory_lock, bash_executable, sha256_of_file, sha256_of_text

EVENT_INSTALL = "install"
EVENT_POST_APPLY = "post-apply"
EVENT_SESSION_START = "session-start"
APPLY_EVENTS = (EVENT_INSTALL, EVENT_POST_APPLY)
LOG_DIRECTORY = "agent-ready/scripts"
CLI_PATH_FILE = "agent-ready/cli-path"
PRIVATE_FILE_MODE = 0o600
TERMINATE_GRACE_SECONDS = 5
SESSION_LOCK_NAME = ".session-start.lock"
# The process groups of the scripts running now, one per line, in one file per invocation: whoever
# stops the sync that started them stops them too (stop_running_scripts), since each one runs in a
# session of its own. A sync names its invocation in OWNER_VARIABLE; anything else uses its own pid.
RUNNING_FILE_PREFIX = "running-"
OWNER_VARIABLE = "AGENT_READY_SETUP_SCRIPT_OWNER"
# Which install scripts ran in this checkout, with the sha256 that ran: a clone of the repository,
# whose lock says nothing about its own files, runs them again.
INSTALLED_FILE_NAME = "installed.json"
# The result of the last session-start run, shown once by the next session (previous_session_report).
SESSION_REPORT_NAME = "session-start-report.json"
# Like the background update: after this many failed session-start runs in a row, the next one
# waits this long, so a broken script does not download or install again at every session start.
SESSION_MAX_FAILURES = 3
SESSION_RETRY_AFTER_SECONDS = 3600
# What a script learns about the run, besides the environment it inherits.
PACK_ROOT_VARIABLE = "AGENT_READY_PACK_ROOT"
PROJECT_ROOT_VARIABLE = "AGENT_READY_PROJECT_ROOT"
EVENT_VARIABLE = "AGENT_READY_EVENT"


def interpreter_command(interpreter, pack_directories):
    """The executable for a declared interpreter.

    One that a pack installed (agent-ready/cli-path) wins; otherwise the bash of PATH (never the
    WSL launcher), the Python of the engine, or node and pwsh from the PATH.
    """
    if pack_directories:
        installed = shutil.which(interpreter, path=os.pathsep.join(pack_directories))
        if installed:
            return installed
    if interpreter == "bash":
        return bash_executable()
    if interpreter == "python3":
        return sys.executable
    return shutil.which(interpreter) or interpreter


def git_directory(project_root):
    try:
        completed = subprocess.run(["git", "-C", project_root, "rev-parse", "--absolute-git-dir"],
                                   capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def cli_path_directories(project_root):
    """The directories the installed CLIs of the packs put on the PATH (agent_ready_pack_clis.py)."""
    directory = git_directory(project_root)
    if not directory:
        return []
    try:
        with open(os.path.join(directory, *CLI_PATH_FILE.split("/")), encoding="utf-8") as path_file:
            return [line.strip() for line in path_file if line.strip()]
    except OSError:
        return []


def scripts_directory(project_root):
    directory = git_directory(project_root) or os.path.join(project_root, ".git")
    return os.path.join(directory, *LOG_DIRECTORY.split("/"))


def invocation_owner():
    return os.environ.get(OWNER_VARIABLE) or str(os.getpid())


def running_file_path(project_root, owner):
    safe_owner = "".join(character for character in owner if character.isalnum() or character in "-_")
    return os.path.join(scripts_directory(project_root), RUNNING_FILE_PREFIX + safe_owner)


def running_groups(project_root, owner=None):
    try:
        with open(running_file_path(project_root, owner or invocation_owner()), encoding="utf-8") as groups_file:
            return [int(line) for line in groups_file if line.strip().isdigit()]
    except OSError:
        return []


def write_running_groups(project_root, groups, owner=None):
    path = running_file_path(project_root, owner or invocation_owner())
    if not groups:
        if os.path.exists(path):
            os.unlink(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as running_file:
        running_file.write("".join(f"{group}\n" for group in groups))


def stop_running_scripts(project_root, owner):
    """Stop the scripts that one invocation (a sync stopped by its timeout) left running; others go on."""
    for group in running_groups(project_root, owner):
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(group)], capture_output=True, check=False)
            continue
        try:
            os.killpg(group, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    write_running_groups(project_root, [], owner)


def log_path(project_root, name, event):
    """A private log per script and event in the Git directory, never in the checkout."""
    directory = git_directory(project_root) or os.path.join(project_root, ".git")
    return os.path.join(directory, *LOG_DIRECTORY.split("/"), f"{sha256_of_text(name)[:16]}-{event}.log")


def open_private_log(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.islink(path):
        raise OSError(f"refusing to write the script log through a symlink: {path}")
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_FILE_MODE), "w")


class WindowsJob:
    """A Windows job object: every process a script starts belongs to it, so stopping the job ends them.

    taskkill /T misses processes whose parent already exited, such as what Git Bash starts.
    """

    PROCESS_ACCESS = 0x0001 | 0x0100  # PROCESS_TERMINATE | PROCESS_SET_QUOTA

    def __init__(self, process):
        import ctypes
        from ctypes import wintypes

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        # Without kill-on-close: what a script that finished leaves running is its business, as on POSIX.
        self.handle = self.kernel.CreateJobObjectW(None, None)
        process_handle = self.kernel.OpenProcess(self.PROCESS_ACCESS, False, process.pid)
        if process_handle:
            self.kernel.AssignProcessToJobObject(wintypes.HANDLE(self.handle), wintypes.HANDLE(process_handle))
            self.kernel.CloseHandle(wintypes.HANDLE(process_handle))

    def stop(self):
        from ctypes import wintypes
        if self.handle:
            self.kernel.TerminateJobObject(wintypes.HANDLE(self.handle), 1)

    def close(self):
        from ctypes import wintypes
        if self.handle:
            self.kernel.CloseHandle(wintypes.HANDLE(self.handle))
            self.handle = None


def stop_process_tree(process, job=None):
    """End a script and whatever it started; a script that ignores the signal is killed."""
    if os.name == "nt":
        if job:
            job.stop()
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
        try:
            process.wait(timeout=TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass
    time.sleep(TERMINATE_GRACE_SECONDS if process.poll() is None else 0.2)
    try:
        # The parent may have accepted SIGTERM while a child ignored it: the whole group goes.
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_script(project_root, script, event):
    """(succeeded, message) of one script; the message names the log, never the environment."""
    environment = dict(os.environ)
    pack_directories = cli_path_directories(project_root)
    environment["PATH"] = os.pathsep.join(pack_directories + [environment.get("PATH", "")])
    environment.update({PACK_ROOT_VARIABLE: script["root"], PROJECT_ROOT_VARIABLE: project_root,
                        EVENT_VARIABLE: event})
    log = log_path(project_root, script["name"], event)
    command = [interpreter_command(script["interpreter"], pack_directories), script["file"]]
    started = time.monotonic()
    try:
        with open_private_log(log) as log_file:
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(command, cwd=project_root, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=log_file, stderr=subprocess.STDOUT, **options)
            job = WindowsJob(process) if os.name == "nt" else None
            write_running_groups(project_root, running_groups(project_root) + [process.pid])
            try:
                code = process.wait(timeout=script["timeoutSeconds"])
            except subprocess.TimeoutExpired:
                stop_process_tree(process, job)
                return False, f"did not finish in {script['timeoutSeconds']} seconds and was stopped; log: {log}"
            except BaseException:
                # Ctrl-C reaches the runner, not the script in its own session: stop it before leaving.
                stop_process_tree(process, job)
                raise
            finally:
                write_running_groups(project_root, [group for group in running_groups(project_root) if group != process.pid])
                if job:
                    job.close()
    except OSError as problem:
        return False, f"could not start {script['interpreter']}: {problem}"
    elapsed = time.monotonic() - started
    if code != 0:
        return False, f"exited with {code} after {elapsed:.1f}s; log: {log}"
    return True, f"{elapsed:.1f}s"


def allowed_scripts(report, event):
    """The scripts the policy allows for an event, each with its file and digest."""
    scripts = []
    for tool in (report or {}).get("tools", []):
        if tool.get("type") != "script" or tool.get("decision") != "allowed" or tool.get("event") != event:
            continue
        if not tool.get("file") or not os.path.isfile(tool["file"]):
            continue
        scripts.append(dict(tool, sha256=sha256_of_file(tool["file"])))
    return scripts


def lock_key(script):
    """The lock keeps each event of a script apart: one script can be the install and the session-start."""
    return f"{script['event']}:{script['name']}"


def lock_entry(script):
    return {"source": script["source"], "profile": script["profile"], "event": script["event"],
            "path": script["path"], "interpreter": script["interpreter"], "sha256": script["sha256"]}


def read_installed(project_root):
    try:
        with open(os.path.join(scripts_directory(project_root), INSTALLED_FILE_NAME), encoding="utf-8") as installed_file:
            installed = json.load(installed_file)
    except (OSError, ValueError):
        return {}
    return installed if isinstance(installed, dict) else {}


def write_installed(project_root, installed):
    if installed == read_installed(project_root):
        return
    path = os.path.join(scripts_directory(project_root), INSTALLED_FILE_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as installed_file:
        json.dump(installed, installed_file, indent=2, sort_keys=True)


def run_apply_events(project_root, report, previous):
    """Run install (new or changed scripts) and post-apply; returns what ran and the lock entries."""
    result = {"ran": [], "failed": [], "lock": {}}
    installed = read_installed(project_root)
    for event in APPLY_EVENTS:
        for script in allowed_scripts(report, event):
            if lock_key(script) in result["lock"]:
                # Another selected profile declares the same script for this event: it ran already.
                continue
            result["lock"][lock_key(script)] = lock_entry(script)
            if event == EVENT_INSTALL and installed.get(lock_key(script)) == script["sha256"]:
                # These very bytes already ran in this checkout: install runs for a new or changed script.
                continue
            succeeded, message = run_script(project_root, script, event)
            (result["ran"] if succeeded else result["failed"]).append(f"{event} {script['name']}: {message}")
            if event == EVENT_INSTALL:
                if succeeded:
                    installed[lock_key(script)] = script["sha256"]
                else:
                    installed.pop(lock_key(script), None)
    # An apply is the retry the waiting session-start runs point to: the count of failures starts over.
    session_report = read_session_report(project_root)
    if session_report.get("consecutiveFailures"):
        session_report["consecutiveFailures"] = 0
        with open(os.path.join(scripts_directory(project_root), SESSION_REPORT_NAME), "w", encoding="utf-8") as report_file:
            json.dump(session_report, report_file, indent=2)
    if any(entry["event"] == EVENT_INSTALL for entry in result["lock"].values()) or installed:
        write_installed(project_root, {key: digest for key, digest in installed.items() if key in result["lock"]})
    # session-start scripts are recorded so the session hook runs exactly these bytes.
    for script in allowed_scripts(report, EVENT_SESSION_START):
        result["lock"][lock_key(script)] = lock_entry(script)
    return result


def session_lock_path(project_root):
    directory = git_directory(project_root) or os.path.join(project_root, ".git")
    return os.path.join(directory, *LOG_DIRECTORY.split("/"), SESSION_LOCK_NAME)


def run_session_start(project_root, report, locked, check_digest):
    """Run the allowed session-start scripts; with check_digest, only what the lock recorded.

    Two sessions that start together in one checkout never run them at the same time: the second
    one finds the lock taken and leaves them to the first.
    """
    result = {"ran": [], "failed": [], "skipped": []}
    waiting = waiting_after_failures(project_root)
    if waiting:
        result["skipped"].append(waiting)
        return result
    lock = session_lock_path(project_root)
    if not acquire_directory_lock(lock):
        result["skipped"].append("another session of this checkout is running the session-start scripts")
        return result
    try:
        run_session_scripts(project_root, report, locked, check_digest, result)
        write_session_report(project_root, result)
    finally:
        try:
            os.rmdir(lock)
        except OSError:
            pass
    return result


def read_session_report(project_root):
    try:
        with open(os.path.join(scripts_directory(project_root), SESSION_REPORT_NAME), encoding="utf-8") as report_file:
            report = json.load(report_file)
    except (OSError, ValueError):
        return {}
    return report if isinstance(report, dict) else {}


def write_session_report(project_root, result):
    """Keep what failed in this session-start run, for the next session to show once, and count failures in a row."""
    failures = read_session_report(project_root).get("consecutiveFailures", 0) + 1 if result["failed"] else 0
    path = os.path.join(scripts_directory(project_root), SESSION_REPORT_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as report_file:
        json.dump({"failed": result["failed"], "reported": False, "consecutiveFailures": failures,
                   "finishedAt": time.time()}, report_file, indent=2)


def waiting_after_failures(project_root):
    """Why this session-start run waits, or None: too many failed runs in a row, too recently."""
    report = read_session_report(project_root)
    failures = report.get("consecutiveFailures", 0)
    finished = report.get("finishedAt", 0)
    if failures >= SESSION_MAX_FAILURES and time.time() - finished < SESSION_RETRY_AFTER_SECONDS:
        return (f"{failures} session-start runs failed in a row; the next attempt waits "
                f"{SESSION_RETRY_AFTER_SECONDS} seconds, or run agent-ready apply after fixing the script")
    return None


def previous_session_report(project_root):
    """The failures of the last session-start run, once: reading them marks them as reported."""
    path = os.path.join(scripts_directory(project_root), SESSION_REPORT_NAME)
    try:
        with open(path, encoding="utf-8") as report_file:
            report = json.load(report_file)
    except (OSError, ValueError):
        return []
    if not isinstance(report, dict) or report.get("reported"):
        return []
    report["reported"] = True
    with open(path, "w", encoding="utf-8") as report_file:
        json.dump(report, report_file, indent=2)
    return [problem for problem in report.get("failed", []) if isinstance(problem, str)]


def run_session_scripts(project_root, report, locked, check_digest, result):
    seen = set()
    for script in allowed_scripts(report, EVENT_SESSION_START):
        if lock_key(script) in seen:
            # Another selected profile declares the same script: it runs once.
            continue
        seen.add(lock_key(script))
        recorded = locked.get(lock_key(script), {})
        if check_digest and recorded.get("sha256") != script["sha256"]:
            result["skipped"].append(f"{script['name']}: not the script the last apply recorded; run agent-ready apply")
            continue
        succeeded, message = run_script(project_root, script, EVENT_SESSION_START)
        (result["ran"] if succeeded else result["failed"]).append(f"{EVENT_SESSION_START} {script['name']}: {message}")
