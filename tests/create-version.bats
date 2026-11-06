#!/usr/bin/env bats

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
  test_root="$(mktemp -d)"
  repo_dir="$test_root/repo"
  mkdir -p \
    "$repo_dir/scripts/lib" \
    "$repo_dir/plugins/golfo-kit/.claude-plugin" \
    "$repo_dir/plugins/golfo-kit/.codex-plugin"

  cp "$repository_root/scripts/create-version.js" "$repo_dir/scripts/create-version.js"
  cp "$repository_root/scripts/lib/plugin-manifests.js" "$repository_root/scripts/lib/terminal-output.js" "$repo_dir/scripts/lib/"
  cat > "$repo_dir/plugins/golfo-kit/.claude-plugin/plugin.json" <<'JSON'
{
  "name": "golfo-kit",
  "version": "1.12.0"
}
JSON
  cat > "$repo_dir/plugins/golfo-kit/.codex-plugin/plugin.json" <<'JSON'
{
  "name": "golfo-kit",
  "version": "1.12.0"
}
JSON

  git -C "$repo_dir" -c init.defaultBranch=main init -q
  git -C "$repo_dir" config user.name "Create Version Test"
  git -C "$repo_dir" config user.email "create-version-test@example.com"
  git -C "$repo_dir" add -A
  git -C "$repo_dir" commit -qm "Initialize fixture"

  remote_dir="$test_root/remote.git"
  git -c init.defaultBranch=main init -q --bare "$remote_dir"
  git -C "$repo_dir" remote add origin "$remote_dir"
  git -C "$repo_dir" push -q origin main
  unset FORCE_COLOR NO_COLOR CI TERM

  # bats has no terminal, and Node only sets these properties on a real one. Every test still
  # runs the real script; this preload only makes it see a terminal on the chosen streams.
  cat > "$test_root/simulate-tty.js" <<'JS'
const tty = require('tty');
const columns = Number(process.env.SIMULATED_TTY_COLUMNS || 80);
const streamNames = (process.env.SIMULATED_TTY_STREAMS || 'stdout,stderr').split(',');
process.env.TERM ??= 'xterm-256color';
for (const streamName of streamNames) {
  Object.assign(process[streamName], {
    isTTY: true,
    columns,
    getColorDepth: tty.WriteStream.prototype.getColorDepth,
  });
}
JS
  # Measures independently from the script, so a wrong measure there cannot hide an overflow here.
  cat > "$test_root/assert-fits-columns.js" <<'JS'
const { readFileSync } = require('fs');
const { stripVTControlCharacters } = require('util');
const maximumColumns = Number(process.argv[2]);
const segmenter = new Intl.Segmenter();
const widthOf = (line) =>
  [...segmenter.segment(stripVTControlCharacters(line))].reduce(
    (width, { segment }) => width + (/\p{Emoji_Presentation}|️/u.test(segment) ? 2 : 1),
    0
  );
const overflowingLines = readFileSync(0, 'utf8')
  .split('\n')
  .filter((line) => widthOf(line) > maximumColumns);
if (overflowingLines.length > 0) {
  console.error(`Lines wider than ${maximumColumns} columns:\n${overflowingLines.join('\n')}`);
  process.exit(1);
}
JS
  terminal_node="node --require ../simulate-tty.js"
  cd "$repo_dir"
}

assert_plain_output() {
  [[ "$output" != *$'\e'* ]]
  [[ "$output" != *$'\r'* ]]
}

assert_output_fits_columns() {
  printf '%s\n' "$output" | node ../assert-fits-columns.js "$1"
}

# Output without borders, spaces or line breaks: wrapping must not lose any data.
compact_output() {
  printf '%s' "$output" | sed 's/[│┃]//g' | tr -d ' \n'
}

bottom_border_width() {
  local bottom_border
  bottom_border="$(printf '%s\n' "$output" | grep -m1 '╰')"
  printf '%s' "${#bottom_border}"
}

remote_head() {
  git -C "$remote_dir" rev-parse --verify --quiet "refs/heads/$1"
}

teardown() {
  cd "$repository_root"
  rm -rf "$test_root"
}

assert_head_contains_only_manifests() {
  git show --format= --name-only HEAD | grep -Fxq 'plugins/golfo-kit/.claude-plugin/plugin.json'
  git show --format= --name-only HEAD | grep -Fxq 'plugins/golfo-kit/.codex-plugin/plugin.json'
  [ "$(git show --format= --name-only HEAD | wc -l | tr -d ' ')" = "2" ]
}

