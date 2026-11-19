"""The background update of a repository: the sync that runs detached from the session, and its report.

A session start hands the update to `agent-ready-state.py background-update`; the next session shows what it
changed or why it failed, once (`update-report`). A run that fails too often waits before trying again.
"""

import os
import signal
import subprocess
import time

import agent_ready_blocks as managed_blocks
import agent_ready_pack_scripts as pack_scripts
from agent_ready_common import (
    StateError,
    acquire_directory_lock,
    bash_executable,
    local_state,
    read_json_file,
    serialize_json,
    sha256_of_text,
    write_text_atomically,
)
from agent_ready_content import CONTENT_SOURCE_NAME
from agent_ready_lockfile import STATE_CONFLICT, STATE_FAILED, STATE_RETIRED_PRESERVED, read_lock
from agent_ready_output import write_line

FOREGROUND_SYNC_VARIABLE = "AGENT_READY_SETUP_SYNC_FOREGROUND"
# The background update stops retrying for a while after this many failures in a row.
BACKGROUND_UPDATE_MAX_FAILURES = 3
BACKGROUND_UPDATE_RETRY_AFTER_SECONDS = 3600
BACKGROUND_UPDATE_TIMEOUT_SECONDS = 1800
REPORT_MAX_LISTED_ASSETS = 10
REPORT_MAX_PROBLEM_CHARACTERS = 500
BACKUPS_LINE_PREFIX = "Local backups directory:"


def update_state_paths(project_root):
    """Per-user report and lock of one project; nothing machine-specific lands in it."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME") or os.path.expanduser("~"), ".cache")
    key = sha256_of_text(os.path.realpath(project_root))[:16]
    directory = os.path.join(base, "agent-ready-setup", "updates")
    return os.path.join(directory, f"{key}.json"), os.path.join(directory, f"{key}.lock")


def read_update_report(report_path):
    """Last background update of a project, or an empty report."""
    try:
        return read_json_file(report_path, "background update report")
    except StateError:
        return {}


def lock_for_comparison(project_root):
    """The lock before or after an update; an unreadable one compares as empty."""
    try:
        return read_lock(project_root) or {}
    except StateError:
        return {}


def assets_needing_attention(lock):
    """Assets an update could not leave as published: the next session must hear about them."""
    labels = {STATE_CONFLICT: "preserved conflict", STATE_FAILED: "could not be applied", STATE_RETIRED_PRESERVED: "retired but preserved"}
    inventory = {**lock.get("assets", {}), **managed_blocks.inventory(lock)}
    return [
        f"{labels[entry.get('state')]}: {destination}"
        for destination, entry in sorted(inventory.items())
        if entry.get("state") in labels
    ]


def summarize_lock_changes(before, after):
    """What an update changed, from the two lockfiles."""
    assets_before = {**before.get("assets", {}), **managed_blocks.inventory(before)}
    assets_after = {**after.get("assets", {}), **managed_blocks.inventory(after)}
    changes = {
        "created": sorted(set(assets_after) - set(assets_before)),
        "updated": sorted(
            destination for destination in set(assets_after) & set(assets_before)
            if assets_after[destination].get("sha256") != assets_before[destination].get("sha256")
        ),
        "retired": sorted(set(assets_before) - set(assets_after)),
        "sources": [],
    }
    sources_before, sources_after = before.get("profileSources", {}), after.get("profileSources", {})
    for name in sorted(set(sources_before) | set(sources_after)):
        old_entry, new_entry = sources_before.get(name, {}), sources_after.get(name, {})
        if old_entry.get("resolvedCommit") != new_entry.get("resolvedCommit") or old_entry.get("contentDigest") != new_entry.get("contentDigest"):
            old_revision = (old_entry.get("resolvedCommit") or old_entry.get("contentDigest") or "none")[:12]
            new_revision = (new_entry.get("resolvedCommit") or new_entry.get("contentDigest") or "removed")[:12]
            changes["sources"].append(f"{name} {old_revision} -> {new_revision}")
    source_before, source_after = before.get("source", {}), after.get("source", {})
    if source_before.get("contentDigest") != source_after.get("contentDigest"):
        changes["sources"].append(f"{CONTENT_SOURCE_NAME} {source_before.get('version') or 'none'} -> {source_after.get('version') or 'unknown'}")
    return changes


def locally_changed_assets(project_root, lock):
    """Managed files that differ from what the lock recorded, or that someone deleted."""
    changed = [
        destination for destination, entry in lock.get("assets", {}).items()
        if entry.get("sha256") and local_state(os.path.join(project_root, destination)) != entry["sha256"]
    ]
    changed += [
        f"{destination} (block {block_id})"
        for destination, blocks in (lock.get("blocks") or {}).items() for block_id, entry in blocks.items()
        if entry.get("sha256") and managed_blocks.local_sha256(project_root, destination, block_id) != entry["sha256"]
    ]
    return sorted(changed)


def terminate_process_tree(process):
    """Stop a process and its children: an orphan could keep writing after the lock is released."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, check=False)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        process.kill()


