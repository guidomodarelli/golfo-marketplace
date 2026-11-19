#!/usr/bin/env bats

# The PostToolUse hook receives the Claude Code hook JSON on stdin. A fake `gh` on PATH answers
# from files and a real bare repository at `acme/app.git` plays the PR's base repository, so a detected push runs the real
# refresh-file-count.sh end to end.

setup() {
  HOOK_SCRIPT="${BATS_TEST_DIRNAME}/../refresh-pr-file-count.sh"
  FAKE_DIR="${BATS_TEST_TMPDIR}/gh"
  ORIGIN_DIR="${BATS_TEST_TMPDIR}/acme/app.git"
  WORK_DIR="${BATS_TEST_TMPDIR}/work"
  PR_URL="https://github.com/acme/app/pull/7"
  mkdir -p "${FAKE_DIR}/bin"
  export FAKE_DIR
  : > "${FAKE_DIR}/calls"
  printf '7\t%s\tOPEN\tmain\tfeature/login\tfalse\n' "$PR_URL" > "${FAKE_DIR}/fields"
  printf '%s\n' '## 📝 Descripción <sup>📄 Archivos de código modificados: 0</sup>' '' 'Texto' > "${FAKE_DIR}/body"
  cat > "${FAKE_DIR}/bin/gh" <<'FAKE_GH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_DIR/calls"
case "$*" in
  "pr view"*"--json number,url"*) cat "$FAKE_DIR/fields" ;;
  "pr view"*"--json body"*) cat "$FAKE_DIR/body" ;;
  "pr edit"*) while [ $# -gt 0 ]; do [ "$1" = "--body-file" ] && cp "$2" "$FAKE_DIR/body"; shift; done ;;
  *) echo "fake gh: unexpected call: $*" >&2; exit 64 ;;
esac
FAKE_GH
  chmod +x "${FAKE_DIR}/bin/gh"
  export PATH="${FAKE_DIR}/bin:${PATH}"
  unset GOLFO_PR_FILE_COUNT_REFRESH

  mkdir -p "$(dirname "$ORIGIN_DIR")"
  git init --quiet --bare "$ORIGIN_DIR"
  git init --quiet -b main "$WORK_DIR"
  git -C "$WORK_DIR" config user.email test@example.com
  git -C "$WORK_DIR" config user.name Test
  git -C "$WORK_DIR" remote add origin "$ORIGIN_DIR"
  echo base > "${WORK_DIR}/README.md"
  git -C "$WORK_DIR" add README.md
  git -C "$WORK_DIR" commit --quiet -m base
  git -C "$WORK_DIR" push --quiet origin main
  git -C "$WORK_DIR" checkout --quiet -b feature/login
  echo 'package main' > "${WORK_DIR}/main.go"
  git -C "$WORK_DIR" add main.go
  git -C "$WORK_DIR" commit --quiet -m feature
  git -C "$WORK_DIR" push --quiet origin feature/login
}

# Runs the hook with a Bash tool call whose command is $1, from directory $2 (default: the checkout).
run_hook() {
  hook_json="$(jq -cn --arg command "$1" --arg cwd "${2:-$WORK_DIR}" '{hook_event_name: "PostToolUse", tool_name: "Bash", cwd: $cwd, tool_input: {command: $command}}')"
  run bash -c 'printf "%s" "$1" | bash "$2"' _ "$hook_json" "$HOOK_SCRIPT"
}

@test "refreshes the PR count after a git push and tells the agent through additionalContext" {
  run_hook 'git push origin feature/login'
  [ "$status" -eq 0 ]
  [ "$(jq -r '.hookSpecificOutput.hookEventName' <<<"$output")" = "PostToolUse" ]
  [[ "$(jq -r '.hookSpecificOutput.additionalContext' <<<"$output")" == *"UPDATED: 0 -> 1 ${PR_URL}"* ]]
  grep -qF 'Archivos de código modificados: 1</sup>' "${FAKE_DIR}/body"
}

@test "follows a leading cd and git -C to the pushed checkout" {
  run_hook "cd '${WORK_DIR}' && git push" "$BATS_TEST_TMPDIR"
  [ "$status" -eq 0 ]
  [[ "$output" == *"UPDATED: 0 -> 1"* ]]

  printf '%s\n' '## 📝 Descripción <sup>📄 Archivos de código modificados: 5</sup>' > "${FAKE_DIR}/body"
  run_hook "git -C \"${WORK_DIR}\" push -u origin HEAD" "$BATS_TEST_TMPDIR"
  [ "$status" -eq 0 ]
  [[ "$output" == *"UPDATED: 5 -> 1"* ]]
}

@test "ignores commands that are not a git push and dry runs" {
  for command in 'git status' 'git commit -m "push the fix"' 'echo git push origin feature/login' 'printf "%s" "run git push later"' 'git push --dry-run origin feature/login' 'git push -n'; do
    run_hook "$command"
    [ "$status" -eq 0 ]
    [ -z "$output" ]
  done
  [ ! -s "${FAKE_DIR}/calls" ]
}

@test "detects git push after a command separator or on a later line" {
  run_hook "git add . && git commit -m wip && git push"
  [ "$status" -eq 0 ]
  [[ "$output" == *"UPDATED: 0 -> 1"* ]]

  printf '%s\n' '## 📝 Descripción <sup>📄 Archivos de código modificados: 0</sup>' > "${FAKE_DIR}/body"
  run_hook $'git status\ngit push origin feature/login'
  [ "$status" -eq 0 ]
  [[ "$output" == *"UPDATED: 0 -> 1"* ]]
}

@test "does nothing when GOLFO_PR_FILE_COUNT_REFRESH=0" {
  export GOLFO_PR_FILE_COUNT_REFRESH=0
  run_hook 'git push'
  [ "$status" -eq 0 ]
  [ -z "$output" ]
  [ ! -s "${FAKE_DIR}/calls" ]
}

@test "never fails the tool call and reports a refresh failure as context" {
  printf '7\t%s\tOPEN\tmain\tfeature/missing\tfalse\n' "$PR_URL" > "${FAKE_DIR}/fields"
  run_hook 'git push'
  [ "$status" -eq 0 ]
  [[ "$(jq -r '.hookSpecificOutput.additionalContext' <<<"$output")" == *"FAILED: refresh-file-count: git fetch origin main refs/heads/feature/missing failed"* ]]
}
