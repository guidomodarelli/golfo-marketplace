#!/usr/bin/env bash
# Run the bats of this repository (the devDependency pinned in package.json) with the options and test
# files it gets:
#
#   bash scripts/run-bats.sh [bats options] <test files...>
#
# Every bats run of the repository goes through here, so that bats starts from a path without a drive
# letter. On Windows the pnpm shim (`pnpm exec bats`, or `bats` in a package.json script) starts bats by
# its C:\ path, and bats loads its library from there. The DEBUG trap that bats keeps for the whole run
# turns every C:/ source path it sees into a /c/ one in a subshell, so in Git Bash each command of the
# library costs a process: about three minutes per run of bootstrap.bats before its first test, and a few
# seconds per test (#95). Started by its /c/ path, bats never takes that branch. On Linux and macOS both
# ways start the same bats from the same path.
#
# Exit codes: the ones of bats, or 1 when bats is not installed.
set -euo pipefail

repository_root="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
bats_executable="$repository_root/node_modules/bats/bin/bats"

if [[ ! -f "$bats_executable" ]]; then
  printf 'run-bats: bats is not installed in %s; run pnpm install in %s first.\n' \
    "$repository_root/node_modules" "$repository_root" >&2
  exit 1
fi

exec bash "$bats_executable" "$@"
