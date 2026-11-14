"""Terminal output of the agent-ready-setup engine: one palette, and color only where the stream supports it.

NO_COLOR, TERM=dumb and a stream that is not a terminal (a pipe, a file) get plain text.
"""

import os
import sys

ANSI_RESET = "\033[0m"
ANSI_COLORS = {
    "create": "\033[32m",
    "update": "\033[36m",
    "adopt": "\033[36m",
    "conflict": "\033[31m",
    "retire": "\033[33m",
    "retire-conflict": "\033[31m",
    "heading": "\033[1m",
    "muted": "\033[2m",
    "ok": "\033[32m",
    "warning": "\033[33m",
    "error": "\033[31m",
}


def colors_enabled(stream):
    """Return True when ANSI colors are safe on ``stream``."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def paint(text, color_key, stream):
    """Wrap ``text`` in the palette color when the stream supports it."""
    if not colors_enabled(stream):
        return text
    return f"{ANSI_COLORS[color_key]}{text}{ANSI_RESET}"


def write_line(text="", stream=None):
    """Print one line to the given stream (stdout by default)."""
    target = stream or sys.stdout
    target.write(text + "\n")
