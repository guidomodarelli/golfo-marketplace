"""Finalize, after the Bash projection: the lockfile and the manifest of an apply, the instructions that wait for
the normalization, the scripts, CLIs and MCP servers of the packs, and the report of what changed.
"""

import os
import sys

import agent_ready_blocks as managed_blocks
import agent_ready_conflicts as conflicts_review
import agent_ready_machine as machine
import agent_ready_nested as nested
import agent_ready_pack_clis as pack_clis
import agent_ready_pack_mcp as pack_mcp
import agent_ready_pack_scripts as pack_scripts
import agent_ready_rule_changes as rule_changes
import agent_ready_workspaces as workspace_selection
from agent_ready_actions import (
    ACTION_CONFLICT,
    ACTION_DROP,
    ACTION_RETIRE,
    ACTION_RETIRE_CONFLICT,
    DETACHED_VIEW_REASON,
)
from agent_ready_common import (
    has_linked_parent,
    is_link,
    local_state,
    remove_empty_parents,
    serialize_json,
    write_text_atomically,
    write_text_if_changed,
)
from agent_ready_content import engine_version_of
from agent_ready_layout import (
    CLAUDE_PROXY_RELATIVE_PATH,
    MANAGED_BLOCK_START,
    MANIFEST_RELATIVE_PATH,
    SKILL_NAME,
    claude_proxy_text,
    claude_view_of,
)
from agent_ready_lockfile import (
    LOCK_RELATIVE_PATH,
    SCHEMA_VERSION,
    STATE_APPLIED,
    STATE_CONFLICT,
    STATE_FAILED,
    STATE_RETIRED_PRESERVED,
    read_lock,
)
from agent_ready_manifest import build_manifest, configuration_of, read_manifest
from agent_ready_options import (
    PROVIDERS_KEY,
    SHADOWING_ENABLED_KEY,
    USER_SERVERS_ENABLED_KEY,
    USER_SERVERS_REGISTER_KEY,
)
from agent_ready_output import paint, write_line
from agent_ready_review_findings import record_review_settings


def remove_claude_view_of(project_root, destination):
    """Remove the .claude view of a retired .agents asset when it is a managed view."""
    if not destination.startswith(".agents/"):
        return None
    relative_view = ".claude/" + destination[len(".agents/"):]
    if has_linked_parent(project_root, relative_view):
        return None
    view = os.path.join(project_root, relative_view)
    asset = os.path.join(project_root, destination)
    if os.path.islink(view):
        target = os.path.normpath(os.path.join(os.path.dirname(view), os.readlink(view)))
        if target == os.path.normpath(asset):
            os.unlink(view)
            return view
        return None
    if os.path.isfile(view) and os.path.isfile(asset) and os.path.samefile(view, asset):
        os.unlink(view)
        return view
    return None


def is_instruction_destination(destination):
    """True for an AGENTS.md that takes blocks: the root one (stack sections) or a nested target's."""
    return destination == managed_blocks.INSTRUCTION_SECTIONS_DESTINATION or nested.is_nested_destination(destination)


