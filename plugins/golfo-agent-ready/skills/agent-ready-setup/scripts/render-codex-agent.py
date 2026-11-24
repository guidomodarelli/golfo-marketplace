#!/usr/bin/env python3
"""Render a view of one subagent template: the native Codex subagent (.codex/agents/<name>.toml), or the
Markdown view of Antigravity (.agents/agents/<name>.md) or Claude Code (.claude/agents/<name>.md) of a
subagent that declares access or model-tier.

Internal helper of the Bash projections (bootstrap-asset-projection.sh and sync-marketplace.sh): they
write what it renders with sync_file, so the bytes are the ones the plan records (agent_ready_codex_agents,
agent_ready_agent_metadata). The mapping of access and model-tier is the one of assets/providers.json of
this skill. Exit codes: 0 rendered, 1 the template cannot become that view, 3 a Markdown view was asked of
a template without metadata (the canonical file, or its view, is projected as it is).
"""

import argparse
import os
import sys

# The rendering logic loads from this script's own directory, so both stay on one version.
SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIRECTORY)

import agent_ready_agent_metadata as agent_metadata  # noqa: E402
from agent_ready_codex_agents import render_codex_agent_file  # noqa: E402
from agent_ready_common import ProfileError, write_text_atomically  # noqa: E402

SKILL_DIRECTORY = os.path.dirname(SCRIPT_DIRECTORY)
NO_METADATA_STATUS = 3
VIEWS = (agent_metadata.VIEW_CODEX, agent_metadata.VIEW_ANTIGRAVITY, agent_metadata.VIEW_CLAUDE)


def render(view, source, name):
    """The text of the view, or None for a Markdown view of a template without metadata."""
    if view == agent_metadata.VIEW_CODEX:
        return render_codex_agent_file(source, name, SKILL_DIRECTORY)
    with open(source, encoding="utf-8", newline="") as template_file:
        return agent_metadata.render_view(SKILL_DIRECTORY, template_file.read(), f"agents/{name}", view)


def main():
    """Write the --view of --source (a file named --name under agents/) to --output."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--source", required=True, help="the subagent template (Markdown)")
    parser.add_argument("--name", required=True, help="its file name under agents/, such as test-reviewer.md")
    parser.add_argument("--output", required=True, help="where to write the view")
    parser.add_argument("--view", choices=VIEWS, default=agent_metadata.VIEW_CODEX, help="which view (default: codex)")
    arguments = parser.parse_args()
    try:
        text = render(arguments.view, arguments.source, arguments.name)
        if text is None:
            return NO_METADATA_STATUS
        write_text_atomically(arguments.output, text)
    except (OSError, ProfileError) as caught_error:
        print(f"ERROR: render-codex-agent: {arguments.source}: {caught_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
