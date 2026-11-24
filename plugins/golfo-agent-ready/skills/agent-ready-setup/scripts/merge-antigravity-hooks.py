#!/usr/bin/env python3
"""Merge the managed group of the Antigravity hooks template into .agents/hooks.json.

Internal helper of the Bash projections (asset-sync-common.sh, sync_antigravity_hooks):

  merge-antigravity-hooks.py <template> <current>            the current hooks with the managed group
  merge-antigravity-hooks.py --remove <current>              the current hooks without the managed group

It prints the result on stdout, or nothing when no hook name is left; the caller writes it after checking
that the file did not change meanwhile. Exit codes: 0 printed, 1 the current file is not valid hooks, 2 the
arguments are wrong, 3 --remove found no managed group (the file stays as it is).
"""

import os
import sys

# The merge logic loads from this script's own directory, so both stay on one version.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent_ready_antigravity_hooks as antigravity_hooks  # noqa: E402

NOTHING_TO_REMOVE_STATUS = 3


def main(arguments):
    # Windows stdout defaults to CRLF and the locale code page; the generated JSON is LF UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    try:
        if arguments[:1] == ["--remove"] and len(arguments) == 2:
            current = antigravity_hooks.read(arguments[1])
            if antigravity_hooks.MANAGED_GROUP not in current:
                return NOTHING_TO_REMOVE_STATUS
            result = antigravity_hooks.without_managed(current)
        elif len(arguments) == 2:
            template, current = (antigravity_hooks.read(path) for path in arguments)
            result = antigravity_hooks.merged(current, template)
        else:
            print("usage: merge-antigravity-hooks.py <template> <current> | --remove <current>", file=sys.stderr)
            return 2
    except (OSError, antigravity_hooks.HooksError) as caught_error:
        print(f"Antigravity hook merge failed: {caught_error}", file=sys.stderr)
        return 1
    if result:
        sys.stdout.write(antigravity_hooks.serialize(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