@test "auto-detects one changed plugin and commits only the plugin manifests" {
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md
  printf '%s\n' 'staged change' > staged.txt
  git add staged.txt
  printf '%s\n' 'untracked change' > untracked.txt

  run bash -c "printf '1\\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" == *"Detected changed plugin: golfo-kit"* ]]
  [[ "$output" != *"Select a plugin by number"* ]]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.12.1" ]
  [ "$(node -p "require('./plugins/golfo-kit/.codex-plugin/plugin.json').version")" = "1.12.1" ]
  [ "$(git log -1 --pretty=%s)" = 'Bump the version number from 1.12.0 to 1.12.1 in all "plugin.json" files for the "golfo-kit" plugin' ]
  git log -1 --pretty=%B | grep -Fxq 'Co-Authored-By: Claude Code <noreply@anthropic.com>'
  assert_head_contains_only_manifests
  git status --porcelain | grep -Fxq 'A  staged.txt'
  git status --porcelain | grep -Fxq '?? plugins/golfo-kit/docs/'
  git status --porcelain | grep -Fxq '?? untracked.txt'
  [ "$(git status --porcelain | wc -l | tr -d ' ')" = "3" ]
}

@test "auto-detects plugin changed in branch history" {
  git update-ref refs/remotes/origin/main "$(git rev-parse HEAD)"
  git switch -q -c feature/golfo-kit-change
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'committed plugin change' > plugins/golfo-kit/docs/committed.md
  git add plugins/golfo-kit/docs/committed.md
  git commit -qm "Change Golfo Kit"

  run bash -c "printf '1\\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" == *"Detected changed plugin: golfo-kit"* ]]
  [[ "$output" != *"Select a plugin by number"* ]]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.12.1" ]
  [ -z "$(git status --porcelain)" ]
}

@test "keeps plugin menu when multiple plugins changed" {
  mkdir -p \
    plugins/golfo-kit/docs \
    plugins/other-plugin/.claude-plugin \
    plugins/other-plugin/.codex-plugin
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md
  cat > plugins/other-plugin/.claude-plugin/plugin.json <<'JSON'
{
  "name": "other-plugin",
  "version": "2.0.0"
}
JSON
  cat > plugins/other-plugin/.codex-plugin/plugin.json <<'JSON'
{
  "name": "other-plugin",
  "version": "2.0.0"
}
JSON

  run bash -c "printf '1\\n1\\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" == *"Detected changed plugins:"* ]]
  [[ "$output" == *"Select a plugin by number"* ]]
  [ "$(git log -1 --pretty=%s)" = 'Bump the version number from 1.12.0 to 1.12.1 in all "plugin.json" files for the "golfo-kit" plugin' ]
  assert_head_contains_only_manifests
  git status --porcelain | grep -Fxq '?? plugins/other-plugin/'
}

@test "pushes new feature branch and sets upstream" {
  git switch -q -c feature/golfo-kit-change
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "printf '1\\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" == *'Pushed "feature/golfo-kit-change" to origin'* ]]
  [ "$(remote_head feature/golfo-kit-change)" = "$(git rev-parse HEAD)" ]
  [ "$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}')" = "origin/feature/golfo-kit-change" ]
}

@test "pushes to existing upstream branch" {
  git switch -q -c feature/golfo-kit-change
  git push -q -u origin HEAD
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "printf '2\\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.13.0" ]
  [ "$(remote_head feature/golfo-kit-change)" = "$(git rev-parse HEAD)" ]
}

@test "pushes default branch" {
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "printf '1\\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" == *'Pushed "main" to origin'* ]]
  [ "$(remote_head main)" = "$(git rev-parse HEAD)" ]
  [ "$(git log -1 --pretty=%s)" = 'Bump the version number from 1.12.0 to 1.12.1 in all "plugin.json" files for the "golfo-kit" plugin' ]
}

