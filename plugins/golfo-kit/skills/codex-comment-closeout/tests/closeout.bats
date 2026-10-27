#!/usr/bin/env bats

# closeout.sh only talks to GitHub through `gh`: a fake `gh` on PATH answers from files and logs every
# call, so the tests check what would be published (reaction, reply, edit, thread resolution).

setup() {
  CLOSEOUT="${BATS_TEST_DIRNAME}/../scripts/closeout.sh"
  FAKE_DIR="${BATS_TEST_TMPDIR}/gh"
  mkdir -p "${FAKE_DIR}/bin"
  export FAKE_DIR CLOSEOUT_WAIT_SECONDS=0 CLOSEOUT_WAIT_ATTEMPTS=3
  printf 'abcdef1234567890abcdef1234567890abcdef12\n' > "${FAKE_DIR}/head"
  printf 'identical\n' > "${FAKE_DIR}/compare"
  : > "${FAKE_DIR}/calls"
  echo THREAD_1 > "${FAKE_DIR}/threads"
  cat > "${FAKE_DIR}/bin/gh" <<'FAKE_GH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_DIR/calls"
case "$*" in
  "pr view"*) cat "$FAKE_DIR/head" ;;
  "api repos/acme/docs/compare/"*) head -n 1 "$FAKE_DIR/compare"; tail -n +2 "$FAKE_DIR/compare" > "$FAKE_DIR/compare.next"; [ -s "$FAKE_DIR/compare.next" ] && mv "$FAKE_DIR/compare.next" "$FAKE_DIR/compare" || true ;;
  *"/reactions"*) echo '{}' ;;
  "api -X POST repos/acme/docs/pulls/7/comments/"*"/replies"*|"api -X POST repos/acme/docs/issues/7/comments"*)
    for argument in "$@"; do case "$argument" in body=*) printf '%s' "${argument#body=}" > "$FAKE_DIR/published" ;; esac; done
    echo 900 ;;
  "api -X PATCH"*)
    for argument in "$@"; do case "$argument" in body=*) printf '%s' "${argument#body=}" > "$FAKE_DIR/published" ;; esac; done ;;
  "api repos/acme/docs/pulls/comments/900"*|"api repos/acme/docs/issues/comments/900"*)
    if [ -f "$FAKE_DIR/mangle" ]; then rm "$FAKE_DIR/mangle"; echo 'Corregido.'; else cat "$FAKE_DIR/published"; fi ;;
  "api graphql"*"resolveReviewThread"*) echo true ;;
  "api graphql"*"reviewThreads"*) cat "$FAKE_DIR/threads" ;;
  "api graphql"*) echo '{}' ;;
  *) echo "fake gh: unexpected call: $*" >&2; exit 64 ;;
esac
FAKE_GH
  chmod +x "${FAKE_DIR}/bin/gh"
  export PATH="${FAKE_DIR}/bin:${PATH}"
  SHA=abcdef1234567890abcdef1234567890abcdef12
}

@test "closes an inline comment as resolved: 👍, template reply with the commit and resolved thread" {
  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant resolved --sha "$SHA" --summary "el enlace usa la URL pública."

  [ "$status" -eq 0 ]
  [[ "$output" == *"closeout: comment 55 resolved reply=900 resolved=true"* ]]
  grep -q 'repos/acme/docs/pulls/comments/55/reactions -f content=+1' "$FAKE_DIR/calls"
  grep -q 'resolveReviewThread' "$FAKE_DIR/calls"
  published=$(cat "$FAKE_DIR/published")
  [[ "$published" == '✅ **Resuelto** en [`abcdef1`](https://github.com/acme/docs/commit/'"$SHA"').'* ]]
  [[ "$published" == *'**Qué cambió:** el enlace usa la URL pública.'* ]]
  [[ "$published" == *'<sub>🤖 Fix automático en respuesta a este comentario de Codex</sub>' ]]
}

@test "waits until the commit reaches the PR head before replying" {
  printf 'behind\nbehind\nidentical\n' > "$FAKE_DIR/compare"

  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant resolved --sha "$SHA" --summary "fix"

  [ "$status" -eq 0 ]
  [ "$(grep -c 'compare/' "$FAKE_DIR/calls")" -eq 3 ]
}

@test "fails without replying when the commit never reaches the PR head" {
  printf 'behind\n' > "$FAKE_DIR/compare"

  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant resolved --sha "$SHA" --summary "fix"

  [ "$status" -eq 1 ]
  [[ "$output" == *"commit abcdef1 is not in the head of PR #7 after 3 attempts"* ]]
  ! grep -q 'replies\|reactions' "$FAKE_DIR/calls"
}

