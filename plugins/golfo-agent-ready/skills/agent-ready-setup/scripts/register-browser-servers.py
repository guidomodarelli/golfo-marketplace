#!/usr/bin/env python3
"""Register or update portable browser MCP servers from the existing installation.

Never installs packages, Chromium, or the TOML editor. SessionStart sync runs it so
managed registrations stay current without a full bootstrap.
"""

import argparse
import importlib.util
from pathlib import Path
import sys

# Shared browser setup logic loads from this script's own directory so both stay on one version.
BROWSER_SETUP_PATH = Path(__file__).resolve().with_name("setup-browser-tools.py")


def load_browser_setup():
    """Load the shared browser setup module, whose file name is not importable directly."""
    specification = importlib.util.spec_from_file_location("browser_setup", BROWSER_SETUP_PATH)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def main():
    """Register project servers from the current launchers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    return load_browser_setup().register_from_installation(arguments.project.absolute())


if __name__ == "__main__":
    sys.exit(main())
