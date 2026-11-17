"""agent-ready rules: list, show, lint, impact and graph of the atomic rules of a repository or of a pack.

Without --path the command reads the rules of the repository, under .agents/rules/. With --path it
reads the files given, or every .md under a rules/ directory of each directory given, which is how
the author of a pack lints it from its own checkout, without a consumer repository. impact and graph
also read the skills next to the rules (.agents/skills/, or the skills/ directories under --path) for
the rules they cite.
"""

import os
import sys

import agent_ready_rule_graph
import agent_ready_rules
from agent_ready_cli_common import CLI_NAME, EXIT_FAILED, EXIT_OK, UsageError, find_repository_root
import agent_ready_common
from agent_ready_common import StateError, serialize_json
from agent_ready_config import resolve_configuration
from agent_ready_options import RULES_ENABLED_KEY
from agent_ready_workspaces import WORKSPACE_RULES_DIRECTORY
from agent_ready_lockfile import read_lock
import agent_ready_rule_overrides as rule_overrides

PROJECT_RULES_RELATIVE_PATH = ".agents/rules"
PROJECT_SKILLS_RELATIVE_PATH = ".agents/skills"
STATEMENT_WARN_CHARS_KEY = "rules.statementWarnChars"
MAX_STATEMENT_CHARS_KEY = "rules.maxStatementChars"
LISTED_STATEMENT_CHARS = 100
ELLIPSIS = "…"


def targets(arguments):
    """(rule files, root their paths are shown from) of the command."""
    if arguments.path:
        missing = [path for path in arguments.path if not os.path.exists(path)]
        if missing:
            raise UsageError(f"--path {missing[0]} does not exist")
        root = os.path.abspath(".")
        files = []
        for path in arguments.path:
            files.extend(agent_ready_rules.rule_files(os.path.abspath(path)))
        return sorted(set(files)), root
    root = find_repository_root(arguments.project)
    return agent_ready_rules.rule_files(os.path.join(root, PROJECT_RULES_RELATIVE_PATH)), root


def citations(arguments, root):
    """The rule citations of the skills of the targets of the command (agent_ready_rule_graph)."""
    if arguments.path:
        files = sorted({path for target in arguments.path
                        for path in agent_ready_rule_graph.skill_files(os.path.abspath(target))})
    else:
        files = agent_ready_rule_graph.skill_files(os.path.join(root, PROJECT_SKILLS_RELATIVE_PATH))
    try:
        return agent_ready_rule_graph.skill_citations(files, root)
    except OSError as read_error:
        raise StateError(f"could not read a skill file: {read_error}") from read_error


def read(arguments):
    """(rules, parse findings, root) of the targets of the command."""
    files, root = targets(arguments)
    try:
        rules, findings = agent_ready_rules.read_rules(files, root)
    except (OSError, UnicodeDecodeError) as read_error:
        raise StateError(f"could not read a rule file: {read_error}") from read_error
    return rules, findings, root


def limits(arguments):
    """(enabled, warn, max) of the configuration of --project's repository, or the defaults outside one."""
    return configured_limits(resolve_configuration(agent_ready_common.find_repository_root(arguments.project)))


def configured_limits(configuration):
    """(enabled, warn, max) of the rules module of a configuration."""
    warn_chars = configuration.value(STATEMENT_WARN_CHARS_KEY)
    max_chars = configuration.value(MAX_STATEMENT_CHARS_KEY)
    if warn_chars > max_chars:
        raise UsageError(f"{STATEMENT_WARN_CHARS_KEY} ({warn_chars}) is over {MAX_STATEMENT_CHARS_KEY} ({max_chars})")
    return configuration.value(RULES_ENABLED_KEY), warn_chars, max_chars


def rule_set_of(project_root, path, lock):
    """(workspace, source) of a rule file of .agents/rules/: the rules of one set load together.

    The root and each workspace (.agents/rules/workspaces/<path>/, with any folder of its rules under it)
    load apart, and two sources may publish the same id, as their rules are named <source>:<id>. A file
    the lock records takes its profile's source and workspace; any other file is the project's.
    """
    destination = os.path.relpath(path, project_root).replace(os.sep, "/")
    entry = ((lock or {}).get("assets") or {}).get(destination) or {}
    source = rule_overrides.rule_source(entry["profile"]) if entry.get("profile") else rule_overrides.PROJECT_RULE_SOURCE
    if entry.get("workspace"):
        return entry["workspace"], source
    relative = os.path.relpath(path, os.path.join(project_root, PROJECT_RULES_RELATIVE_PATH)).replace(os.sep, "/")
    if not relative.startswith(f"{WORKSPACE_RULES_DIRECTORY}/"):
        return "", source
    inside = relative[len(WORKSPACE_RULES_DIRECTORY) + 1:]
    # The longest workspace of the lock that holds the file; without one, the folder of the file.
    workspaces = sorted((lock or {}).get("workspaces") or {}, key=len, reverse=True)
    owner = next((workspace for workspace in workspaces if inside.startswith(f"{workspace}/")), None)
    return owner or os.path.dirname(inside), source