def instructions_conflict(project_root, skill_dir, folder=""):
    """True when the CLAUDE.md of a folder (the root by default) holds instructions of its own besides AGENTS.md.

    Mirrors normalize_root_instructions and normalize_nested_instruction_pair in
    instruction-normalization.sh: a CLAUDE.md that is the proxy, the bare "@AGENTS.md" or the same bytes
    as AGENTS.md is normalized, and one without an AGENTS.md is moved there; any other one is a conflict
    the agent resolves by hand, and so is a symlink or something that is not a file. The normalization
    skips the files Git ignores, so in a nested folder an ignored CLAUDE.md that is not the proxy stays as
    it is and is a conflict too, with or without an AGENTS.md: the block would never reach Claude Code.
    """
    claude_path = os.path.join(project_root, *folder.split("/"), "CLAUDE.md") if folder else \
        os.path.join(project_root, "CLAUDE.md")
    if not os.path.lexists(claude_path):
        return False
    agents_path = os.path.join(os.path.dirname(claude_path), managed_blocks.INSTRUCTION_SECTIONS_DESTINATION)
    if is_link(claude_path) or not os.path.isfile(claude_path) or is_link(agents_path):
        return True
    with open(claude_path, "rb") as file_handle:
        claude = file_handle.read()
    with open(os.path.join(skill_dir, CLAUDE_PROXY_RELATIVE_PATH), "rb") as file_handle:
        proxy = file_handle.read()
    if claude == proxy or claude.strip() == b"@AGENTS.md":
        return False
    if folder and managed_blocks.has_linked_directory(project_root, nested.destination_in(folder)):
        # Beyond a symlink nothing is written: the block reports the link as its conflict.
        return False
    if folder and nested.is_ignored(project_root, f"{folder}/{nested.PROXY_FILE}"):
        # The normalization never turns it into the proxy, whatever its AGENTS.md holds.
        return True
    if os.path.isfile(agents_path):
        with open(agents_path, "rb") as file_handle:
            return file_handle.read() != claude
    return False


def instructions_wait(project_root, skill_dir, destination):
    """True when the apply must leave the blocks of this AGENTS.md as they are.

    The two instruction files of a folder are the agent's to merge while CLAUDE.md conflicts with
    AGENTS.md, and the root AGENTS.md is the project's own file until the instruction review places the
    managed block (a legacy file). In both cases the apply adds, updates and removes no block there:
    they catch up on the next apply after that, so it never writes into instructions it has not adopted.
    A nested AGENTS.md without the managed block is not legacy: the block of its target goes at the end.
    """
    if instructions_conflict(project_root, skill_dir, os.path.dirname(destination)):
        return True
    if destination != managed_blocks.INSTRUCTION_SECTIONS_DESTINATION:
        return False
    path = os.path.join(project_root, managed_blocks.INSTRUCTION_SECTIONS_DESTINATION)
    if is_link(path) or not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8", errors="replace") as file_handle:
        return MANAGED_BLOCK_START not in file_handle.read().splitlines()


def waiting_instruction_files(project_root, skill_dir, destinations):
    """The AGENTS.md files among these destinations whose blocks wait (instructions_wait)."""
    return {destination for destination in destinations
            if is_instruction_destination(destination) and instructions_wait(project_root, skill_dir, destination)}


def without_waiting_sections(project_root, skill_dir, desired, locked):
    """(desired, locked) of the blocks to classify, without those of an AGENTS.md whose blocks wait."""
    waiting = waiting_instruction_files(project_root, skill_dir, {destination for destination, _ in desired} | set(locked))
    if not waiting:
        return desired, locked
    return ({key: item for key, item in desired.items() if key[0] not in waiting},
            {target: blocks for target, blocks in locked.items() if target not in waiting})


def instruction_sections_now(project_root, skill_dir, entries):
    """The block entries of a plan, with those of each AGENTS.md classified again against the file as it is.

    Between the plan and finalize the apply itself writes the instructions: it creates the root
    AGENTS.md from the template or renders the managed block again, and the normalization moves the
    instructions of a CLAUDE.md to its AGENTS.md. Without this, the blocks would see a file that
    changed during synchronization and stay out of it.
    """
    kept = [entry for entry in entries if not is_instruction_destination(entry["destination"])]
    destinations = sorted({entry["destination"] for entry in entries if is_instruction_destination(entry["destination"])})
    waiting = waiting_instruction_files(project_root, skill_dir, destinations)
    for destination in destinations:
        if destination in waiting:
            continue
        sections = [entry for entry in entries if entry["destination"] == destination]
        desired = {(destination, entry["id"]): {"profile": entry["profile"], "source": entry["source"],
                                                "content": entry["content"]}
                   for entry in sections if entry.get("content") is not None}
        # Every block the lock records stays in it: one that only comes from the lock (to retire) may
        # have no applied base yet, when its first write was a conflict.
        locked = {destination: {entry["id"]: {"profile": entry["profile"], "source": entry["source"],
                                              "sha256": entry["baseSha256"]}
                                for entry in sections if entry["baseSha256"] or entry.get("content") is None}}
        kept += managed_blocks.classify(project_root, desired, locked)
    return kept


