#!/usr/bin/env bash
# Counts reviewable product code files for the PR body file-count line.
#
# Usage:
#   count-reviewable-files.sh <base-ref>...<head-ref>   # reads paths from git diff
#   git diff --name-only <range> | count-reviewable-files.sh   # reads paths from stdin
#
# Excluded: dot directories and dotfiles, root config/ and settings/, tests, mocks,
# fixtures, snapshots, e2e, stories, declaration files, tooling configuration, and any
# file that is not JavaScript or TypeScript.
set -euo pipefail

list_paths() {
  if [[ $# -gt 0 ]]; then
    git diff --name-only "$1"
  else
    cat
  fi
}

list_paths "$@" |
awk '
  {
    path = tolower($0)
    segment_count = split(path, segments, "/")
    basename = segments[segment_count]
    for (i = 1; i <= segment_count; i++) if (segments[i] ~ /^\./) next
    if (path ~ /^(config|settings)\//) next
    if (path ~ /(^|\/)(__tests__|__mocks__|__fixtures__|__snapshots__|tests?|mocks?|fixtures?|e2e|cypress|playwright)(\/|$)/) next
    if (basename ~ /^([^\/]*[-_.])?(test|tests|mock|mocks)([-_.][^\/]*)?\.[^\/]+$/) next
    if (basename ~ /\.(spec|test|stories|story|e2e)\.[^\/]+$/) next
    if (basename ~ /\.d\.[cm]?ts$/) next
    if (basename ~ /\.config\.[^\/]+$/) next
    if (basename ~ /^(jest|babel|webpack|rollup|vite|vitest|postcss|tailwind|prettier|eslint|stylelint|commitlint|lint-staged|husky|karma|gulpfile|gruntfile)([-_.][^\/]*)?\.[cm]?[jt]sx?$/) next
    if (basename ~ /\.[cm]?[jt]sx?$/) count++
  }
  END { print count + 0 }
'