@test "reports push failure and keeps local commit" {
  git switch -q -c feature/golfo-kit-change
  git remote set-url origin "$test_root/missing-remote.git"
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "printf '1\\n' | node scripts/create-version.js"

  [ "$status" -eq 1 ]
  [[ "$output" == *'Version bump commit was created but "git push -u origin HEAD" failed for branch "feature/golfo-kit-change"'* ]]
  [ "$(git log -1 --pretty=%s)" = 'Bump the version number from 1.12.0 to 1.12.1 in all "plugin.json" files for the "golfo-kit" plugin' ]
  assert_head_contains_only_manifests
  [ "$(git status --porcelain)" = '?? plugins/golfo-kit/docs/' ]
}

@test "prints plain output when stdout is not a terminal" {
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "printf '1\\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" != *$'\e['* ]]
  [[ "$output" == *"╭─ 📦 Plugin"* ]]
  [[ "$output" == *"1.12.0 → 1.12.1"* ]]
}

@test "colors output when FORCE_COLOR is set" {
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "printf '1\\n' | FORCE_COLOR=1 node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" == *$'\e[32m'* ]]
}

@test "NO_COLOR overrides FORCE_COLOR" {
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "printf '1\\n' | FORCE_COLOR=1 NO_COLOR=1 node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" != *$'\e['* ]]
}

@test "FORCE_COLOR=0 prints plain output" {
  run bash -c "printf '1\n' | FORCE_COLOR=0 node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  assert_plain_output
  [[ "$output" == *"1.12.0 → 1.12.1"* ]]
}

@test "FORCE_COLOR=false prints plain output" {
  run bash -c "printf '1\n' | FORCE_COLOR=false node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  assert_plain_output
}

@test "TERM=dumb overrides FORCE_COLOR" {
  run bash -c "printf '1\n' | TERM=dumb FORCE_COLOR=1 node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  assert_plain_output
}

@test "an empty NO_COLOR does not turn color off" {
  run bash -c "printf '1\n' | NO_COLOR= FORCE_COLOR=1 node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [[ "$output" == *$'\e[32m'* ]]
}

@test "FORCE_COLOR colors output even under CI" {
  run bash -c "printf '1\n' | CI=1 FORCE_COLOR=1 node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [[ "$output" == *$'\e[32m'* ]]
}

@test "colors output on a terminal" {
  run bash -c "printf '1\n' | $terminal_node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [[ "$output" == *$'\e[32m'* ]]
}

@test "CI=1 prints plain output on a terminal, prompts included" {
  run bash -c "printf '1\n' | CI=1 $terminal_node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  assert_plain_output
  [[ "$output" == *"Select an option"* ]]
  [[ "$output" == *"1.12.0 → 1.12.1"* ]]
}

@test "CI=0 and CI=false keep color on a terminal" {
  run bash -c "printf '1\n' | CI=0 $terminal_node scripts/create-version.js --dry-run"
  [ "$status" -eq 0 ]
  [[ "$output" == *$'\e[32m'* ]]

  run bash -c "printf '1\n' | CI=false $terminal_node scripts/create-version.js --dry-run"
  [ "$status" -eq 0 ]
  [[ "$output" == *$'\e[32m'* ]]
}

@test "TERM=dumb prints plain output on a terminal" {
  run bash -c "printf '1\n' | TERM=dumb $terminal_node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  assert_plain_output
}

@test "FORCE_COLOR=0 prints plain output on a terminal" {
  run bash -c "printf '1\n' | FORCE_COLOR=0 $terminal_node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  assert_plain_output
}

@test "NO_COLOR prints plain output on a terminal" {
  run bash -c "printf '1\n' | NO_COLOR=1 $terminal_node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  assert_plain_output
}

@test "decides color for stderr apart from stdout" {
  run bash -c "SIMULATED_TTY_STREAMS=stdout $terminal_node scripts/create-version.js --force"
  [ "$status" -eq 1 ]
  [[ "$output" == *"create-version failed"* ]]
  assert_plain_output

  run bash -c "SIMULATED_TTY_STREAMS=stderr $terminal_node scripts/create-version.js --force"
  [ "$status" -eq 1 ]
  [[ "$output" == *$'\e[31m'* ]]
}

@test "removes the escapes and line breaks of git errors from plain output" {
  mkdir -p .git/hooks
  cat > .git/hooks/pre-commit <<'SH'
#!/bin/sh
printf '\033[31mhook rejected\033[0m\r\nsecond hook line\n' >&2
exit 1
SH
  chmod +x .git/hooks/pre-commit

  run node scripts/create-version.js golfo-kit --bump patch

  [ "$status" -eq 1 ]
  assert_plain_output
  [[ "$output" == *"hook rejected"* ]]
  [[ "$output" == *$'│  second hook line'* ]]
}

