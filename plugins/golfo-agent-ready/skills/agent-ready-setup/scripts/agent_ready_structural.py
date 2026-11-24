"""Structural checks: what the selection adds to the context of every session, what the repository really uses,
the parity of CI and .env examples, skills and tools that compete, and settings that contradict each other.
plan prints them; status and check report them as conflicts.
"""

import importlib.util
import os
import sys
import tempfile

import agent_ready_blocks as managed_blocks
import agent_ready_conflicts as conflicts_review
import agent_ready_pack_mcp as pack_mcp
import agent_ready_pack_tools as pack_tools
import agent_ready_agent_metadata as agent_metadata
import agent_ready_rule_triggers as rule_triggers
import agent_ready_parity as parity
import agent_ready_repo_facts as repo_facts
import agent_ready_rules as atomic_rules
import agent_ready_settings_conflicts as settings_conflicts
import agent_ready_skill_overlap as skill_overlap
from agent_ready_actions import ACTION_CONFLICT, ACTION_RETIRE
from agent_ready_common import bash_executable, is_link, text_bytes, walk_files
from agent_ready_desired_assets import compose_stack_directory
from agent_ready_finalize import machine_report, machine_report_lines
from agent_ready_layout import BROWSER_TOOL_NAME, ENGINE_SKILL_DIRECTORY, review_cache_module
from agent_ready_merged_files import extract_managed_block, render_instructions
from agent_ready_options import (
    CI_JOB_CONFLICTS_ENABLED_KEY,
    COMPETING_SKILLS_ENABLED_KEY,
    COMPETING_TOOLS_ENABLED_KEY,
    CONTEXT_BUDGET_BYTES_KEY,
    CONTEXT_BUDGET_ENABLED_KEY,
    CONTEXT_BUDGET_RULES_BYTES_KEY,
    ENVIRONMENT_CONFLICTS_ENABLED_KEY,
    HOOK_CONFLICTS_ENABLED_KEY,
    PERMISSION_CONFLICTS_ENABLED_KEY,
    PROVIDERS_KEY,
    PROVIDER_PARITY_ENABLED_KEY,
    REPO_REALITY_ENABLED_KEY,
    REVIEWS_CACHE_KEY,
    REVIEWS_COMMIT_KEY,
    REVIEWS_ENABLED_KEY,
    REVIEWS_TTL_KEY,
    RULES_ENABLED_KEY,
    TOOLS_ENABLED_KEY,
)
from agent_ready_output import paint, write_line
from agent_ready_packs import is_pack_profile

# How many profiles the context warning names as the ones that add the most.
CONTEXT_LARGEST_PROFILES = 3
# The entry point that registers the browser MCP servers; its SERVER_ALIASES is their roster.
BROWSER_SETUP_RELATIVE_PATH = "scripts/setup-browser-tools.py"
RULES_DESTINATION_PREFIX = ".agents/rules/"
# The owner the reports give to the rules the project wrote itself.
PROJECT_RULES_PROFILE = "project"


