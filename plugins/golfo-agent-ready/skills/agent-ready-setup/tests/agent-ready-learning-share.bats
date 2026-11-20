#!/usr/bin/env bats
# Learning (#156, 156h1): learn export writes what one repository learned without the quotes of the user,
# and learn harvest groups what several repositories learned, skipping the ones with learning.share off.
# A fake provider groups and generalizes the statements.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-agent-ready/skills/agent-ready-setup"
  cli="$skill_dir/scripts/agent-ready"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  mkdir -p "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CONFIG_HOME="$test_root/config"
  export XDG_CACHE_HOME="$test_root/cache"
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_ORGANIZATION_CONFIG="$test_root/organization.json"
  export AGENT_READY_LEARNING_SCHEDULER=none
  fake_provider
  cd "$test_root"
}

teardown() {
  cd /
  rm -rf "$test_root"
}

agent_ready() {
  run --separate-stderr python3 -B "$cli" "$@"
}

# A fake claude on PATH: call N saves its stdin in $FAKE_INPUTS/N.txt and answers $FAKE_RESPONSES/N.json
# as its structured output; a call without a response fails.
fake_provider() {
  fake_bin="$test_root/bin"
  export FAKE_INPUTS="$test_root/inputs"
  export FAKE_RESPONSES="$test_root/responses"
  mkdir -p "$fake_bin" "$FAKE_INPUTS" "$FAKE_RESPONSES"
  cat > "$fake_bin/fake-provider.py" <<'PY'
import json, os, sys
number = len(os.listdir(os.environ["FAKE_INPUTS"])) + 1
with open(os.path.join(os.environ["FAKE_INPUTS"], f"{number}.txt"), "wb") as saved:
    saved.write(sys.stdin.buffer.read())
response = os.path.join(os.environ["FAKE_RESPONSES"], f"{number}.json")
if not os.path.exists(response):
    sys.exit(1)
print(json.dumps({"structured_output": json.load(open(response, encoding="utf-8"))}))
PY
  cat > "$fake_bin/claude" <<EOF
#!/bin/bash
[[ "\$1" == -p ]] || exit 0
python3 "$fake_bin/fake-provider.py"
EOF
  chmod +x "$fake_bin/claude"
  export PATH="$fake_bin:$PATH"
  unset CI
}

respond() {
  printf '%s\n' "$2" > "$FAKE_RESPONSES/$1.json"
}

# repository NAME: a new Git repository in $test_root/NAME.
repository() {
  git -c init.defaultBranch=main init -q "$test_root/$1"
  git -C "$test_root/$1" config user.name Test
  git -C "$test_root/$1" config user.email test@example.invalid
  git -C "$test_root/$1" commit -q --allow-empty -m init
}

# learn_in NAME "statement" "quote": the repository learns an explicit instruction as a rule.
learn_in() {
  agent_ready learn record --project "$test_root/$1" --kind rule --statement "$2" --quote "$3" --explicit --session s1
  [ "$status" -eq 0 ]
  local id
  id="$(printf '%s' "$output" | head -n 1 | cut -d' ' -f1)"
  agent_ready learn apply --project "$test_root/$1" "$id"
  [ "$status" -eq 0 ]
}

# share_off NAME: the client of the repository leaves the harvest in its manifest.
share_off() {
  mkdir -p "$test_root/$1/.agents"
  printf '%s\n' '{"learning": {"share": false}}' > "$test_root/$1/.agents/agent-ready.json"
  git -C "$test_root/$1" add .agents/agent-ready.json
  git -C "$test_root/$1" commit -q -m "no harvest"
}