def finalize(project_root, skill_dir, plan, updates):
    """Retire assets, then write the lockfile and the manifest."""
    lock_assets = {}
    removed = []
    retire_conflicts = []
    failed = []
    conflicts = []
    preserved_views = set(plan["detachedViews"])
    previous_lock = read_lock(project_root)
    previous_assets = previous_lock["assets"] if previous_lock else {}

    for entry in plan["entries"]:
        destination = entry["destination"]
        absolute_path = os.path.join(project_root, destination)
        previous_entry = previous_assets.get(destination, {})
        if entry["action"] == ACTION_DROP:
            continue
        if entry["action"] == ACTION_RETIRE:
            if local_state(absolute_path) != entry["local"] or has_linked_parent(project_root, destination):
                retire_conflicts.append(f"{destination} changed during synchronization; preserved")
                lock_assets[destination] = dict(previous_entry, state=STATE_RETIRED_PRESERVED)
                continue
            view = remove_claude_view_of(project_root, destination)
            if view:
                removed.append(os.path.relpath(view, project_root).replace(os.sep, "/"))
                # A view in a folder of its own (the rules of a workspace) leaves no empty folder behind.
                remove_empty_parents(project_root, view)
            os.unlink(absolute_path)
            remove_empty_parents(project_root, absolute_path)
            removed.append(destination)
            continue
        if entry["action"] == ACTION_RETIRE_CONFLICT:
            retire_conflicts.append(f"{destination}: {entry['reason']}")
            lock_assets[destination] = dict(previous_entry, state=STATE_RETIRED_PRESERVED)
            continue
        if entry["action"] == ACTION_CONFLICT:
            conflicts.append(f"{destination}: {entry['reason']}")
            lock_assets[destination] = {
                "profile": entry["profile"],
                "source": entry["source"],
                "sha256": entry["baseSha256"],
                # What the source wanted to write: --from-lock verifies the content against it.
                "desiredSha256": entry["sha256"],
                "state": STATE_CONFLICT,
            }
            continue
        if local_state(absolute_path) == entry["sha256"]:
            lock_assets[destination] = {
                "profile": entry["profile"],
                "source": entry["source"],
                "sha256": entry["sha256"],
                "state": STATE_APPLIED,
            }
            # The hash of each atomic rule of the file, so a change shows rule by rule.
            if rule_changes.is_rule_destination(destination):
                hashes = rule_changes.rule_hashes(rule_changes.read_text(absolute_path), destination)
                if hashes:
                    lock_assets[destination]["rules"] = hashes
        else:
            failed.append(destination)
            lock_assets[destination] = {
                "profile": entry["profile"],
                "source": entry["source"],
                "sha256": entry["baseSha256"],
                "desiredSha256": entry["sha256"],
                "state": STATE_FAILED,
            }

    for entry in plan["entries"]:
        if entry.get("workspace") and entry["destination"] in lock_assets:
            lock_assets[entry["destination"]]["workspace"] = entry["workspace"]

    # Whatever happened to the asset, a project file in its view stays the project's.
    for entry in plan["entries"]:
        if entry["sha256"] and entry["destination"] in lock_assets and                 claude_view_of(entry["destination"], entry["source"]) in preserved_views:
            lock_assets[entry["destination"]]["viewPreserved"] = True

    conflicts += [f"{view}: {DETACHED_VIEW_REASON}" for view in plan["detachedViews"]]
    block_report = managed_blocks.apply(project_root, instruction_sections_now(project_root, skill_dir, plan.get("blocks", [])))
    conflicts += block_report["conflicts"]
    failed += [f"managed blocks of {problem}" for problem in block_report["failed"]]
    # Claude Code loads a nested AGENTS.md only through the CLAUDE.md next to it.
    block_report["proxiesWritten"], block_report["proxiesRemoved"], proxy_failures = nested.place_proxies(
        project_root, block_report["changed"], block_report["removed"], claude_proxy_text(skill_dir))
    failed += [f"proxy {problem}" for problem in proxy_failures]

    lock = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": SKILL_NAME, "version": engine_version_of(skill_dir), "stateSchemaVersion": SCHEMA_VERSION},
        "source": plan["source"],
        "profiles": plan["profileDigests"],
        # The digests map is keyed by name; profileOrder keeps the resolution order.
        "profileOrder": plan["profiles"],
        "primaryStack": plan["primaryStack"],
        "providers": configuration_of(project_root).value(PROVIDERS_KEY),
        "requires": {"bash": "3.2+", "git": "any", "python3": "3.8+"},
        "assets": lock_assets,
        "merged": plan["merged"],
    }
    if plan.get("workspaces"):
        lock["workspaces"] = workspace_selection.lock_entries(plan["workspaces"])
    previous_blocks = (previous_lock or {}).get("blocks") or {}
    for destination in waiting_instruction_files(project_root, skill_dir, previous_blocks):
        # Its blocks were left out of this apply: the lock keeps what it knew of them.
        block_report["lock"][destination] = previous_blocks[destination]
    if block_report["lock"]:
        lock["blocks"] = block_report["lock"]
    if plan["profileSources"]:
        lock["profileSources"] = plan["profileSources"]
    mcp_report = register_pack_mcp_servers(project_root, plan, previous_lock)
    if mcp_report["lock"]:
        lock["mcpServers"] = mcp_report["lock"]
    cli_report = install_pack_clis(project_root, plan, previous_lock)
    if cli_report["lock"]:
        lock["clis"] = cli_report["lock"]
    # Last: a script finds the files of this apply and the CLIs on its PATH.
    script_report = run_pack_scripts(project_root, plan, previous_lock)
    if script_report["lock"]:
        lock["scripts"] = script_report["lock"]
    write_text_if_changed(os.path.join(project_root, LOCK_RELATIVE_PATH), serialize_json(lock))

    manifest = read_manifest(project_root)
    desired_manifest = build_manifest(manifest, plan["profiles_requested"], updates)
    if manifest != desired_manifest:
        write_text_atomically(os.path.join(project_root, MANIFEST_RELATIVE_PATH), serialize_json(desired_manifest))
    record_review_settings(project_root)
    # The update the last plan reviewed is on disk now: its conflicts are the current ones.
    conflicts_review.record_pending(project_root, [])

    return {"removed": removed, "retireConflicts": retire_conflicts, "failed": failed, "conflicts": conflicts,
            "blocks": block_report, "mcpServers": mcp_report, "clis": cli_report, "scripts": script_report}