def run_sync(command, project_root, environment, timeout_seconds):
    """Run the foreground sync in its own process group. Returns (output, exit status)."""
    # The scripts of the packs this sync starts are this sync's: its timeout stops them, and no other.
    owner = f"sync-{os.getpid()}"
    environment = dict(environment, **{pack_scripts.OWNER_VARIABLE: owner})
    try:
        process = subprocess.Popen(
            command, cwd=project_root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace", start_new_session=True,
        )
    except OSError as start_error:
        return f"ERROR: the sync could not start: {type(start_error).__name__}\n", 1
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
        return output, process.returncode
    except subprocess.TimeoutExpired:
        terminate_process_tree(process)
        # Each script of a pack runs in a session of its own, outside the group just stopped.
        pack_scripts.stop_running_scripts(project_root, owner)
        output, _ = process.communicate()
        return f"{output}ERROR: the sync did not finish in {timeout_seconds} seconds and was stopped\n", 1


def command_background_update(arguments):
    """Run the sync detached from the session and leave its result for the next one."""
    report_path, lock_path = update_state_paths(arguments.project)
    if not acquire_directory_lock(lock_path):
        write_line("Another background update of this project is running.")
        return 0
    try:
        previous = read_update_report(report_path)
        failures = previous.get("consecutiveFailures", 0)
        age = time.time() - os.path.getmtime(report_path) if os.path.exists(report_path) else None
        if failures >= BACKGROUND_UPDATE_MAX_FAILURES and age is not None and age < BACKGROUND_UPDATE_RETRY_AFTER_SECONDS:
            write_line(f"{failures} background updates failed in a row; the next attempt waits {BACKGROUND_UPDATE_RETRY_AFTER_SECONDS} seconds.")
            return 0
        before = lock_for_comparison(arguments.project)
        changed_before = locally_changed_assets(arguments.project, before)
        environment = dict(os.environ)
        environment[FOREGROUND_SYNC_VARIABLE] = "1"
        command = [bash_executable(), arguments.hook, "--provider", arguments.provider]
        output, return_code = run_sync(command, arguments.project, environment, BACKGROUND_UPDATE_TIMEOUT_SECONDS)
        write_line(output.rstrip("\n"))
        problems = [line.strip() for line in output.splitlines() if line.startswith(("ERROR:", "WARNING:", "Evaluation incomplete:"))]
        if return_code != 0 and not problems:
            problems = [f"the sync exited with status {return_code}"]
        after = lock_for_comparison(arguments.project)
        changes = summarize_lock_changes(before, after)
        # The lock keeps its hash when a sync overwrites a local edit: only the checkout shows it.
        still_changed = set(locally_changed_assets(arguments.project, after))
        changes["restored"] = sorted(
            destination for destination in changed_before
            if destination not in still_changed
            and destination in {**after.get("assets", {}), **managed_blocks.inventory(after)}
            and destination not in changes["updated"]
        )
        backup_line = next((line.strip() for line in output.splitlines() if line.startswith(BACKUPS_LINE_PREFIX)), None)
        if backup_line:
            changes["backups"] = backup_line
        report = {
            "reported": False,
            "consecutiveFailures": failures + 1 if problems else 0,
            "changes": changes,
            "attention": assets_needing_attention(after),
            "problems": problems,
        }
        write_text_atomically(report_path, serialize_json(report))
    finally:
        os.rmdir(lock_path)
    return 0


def describe_update_changes(changes):
    """Readable lines of what a background update changed; nothing when it changed nothing."""
    counts = [f"{len(changes[key])} {key}" for key in ("created", "updated", "restored", "retired") if changes.get(key)]
    if not counts and not changes.get("sources"):
        return []
    details = ", ".join(counts + changes.get("sources", []))
    lines = [f"[marketplace-sync] The last background update changed the repository: {details}. Review it with git diff and commit it."]
    for key in ("created", "updated", "restored", "retired"):
        listed = changes.get(key, [])[:REPORT_MAX_LISTED_ASSETS]
        lines += [f"  {key}: {destination}" for destination in listed]
    if changes.get("backups"):
        lines.append(f"  {changes['backups']}")
    return lines


def command_update_report(arguments):
    """Show the result of the last background update once, in the next session."""
    report_path, _ = update_state_paths(arguments.project)
    report = read_update_report(report_path)
    if not report or report.get("reported"):
        return 0
    for line in describe_update_changes(report.get("changes", {})):
        write_line(line)
    for problem in report.get("problems", []) + report.get("attention", []):
        write_line(f"[marketplace-sync] The last background update reported: {problem[:REPORT_MAX_PROBLEM_CHARACTERS]}")
    report["reported"] = True
    write_text_atomically(report_path, serialize_json(report))
    return 0
