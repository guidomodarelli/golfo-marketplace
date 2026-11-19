#!/usr/bin/env python3
"""Remove the portable browser MCP servers that agent-ready-setup registered in a project.

Only entries whose command points into the per-user browser-tools directory go away;
servers the project defined stay. `agent-ready remove` runs it. Never installs anything.
"""

import argparse
import importlib.util
from pathlib import Path
import sys

# Shared browser setup logic loads from this script's own directory so both stay on one version.
BROWSER_SETUP_PATH = Path(__file__).resolve().with_name("setup-browser-tools.py")
# The browser setup reads TOML with tomllib, which Python ships since 3.11.
MINIMUM_PYTHON = (3, 11)


def load_browser_setup():
    """Load the shared browser setup module, whose file name is not importable directly."""
    specification = importlib.util.spec_from_file_location("browser_setup", BROWSER_SETUP_PATH)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main():
    """Unregister the managed servers; prints "<removed|edited><TAB><path>" per file that changed."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--project", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    if sys.version_info < MINIMUM_PYTHON:
        print("Browser servers kept: removing them needs Python 3.11+; delete the entries that point into "
              "agent-ready-setup/browser-tools from .mcp.json and .codex/config.toml by hand.", file=sys.stderr)
        return 1
    browser_setup = load_browser_setup()
    try:
        changed = browser_setup.unregister_servers(arguments.project.absolute())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Browser servers partly kept: {error}", file=sys.stderr)
        return 1
    for outcome, relative_path in changed:
        print(f"{outcome}\t{relative_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
