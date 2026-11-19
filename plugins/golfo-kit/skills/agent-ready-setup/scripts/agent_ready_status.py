"""Status: how the checkout and the sources compare with the lock, and how status prints it.

compute_status stays in the entry point while it computes a plan there.
"""

import fnmatch
import os
import re
import sys

import agent_ready_content as content_source
import agent_ready_pack_signatures as pack_signatures
import agent_ready_pack_tools as pack_tools
import agent_ready_parity as parity
import agent_ready_repo_facts as repo_facts
from agent_ready_config import format_value
from agent_ready_layout import MANIFEST_RELATIVE_PATH, review_cache_module
from agent_ready_manifest import print_ignored_configuration
from agent_ready_options import PROFILES_KEY, UPDATES_MODE_KEY, WORKSPACES_KEY
from agent_ready_output import paint, write_line
from agent_ready_packs import SOURCE_AVAILABLE, SOURCE_TYPE_GIT

# Besides the files of the repository facts and of the parity checks (CI and .env examples), what the
# structural checks read: the instructions, the harness directories (rules, skills, settings, hooks) and MCP.
CONFLICT_INPUT_PATTERN = re.compile(r"^(AGENTS\.md|CLAUDE\.md|\.mcp\.json|(\.agents|\.claude|\.codex)/.+)$")


def describe_source_item(name, item):
    """One line about a declared source. Origins never carry credentials: the manifest rejects them."""
    if item["state"] != SOURCE_AVAILABLE:
        need = "needed by the selection" if item["selected"] else "not needed by this selection"
        return f"{name} ({item['type']} {item['origin']}): not available: {item['reason']} ({need})"
    details = []
    if item["type"] == SOURCE_TYPE_GIT:
        details.append(f"requested {item['requestedRef']}, commit {item['resolvedCommit'][:12]}")
    details.append(f"catalog {item['catalogDigest'][:12]}, content {item['contentDigest'][:12]}")
    details.append(f"profiles: {', '.join(item['selected']) or 'none selected'}")
    return f"{name} ({item['type']} {item['origin']}): " + "; ".join(details)


def describe_source(identity):
    """One-line description of a source identity."""
    if not identity:
        return "none"
    version = identity.get("version") or "unknown version"
    revision = identity.get("revision")
    suffix = f", revision {revision[:12]}" if revision else ""
    if identity.get("origin"):
        suffix += f", from {identity['origin']}"
    name = identity.get("name", content_source.CONTENT_SOURCE_NAME)
    return f"{name} {version} ({identity.get('kind', 'unknown')}{suffix}; content {identity.get('contentDigest', '')[:12]})"


def selection_differences(lock, plan):
    """How the selected profiles differ from the lock, in words."""
    differences = []
    locked_order = lock.get("profileOrder")
    if locked_order != plan["profiles"]:
        differences.append(f"the lock has the profiles {', '.join(locked_order or []) or 'none'}; the selection resolves to {', '.join(plan['profiles'])}")
    locked_profiles = lock.get("profiles") or {}
    for name, entry in sorted(plan["profileDigests"].items()):
        if name in locked_profiles and locked_profiles[name] != entry:
            differences.append(f"profile {name} changed since the lock")
    return differences


def conflict_inputs_changed(changed, skill_dir):
    """True when an edited path, relative to the project, is one the structural checks read."""
    facts = repo_facts.load_facts(skill_dir) if skill_dir else {}
    parity_patterns = parity.REPOSITORY_CI_FILES + parity.EXAMPLE_ENVIRONMENT_FILES
    return any(CONFLICT_INPUT_PATTERN.match(path) or repo_facts.is_signal_file(path, facts)
               or any(fnmatch.fnmatchcase(path, pattern) for pattern in parity_patterns)
               for path in (changed_path.replace(os.sep, "/") for changed_path in changed))