def loaded_at_start(text):
    """True when Claude loads a rule at the start of a session: it has no paths: in its frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return True
    for line in lines[1:]:
        if line.strip() == "---":
            return True
        if line.startswith("paths:"):
            return False
    return True


def context_budget(project_root, skill_dir, catalog, plan, configuration):
    """What the selection adds to the context of every session, in bytes, and the profiles that add most.

    AGENTS.md is the file the apply would write: the managed block rendered by
    render-instruction-template.sh, as for the plan diff, and the stack sections the plan places with
    the same block functions as the apply. Claude also loads every rule without paths: at the start,
    managed or the project's own; a rule the apply retires does not count. MCP servers are the ones the
    apply registers: the browser's when its tools are enabled, and the pack servers the policy allows.
    """
    rules, project_rules = projected_rules(project_root, plan)
    rules_by_profile, rule_files = {}, 0
    for rule in rules:
        if loaded_at_start(rule["text"]):
            rule_files += 1
            rules_by_profile[rule["profile"]] = rules_by_profile.get(rule["profile"], 0) + text_bytes(rule["text"])

    agents_text, sections_by_profile = projected_agents_md(project_root, skill_dir, catalog, plan, project_rules)
    browser_servers = len(browser_mcp_servers(skill_dir)) if (
        BROWSER_TOOL_NAME in plan["tools"] and configuration.value(TOOLS_ENABLED_KEY)) else 0
    pack_servers, _ = pack_mcp.desired_servers(plan.get("packTools"))
    agents_bytes, rules_bytes = text_bytes(agents_text), sum(rules_by_profile.values())
    agents_limit = configuration.value(CONTEXT_BUDGET_BYTES_KEY)
    rules_limit = configuration.value(CONTEXT_BUDGET_RULES_BYTES_KEY)
    return {
        "agentsMd": {"bytes": agents_bytes, "limitBytes": agents_limit, "exceeded": agents_bytes > agents_limit,
                     "largest": largest_profiles(sections_by_profile)},
        "rulesLoadedAtStart": {"bytes": rules_bytes, "files": rule_files, "limitBytes": rules_limit,
                               "exceeded": rules_limit is not None and rules_bytes > rules_limit,
                               "largest": largest_profiles(rules_by_profile)},
        "mcpServers": browser_servers + len(pack_servers),
    }


def browser_mcp_servers(skill_dir):
    """The MCP servers the browser setup registers, read from its own roster.

    The setup needs Python 3.11 and exits before registering anything on an older one, so there the
    roster is empty, as the registration would be.
    """
    specification = importlib.util.spec_from_file_location(
        "agent_ready_browser_setup", os.path.join(skill_dir, BROWSER_SETUP_RELATIVE_PATH))
    module = importlib.util.module_from_spec(specification)
    try:
        specification.loader.exec_module(module)
    except SystemExit:
        return ()
    return tuple(module.SERVER_ALIASES)


def projected_rules(project_root, plan):
    """([{path, profile, text}], {path: text}) of the rules in .agents/rules after the apply.

    The first list holds every rule: the managed ones (the local file when the apply keeps it for a
    conflict, the template otherwise) and the project's own, with profile "project". The second
    holds only the project's own.
    """
    # The rules the apply writes or deletes. A dropped or retire-conflict entry leaves its file, which
    # stays as the project's own.
    managed_destinations = {entry["destination"] for entry in plan["entries"]
                            if entry["sha256"] or entry["action"] == ACTION_RETIRE}
    rules = []
    for entry in plan["entries"]:
        destination = entry["destination"]
        if not entry["sha256"] or not destination.startswith(RULES_DESTINATION_PREFIX) or not destination.endswith(".md"):
            continue
        # A conflict keeps the local file: that file is the one the agents load, not the template.
        local_path = os.path.join(project_root, destination)
        kept_local = entry["action"] == ACTION_CONFLICT and os.path.isfile(local_path) and not is_link(local_path)
        with open(local_path if kept_local else entry["sourcePath"], encoding="utf-8", errors="replace") as rule_file:
            rules.append({"path": destination, "profile": entry["profile"], "text": rule_file.read(),
                          "workspace": entry.get("workspace")})
    project_rules = project_owned_rules(project_root, managed_destinations)
    rules += [{"path": RULES_DESTINATION_PREFIX + path, "profile": PROJECT_RULES_PROFILE, "text": text}
              for path, text in sorted(project_rules.items())]
    return rules, project_rules


def rule_key_report(project_root, plan):
    """[{key, rules: [{id, path, profile, line}]}] of the decision keys that the rules after the apply,
    managed and the project's own, decide differently: a conflict found without any model."""
    rules, _ = projected_rules(project_root, plan)
    root_rules = []
    workspace_rules = {}
    profiles = {}
    for rule_file in rules:
        file_rules, _ = atomic_rules.parse_rule_text(rule_file["text"], rule_file["path"])
        for rule in file_rules:
            profiles[id(rule)] = rule_file["profile"]
        workspace = rule_file.get("workspace")
        (workspace_rules.setdefault(workspace, []) if workspace else root_rules).extend(file_rules)
    # A rule of the root applies to every workspace; the rules of two workspaces never apply to the same
    # files, as in the AI review (agent_ready_conflicts), so each workspace is compared with the root only.
    scopes = [root_rules] + [root_rules + scoped for _, scoped in sorted(workspace_rules.items())]
    report = []
    seen = set()
    for scope in scopes:
        for conflict in atomic_rules.key_conflicts(scope):
            identity = (conflict["key"], tuple(sorted((rule.path, rule.line) for rule in conflict["rules"])))
            if identity in seen:
                continue
            seen.add(identity)
            report.append({"key": conflict["key"],
                           "rules": [{"id": rule.id, "path": rule.path, "line": rule.line,
                                      "profile": profiles[id(rule)]} for rule in conflict["rules"]]})
    return report


