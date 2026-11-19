#!/usr/bin/env bash
# Counts reviewable product code files for the PR body file-count marker.
#
# Usage:
#   count-reviewable-files.sh <base-ref>...<head-ref>   # reads paths from git diff
#   git diff --name-only <range> | count-reviewable-files.sh   # reads paths from stdin
#
# Counted: source files of any mainstream language (JavaScript/TypeScript and their
# frameworks, Kotlin, Java, Scala, Groovy, Go, Python, Ruby, PHP, Rust, C/C++,
# Objective-C, Swift, C#, F#, Dart, Elixir, Erlang, Clojure, Haskell, Lua, Perl, R,
# Julia, Zig, Nim, SQL and shell/PowerShell scripts).
#
# Excluded: dot directories and dotfiles, root config/ and settings/, vendored and build
# output directories, tests (directories and per-language naming such as `*_test.go`,
# `FooTest.kt`, `FooTests.swift`, `test_foo.py`, `foo_spec.rb`), mocks, fakes, fixtures,
# snapshots, e2e, stories, declaration files, generated sources, build scripts (Gradle,
# Maven, Bazel, CMake), tooling configuration and any non-code file.
set -euo pipefail
# Byte semantics, so the case-sensitive test-name checks do not depend on the caller's locale.
export LC_ALL=C

# Lowercase extensions that count as reviewable source code.
readonly SOURCE_EXTENSIONS='js|jsx|mjs|cjs|ts|tsx|mts|cts|vue|svelte|astro|kt|java|scala|sc|groovy|go|py|pyi|rb|php|rs|c|h|cc|cpp|cxx|hpp|hh|hxx|m|mm|swift|cs|fs|fsx|vb|dart|ex|exs|erl|hrl|clj|cljs|cljc|hs|lua|pl|pm|r|jl|zig|nim|sql|sh|bash|zsh|ps1|psm1'

list_paths() {
  if [[ $# -gt 0 ]]; then
    git diff --name-only "$1"
  else
    cat
  fi
}

list_paths "$@" |
awk -v source_extensions="$SOURCE_EXTENSIONS" '
  BEGIN { source_regex = "\\.(" source_extensions ")$" }
  {
    sub(/\r$/, "")
    original_segment_count = split($0, original_segments, "/")
    original_basename = original_segments[original_segment_count]
    path = tolower($0)
    segment_count = split(path, segments, "/")
    basename = segments[segment_count]
    for (i = 1; i <= segment_count; i++) if (segments[i] ~ /^\./) next
    if (path ~ /^(config|settings)\//) next
    if (path ~ /(^|\/)(node_modules|vendor|third_party|dist|build|target|obj|generated)\//) next
    if (path ~ /(^|\/)(__tests__|__mocks__|__fixtures__|__snapshots__|tests?|specs?|testing|testdata|testfixtures|test-fixtures|androidtest|unittest|integrationtest|integration-tests?|mocks?|fakes?|fixtures?|e2e|cypress|playwright)(\/|$)/) next
    if (basename ~ /^([^\/]*[-_.])?(test|tests|spec|specs|mock|mocks|fake|fakes)([-_.][^\/]*)?\.[^\/]+$/) next
    if (basename ~ /^conftest\.py$/) next
    if (original_basename ~ /[a-z0-9](Test|Tests|TestCase|IT|ITCase|Spec|Specs|Mock|Mocks|Fake|Fakes)\.[A-Za-z0-9]+$/) next
    if (original_basename ~ /^(Test|Mock|Fake)[A-Z][A-Za-z0-9]*\.[A-Za-z0-9]+$/) next
    if (basename ~ /\.(spec|test|stories|story|e2e)\.[^\/]+$/) next
    if (basename ~ /\.d\.[cm]?ts$/) next
    if (basename ~ /\.(pb|pb\.gw|g|freezed|gen|generated)\.[^.\/]+$/ || basename ~ /(_generated|_gen|\.generated)\.[^.\/]+$/ || basename ~ /_pb2(_grpc)?\.py$/) next
    if (basename ~ /\.config\.[^\/]+$/) next
    if (basename ~ /\.gradle(\.kts)?$/ || basename ~ /^(pom\.xml|build\.bazel|workspace|cmakelists\.txt|makefile|setup\.py|noxfile\.py|fabfile\.py|gulpfile\..*|gruntfile\..*)$/) next
    if (basename ~ /^(jest|babel|webpack|rollup|vite|vitest|postcss|tailwind|prettier|eslint|stylelint|commitlint|lint-staged|husky|karma)([-_.][^\/]*)?\.[cm]?[jt]sx?$/) next
    if (basename ~ source_regex) count++
  }
  END { print count + 0 }
'