def run_pack_scripts(project_root, plan, previous_lock):
    """Run the install and post-apply scripts of the packs that the policy allows; automated reviews run none."""
    previous = (previous_lock or {}).get("scripts", {})
    if os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") == "1":
        return {"ran": [], "failed": [], "lock": previous, "skipped": "automated reviews never run the scripts of the packs"}
    return pack_scripts.run_apply_events(project_root, plan.get("packTools"), previous)


def print_pack_script_report(report, stream):
    """What ran among the scripts of the packs, and which ones failed."""
    if not report:
        return
    if report.get("skipped"):
        write_line(f"Scripts of profile packs: none ran ({report['skipped']}).", stream)
        return
    for line in report["ran"]:
        write_line(paint(f"Script of a profile pack ran: {line}", "ok", stream), stream)
    for problem in report["failed"]:
        # ERROR: at the start of the line: the background update reports it in the next session and
        # counts it among the consecutive failures.
        write_line(paint(f"ERROR: script of a profile pack failed: {problem}", "error", stream), stream)


def install_pack_clis(project_root, plan, previous_lock):
    """Install the CLIs of the packs that the policy allows, in the cache of the user; automated reviews install none."""
    previous = (previous_lock or {}).get("clis", {})
    if os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") == "1":
        return {"installed": [], "reused": [], "removed": [], "manual": [], "conflicts": [], "failed": [],
                "lock": previous, "path": [], "skipped": "automated reviews never install the CLIs of the packs"}
    return pack_clis.install(project_root, plan.get("packTools"), previous)