def rule_key_lines(conflicts):
    """One line per decision key that two rules decide differently."""
    return [f"  ! {conflict['key']} is decided differently by "
            + " and ".join(f"{rule['id']} ({rule['profile']}, {rule['path']}:{rule['line']})" for rule in conflict["rules"])
            + "; keep one, or replace the other with overrides"
            for conflict in conflicts]


def print_rule_keys(conflicts):
    """Print the lines of rule_key_lines."""
    for line in rule_key_lines(conflicts):
        write_line(paint(line, "warning", sys.stdout))


def repo_reality_report(project_root, skill_dir, plan):
    """The assumptions of the rules that the repository contradicts. Read-only."""
    rules, _ = projected_rules(project_root, plan)
    facts = repo_facts.load_facts(skill_dir)
    findings = repo_facts.contradictions(project_root, facts, [rule for rule in rules if not rule.get("workspace")])
    # A rule of a workspace is checked against that folder: its package.json, its configuration files.
    for path in sorted({rule["workspace"] for rule in rules if rule.get("workspace")}):
        workspace_rules = [rule for rule in rules if rule.get("workspace") == path]
        for finding in repo_facts.contradictions(os.path.join(project_root, *path.split("/")), facts, workspace_rules):
            if "evidence" in finding:
                finding["evidence"] = [f"{path}/{evidence}" for evidence in finding["evidence"]]
            findings.append(finding)
    return findings


def repo_reality_lines(findings):
    """One line per rule the repository contradicts."""
    lines = []
    for finding in findings:
        if finding.get("unknown"):
            lines.append(f"  ~ {finding['rule']} ({finding['profile']}) assumes {finding['fact']}: {finding['assumes']}, "
                         f"which {repo_facts.FACTS_RELATIVE_PATH} does not know; it is not checked")
            continue
        lines.append(f"  ! {finding['rule']} ({finding['profile']}) assumes {finding['description']} {finding['assumes']}, "
                     f"but the repository uses {', '.join(finding['repository'])} ({', '.join(finding['evidence'])})")
    return lines


def print_repo_reality(findings):
    """Print the lines of repo_reality_lines."""
    for line in repo_reality_lines(findings):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def antigravity_dropped_rules(project_root, plan):
    """[{path, profile, problem}] of the rules after the apply that Antigravity reads (the first level of
    .agents/rules/ and the folders of .agents/rules.json) but drops for their frontmatter
    (agent_ready_rule_triggers.trigger_problem). The personal rules of each person stay out."""
    rules, _ = projected_rules(project_root, plan)
    reachable = set(rule_triggers.loaded_rule_files([rule["path"] for rule in rules]))
    dropped = []
    for rule in rules:
        problem = rule_triggers.trigger_problem(rule["text"]) if rule["path"] in reachable else None
        if problem:
            dropped.append({"path": rule["path"], "profile": rule["profile"], "problem": problem})
    return dropped