@test "keeps the 64-column box and whole lines without a terminal" {
  run bash -c "printf '1\n' | node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [ "$(bottom_border_width)" -eq 64 ]
  [[ "$output" == *'Would commit only the plugin manifests: Bump the version number from 1.12.0 to 1.12.1 in all "plugin.json" files for the "golfo-kit" plugin'* ]]
}

@test "keeps the 64-column box and whole lines on a wide terminal" {
  run bash -c "printf '1\n' | CI=1 SIMULATED_TTY_COLUMNS=200 $terminal_node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [ "$(bottom_border_width)" -eq 64 ]
  [[ "$output" == *'Would commit only the plugin manifests: Bump the version number from 1.12.0 to 1.12.1 in all "plugin.json" files for the "golfo-kit" plugin'* ]]
}

@test "fits a dry run in 40 columns without losing data" {
  run bash -c "printf '1\n' | CI=1 SIMULATED_TTY_COLUMNS=40 $terminal_node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  assert_plain_output
  assert_output_fits_columns 40
  [ "$(bottom_border_width)" -eq 40 ]
  local compacted
  compacted="$(compact_output)"
  [[ "$compacted" == *'Bumptheversionnumberfrom1.12.0to1.12.1inall"plugin.json"filesforthe"golfo-kit"plugin'* ]]
  [[ "$compacted" == *'plugins/golfo-kit/.claude-plugin/plugin.json'* ]]
  [[ "$compacted" == *'1.12.0→1.12.1'* ]]
  [[ "$compacted" == *'nothingwillbewritten,committedorpushed'* ]]
}

@test "fits a colored dry run in 40 columns" {
  run bash -c "printf '1\n' | SIMULATED_TTY_COLUMNS=40 $terminal_node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [[ "$output" == *$'\e[32m'* ]]
  assert_output_fits_columns 40
}

@test "fits the help in 40 columns" {
  run bash -c "CI=1 SIMULATED_TTY_COLUMNS=40 $terminal_node scripts/create-version.js --help"

  [ "$status" -eq 0 ]
  assert_output_fits_columns 40
  local compacted
  compacted="$(compact_output)"
  [[ "$compacted" == *'Previewwithoutwriting,committingorpushing'* ]]
}

@test "fits a whole bump and its push in 40 columns" {
  git switch -q -c feature/golfo-kit-change

  run bash -c "SIMULATED_TTY_COLUMNS=40 CI=1 $terminal_node scripts/create-version.js golfo-kit --bump patch < /dev/null"

  [ "$status" -eq 0 ]
  assert_output_fits_columns 40
  [ "$(remote_head feature/golfo-kit-change)" = "$(git rev-parse HEAD)" ]
  local compacted
  compacted="$(compact_output)"
  [[ "$compacted" == *'Pushed"feature/golfo-kit-change"toorigin'* ]]
}

@test "wraps a failure in 40 columns keeping its style on every line" {
  run bash -c "FORCE_COLOR=1 SIMULATED_TTY_COLUMNS=40 $terminal_node scripts/create-version.js --force"

  [ "$status" -eq 1 ]
  assert_output_fits_columns 40
  [ "$(printf '%s\n' "$output" | grep -c $'\e\\[31m│\e\\[0m  \e\\[31m.*\e\\[0m$')" -ge 2 ]
}

@test "dry run previews bump without writing, committing or pushing" {
  git switch -q -c feature/golfo-kit-change
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md
  initial_head="$(git rev-parse HEAD)"
  initial_status="$(git status --porcelain)"

  run bash -c "printf '1\\n' | node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [[ "$output" == *"🧪 DRY RUN"* ]]
  [[ "$output" == *"Would update plugins/golfo-kit/.claude-plugin/plugin.json"* ]]
  [[ "$output" == *'Would commit only the plugin manifests: Bump the version number from 1.12.0 to 1.12.1'* ]]
  [[ "$output" == *'Would push "feature/golfo-kit-change" to origin (git push -u origin HEAD)'* ]]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.12.0" ]
  [ "$(node -p "require('./plugins/golfo-kit/.codex-plugin/plugin.json').version")" = "1.12.0" ]
  [ "$(git rev-parse HEAD)" = "$initial_head" ]
  [ "$(git status --porcelain)" = "$initial_status" ]
  [ -z "$(remote_head feature/golfo-kit-change)" ]
}