def print_pack_cli_report(report, stream):
    """What an apply installed, reused or dropped among the CLIs of the packs."""
    if not report:
        return
    if report.get("skipped"):
        write_line(f"CLIs of profile packs: unchanged ({report['skipped']}).", stream)
        return
    if report["installed"]:
        write_line(paint(f"CLIs of profile packs installed in {pack_clis.installs_root()}: {', '.join(report['installed'])}",
                         "ok", stream), stream)
    if report["reused"]:
        write_line(f"CLIs of profile packs already in the cache: {', '.join(report['reused'])}", stream)
    if report["removed"]:
        write_line(f"CLIs this repository no longer uses: {', '.join(report['removed'])}", stream)
    for note in report["manual"] + report["conflicts"]:
        write_line(paint(f"  ! {note}", "warning", stream), stream)
    for problem in report["failed"]:
        write_line(paint(f"  ! CLI not installed: {problem}", "error", stream), stream)


def register_pack_mcp_servers(project_root, plan, previous_lock):
    """Register the MCP servers of the packs that the policy allows; automated reviews change none."""
    previous = (previous_lock or {}).get("mcpServers", {})
    if os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") == "1":
        return {"registered": {}, "removed": {}, "conflicts": [], "failed": [], "lock": previous,
                "skipped": "automated reviews never change the MCP servers the providers start"}
    configuration = configuration_of(project_root)
    providers = configuration.value(PROVIDERS_KEY)
    return pack_mcp.register(project_root, plan.get("packTools"), previous, providers,
                             user_duplicates_to_skip(plan, configuration, providers))


def user_duplicates_to_skip(plan, configuration, providers):
    """{provider: {name: user name}} of the pack servers the apply leaves to the user's configuration."""
    if not configuration.value(USER_SERVERS_ENABLED_KEY) or configuration.value(USER_SERVERS_REGISTER_KEY):
        return {}
    desired, _ = pack_mcp.desired_servers(plan.get("packTools"))
    return machine.duplicated_servers(desired, providers)


def machine_report(project_root, plan, configuration):
    """What the selection collides with on this machine: skills, subagents and commands of the same
    name, and pack MCP servers the user already has. Read-only."""
    report = {}
    if configuration.value(SHADOWING_ENABLED_KEY):
        report["shadowed"] = machine.shadowed_assets(project_root, plan["entries"])
    if configuration.value(USER_SERVERS_ENABLED_KEY):
        desired, _ = pack_mcp.desired_servers(plan.get("packTools"))
        providers = configuration.value(PROVIDERS_KEY)
        files = machine.user_server_paths()
        registered = configuration.value(USER_SERVERS_REGISTER_KEY)
        report["userServers"] = [
            {"name": name, "profile": desired[name]["profile"], "provider": provider, "userName": user_name,
             "userFile": files[provider], "registered": bool(registered)}
            for provider, names in sorted(machine.duplicated_servers(desired, providers).items())
            for name, user_name in sorted(names.items())
        ]
    return report


