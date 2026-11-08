"""agent-ready review: the findings of the AI reviews and the decisions of the team about them.

The findings come from the local review cache and the decisions from the versioned
.agents/agent-ready.reviews.json, both through review-cache.py, the same module the hooks use.
Accepting or dismissing a finding needs a reason and silences only that finding; the other
findings of the same pair keep showing.
"""

import subprocess
import sys

from agent_ready_cli_common import CLI_NAME, EXIT_OK, UsageError, engine
from agent_ready_common import StateError, serialize_json

# The words of each decision as the CLI prints them.
DECISION_VERBS = {"accept": "accepted", "dismiss": "dismissed"}
UNKNOWN_DECIDER = "unknown"


def review_module():
    return engine().review_cache_module()


def current_review(project_root):
    """(findings, decisions) of the repository; a decisions file that cannot be read stops the command."""
    try:
        findings, decisions, _, _ = engine().review_findings(project_root, strict=True)
    except review_module().DecisionsError as decisions_error:
        raise StateError(f"{decisions_error}; fix it or remove it before deciding on findings") from decisions_error
    return findings, decisions


def update_decisions(project_root, change):
    """Apply ``change`` to the decisions under their lock, so two sessions never lose each other's decision."""
    module = review_module()
    try:
        return module.Decisions(project_root).update(change)
    except module.DecisionsError as decisions_error:
        raise StateError(f"{decisions_error}; fix it or remove it before deciding on findings") from decisions_error
    except (OSError, module.CacheLockTimeout) as write_error:
        raise StateError(f"could not write {module.DECISIONS_RELATIVE_PATH}: {write_error}") from write_error


def decider(project_root):
    """Who decides: the Git user of the repository, as a commit would name them."""
    completed = subprocess.run(["git", "config", "user.name"], cwd=project_root, capture_output=True,
                               encoding="utf-8", errors="replace", check=False)
    return completed.stdout.strip() or UNKNOWN_DECIDER


def command_review_list(arguments):
    """Every current finding with its id and status, and the decisions that no finding uses anymore."""
    module = review_module()
    findings, decisions = current_review(arguments.project_root)
    used = {finding["id"] for finding in findings}
    unused = {identifier: decision for identifier, decision in sorted(decisions.items()) if identifier not in used}
    if arguments.json:
        sys.stdout.write(serialize_json({"findings": findings, "unusedDecisions": unused}))
        return EXIT_OK
    if not findings and not unused:
        sys.stdout.write("No finding of the AI reviews in the cache.\n")
        return EXIT_OK
    for finding in findings:
        label = finding["status"]
        names = " <-> ".join(finding.get("files", []))
        sys.stdout.write(f"{finding['id']}  {label:<10}  {finding.get('check')}  {names}\n    {finding.get('text', '')}\n")
        if finding.get("decision"):
            decision = finding["decision"]
            sys.stdout.write(f"    {decision.get('decision')} by {decision.get('by')} ({decision.get('scope')}): "
                             f"{decision.get('reason')}\n")
    if unused:
        sys.stdout.write("Decisions without a current finding (reset them when they no longer apply):\n")
        for identifier, decision in unused.items():
            sys.stdout.write(f"{identifier}  {module.Decisions(arguments.project_root).status(decision):<10}  "
                             f"{decision.get('text', '')}\n")
    return EXIT_OK


def command_review_decide(arguments):
    """accept or dismiss one finding by id, with a reason and a scope."""
    module = review_module()
    reason = " ".join(arguments.reason.split())
    if not reason:
        raise UsageError(f"--reason cannot be empty: say why the finding is {DECISION_VERBS[arguments.review_action]}")
    findings, _ = current_review(arguments.project_root)
    finding = next((candidate for candidate in findings if candidate["id"] == arguments.id), None)
    if finding is None:
        raise UsageError(f"no current finding has the id {arguments.id} (see {CLI_NAME} review list)")
    kind = DECISION_VERBS[arguments.review_action]
    decision = module.decision_for(finding, kind, reason, arguments.scope, decider(arguments.project_root),
                                   arguments.project_root)
    update_decisions(arguments.project_root, lambda decisions: dict(decisions, **{arguments.id: decision}))
    lasts = ("while its files do not change" if arguments.scope == module.SCOPE_CONTENT
             else f"for this pair until {CLI_NAME} review reset {arguments.id}")
    sys.stderr.write(f"{kind} {arguments.id}: {finding.get('text', '')}\n"
                     f"It stays quiet {lasts}. Commit {module.DECISIONS_RELATIVE_PATH} to share the decision.\n")
    return EXIT_OK


def command_review_reset(arguments):
    """Remove decisions, so their findings show again."""
    if not arguments.ids and not arguments.all:
        raise UsageError("name the ids to reset, or pass --all")
    if arguments.ids and arguments.all:
        raise UsageError("pass either ids or --all, not both")
    removed = []

    def without_reset(decisions):
        unknown = [identifier for identifier in arguments.ids if identifier not in decisions]
        if unknown:
            raise UsageError(f"no decision has the id {', '.join(unknown)} (see {CLI_NAME} review list)")
        removed.extend(sorted(decisions) if arguments.all else arguments.ids)
        return {identifier: decision for identifier, decision in decisions.items() if identifier not in removed}

    update_decisions(arguments.project_root, without_reset)
    sys.stderr.write(f"Reset {len(removed)} decision(s); their findings show again.\n")
    return EXIT_OK


def register(subparsers, new_subparser):
    """Add review list|accept|dismiss|reset to the CLI parser."""
    review = new_subparser(subparsers, "review", "List the findings of the AI reviews and decide on them.",
                           "  agent-ready review list\n  agent-ready review accept 3f9a1c2b7e --reason \"golfo mocks on purpose\"",
                           None, with_project=False)
    actions = review.add_subparsers(dest="review_action", metavar="<action>", required=True)
    listing = new_subparser(actions, "list", "Current findings with their id and status, read from the cache.",
                            "  agent-ready review list\n  agent-ready review list --json", command_review_list)
    listing.add_argument("--json", action="store_true", help="print the findings and the decisions as JSON")
    for name, summary in (("accept", "Accept a finding on purpose; it stays quiet while the decision holds."),
                          ("dismiss", "Dismiss a finding that is wrong; it stays quiet while the decision holds.")):
        action = new_subparser(actions, name, summary,
                               f"  agent-ready review {name} 3f9a1c2b7e --reason \"...\"\n"
                               f"  agent-ready review {name} 3f9a1c2b7e --reason \"...\" --scope pair", command_review_decide)
        action.add_argument("id", help="id of the finding, as review list and status print it")
        action.add_argument("--reason", required=True, help="why; it is saved with the decision")
        action.add_argument("--scope", choices=("content", "pair"), default="content",
                            help="content: until a file of the finding changes; pair: until it is reset (default: content)")
    reset = new_subparser(actions, "reset", "Remove decisions, so their findings show again.",
                          "  agent-ready review reset 3f9a1c2b7e\n  agent-ready review reset --all", command_review_reset)
    reset.add_argument("ids", nargs="*", metavar="id", help="ids of the decisions to remove")
    reset.add_argument("--all", action="store_true", help="remove every decision")