@test "closes a general comment without changes: 👎, reason and no thread resolution" {
  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 66 --kind general --variant no-change --reason "defecto preexistente: ya estaba en la base."

  [ "$status" -eq 0 ]
  grep -q 'repos/acme/docs/issues/comments/66/reactions -f content=-1' "$FAKE_DIR/calls"
  ! grep -q 'resolveReviewThread' "$FAKE_DIR/calls"
  published=$(cat "$FAKE_DIR/published")
  [[ "$published" == 'ℹ️ **Sin cambios.**'* ]]
  [[ "$published" == *'**Motivo:** defecto preexistente: ya estaba en la base.'* ]]
}

@test "a failed fix gets no reaction and no resolution" {
  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant failed

  [ "$status" -eq 0 ]
  ! grep -q 'reactions\|resolveReviewThread' "$FAKE_DIR/calls"
  [[ "$(cat "$FAKE_DIR/published")" == '⚠️ **No pude aplicar el fix**'* ]]
}

@test "edits a reply whose published body lost the template instead of posting another" {
  touch "$FAKE_DIR/mangle"

  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant resolved --sha "$SHA" --summary "fix"

  [ "$status" -eq 0 ]
  grep -q 'api -X PATCH repos/acme/docs/pulls/comments/900' "$FAKE_DIR/calls"
  [ "$(grep -c '/replies' "$FAKE_DIR/calls")" -eq 1 ]
}

@test "rejects incomplete usage before calling GitHub" {
  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant resolved --summary "fix"

  [ "$status" -eq 2 ]
  [[ "$output" == *"--variant resolved needs --sha and --summary"* ]]
  [ ! -s "$FAKE_DIR/calls" ]
}

@test "renders the reply from the skill templates, so editing a template changes what is published" {
  local copy="${BATS_TEST_TMPDIR}/closeout-copy"
  mkdir -p "$copy/scripts"
  cp "$CLOSEOUT" "$copy/scripts/closeout.sh"
  cp -r "${BATS_TEST_DIRNAME}/../templates" "$copy/templates"
  printf '%s\n' 'ℹ️ **Sin cambios.** Texto editado en la plantilla.' '' '<sub>🤖 Auto-fix de Codex · [run]({{run_url}})</sub>' > "$copy/templates/no-change.md"

  run bash "$copy/scripts/closeout.sh" --repo acme/docs --pr 7 --comment 66 --kind general --variant no-change

  [ "$status" -eq 0 ]
  [[ "$(cat "$FAKE_DIR/published")" == *'Texto editado en la plantilla.'* ]]
}

@test "drops the reason line and its blank line when there is no reason" {
  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 66 --kind general --variant no-change

  [ "$status" -eq 0 ]
  published=$(cat "$FAKE_DIR/published")
  [[ "$published" != *'Motivo'* ]]
  [ "$published" = $'ℹ️ **Sin cambios.** Revisé la sugerencia pero no requería cambios de código.\n\n<sub>🤖 Auto-fix de Codex</sub>' ]
}

@test "keeps the run link only when a run URL is given" {
  CLOSEOUT_RUN_URL="https://github.com/acme/docs/actions/runs/1" run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant failed

  [ "$status" -eq 0 ]
  [[ "$(cat "$FAKE_DIR/published")" == *'<sub>🤖 Auto-fix de Codex · [run](https://github.com/acme/docs/actions/runs/1)</sub>' ]]
}

@test "fails before publishing anything when no review thread holds the comment" {
  : > "$FAKE_DIR/threads"

  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant resolved --sha "$SHA" --summary "fix"

  [ "$status" -eq 1 ]
  [[ "$output" == *"no review thread holds comment 55 in PR #7 (repo acme/docs); nothing was published"* ]]
  ! grep -q 'reactions\|/replies' "$FAKE_DIR/calls"
}

@test "resolves the first thread the paginated lookup returns" {
  printf 'THREAD_A\nTHREAD_B\n' > "$FAKE_DIR/threads"

  run bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant no-change --reason "nit no bloqueante"

  [ "$status" -eq 0 ]
  grep -q 'resolveReviewThread.*threadId=THREAD_A' "$FAKE_DIR/calls"
  ! grep -q 'threadId=THREAD_B' "$FAKE_DIR/calls"
}

@test "keeps placeholders written in the reason or summary as literal text instead of expanding them" {
  run timeout 10 bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 66 --kind general --variant no-change --reason 'El placeholder {{motivo}} ya se completa y {{run_url}} queda igual.'

  [ "$status" -eq 0 ]
  [[ "$(cat "$FAKE_DIR/published")" == *'**Motivo:** El placeholder {{motivo}} ya se completa y {{run_url}} queda igual.'* ]]

  run timeout 10 bash "$CLOSEOUT" --repo acme/docs --pr 7 --comment 55 --kind inline --variant resolved --sha "$SHA" --summary 'el texto {{resumen}} y {{sha_corto}} no se reemplazan.'

  [ "$status" -eq 0 ]
  [[ "$(cat "$FAKE_DIR/published")" == *'**Qué cambió:** el texto {{resumen}} y {{sha_corto}} no se reemplazan.'* ]]
}