def adopted_rule_errors(project_root, configuration):
    """The lint errors of the rule files of .agents/rules/ that already use atomic rules, for agent-ready check.

    A file with no rule marker is prose its project has not migrated: its bullets are not reported, so
    adopting the format is a decision per file and never a failing CI on a repository that did not take it.
    """
    enabled, warn_chars, max_chars = configured_limits(configuration)
    if not enabled:
        return []
    lock = read_lock(project_root)
    rules_root = os.path.join(project_root, PROJECT_RULES_RELATIVE_PATH)
    sets = {}
    for path in agent_ready_rules.rule_files(rules_root):
        sets.setdefault(rule_set_of(project_root, path, lock), []).append(path)
    parsed = {}
    for rule_set, files in sets.items():
        try:
            parsed[rule_set] = agent_ready_rules.read_rules(files, project_root)
        except (OSError, UnicodeDecodeError) as read_error:
            raise StateError(f"could not read a rule file: {read_error}") from read_error
    # A rule another one replaces with overrides=<source>:<id> is not projected, but the rules that
    # require it keep the reference (references/atomic-rules.md, «Una rule reemplazada»).
    replaced = {}
    for rules, _ in parsed.values():
        for rule in rules:
            for target in rule.overrides:
                source, _, identifier = target.partition(rule_overrides.RULE_SOURCE_SEPARATOR)
                replaced.setdefault(source, set()).add(identifier)
    errors = []
    for (workspace, source), (rules, findings) in parsed.items():
        own_paths = {rule.path for rule in rules} | {finding.path for finding in findings}
        adopted = {rule.path for rule in rules} | {finding.path for finding in findings
                                                   if finding.code != agent_ready_rules.CODE_UNTAGGED_RULE}
        findings = [finding for finding in findings if finding.path in adopted]
        # A workspace loads the root's rules too: its rules are checked with the root's of their source,
        # and only the findings of its own files are reported, the root's being reported once, by the root.
        # The root's go first, so a workspace rule that repeats one of their ids is the one reported.
        together = (parsed.get(("", source), ([], []))[0] if workspace else []) + rules
        findings += [finding for finding in agent_ready_rules.lint_rules(together, warn_chars, max_chars,
                                                                         replaced.get(source, set()))
                     if finding.path in own_paths]
        errors += [finding for finding in findings if finding.level == agent_ready_rules.LEVEL_ERROR]
    return sorted(errors, key=lambda finding: (finding.path, finding.line, finding.code))


def shortened(text):
    return text if len(text) <= LISTED_STATEMENT_CHARS else text[:LISTED_STATEMENT_CHARS - 1] + ELLIPSIS


def command_rules_list(arguments):
    """Every rule with its id, key and place, or the full rules as JSON."""
    rules, _, _ = read(arguments)
    if arguments.json:
        sys.stdout.write(serialize_json({"rules": [rule.to_json() for rule in rules]}))
        return EXIT_OK
    if not rules:
        sys.stdout.write("No atomic rule found.\n")
        return EXIT_OK
    for rule in rules:
        key = f"  key={rule.key}" if rule.key else ""
        sys.stdout.write(f"{rule.id}{key}  {rule.path}:{rule.line}\n    {shortened(rule.statement)}\n")
    return EXIT_OK


def command_rules_show(arguments):
    """One rule by id: metadata, statement, exceptions, details and hash."""
    rules, _, _ = read(arguments)
    matches = [rule for rule in rules if rule.id == arguments.id]
    if not matches:
        raise StateError(f"no rule has the id {arguments.id} (see {CLI_NAME} rules list)")
    if arguments.json:
        sys.stdout.write(serialize_json({"rules": [rule.to_json() for rule in matches]}))
        return EXIT_OK
    for rule in matches:
        sys.stdout.write(f"{rule.id}  {rule.path}:{rule.line}\n")
        for label, value in (("key", rule.key), ("requires", ", ".join(rule.requires)),
                             ("paths", ", ".join(rule.paths)), ("overrides", ", ".join(rule.overrides)),
                             ("locked", "yes" if rule.locked else "")):
            if value:
                sys.stdout.write(f"  {label}: {value}\n")
        sys.stdout.write(f"  statement: {rule.statement}\n")
        for exception in rule.exceptions:
            sys.stdout.write(f"  except: {exception}\n")
        for detail in rule.details:
            sys.stdout.write(f"  detail: {detail}\n")
        sys.stdout.write(f"  hash: {rule.hash()}\n")
    return EXIT_OK


