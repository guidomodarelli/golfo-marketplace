#!/usr/bin/env python3
"""Render the native Codex subagent (.codex/agents/<name>.toml) of one subagent template.

Internal helper of the Bash projections (bootstrap-asset-projection.sh and sync-marketplace.sh): they
write the TOML it renders with sync_file, so the bytes are the ones the plan records
(agent_ready_codex_agents). Exit codes: 0 rendered, 1 the template cannot become a Codex subagent.
"""

import argparse
import os
import sys

# The rendering logic loads from this script's own directory, so both stay on one version.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_ready_codex_agents import render_codex_agent_file  # noqa: E402
from agent_ready_common import ProfileError, write_text_atomically  # noqa: E402


def main():
    """Write the TOML of --source (a file named --name under agents/) to --output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="the subagent template (Markdown)")
    parser.add_argument("--name", required=True, help="its file name under agents/, such as test-reviewer.md")
    parser.add_argument("--output", required=True, help="where to write the TOML")
    arguments = parser.parse_args()
    try:
        write_text_atomically(arguments.output, render_codex_agent_file(arguments.source, arguments.name))
    except (OSError, ProfileError) as caught_error:
        print(f"ERROR: render-codex-agent: {arguments.source}: {caught_error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
