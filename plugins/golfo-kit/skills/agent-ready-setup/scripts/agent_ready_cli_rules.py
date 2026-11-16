"""agent-ready rules: list, show and lint the atomic rules of a repository or of a content pack.

Without --path the command reads the rules of the repository, under .agents/rules/. With --path it
reads the files given, or every .md under a rules/ directory of each directory given, which is how
the author of a pack lints it from its own checkout, without a consumer repository.
"""

import os
import sys

import agent_ready_rules
from agent_ready_cli_common import CLI_NAME, EXIT_FAILED, EXIT_OK, UsageError, find_repository_root
import agent_ready_common
from agent_ready_common import StateError, serialize_json
from agent_ready_config import resolve_configuration

PROJECT_RULES_RELATIVE_PATH = ".agents/rules"
STATEMENT_WARN_CHARS_KEY = "rules.statementWarnChars"
MAX_STATEMENT_CHARS_KEY = "rules.maxStatementChars"
RULES_ENABLED_KEY = "rules.enabled"
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
    configuration = resolve_configuration(agent_ready_common.find_repository_root(arguments.project))
    warn_chars = configuration.value(STATEMENT_WARN_CHARS_KEY)
    max_chars = configuration.value(MAX_STATEMENT_CHARS_KEY)
    if warn_chars > max_chars:
        raise UsageError(f"{STATEMENT_WARN_CHARS_KEY} ({warn_chars}) is over {MAX_STATEMENT_CHARS_KEY} ({max_chars})")
    return configuration.value(RULES_ENABLED_KEY), warn_chars, max_chars


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


def register(subparsers, new_subparser):
    """Add rules list|show|lint to the CLI parser."""
    rules = new_subparser(subparsers, "rules", "List, show and lint the atomic rules.",
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
    )
    for name, summary, examples, handler in commands:
        action = new_subparser(actions, name, summary, examples, handler)
        if name == "show":
            action.add_argument("id", help="id of the rule, as rules list prints it")
        action.add_argument("--path", action="append",
                            help="a rule file, or a directory whose rules/ directories are read; repeatable "
                                 f"(default: {PROJECT_RULES_RELATIVE_PATH} of the repository)")
        action.add_argument("--json", action="store_true", help="print the result as JSON")
        # --path works without a consumer repository: the command finds one only when it needs it.
        action.set_defaults(needs_repository=False)
