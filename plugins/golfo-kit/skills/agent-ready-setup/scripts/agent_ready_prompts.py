"""Questions for the subcommands that can ask, drawn on stderr with the standard library.

A subcommand asks only when a person is there: stdin and stderr are terminals, --no-input
was not passed, ``CI`` is not set and ``TERM`` is not ``dumb``. Each question validates
with the same function as its flag, so asking and passing flags give the same result, and
nothing is written until the last answer. Ctrl+C and a closed stdin cancel.
"""

import os
import re
import shlex
import sys

CONTINUOUS_INTEGRATION_VARIABLE = "CI"
CONTINUOUS_INTEGRATION_OFF_VALUES = ("", "0", "false")
DUMB_TERMINAL = "dumb"
YES_ANSWERS = ("y", "yes", "s", "si", "sí")
NO_ANSWERS = ("n", "no")
WINDOWS_SAFE_TOKEN = re.compile(r"^[\w@+=:,./\\-]+$")


class Cancelled(Exception):
    """The person pressed Ctrl+C or closed stdin; nothing was written."""


def can_prompt(no_input):
    """True only when a person can answer on this terminal."""
    continuous_integration = os.environ.get(CONTINUOUS_INTEGRATION_VARIABLE, "").lower()
    return (
        sys.stdin.isatty()
        and sys.stderr.isatty()
        and not no_input
        and continuous_integration in CONTINUOUS_INTEGRATION_OFF_VALUES
        and os.environ.get("TERM") != DUMB_TERMINAL
    )


def read_answer(question):
    """Draw the question on stderr and read one line; Ctrl+C or end of input cancel."""
    sys.stderr.write(question)
    sys.stderr.flush()
    try:
        return input().strip()
    except (KeyboardInterrupt, EOFError) as cancelled:
        sys.stderr.write("\n")
        raise Cancelled() from cancelled


def ask_text(question, default, validate):
    """Ask until the answer is valid; an empty answer takes the default."""
    while True:
        answer = read_answer(f"{question} [{default}]: " if default else f"{question}: ") or default
        error = validate(answer)
        if error is None:
            return answer
        sys.stderr.write(f"  {error}\n")


def ask_confirmation(question, default):
    """Ask yes or no; an empty answer takes the default."""
    hint = "Y/n" if default else "y/N"
    while True:
        answer = read_answer(f"{question} [{hint}]: ").lower()
        if not answer:
            return default
        if answer in YES_ANSWERS:
            return True
        if answer in NO_ANSWERS:
            return False
        sys.stderr.write("  answer y or n\n")


def quote_for_shell(value):
    """Quote one argument for the shell of this platform."""
    if sys.platform != "win32":
        return shlex.quote(value)
    if WINDOWS_SAFE_TOKEN.match(value):
        return value
    escaped = re.sub(r'(\\*)"', r'\1\1\\"', value)
    escaped = re.sub(r"(\\+)$", r"\1\1", escaped)
    return f'"{escaped}"'


def equivalent_command(arguments):
    """The command that reproduces what the person answered, without a single question."""
    return " ".join(quote_for_shell(argument) for argument in arguments)
