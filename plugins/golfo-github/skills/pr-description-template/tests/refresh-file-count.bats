#!/usr/bin/env bats

# refresh-file-count.sh talks to GitHub only through `gh`: a fake `gh` on PATH answers from files
# and logs every call, while a real bare repository at `acme/app.git` plays the base repository
# of the PR URL, so the count comes from a real `git fetch` + `git diff` of the PR range.

setup() {
  REFRESH_SCRIPT="${BATS_TEST_DIRNAME}/../scripts/refresh-file-count.sh"
  FAKE_DIR="${BATS_TEST_TMPDIR}/gh"
  ORIGIN_DIR="${BATS_TEST_TMPDIR}/acme/app.git"
  WORK_DIR="${BATS_TEST_TMPDIR}/work"
  PR_URL="https://github.com/acme/app/pull/7"
  mkdir -p "${FAKE_DIR}/bin"
  export FAKE_DIR PR_URL
  : > "${FAKE_DIR}/calls"
  printf '7\t%s\tOPEN\tmain\tfeature/login\tfalse\n' "$PR_URL" > "${FAKE_DIR}/fields"
  cat > "${FAKE_DIR}/bin/gh" <<'FAKE_GH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_DIR/calls"
case "$*" in
  "pr view"*"--json number,url"*) [ -f "$FAKE_DIR/no-pr" ] && exit 1; cat "$FAKE_DIR/fields" ;;
  "pr view"*"--json body"*) cat "$FAKE_DIR/body" ;;
  "pr edit"*)
    while [ $# -gt 0 ]; do [ "$1" = "--body-file" ] && cp "$2" "$FAKE_DIR/body"; shift; done ;;
  *) echo "fake gh: unexpected call: $*" >&2; exit 64 ;;
esac
FAKE_GH
  chmod +x "${FAKE_DIR}/bin/gh"
  export PATH="${FAKE_DIR}/bin:${PATH}"

  mkdir -p "$(dirname "$ORIGIN_DIR")"
  git init --quiet --bare "$ORIGIN_DIR"
  git init --quiet -b main "$WORK_DIR"
  cd "$WORK_DIR"
  git config user.email test@example.com
  git config user.name Test
  git remote add origin "$ORIGIN_DIR"
  echo base > README.md
  git add README.md && git commit --quiet -m base && git push --quiet origin main
  git checkout --quiet -b feature/login
  mkdir -p app/src/main/kotlin app/src/test/kotlin cmd
  echo 'class Login' > app/src/main/kotlin/Login.kt
  echo 'class LoginTest' > app/src/test/kotlin/LoginTest.kt
  echo 'package main' > cmd/main.go
  git add . && git commit --quiet -m feature && git push --quiet origin feature/login
}

write_body() {
  printf '%s\n' "$@" > "${FAKE_DIR}/body"
}

@test "moves the legacy right-aligned marker onto the Descripción heading with the new count" {
  write_body '<div align="right"><sup>📄 Archivos de código modificados: 1</sup></div>' '' '## 📝 Descripción' '' '### ❓ ¿Qué problema resuelve?' 'Texto'
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 0 ]
  [ "$output" = "UPDATED: 1 -> 2 ${PR_URL}" ]
  expected="$(printf '%s\n' '## 📝 Descripción <sup>📄 Archivos de código modificados: 2</sup>' '' '### ❓ ¿Qué problema resuelve?' 'Texto')"
  [ "$(cat "${FAKE_DIR}/body")" = "$expected" ]
}

@test "updates the count on the heading after a new push and preserves the rest of the body" {
  write_body '## 📝 Descripción <sup>📄 Archivos de código modificados: 2</sup>' '' '🎫 Jira: [ABC-1](https://acme.atlassian.net/browse/ABC-1)' '' '## 👀 Notas para el Revisor' 'Nota'
  echo 'package user' > internal.go
  git add internal.go && git commit --quiet -m more && git push --quiet origin feature/login
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 0 ]
  [ "$output" = "UPDATED: 2 -> 3 ${PR_URL}" ]
  expected="$(printf '%s\n' '## 📝 Descripción <sup>📄 Archivos de código modificados: 3</sup>' '' '🎫 Jira: [ABC-1](https://acme.atlassian.net/browse/ABC-1)' '' '## 👀 Notas para el Revisor' 'Nota')"
  [ "$(cat "${FAKE_DIR}/body")" = "$expected" ]
}

@test "does not edit the PR when the count is already right" {
  write_body '## 📝 Descripción <sup>📄 Archivos de código modificados: 2</sup>' '' 'Texto'
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 0 ]
  [ "$output" = "UNCHANGED: 2 ${PR_URL}" ]
  ! grep -q '^pr edit' "${FAKE_DIR}/calls"
}

@test "skips a PR body that was not written with the template marker" {
  write_body '## Qué cambia' 'Texto libre'
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 0 ]
  [ "$output" = "SKIPPED: PR ${PR_URL} has no file-count marker" ]
  ! grep -q '^pr edit' "${FAKE_DIR}/calls"
}

@test "skips a closed PR and a branch without PR" {
  printf '7\t%s\tMERGED\tmain\tfeature/login\tfalse\n' "$PR_URL" > "${FAKE_DIR}/fields"
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 0 ]
  [ "$output" = "SKIPPED: PR ${PR_URL} is MERGED" ]

  touch "${FAKE_DIR}/no-pr"
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 0 ]
  [ "$output" = "SKIPPED: no pull request for the current branch" ]
}

@test "fails with the PR and branches in the message when the head branch cannot be fetched" {
  write_body '## 📝 Descripción <sup>📄 Archivos de código modificados: 2</sup>'
  printf '7\t%s\tOPEN\tmain\tfeature/missing\tfalse\n' "$PR_URL" > "${FAKE_DIR}/fields"
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 1 ]
  [[ "$output" == *"git fetch origin main refs/heads/feature/missing failed for PR ${PR_URL}"* ]]
}

@test "deepens a depth-1 clone until base...head has a merge base" {
  write_body '## 📝 Descripción <sup>📄 Archivos de código modificados: 0</sup>'
  git checkout --quiet main
  echo 'more' >> README.md
  git commit --quiet -am 'main moves on' && git push --quiet origin main
  git clone --quiet --depth 1 --single-branch --no-tags --branch feature/login "file://${ORIGIN_DIR}" "${BATS_TEST_TMPDIR}/shallow"
  cd "${BATS_TEST_TMPDIR}/shallow"
  [ "$(git rev-parse --is-shallow-repository)" = "true" ]
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 0 ]
  [ "$output" = "UPDATED: 0 -> 2 ${PR_URL}" ]
}

@test "fetches a fork PR from the base repository when origin is the contributor's fork" {
  write_body '## 📝 Descripción <sup>📄 Archivos de código modificados: 0</sup>'
  FORK_DIR="${BATS_TEST_TMPDIR}/contributor/app.git"
  git clone --quiet --bare "$ORIGIN_DIR" "$FORK_DIR"
  git push --quiet origin feature/login:refs/pull/7/head
  git push --quiet origin --delete feature/login
  git remote rename origin upstream
  git remote add origin "$FORK_DIR"
  printf '7	%s	OPEN	main	feature/login	true
' "$PR_URL" > "${FAKE_DIR}/fields"
  run bash "$REFRESH_SCRIPT"
  [ "$status" -eq 0 ]
  [ "$output" = "UPDATED: 0 -> 2 ${PR_URL}" ]
  ! git show-ref | grep -q 'refs/pr-file-count'
}