@test "dry run shorthand works with plugin name on default branch" {
  run bash -c "printf '3\\n' | node scripts/create-version.js -n golfo-kit"

  [ "$status" -eq 0 ]
  [[ "$output" == *"1.12.0 → 2.0.0"* ]]
  [[ "$output" == *'Would push "main" to origin (git push -u origin HEAD)'* ]]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.12.0" ]
  [ "$(git log -1 --pretty=%s)" = "Initialize fixture" ]
}

@test "rejects unknown options" {
  run bash -c "node scripts/create-version.js --force"

  [ "$status" -eq 1 ]
  [[ "$output" == *'Unknown option "--force". Supported options: --dry-run, -n'* ]]
}

@test "prints help without touching the repository" {
  run bash -c "node scripts/create-version.js -h"

  [ "$status" -eq 0 ]
  [[ "$output" == *"Usage"* ]]
  [[ "$output" == *"--bump <kind>"* ]]
  [[ "$output" == *"--set <version>"* ]]
  [ "$(git log -1 --pretty=%s)" = "Initialize fixture" ]
}

@test "bumps without prompts using --bump" {
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "node scripts/create-version.js golfo-kit --bump minor < /dev/null"

  [ "$status" -eq 0 ]
  [[ "$output" != *"Select an option"* ]]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.13.0" ]
  [ "$(node -p "require('./plugins/golfo-kit/.codex-plugin/plugin.json').version")" = "1.13.0" ]
}

@test "sets exact version using --set=value" {
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "node scripts/create-version.js --set=3.1.4 < /dev/null"

  [ "$status" -eq 0 ]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "3.1.4" ]
}

@test "combines dry run with --set" {
  mkdir -p plugins/golfo-kit/docs
  printf '%s\n' 'plugin change' > plugins/golfo-kit/docs/change.md

  run bash -c "node scripts/create-version.js -n --set 2.0.0 < /dev/null"

  [ "$status" -eq 0 ]
  [[ "$output" == *"1.12.0 → 2.0.0"* ]]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.12.0" ]
}

@test "rejects invalid --bump and --set values" {
  run bash -c "node scripts/create-version.js --bump huge"
  [ "$status" -eq 1 ]
  [[ "$output" == *'Invalid --bump value "huge". Expected one of: patch, minor, major'* ]]

  run bash -c "node scripts/create-version.js --set 1.2"
  [ "$status" -eq 1 ]
  [[ "$output" == *'Invalid --set value "1.2". Expected MAJOR.MINOR.PATCH.'* ]]
}

@test "rejects --bump with --set and missing values" {
  run bash -c "node scripts/create-version.js --bump patch --set 2.0.0"
  [ "$status" -eq 1 ]
  [[ "$output" == *"Options --bump and --set cannot be used together."* ]]

  run bash -c "node scripts/create-version.js --bump --dry-run"
  [ "$status" -eq 1 ]
  [[ "$output" == *'Option "--bump" requires a value.'* ]]
}

add_other_plugin_on_base() {
  mkdir -p plugins/other-plugin/.claude-plugin plugins/other-plugin/.codex-plugin
  for provider_directory in .claude-plugin .codex-plugin; do
    printf '%s\n' '{' '  "name": "other-plugin",' '  "version": "2.0.0"' '}' \
      > "plugins/other-plugin/$provider_directory/plugin.json"
  done
  git add plugins/other-plugin
  git commit -qm "Add other plugin"
  git update-ref refs/remotes/origin/main "$(git rev-parse HEAD)"
  git switch -q -c feature/multi-plugin-change
}

@test "skips plugins already bumped in the branch and auto-selects the pending one" {
  add_other_plugin_on_base
  mkdir -p plugins/golfo-kit/docs plugins/other-plugin/docs
  printf '%s\n' 'golfo kit change' > plugins/golfo-kit/docs/change.md
  printf '%s\n' 'other plugin change' > plugins/other-plugin/docs/change.md
  git add plugins
  git commit -qm "Change both plugins"
  node scripts/create-version.js other-plugin --bump minor >/dev/null

  run bash -c "printf '1\\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" == *"Already bumped in this branch: other-plugin (2.0.0 → 2.1.0)"* ]]
  [[ "$output" == *"Detected changed plugin: golfo-kit"* ]]
  [[ "$output" != *"Select a plugin by number"* ]]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.12.1" ]
  [ "$(node -p "require('./plugins/other-plugin/.claude-plugin/plugin.json').version")" = "2.1.0" ]
}