native_path() {
  if command -v cygpath >/dev/null; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

json_value() {
  printf '%s' "$output" | PYTHONIOENCODING=utf-8 python3 -c 'import json, sys; report = json.load(sys.stdin); print(eval(sys.argv[1]))' "$1" | tr -d '\r'
}

@test "learn export writes the statements of what was learned, never the quotes of the user" {
  repository acme
  learn_in acme "Records carry the case number in the header." "siempre el expediente 4471/2025 de Acme arriba"
  agent_ready learn record --project "$test_root/acme" --kind rule --statement "Dates use the long format." \
    --quote "esta vez fecha larga" --session s1
  agent_ready learn export --project "$test_root/acme" --output "$test_root/acme-export.json"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Exported 1 learned instructions of acme"* ]]
  ! grep -q "4471" "$test_root/acme-export.json"
  ! grep -q "esta vez" "$test_root/acme-export.json"
  grep -q "Records carry the case number in the header." "$test_root/acme-export.json"
  # Only what was learned: a candidate that waits stays in the repository.
  ! grep -q "Dates use the long format." "$test_root/acme-export.json"

  agent_ready learn export --project "$test_root/acme" --name client-a
  [ "$status" -eq 0 ]
  [ "$(json_value 'report["repository"], len(report["learned"]), report["learned"][0]["kind"]')" = "('client-a', 1, 'rule')" ]
}

@test "two repositories that learned the same propose one general candidate, without the names of the clients" {
  repository acme
  repository globex
  learn_in acme "Records carry the case number of Acme in the header." "siempre el expediente de Acme arriba"
  learn_in globex "Records carry the Globex file number in the header." "de ahora en más el número de Globex arriba"
  respond 1 '{"findings": [{"statement": "Records carry the case number in the header.", "kind": "rule", "key": "", "items": [0, 1], "reason": "Both ask for the case number in the header."}]}'

  agent_ready learn harvest --repos "$test_root/acme" "$test_root/globex" --json
  [ "$status" -eq 0 ]
  [ "$(json_value 'report["review"], len(report["candidates"])')" = "('grouped by the review', 1)" ]
  [ "$(json_value 'report["candidates"][0]["statement"], report["candidates"][0]["repositories"]')" = \
    "('Records carry the case number in the header.', ['acme', 'globex'])" ]
  [[ "$(json_value 'report["candidates"][0]["id"]')" == harvest-* ]]
  # The provider sees each repository by an anonymous label, and never a quote.
  grep -q 'project="repo-1"' "$FAKE_INPUTS/1.txt"
  grep -q 'project="repo-2"' "$FAKE_INPUTS/1.txt"
  ! grep -q "$test_root" "$FAKE_INPUTS/1.txt"
  ! grep -qi "siempre\|ahora en m" "$FAKE_INPUTS/1.txt"
  # The result stays in the cache of the developer; the repositories do not change.
  [ -f "$XDG_CACHE_HOME/agent-ready-setup/learning-harvest/latest.json" ]
  [ -z "$(git -C "$test_root/acme" status --porcelain)" ]
  [ -z "$(git -C "$test_root/globex" status --porcelain)" ]

  cp "$FAKE_RESPONSES/1.json" "$FAKE_RESPONSES/2.json"
  agent_ready learn harvest --repos "$test_root/acme" "$test_root/globex"
  [ "$status" -eq 0 ]
  [[ "$output" == *"acme  read, 1 learned"* ]]
  [[ "$output" == *"rule  in acme, globex"* ]]
  [[ "$output" == *"Records carry the case number in the header."* ]]
}

@test "a repository with learning.share off is not read" {
  repository acme
  repository globex
  learn_in acme "Records carry the case number in the header." "siempre arriba"
  learn_in globex "Records carry the case number in the header." "siempre arriba"
  share_off globex

  agent_ready learn harvest --repos "$test_root/acme" "$test_root/globex" --json
  [ "$status" -eq 0 ]
  [ "$(json_value '[(source["name"], source["status"], source["learned"]) for source in report["sources"]]')" = \
    "[('acme', 'read', 1), ('globex', 'share off', 0)]" ]
  [ "$(json_value 'len(report["candidates"])')" = "0" ]
  # One repository is not several: no provider call.
  [ -z "$(ls "$FAKE_INPUTS")" ]
}

@test "without a review harvest proposes only what the repositories learned word for word" {
  repository acme
  repository globex
  repository initech
  learn_in acme "Records carry the case number in the header." "siempre arriba"
  learn_in globex "records carry the case number in the header" "siempre arriba"
  learn_in initech "Dates use the long format." "siempre fecha larga"
  learn_in acme "Dates use the short format." "siempre fecha corta"
  export CI=true
  agent_ready learn harvest --repos "$test_root/acme" "$test_root/globex" "$test_root/initech" --json
  [ "$status" -eq 0 ]
  [ "$(json_value 'report["review"], report["reviewProblem"]')" = "('exact matches only', 'no review under CI')" ]
  [ "$(json_value '[(candidate["statement"], candidate["repositories"]) for candidate in report["candidates"]]')" = \
    "[('Records carry the case number in the header.', ['acme', 'globex'])]" ]
  [ -z "$(ls "$FAKE_INPUTS")" ]

  # A provider that fails gives the same.
  unset CI
  agent_ready learn harvest --repos "$test_root/acme" "$test_root/globex" "$test_root/initech" --json
  [ "$status" -eq 0 ]
  [ "$(json_value 'report["reviewProblem"], len(report["candidates"])')" = "('the provider claude failed', 1)" ]
}

@test "a group of the review is kept only with enough repositories and valid statements" {
  repository acme
  repository globex
  learn_in acme "Records carry the case number in the header." "siempre arriba"
  learn_in acme "Records end with the date." "siempre la fecha"
  learn_in globex "Records carry the file number in the header." "siempre arriba"
  # One group of one repository, one with an index that does not exist, one with two lines, and a good one
  # that reuses a statement of the first.
  respond 1 '{"findings": [
    {"statement": "Records end with the date.", "kind": "rule", "key": "", "items": [0, 1], "reason": "one repository"},
    {"statement": "Records carry a number.", "kind": "rule", "key": "", "items": [0, 7], "reason": "bad index"},
    {"statement": "Records carry\nthe number.", "kind": "rule", "key": "", "items": [0, 2], "reason": "two lines"},
    {"statement": "Records carry the case number in the header.", "kind": "rule", "key": "records.header", "items": [0, 2], "reason": "same"}]}'
  agent_ready learn harvest --repos "$test_root/acme" "$test_root/globex" --json
  [ "$status" -eq 0 ]
  [ "$(json_value '[(candidate["statement"], candidate.get("key"), candidate["repositories"]) for candidate in report["candidates"]]')" = \
    "[('Records carry the case number in the header.', 'records.header', ['acme', 'globex'])]" ]
}