def parity_report(project_root, skill_dir, plan, configuration, with_user=True):
    """What each provider sees and the variables and CI jobs that collide. Read-only.

    ``with_user`` False leaves the user's own hooks out of the comparison.
    """
    report = {}
    providers = configuration.value(PROVIDERS_KEY)
    if configuration.value(PROVIDER_PARITY_ENABLED_KEY) and len(set(providers)) > 1:
        rules, _ = projected_rules(project_root, plan)
        scoped = sum(1 for rule in rules if not loaded_at_start(rule["text"]))
        views = parity.provider_views(len(rules), scoped, plan["entries"])
        report["views"] = {provider: view for provider, view in views.items() if provider in providers}
        hook_providers = [provider for provider in PROVIDER_VIEW_ORDER if provider in providers]
        report["hookDifferences"] = parity.hook_differences(project_root, skill_dir, with_user, hook_providers)
    if configuration.value(PROVIDER_PARITY_ENABLED_KEY) and parity.PROVIDER_ANTIGRAVITY in providers:
        report["antigravityDropped"] = antigravity_dropped_rules(project_root, plan)
    if configuration.value(PROVIDER_PARITY_ENABLED_KEY):
        report["agentLimitations"] = [
            {"agent": entry["destination"], "provider": provider, "note": note}
            for entry in plan["entries"] if entry.get("agentMetadata")
            for provider, note in agent_metadata.limitations(skill_dir, entry["agentMetadata"]) if provider in providers]
    if configuration.value(ENVIRONMENT_CONFLICTS_ENABLED_KEY):
        report["environment"] = parity.environment_variables(plan.get("packToolDeclarations", []), project_root)
    if configuration.value(CI_JOB_CONFLICTS_ENABLED_KEY):
        block_destinations = {block["destination"] for block in plan.get("blocks", []) if block.get("content")}
        report["ciJobs"] = parity.duplicated_ci_jobs(project_root, plan["entries"], block_destinations)
    return report


def competing_skills_report(arguments, plan, catalog, configuration):
    """The AI review of the skills that compete for the same request, or None when it is off."""
    if not configuration.value(COMPETING_SKILLS_ENABLED_KEY) or not configuration.value(REVIEWS_ENABLED_KEY):
        conflicts_review.record_pending(arguments.project, [], check=skill_overlap.CHECK)
        return None
    if not conflicts_review.engine_can_review(ENGINE_SKILL_DIRECTORY):
        return None
    module = review_cache_module()
    directions, texts = skill_overlap.skill_pairs(arguments.project, plan["entries"], catalog, is_pack_profile,
                                                  module.normalized_text)
    if not directions:
        conflicts_review.record_pending(arguments.project, [], check=skill_overlap.CHECK)
        return None
    use_provider = not arguments.offline and os.environ.get("AGENT_READY_SETUP_REVIEW_MODE") != "1"
    settings = {"enabled": True, "cache": configuration.value(REVIEWS_CACHE_KEY),
                "ttl": configuration.value(REVIEWS_TTL_KEY), "commit": configuration.value(REVIEWS_COMMIT_KEY)}
    check = skill_overlap.reviewer(conflicts_review.load_harness_review(ENGINE_SKILL_DIRECTORY))
    report = conflicts_review.review_conflicts(arguments.project, ENGINE_SKILL_DIRECTORY, module, arguments.provider,
                                               directions, texts, bash_executable(), use_provider, settings,
                                               publish=arguments.format == "protected", check=check,
                                               pending_directions=(skill_overlap.DIRECTION_SKILLS,))
    # The skills an apply brings are not on disk yet: all their findings, decided ones included, wait
    # here, so agent-ready review can accept or dismiss one before the apply and keep that decision.
    conflicts_review.record_pending(arguments.project, report.pop("pending", []), check=skill_overlap.CHECK)
    return report


def competing_skills_lines(report):
    """The skills that compete, with the requests both take and how they differ."""
    lines = []
    if not report:
        return lines
    module = review_cache_module()
    for finding in report["findings"]:
        requests = "; ".join(f'"{request}"' for request in finding.get("lines", []))
        lines.append(f"  {module.finding_line(finding)} (competing skills"
                     f"{': ' + requests if requests else ''})")
    if report.get("unchecked"):
        lines.append(f"  Competing skills: {report['unchecked']} pair(s) not reviewed ({report['reason']})")
    return lines