@test "marks bumped plugins in the menu when every changed plugin is bumped" {
  add_other_plugin_on_base
  mkdir -p plugins/golfo-kit/docs plugins/other-plugin/docs
  printf '%s\n' 'golfo kit change' > plugins/golfo-kit/docs/change.md
  printf '%s\n' 'other plugin change' > plugins/other-plugin/docs/change.md
  git add plugins
  git commit -qm "Change both plugins"
  node scripts/create-version.js golfo-kit --bump patch >/dev/null
  node scripts/create-version.js other-plugin --bump patch >/dev/null

  run bash -c "printf '1\\n1\\n' | node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [[ "$output" == *"golfo-kit  ✔ bumped 1.12.0 → 1.12.1"* ]]
  [[ "$output" == *"other-plugin  ✔ bumped 2.0.0 → 2.0.1"* ]]
  [[ "$output" == *"Select a plugin by number"* ]]
  [[ "$output" != *"Detected changed plugin"* ]]
}

@test "auto-selects the only plugin when no plugin changed" {
  run bash -c "printf '1\n' | node scripts/create-version.js"

  [ "$status" -eq 0 ]
  [[ "$output" == *"Only plugin available: golfo-kit"* ]]
  [[ "$output" != *"Select a plugin by number"* ]]
  [ "$(node -p "require('./plugins/golfo-kit/.claude-plugin/plugin.json').version")" = "1.12.1" ]
}

@test "auto-detects plugin committed on the default branch after its last version change" {
  mkdir -p plugins/other-plugin/.claude-plugin plugins/other-plugin/.codex-plugin plugins/golfo-kit/docs
  for provider_directory in .claude-plugin .codex-plugin; do
    printf '%s\n' '{' '  "name": "other-plugin",' '  "version": "2.0.0"' '}' \
      > "plugins/other-plugin/$provider_directory/plugin.json"
  done
  git add plugins/other-plugin
  git commit -qm "Add other plugin"
  printf '%s\n' 'released without bump' > plugins/golfo-kit/docs/change.md
  git add plugins/golfo-kit/docs/change.md
  git commit -qm "Change Golfo Kit"
  git push -q origin main
  git fetch -q origin

  run bash -c "printf '1\n' | node scripts/create-version.js --dry-run"

  [ "$status" -eq 0 ]
  [[ "$output" == *"Detected changed plugin: golfo-kit"* ]]
  [[ "$output" != *"Select a plugin by number"* ]]
  [[ "$output" == *"1.12.0 → 1.12.1"* ]]
}

@test "bumps the portable root manifest together with the provider manifests" {
  cat > plugins/golfo-kit/plugin.json <<'JSON'
{
  "name": "golfo-kit",
  "version": "1.12.0"
}
JSON
  git add plugins/golfo-kit/plugin.json
  git commit -qm "Add portable manifest"

  run node scripts/create-version.js golfo-kit --bump patch

  [ "$status" -eq 0 ]
  [[ "$output" == *"Portable in sync"* ]]
  [ "$(node -p "require('./plugins/golfo-kit/plugin.json').version")" = "1.12.1" ]
  [ "$(node -p "require('./plugins/golfo-kit/.codex-plugin/plugin.json').version")" = "1.12.1" ]
  git show --format= --name-only HEAD | grep -Fxq 'plugins/golfo-kit/plugin.json'
  [ "$(git show --format= --name-only HEAD | wc -l | tr -d ' ')" = "3" ]
}

@test "rejects bumping when the portable root manifest is out of sync" {
  cat > plugins/golfo-kit/plugin.json <<'JSON'
{
  "name": "golfo-kit",
  "version": "1.11.0"
}
JSON
  git add plugins/golfo-kit/plugin.json
  git commit -qm "Add stale portable manifest"
  local head_before
  head_before="$(git rev-parse HEAD)"

  run node scripts/create-version.js golfo-kit --bump patch

  [ "$status" -eq 1 ]
  [[ "$output" == *"plugins/golfo-kit/plugin.json is 1.11.0"* ]]
  [ "$(git rev-parse HEAD)" = "$head_before" ]
}