@test "harvest reads the export a client handed over, and only its statements" {
  repository acme
  learn_in acme "Records carry the case number in the header." "siempre arriba"
  cat > "$test_root/client-b.json" <<'JSON'
{"format": "agent-ready-learning-export", "version": 1, "repository": "client-b", "exportedAt": "2026-11-01",
 "learned": [{"statement": "Records carry the case number in the header.", "kind": "rule",
              "evidence": [{"quote": "expediente 9921 de Globex"}]}]}
JSON
  export CI=true
  agent_ready learn harvest --repos "$test_root/acme" --export "$test_root/client-b.json" --json
  [ "$status" -eq 0 ]
  [ "$(json_value '[(candidate["statement"], candidate["repositories"]) for candidate in report["candidates"]]')" = \
    "[('Records carry the case number in the header.', ['acme', 'client-b'])]" ]
  ! grep -q "9921" "$XDG_CACHE_HOME/agent-ready-setup/learning-harvest/latest.json"

  printf '%s\n' '{"format": "something-else", "version": 1, "learned": []}' > "$test_root/bad.json"
  agent_ready learn harvest --export "$test_root/bad.json"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"is not an export of agent-ready learn export"* ]]
}

@test "harvest takes the repositories of the user configuration, and fails without any" {
  repository acme
  repository globex
  learn_in acme "Records carry the case number in the header." "siempre arriba"
  learn_in globex "Records carry the case number in the header." "siempre arriba"
  agent_ready learn harvest
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"no repository to harvest"* ]]

  mkdir -p "$XDG_CONFIG_HOME/agent-ready-setup"
  # A path inside a file is not converted for Windows Python, as an argument is.
  printf '{"learning": {"harvest": {"repos": ["%s", "%s", "%s"]}}}\n' "$(native_path "$test_root/acme")" \
    "$(native_path "$test_root/globex")" "$(native_path "$test_root/missing")" \
    > "$XDG_CONFIG_HOME/agent-ready-setup/config.json"
  export CI=true
  agent_ready learn harvest --json
  [ "$status" -eq 0 ]
  [ "$(json_value '[(source["name"], source["status"]) for source in report["sources"]]')" = \
    "[('acme', 'read'), ('globex', 'read'), ('missing', 'not found')]" ]
  [ "$(json_value 'len(report["candidates"])')" = "1" ]

  # A repository cannot add itself to the list of the developer.
  mkdir -p "$test_root/acme/.agents"
  printf '%s\n' '{"learning": {"harvest": {"repos": ["/somewhere"]}}}' > "$test_root/acme/.agents/agent-ready.json"
  agent_ready learn harvest --project "$test_root/acme" --json
  [ "$status" -ne 0 ]
}