def status_has_drift(status):
    """True when the checkout or the source differs from the lock, or the selection cannot resolve."""
    if status["errors"] or status["incomplete"]:
        return True
    checkout = status["checkout"]
    if any(checkout[key] for key in ("modified", "missing", "conflict", "failed", "retiredPreserved")):
        return True
    if status.get("workspaceDifferences"):
        # A workspace of the manifest that the last apply did not adopt, or one that left it.
        return True
    return bool(status["update"] and status["update"]["available"]) or not status["hasLock"]


def pack_tools_report(plan, catalog, configuration):
    """The verdict of every tool the selected profiles declare, with the signature of each source checked locally."""
    return pack_tools.report(plan["packToolDeclarations"], catalog, configuration,
                             verify_signature=pack_signatures.verifier(configuration))


def print_pack_tools(report, stream, brief=False):
    """What the selected packs declare besides files, and what the security policy decides about each one."""
    if not report:
        return
    blocked = sum(tool["decision"] == pack_tools.DECISION_BLOCKED for tool in report["tools"])
    write_line(paint("Pack tools (what the security policy allows; an apply registers the allowed MCP servers, "
                     "installs the allowed CLIs and runs the allowed scripts)", "heading", stream), stream)
    for tool in report["tools"]:
        label = f"{pack_tools.describe_tool(tool)} [{tool['profile']}]"
        if tool["decision"] == pack_tools.DECISION_ALLOWED:
            effect = "" if tool["type"] in report.get("applies", []) else " (not installed or run yet)"
            write_line(paint(f"  + allowed: {label}{effect}", "ok", stream), stream)
        else:
            write_line(paint(f"  - blocked: {label}: {tool['reason']}", "warning", stream), stream)
    if not brief:
        write_line("  Policy:", stream)
        for key, item in report["policy"].items():
            write_line(f"    {key}: {format_value(item['value'])} ({item['origin']})", stream)
    elif blocked:
        write_line(f"  {blocked} blocked; agent-ready plan shows the policy and the layer of each value.", stream)
    write_line("", stream)


def print_review_summary(reviews, brief, stream):
    """Open findings of the AI reviews and decisions to confirm, from the cache; nothing when there is no review yet."""
    if not reviews or not (reviews["units"] or reviews["stale"]):
        return
    module = review_cache_module()
    quiet = f"; {reviews['quiet']} accepted or dismissed" if reviews.get("quiet") else ""
    if reviews["findings"]:
        write_line(paint(f"AI reviews: {len(reviews['findings'])} known finding(s) in {reviews['units']} reviewed unit(s), "
                         f"from the cache{quiet}:", "warning", stream), stream)
        if not brief:
            for finding in reviews["findings"]:
                write_line(paint(f"  {module.finding_line(finding)}", "warning", stream), stream)
            write_line(f"  Accept or dismiss one with: agent-ready review accept <id> --reason \"...\"", stream)
    else:
        write_line(paint(f"AI reviews: no known finding in {reviews['units']} reviewed unit(s){quiet}.", "ok", stream), stream)
    if reviews["stale"] and not brief:
        write_line(f"  {reviews['stale']} review(s) are out of date and run again on the next edit or apply.", stream)


def print_status_conflicts(lines, stream):
    """The structural conflicts status knows about, one per line; nothing when there is none."""
    if not lines:
        return
    write_line(paint(f"Conflicts between the profiles: {len(lines)} structural, "
                     f"listed with their fix by `agent-ready conflicts`:", "warning", stream))
    for line in lines:
        write_line(paint(line, "warning", stream))


