"""The subagents a selection names but does not install: a structural conflict, found without any model.

An orchestrating skill or command keeps its roster as a table of `.agents/agents/<name>.md` files
(`<stack>-review-pr` in the official pack, references/profile-packs.md, «Subagente o skill»). When a
roster names a subagent that no selected profile publishes and the project does not have, the orchestrator
dispatches to nothing, so agent-ready plan, conflicts, check and conflicts --pack report it.
"""

import os
import re

from agent_ready_actions import ACTION_RETIRE

SHARED_PREFIX = ".agents/"
AGENTS_PREFIX = ".agents/agents/"
MARKDOWN_SUFFIX = ".md"
# A subagent named by its path, as a roster names it: .agents/agents/<kebab-case name>.md.
AGENT_REFERENCE = re.compile(r"\.agents/agents/([a-z0-9]+(?:-[a-z0-9]+)*)\.md")


def installed_agents(project_root, plan):
    """The names of the subagents in .agents/agents/ after the apply: the managed ones and the project's own."""
    retired = {entry["destination"] for entry in plan["entries"] if entry["action"] == ACTION_RETIRE}
    names = {entry["destination"][len(AGENTS_PREFIX):-len(MARKDOWN_SUFFIX)] for entry in plan["entries"]
             if entry["sha256"] and entry["destination"].startswith(AGENTS_PREFIX)
             and entry["destination"].endswith(MARKDOWN_SUFFIX)}
    agents_directory = os.path.join(project_root, *AGENTS_PREFIX.rstrip("/").split("/"))
    if os.path.isdir(agents_directory):
        for file_name in os.listdir(agents_directory):
            if file_name.endswith(MARKDOWN_SUFFIX) and AGENTS_PREFIX + file_name not in retired:
                names.add(file_name[:-len(MARKDOWN_SUFFIX)])
    return names


def missing_agents(project_root, plan):
    """[{file, profile, agent}] of each subagent a managed file of .agents/ names and the selection does not
    install, in the order of the plan."""
    installed = installed_agents(project_root, plan)
    missing = []
    for entry in plan["entries"]:
        destination = entry["destination"]
        if not entry["sha256"] or not destination.startswith(SHARED_PREFIX) or not destination.endswith(MARKDOWN_SUFFIX):
            continue
        with open(entry["sourcePath"], encoding="utf-8", errors="replace") as source_file:
            text = source_file.read()
        for agent in sorted(set(AGENT_REFERENCE.findall(text)) - installed):
            missing.append({"file": destination, "profile": entry["profile"], "agent": agent})
    return missing


def missing_agent_lines(missing):
    """One line per subagent a file names and the selection does not install."""
    return [f"  ! {reference['file']} ({reference['profile']}) names {AGENTS_PREFIX}{reference['agent']}{MARKDOWN_SUFFIX}, "
            "which no selected profile publishes and the project does not have" for reference in missing]