def print_competing_skills(report):
    """Print the lines of competing_skills_lines."""
    for line in competing_skills_lines(report):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def competing_tools_lines(findings):
    """One line per pair of tools that give the same capability."""
    lines = []
    kinds = {pack_tools.TOOL_CLI: "CLI", pack_tools.TOOL_MCP_SERVER: "MCP server"}
    for finding in findings:
        first, second = finding["tools"]
        lines.append(f"  ~ {kinds[first['type']]} {first['name']} ({first['profile']}) and {kinds[second['type']]} "
                     f"{second['name']} ({second['profile']}) both provide {', '.join(finding['capabilities'])}: the "
                     f"agent picks either; keep one, or declare complements if they go together")
    return lines


def print_competing_tools(findings):
    """Print the lines of competing_tools_lines."""
    for line in competing_tools_lines(findings):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


# The order in which plan names what each provider sees.
PROVIDER_VIEW_ORDER = (parity.PROVIDER_CLAUDE, parity.PROVIDER_CODEX, parity.PROVIDER_ANTIGRAVITY)
PROVIDER_VIEW_NAMES = {parity.PROVIDER_CLAUDE: "Claude Code", parity.PROVIDER_CODEX: "Codex",
                       parity.PROVIDER_ANTIGRAVITY: "Antigravity"}


def provider_view_text(provider, view):
    """What one provider sees, as a clause of the Providers line of plan."""
    name = PROVIDER_VIEW_NAMES[provider]
    if provider == parity.PROVIDER_CLAUDE:
        return (f"{name} sees {view['rules']} rules ({view['rulesForPathsOnly']} only for their paths), "
                f"{view['skills']} skills, {view['subagents']} subagents and {view['commands']} commands")
    return f"{name} sees {view['rules']} rules in AGENTS.md, {view['skills']} skills and {view['subagents']} subagents"


def parity_report_lines(report):
    """What each provider sees, and one line per hook, variable or CI job that collides."""
    lines = []
    views = report.get("views")
    if views:
        lines.append("Providers: " + "; ".join(provider_view_text(provider, views[provider])
                                               for provider in PROVIDER_VIEW_ORDER if provider in views))
    for limitation in report.get("agentLimitations", []):
        lines.append(f"  ~ {limitation['agent']}: {limitation['note']} ({limitation['provider']})")
    for rule in report.get("antigravityDropped", []):
        lines.append(f"  ~ Antigravity drops {rule['path']} ({rule['profile']}): {rule['problem']}; start it with a "
                     f"frontmatter with trigger: always_on, or trigger: glob and globs: for some files")
    for difference in report.get("hookDifferences", []):
        lines.append(f"  ~ {difference['provider']} runs the {difference['event']} hook `{difference['command']}` "
                     f"({difference['file']}) and {difference['missing']} does not")
    for variable in report.get("environment", []):
        profiles = ", ".join(variable["profiles"])
        if variable.get("sources"):
            lines.append(f"  ~ variable {variable['name']} is asked by the sources {', '.join(variable['sources'])} "
                         f"({profiles}): check they mean the same")
        else:
            lines.append(f"  ~ variable {variable['name']} ({profiles}) is already listed in {variable['file']}: "
                         "check the project uses it for the same")
    for job in report.get("ciJobs", []):
        lines.append(f"  ~ {job['file']} already runs the Agent Ready check; the managed {', '.join(job['managed'])} "
                     "runs it again")
    return lines


def print_parity_report(report):
    """Print the lines of parity_report_lines."""
    for line in parity_report_lines(report):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def settings_conflicts_lines(report):
    """One line per permission, hook or formatter that collides across the layers."""
    lines = []
    for conflict in report.get("permissions", []):
        lines.append(f"  ! permission {conflict['pattern']}: allowed in {', '.join(conflict['allow'])} and denied in "
                     f"{', '.join(conflict['deny'])}; Claude Code applies the deny")
    for hook in report.get("duplicatedHooks", []):
        lines.append(f"  ~ {hook['provider']} hook {hook['event']} `{hook['command']}` is registered in "
                     f"{' and '.join(hook['files'])}: it runs once per registration")
    for clash in report.get("formatters", []):
        first, second = clash["hooks"]
        lines.append(f"  ~ {clash['provider']} {clash['event']} runs two formatters that can rewrite the same files: "
                     f"{first['formatter']} ({first['file']}) and {second['formatter']} ({second['file']})")
    return lines