def machine_report_lines(report):
    """The collisions with the machine, one line each."""
    lines = []
    if not report:
        return lines
    for finding in report.get("shadowed", []):
        lines.append(f"  ~ {finding['kind']} {finding['name']} ({finding['profile']}) has the same name as "
                     f"{finding['machine']}: {finding['winner']}")
    for server in report.get("userServers", []):
        action = ("registered anyway" if server["registered"]
                  else f"not registered for {server['provider']} ({USER_SERVERS_REGISTER_KEY}: true registers it)")
        lines.append(f"  ~ MCP server {server['name']} ({server['profile']}) is the user's {server['userName']} "
                     f"in {server['userFile']}: {action}")
    return lines


def print_machine_report(report):
    """Print the lines of machine_report_lines."""
    for line in machine_report_lines(report):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def print_pack_mcp_report(report, stream):
    """What an apply registered, unregistered or left alone among the MCP servers of the packs."""
    if not report:
        return
    if report.get("skipped"):
        write_line(f"MCP servers of profile packs: unchanged ({report['skipped']}).", stream)
        return
    for path, names in sorted(report["registered"].items()):
        if names:
            write_line(paint(f"MCP servers of profile packs in {path}: {', '.join(names)}", "ok", stream), stream)
    for path, names in sorted(report["removed"].items()):
        if names:
            write_line(f"Unregistered from {path}: {', '.join(names)}", stream)
    for conflict in report["conflicts"]:
        write_line(paint(f"  ! MCP server kept as the project has it: {conflict}", "warning", stream), stream)
    for path, names in sorted(report.get("userDuplicates", {}).items()):
        for name, user_name in sorted(names.items()):
            write_line(f"Not registered in {path}: {name}, the user already has it as {user_name}", stream)
    for problem in report["failed"]:
        write_line(paint(f"  ! {problem}", "error", stream), stream)


def print_block_report(report, stream):
    """Which files an apply changed through their managed blocks, and which it kept."""
    if not report:
        return
    for path in report["changed"]:
        write_line(f"Managed blocks written: {path}", stream)
    for path in report["removed"]:
        write_line(f"Removed, only held managed blocks: {path}", stream)
    for path in report.get("proxiesWritten", []):
        write_line(f"Proxy written next to a nested AGENTS.md: {path}", stream)
    for path in report.get("proxiesRemoved", []):
        write_line(f"Removed, proxy of a removed AGENTS.md: {path}", stream)
    for conflict in report["conflicts"]:
        # WARNING: at the start of the line: the background update reports it in the next session.
        write_line(paint(f"WARNING: managed block kept: {conflict}", "warning", stream), stream)


def print_finalize_report(report):
    """Report retirement, preserved conflicts and the overall result."""
    stream = sys.stdout
    if report["removed"]:
        write_line("Retired managed assets:")
        for path in report["removed"]:
            write_line(f"  - {path}")
    # The projection already reported each preserved conflict with its path.
    if report["retireConflicts"]:
        write_line(paint("Retired assets kept because they changed locally:", "warning", stream))
        for conflict in report["retireConflicts"]:
            write_line(f"  ! {conflict}")
    if report["failed"]:
        write_line(paint("Managed assets that could not be applied (see conflicts above):", "error", stream))
        for path in report["failed"]:
            write_line(f"  ! {path}")
    print_block_report(report.get("blocks"), stream)
    print_pack_mcp_report(report.get("mcpServers"), stream)
    print_pack_cli_report(report.get("clis"), stream)
    print_pack_script_report(report.get("scripts"), stream)
    if report["failed"]:
        result = "partial: some managed assets could not be applied"
    elif (report.get("scripts") or {}).get("failed"):
        result = "partial: a script of a profile pack failed"
    elif report["conflicts"] or report["retireConflicts"]:
        preserved = len(report["conflicts"]) + len(report["retireConflicts"])
        result = f"applied with {preserved} preserved conflict(s)"
    else:
        result = "complete"
    write_line(f"Lockfile: {LOCK_RELATIVE_PATH} ({result})")