def print_status(status, brief):
    """Human readable status."""
    stream = sys.stdout
    configuration = status["configuration"]
    profiles = configuration.value(PROFILES_KEY)
    if profiles == []:
        write_line(f"Agent Ready profiles: none, the core only (updates: {configuration.value(UPDATES_MODE_KEY)})")
    elif not profiles:
        hint = "" if brief else " Run /agent-ready-setup to pin this repository."
        write_line(paint(f"Agent Ready: no profiles selected in {MANIFEST_RELATIVE_PATH}.{hint}", "warning", stream))
    else:
        write_line(f"Agent Ready profiles: {', '.join(profiles)} (updates: {configuration.value(UPDATES_MODE_KEY)})")
    for entry in configuration.value(WORKSPACES_KEY) or []:
        write_line(f"Workspace {entry['path']}: {', '.join(entry['profiles']) or 'none'}")
    for difference in status.get("workspaceDifferences", []):
        write_line(paint(f"  ! {difference}: run agent-ready apply to adopt it", "warning", stream))
    # SessionStart already reported what was ignored when it read the configuration.
    if not brief:
        print_ignored_configuration(configuration, stream)
    if not status["hasLock"]:
        write_line(paint("No lockfile: applied assets are not pinned yet.", "warning", stream))
    else:
        write_line(f"Locked source: {describe_source(status['lockedSource'])}")
        checkout = status["checkout"]
        write_line(
            "Checkout: "
            f"{len(checkout['applied'])} applied, {len(checkout['modified'])} modified, "
            f"{len(checkout['missing'])} missing, {len(checkout['conflict'])} preserved conflicts, "
            f"{len(checkout['failed'])} failed, {len(checkout['retiredPreserved'])} retired but preserved"
        )
        if not brief:
            for key, label in (("modified", "modified"), ("missing", "missing"), ("conflict", "conflict"),
                               ("failed", "failed"), ("retiredPreserved", "retired but preserved")):
                for destination in checkout[key]:
                    write_line(f"  ! {label}: {destination}")
    for name, item in status["sources"].items():
        if item["differences"] or item["pendingUpdate"] or item["state"] != SOURCE_AVAILABLE or not brief:
            write_line(f"Profile source {describe_source_item(name, item)}")
        if item["differences"]:
            write_line(paint(f"  ! {name} differs from the lock: {'; '.join(item['differences'])}", "warning", stream))
        if item["pendingUpdate"]:
            write_line(paint(f"  ! {name}: {item['pendingUpdate']}", "warning", stream))
    if status["incomplete"]:
        write_line(paint(f"Evaluation incomplete, nothing was validated: {status['incomplete']}", "warning", stream))
    update = status["update"]
    if update:
        if update["available"]:
            hint = "" if brief else " Review it with `/agent-ready-setup plan` and apply it with `/agent-ready-setup`."
            write_line(paint(
                f"Update available: {describe_source(update['source'])}; {len(update['changedDestinations'])} asset(s) would change.{hint}",
                "warning", stream,
            ))
        else:
            write_line(paint("Source matches the lock: no update pending.", "ok", stream))
    print_status_conflicts(status.get("conflicts"), stream)
    print_review_summary(status.get("reviews"), brief, stream)
    print_pack_tools(status.get("packTools"), stream, brief=True)
    sweep = status.get("learningSweep")
    if sweep and not sweep["ok"]:
        write_line(paint(f"Scheduled learning sweep missing: {sweep['detail']}. Episodes still close when a chat ends "
                         "or from another hook; `agent-ready learn schedule` registers it.", "warning", stream))
    elif sweep and not brief:
        write_line(f"Scheduled learning sweep: {sweep['detail']}")
    if not brief and status["capabilities"]:
        write_line("Provider capabilities:")
        for provider, capabilities in status["capabilities"].items():
            details = ", ".join(f"{name}={value['support']}" for name, value in capabilities.items())
            write_line(f"  {provider}: {details}")
    for error in status["errors"]:
        write_line(paint(f"ERROR: {error}", "error", stream))


def source_report_without_selection(catalog):
    """Readable state of each declared source when no selection could be evaluated."""
    report = {}
    for name, source in sorted(catalog.get("sources", {}).items()):
        if source["state"] == SOURCE_AVAILABLE:
            report[name] = f"available ({source['type']} {source['origin']})"
        else:
            report[name] = f"not available ({source['type']} {source['origin']}): {source['reason']}"
    return report