def print_settings_conflicts(report):
    """Print the lines of settings_conflicts_lines."""
    for line in settings_conflicts_lines(report):
        write_line(paint(line, "warning", sys.stdout) if line.lstrip().startswith(("!", "~")) else line)


def project_owned_rules(project_root, managed_destinations):
    """{relative path: text} of the rules in .agents/rules that no profile manages, now or before."""
    rules_root = os.path.join(project_root, ".agents", "rules")
    rules = {}
    for relative_path, absolute_path in (walk_files(rules_root) if os.path.isdir(rules_root) else []):
        if (not relative_path.endswith(".md") or is_link(absolute_path)
                or RULES_DESTINATION_PREFIX + relative_path in managed_destinations):
            continue
        with open(absolute_path, encoding="utf-8", errors="replace") as rule_file:
            rules[relative_path] = rule_file.read()
    return rules


def projected_agents_md(project_root, skill_dir, catalog, plan, project_rules):
    """(text, {profile: bytes of its section}) of AGENTS.md after the apply, without writing it."""
    with tempfile.TemporaryDirectory(prefix="agent-ready-context.") as work_root:
        # Only the project's own rules: the ones the apply retires are gone when it renders the block.
        rules_copy = os.path.join(work_root, "project-rules")
        for relative_path, rule_text in project_rules.items():
            destination = os.path.join(rules_copy, relative_path)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(destination, "w", encoding="utf-8", newline="") as rule_file:
                rule_file.write(rule_text)
        stack_root = os.environ.get("AGENT_READY_SETUP_STACK_DIR") or compose_stack_directory(
            skill_dir, catalog, plan["profiles"], os.path.join(work_root, "stack"))
        current = current_instructions(project_root, skill_dir)
        project_rules_root = rules_copy if project_rules else None
        if current is not None and extract_managed_block(current) is not None:
            rendered = render_instructions(skill_dir, catalog, stack_root, project_rules_root, managed_block_only=True)
            text = current.replace(extract_managed_block(current), extract_managed_block(rendered or "") or "", 1)
        elif current is not None:
            # Without a block yet, the instruction review adds it after the project's content.
            rendered = render_instructions(skill_dir, catalog, stack_root, project_rules_root, managed_block_only=True)
            text = current.rstrip("\n") + "\n\n" + (rendered or "")
        else:
            text = render_instructions(skill_dir, catalog, stack_root, project_rules_root, managed_block_only=False) or ""
    destination = managed_blocks.INSTRUCTION_SECTIONS_DESTINATION
    sections_by_profile = {}
    for block in plan.get("blocks", []):
        if block["destination"] != destination or block.get("action") == ACTION_CONFLICT:
            continue
        try:
            if block.get("content") is None:
                text = managed_blocks.without_block(text, destination, block["id"])
                continue
            text = managed_blocks.with_block(text, destination, block["id"], block["content"])
            # The whole section, markers included, whatever the file held before.
            size = text_bytes(managed_blocks.with_block("", destination, block["id"], block["content"]))
            sections_by_profile[block["profile"]] = sections_by_profile.get(block["profile"], 0) + size
        except managed_blocks.MarkerError:
            continue
    return text, sections_by_profile


def current_instructions(project_root, skill_dir):
    """The instructions the apply starts AGENTS.md from, or None for a new one.

    The file conflicts_review.project_instructions finds, the same discovery as the instruction
    normalization: AGENTS.md, or a root CLAUDE.md (or its only case variant) that is not the proxy.
    """
    name = conflicts_review.project_instructions(project_root, skill_dir)
    if name is None:
        return None
    with open(os.path.join(project_root, name), encoding="utf-8", errors="replace") as instructions_file:
        return instructions_file.read()


