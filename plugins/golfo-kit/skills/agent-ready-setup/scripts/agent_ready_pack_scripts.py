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

import os
import shutil
import signal
import subprocess
import sys
import time

from agent_ready_common import bash_executable, sha256_of_file, sha256_of_text

EVENT_INSTALL = "install"
EVENT_POST_APPLY = "post-apply"
EVENT_SESSION_START = "session-start"
APPLY_EVENTS = (EVENT_INSTALL, EVENT_POST_APPLY)
LOG_DIRECTORY = "agent-ready/scripts"
CLI_PATH_FILE = "agent-ready/cli-path"
PRIVATE_FILE_MODE = 0o600
TERMINATE_GRACE_SECONDS = 5
# What a script learns about the run, besides the environment it inherits.
PACK_ROOT_VARIABLE = "AGENT_READY_PACK_ROOT"
PROJECT_ROOT_VARIABLE = "AGENT_READY_PROJECT_ROOT"
EVENT_VARIABLE = "AGENT_READY_EVENT"


def interpreter_command(interpreter):
    """The executable for a declared interpreter; the bash of PATH, never the WSL launcher."""
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
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_script(project_root, script, event):
    """(succeeded, message) of one script; the message names the log, never the environment."""
    environment = dict(os.environ)
    environment["PATH"] = os.pathsep.join(cli_path_directories(project_root) + [environment.get("PATH", "")])
    environment.update({PACK_ROOT_VARIABLE: script["root"], PROJECT_ROOT_VARIABLE: project_root,
                        EVENT_VARIABLE: event})
    log = log_path(project_root, script["name"], event)
    command = [interpreter_command(script["interpreter"]), script["file"]]
    started = time.monotonic()
    try:
        with open_private_log(log) as log_file:
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen(command, cwd=project_root, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=log_file, stderr=subprocess.STDOUT, **options)
            job = WindowsJob(process) if os.name == "nt" else None
            try:
                code = process.wait(timeout=script["timeoutSeconds"])
            except subprocess.TimeoutExpired:
                stop_process_tree(process, job)
                return False, f"did not finish in {script['timeoutSeconds']} seconds and was stopped; log: {log}"
            finally:
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


def lock_entry(script, installed):
    entry = {"source": script["source"], "profile": script["profile"], "event": script["event"],
             "path": script["path"], "interpreter": script["interpreter"], "sha256": script["sha256"]}
    if script["event"] == EVENT_INSTALL:
        entry["installed"] = installed
    return entry


def run_apply_events(project_root, report, previous):
    """Run install (new or changed scripts) and post-apply; returns what ran and the lock entries."""
    result = {"ran": [], "failed": [], "lock": {}}
    for event in APPLY_EVENTS:
        for script in allowed_scripts(report, event):
            before = previous.get(script["name"], {})
            if event == EVENT_INSTALL and before.get("sha256") == script["sha256"] and before.get("installed"):
                # Already installed with these very bytes: install runs only for a new or changed script.
                result["lock"][script["name"]] = before
                continue
            succeeded, message = run_script(project_root, script, event)
            (result["ran"] if succeeded else result["failed"]).append(f"{event} {script['name']}: {message}")
            result["lock"][script["name"]] = lock_entry(script, succeeded)
    # session-start scripts are recorded so the session hook runs exactly these bytes.
    for script in allowed_scripts(report, EVENT_SESSION_START):
        result["lock"][script["name"]] = lock_entry(script, False)
    return result


def run_session_start(project_root, report, locked, check_digest):
    """Run the allowed session-start scripts; with check_digest, only what the lock recorded."""
    result = {"ran": [], "failed": [], "skipped": []}
    for script in allowed_scripts(report, EVENT_SESSION_START):
        recorded = locked.get(script["name"], {})
        if check_digest and recorded.get("sha256") != script["sha256"]:
            result["skipped"].append(f"{script['name']}: not the script the last apply recorded; run agent-ready apply")
            continue
        succeeded, message = run_script(project_root, script, EVENT_SESSION_START)
        (result["ran"] if succeeded else result["failed"]).append(f"{EVENT_SESSION_START} {script['name']}: {message}")
    return result