def command_rules_lint(arguments):
    """Atomicity, length and consistency of the rules; exits 1 when one finding is an error."""
    rules, findings, _ = read(arguments)
    enabled, warn_chars, max_chars = limits(arguments)
    if not enabled:
        sys.stderr.write(f"{RULES_ENABLED_KEY} is off: the rules were not linted.\n")
        return EXIT_OK
    findings = findings + agent_ready_rules.lint_rules(rules, warn_chars, max_chars)
    findings.sort(key=lambda finding: (finding.path, finding.line, finding.code))
    errors = sum(1 for finding in findings if finding.level == agent_ready_rules.LEVEL_ERROR)
    if arguments.json:
        sys.stdout.write(serialize_json({"rules": len(rules), "errors": errors,
                                         "warnings": len(findings) - errors,
                                         "findings": [finding.to_json() for finding in findings]}))
    else:
        for finding in findings:
            sys.stdout.write(finding.render() + "\n")
        sys.stdout.write(f"{len(rules)} rules, {errors} errors, {len(findings) - errors} warnings.\n")
    return EXIT_FAILED if errors else EXIT_OK


def place(item):
    return f"{item['path']}:{item['line']}"


def command_rules_impact(arguments):
    """What a change to one rule touches: the rules that require it, the ones that replace it and the
    skills that cite it."""
    rules, _, root = read(arguments)
    report = agent_ready_rule_graph.impact(rules, citations(arguments, root), arguments.id)
    if report is None:
        raise StateError(f"no rule has the id {arguments.id}, and no rule or skill names it "
                         f"(see {CLI_NAME} rules list)")
    if arguments.json:
        sys.stdout.write(serialize_json(report))
        return EXIT_OK
    where = ", ".join(place(rule) for rule in report["rules"]) or "not in this set: replaced, or of another source"
    sys.stdout.write(f"{report['id']}  ({where})\n")
    sections = (("required by", report["requiredBy"]), ("replaced by", report["replacedBy"]),
                ("cited by", report["citedBy"]))
    for label, items in sections:
        for item in items:
            described = f"{item['id']} ({place(item)})" if "id" in item else place(item)
            sys.stdout.write(f"  {label}: {described}\n")
    if not any(items for _, items in sections):
        sys.stdout.write("  nothing requires, replaces or cites it\n")
    return EXIT_OK


def command_rules_graph(arguments):
    """Every edge between the rules, and from the skills to the rules they cite."""
    rules, _, root = read(arguments)
    rule_graph = agent_ready_rule_graph.graph(rules, citations(arguments, root))
    if arguments.json:
        sys.stdout.write(serialize_json(rule_graph))
        return EXIT_OK
    for edge in rule_graph["edges"]:
        sys.stdout.write(f"{edge['from']} {edge['kind']} {edge['to']}  ({place(edge)})\n")
    sys.stdout.write(f"{len(rule_graph['nodes'])} rules, {len(rule_graph['edges'])} edges.\n")
    return EXIT_OK


def register(subparsers, new_subparser):
    """Add rules list|show|lint|impact|graph to the CLI parser."""
    rules = new_subparser(subparsers, "rules", "List, show, lint and trace the atomic rules.",
                          "  agent-ready rules list\n  agent-ready rules lint --path ../my-pack", None,
                          with_project=False)
    actions = rules.add_subparsers(dest="rules_action", metavar="<action>", required=True)
    commands = (
        ("list", "Every rule with its id, key and place.",
         "  agent-ready rules list\n  agent-ready rules list --json", command_rules_list),
        ("show", "One rule by id, with its metadata, exceptions and hash.",
         "  agent-ready rules show testing/unit-runner", command_rules_show),
        ("lint", "Check that each rule is atomic and short, and that the set is consistent.",
         "  agent-ready rules lint\n  agent-ready rules lint --path ../my-pack --json", command_rules_lint),
        ("impact", "What a change to one rule touches: rules that require or replace it, skills that cite it.",
         "  agent-ready rules impact testing/unit-runner\n  agent-ready rules impact golfo:testing/unit-runner --json",
         command_rules_impact),
        ("graph", "Every requires, overrides and skill citation between the rules.",
         "  agent-ready rules graph\n  agent-ready rules graph --path ../my-pack --json", command_rules_graph),
    )
    for name, summary, examples, handler in commands:
        action = new_subparser(actions, name, summary, examples, handler)
        if name in ("show", "impact"):
            action.add_argument("id", help="id of the rule, as rules list prints it"
                                + (", with or without its source" if name == "impact" else ""))
        action.add_argument("--path", action="append",
                            help="a rule file, or a directory whose rules/ directories are read; repeatable "
                                 f"(default: {PROJECT_RULES_RELATIVE_PATH} of the repository)")
        action.add_argument("--json", action="store_true", help="print the result as JSON")
        # --path works without a consumer repository: the command finds one only when it needs it.
        action.set_defaults(needs_repository=False)