def largest_profiles(bytes_by_profile):
    """The profiles that add the most bytes, largest first."""
    ordered = sorted(bytes_by_profile.items(), key=lambda item: (-item[1], item[0]))[:CONTEXT_LARGEST_PROFILES]
    return [{"profile": profile, "bytes": size} for profile, size in ordered]


def print_context_budget(context):
    """The context the selection adds to every session, and a warning when it passes the threshold."""
    agents, rules = context["agentsMd"], context["rulesLoadedAtStart"]
    write_line(f"Context at the start of a session: AGENTS.md ~{agents['bytes']} bytes; {rules['files']} rules "
               f"without paths: ~{rules['bytes']} bytes; MCP servers: {context['mcpServers']}")
    if agents["exceeded"]:
        write_line(paint(f"  ! AGENTS.md passes {agents['limitBytes']} bytes ({CONTEXT_BUDGET_BYTES_KEY}): Codex cuts the "
                         f"combined AGENTS.md there.{largest_suffix(agents['largest'])} Move content to rules or skills.",
                         "warning", sys.stdout))
    if rules["exceeded"]:
        write_line(paint(f"  ! The rules without paths pass {rules['limitBytes']} bytes ({CONTEXT_BUDGET_RULES_BYTES_KEY}): "
                         f"Claude loads them in every session.{largest_suffix(rules['largest'])} Give them paths: or move "
                         "them to skills.", "warning", sys.stdout))


def largest_suffix(largest):
    """' Largest: a (n), b (m).' for a warning, or nothing when no profile adds to it."""
    if not largest:
        return ""
    return " Largest: " + ", ".join(f"{item['profile']} ({item['bytes']})" for item in largest) + "."


def structural_conflicts(project_root, skill_dir, plan, catalog, configuration, with_context=True, with_machine=True):
    """The checks of the profiles that need no AI, on a plan: what plan, conflicts and check report.

    ``with_context`` adds the context budget, which only informs: status leaves it out.
    ``with_machine`` False leaves out what comes from this machine (shadowing, the user's servers and
    settings): a pack check runs on its author's machine, not on a consumer's.
    """
    report = {}
    if with_context and configuration.value(CONTEXT_BUDGET_ENABLED_KEY):
        report["context"] = context_budget(project_root, skill_dir, catalog, plan, configuration)
    if with_machine:
        report["machine"] = machine_report(project_root, plan, configuration)
    if configuration.value(REPO_REALITY_ENABLED_KEY):
        report["repoReality"] = repo_reality_report(project_root, skill_dir, plan)
    if configuration.value(RULES_ENABLED_KEY):
        report["ruleKeys"] = rule_key_report(project_root, plan)
    report["parity"] = parity_report(project_root, skill_dir, plan, configuration, with_user=with_machine)
    if configuration.value(COMPETING_TOOLS_ENABLED_KEY):
        report["competingTools"] = pack_tools.competing_tools(plan.get("packToolDeclarations", []), catalog)
    report["settingsConflicts"] = settings_conflicts.report(
        project_root, skill_dir, configuration.value(HOOK_CONFLICTS_ENABLED_KEY),
        configuration.value(PERMISSION_CONFLICTS_ENABLED_KEY), with_user=with_machine)
    return report


def structural_conflict_lines(report):
    """One line per structural conflict. What only informs is left out: the context budget, what each
    provider sees, the servers left to the user and an assumption the catalog cannot check."""
    lines = machine_report_lines({"shadowed": (report.get("machine") or {}).get("shadowed", [])})
    lines += repo_reality_lines([finding for finding in report.get("repoReality", []) if not finding.get("unknown")])
    lines += rule_key_lines(report.get("ruleKeys", []))
    lines += settings_conflicts_lines(report.get("settingsConflicts") or {})
    lines += parity_report_lines({key: value for key, value in (report.get("parity") or {}).items() if key != "views"})
    lines += competing_tools_lines(report.get("competingTools") or [])
    return lines
