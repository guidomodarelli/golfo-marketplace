#!/usr/bin/env bats
# CI files per provider (ci.provider, agent-ready ci setup): the neutral script every provider
# calls, the GitHub Actions workflow, the GitLab job with its managed include, the Jenkins stage to
# copy, how changing the provider retires the files of the previous one, and the script itself.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-agent-ready/skills/agent-ready-setup"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
  source "$BATS_TEST_DIRNAME/content-pack.bash"
  use_content_pack
  export XDG_CONFIG_HOME="$test_root/config"
  export HOME="$test_root/home"
  mkdir -p "$HOME"
  export AGENT_READY_SETUP_ORGANIZATION_CONFIG="$test_root/organization/config.json"
  export AGENT_READY_SETUP_TOOLS=0
  export AGENT_READY_SETUP_ACTIVE_PROVIDER=claude
  export GIT_CONFIG_GLOBAL="$test_root/gitconfig"
  git config --global user.name Test
  git config --global user.email test@example.invalid
  git config --global init.defaultBranch main
  git config --global core.autocrlf false
  unset CI CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES
  unset AGENT_READY_GIT_TOKEN AGENT_READY_GIT_URL AGENT_READY_MARKETPLACE_URL
  for provider_cli in claude codex; do
    printf '#!/bin/bash\nexit 0\n' > "$fake_bin/$provider_cli"
    chmod +x "$fake_bin/$provider_cli"
  done
  git -C "$project_dir" init -q
  cd "$project_dir"
  printf '{}\n' > package.json
  write_manifest '{"profiles": ["node"]}'
  script=.agents/ci/agent-ready-check.sh
  workflow=.github/workflows/agent-ready.yml
}

teardown() {
  cd "$repository_root"
  local removal_attempt
  for removal_attempt in $(seq 1 50); do
    rm -rf "$test_root" 2>/dev/null && return 0
    sleep 0.2
  done
  rm -rf "$test_root"
}

write_manifest() {
  mkdir -p .agents
  printf '%s\n' "$1" > .agents/agent-ready.json
}

run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready" "$@"
}

json_value() {
  python3 - "$1" "$2" <<'PY'
import json, sys
document = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps(eval(sys.argv[2], {"document": document})))
PY
}

@test "ci setup with GitHub writes ci.provider and creates the script and the workflow, without touching the selection" {
  run_cli ci setup --provider github
  [ "$status" -eq 0 ]
  [ -f "$script" ]
  grep -q 'sh .agents/ci/agent-ready-check.sh' "$workflow"
  [ "$(json_value .agents/agent-ready.json 'document["ci"]["provider"]')" = '"github"' ]
  [ "$(json_value .agents/agent-ready.json 'document["profiles"]')" = '["node"]' ]
  [ "$(json_value .agents/agent-ready.lock.json 'document["assets"][".github/workflows/agent-ready.yml"]["profile"]')" = '"ci-github"' ]
  [[ "$stderr" == *"AGENT_READY_GIT_TOKEN"* ]]
  run_cli check --offline
  [ "$status" -eq 0 ]
}

@test "a versioned file of .engram/ fails the check with private-files, and no ci key can skip it or soften it" {
  run_cli apply
  [ "$status" -eq 0 ]
  mkdir -p .engram/chunks
  printf 'chunk\n' > .engram/chunks/0001.jsonl.gz
  git add -f .engram/chunks/0001.jsonl.gz

  run_cli check --offline
  [ "$status" -eq 8 ]
  [[ "$output" == *"Agent Ready check: files of the memory of Engram are versioned"* ]]
  [[ "$output" == *".engram/chunks/0001.jsonl.gz is a file of the memory of Engram: remove it from Git with git rm --cached"* ]]
  run_cli check --offline --format json
  [ "$status" -eq 8 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; data = json.load(sys.stdin); print(data["status"], data["exitStatus"])' | tr -d '\r')" = "private-files 8" ]

  # Neither a warn mode nor turning the check off lets the memory into the repository.
  python3 - <<'PY'
import json
path = ".agents/agent-ready.json"
manifest = json.load(open(path))
manifest["ci"] = {"mode": "warn", "enabled": False}
json.dump(manifest, open(path, "w"), indent=2)
PY
  run_cli check --offline
  [ "$status" -eq 8 ]

  # Only staged or committed files count: once out of Git, the check goes on as usual.
  git rm -q --cached .engram/chunks/0001.jsonl.gz
  run_cli check --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"skipped"* ]]
}

@test "changing ci.provider without an apply leaves the check outdated, and the apply follows it" {
  run_cli ci setup --provider github
  [ "$status" -eq 0 ]
  run_cli ci setup --provider generic --no-apply
  [ "$status" -eq 0 ]
  [ -f "$workflow" ]
  run_cli check --offline
  [ "$status" -eq 4 ]
  run_cli apply
  [ "$status" -eq 0 ]
  [ ! -e "$workflow" ]
  [ -f "$script" ]
  run_cli check --offline
  [ "$status" -eq 0 ]
}

@test "GitLab gets its own job and only a managed include in .gitlab-ci.yml, and GitHub's files are retired" {
  printf 'stages:\n  - build\n\nbuild:\n  stage: build\n  script:\n    - make\n' > .gitlab-ci.yml
  run_cli ci setup --provider github
  [ "$status" -eq 0 ]
  run_cli ci setup --provider gitlab
  [ "$status" -eq 0 ]
  [ ! -e "$workflow" ]
  grep -q 'sh .agents/ci/agent-ready-check.sh' .agents/ci/gitlab-ci.yml
  # The project declares only a build stage: the job goes to .pre, which every pipeline has.
  grep -qx '  stage: .pre' .agents/ci/gitlab-ci.yml
  grep -qx '# BEGIN AGENT-READY MANAGED: ci-gitlab' .gitlab-ci.yml
  grep -qx '  - local: .agents/ci/gitlab-ci.yml' .gitlab-ci.yml
  grep -qx '    - make' .gitlab-ci.yml
  run_cli ci setup --provider none
  [ "$status" -eq 0 ]
  [ ! -e .agents/ci/gitlab-ci.yml ]
  [ ! -e "$script" ]
  ! grep -q 'AGENT-READY MANAGED' .gitlab-ci.yml
  grep -qx '    - make' .gitlab-ci.yml
}

@test "Jenkins never edits the Jenkinsfile: the stage is printed and kept in .agents/ci" {
  printf "pipeline {\n  agent any\n}\n" > Jenkinsfile
  cp Jenkinsfile "$test_root/Jenkinsfile.before"
  run_cli ci setup --provider jenkins
  [ "$status" -eq 0 ]
  cmp Jenkinsfile "$test_root/Jenkinsfile.before"
  [[ "$output" == *"stage('Agent Ready')"* ]]
  grep -q 'sh .agents/ci/agent-ready-check.sh' .agents/ci/jenkins-stage.groovy
  [ -f "$script" ]
}

@test "none creates nothing and is remembered as the choice" {
  run_cli ci setup --provider none
  [ "$status" -eq 0 ]
  [ ! -e .agents/ci ]
  [ ! -e "$workflow" ]
  [ "$(json_value .agents/agent-ready.json 'document["ci"]["provider"]')" = '"none"' ]
}

@test "ci setup without a provider fails with the valid values and writes nothing" {
  cp .agents/agent-ready.json "$test_root/manifest.before"
  run_cli ci setup
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"--provider github|gitlab|jenkins|generic|none"* ]]
  cmp .agents/agent-ready.json "$test_root/manifest.before"
  run_cli ci setup --provider travis
  [ "$status" -eq 2 ]
}

@test "a selection that names a CI profile is rejected with the command that picks it" {
  run_cli apply --profiles node,ci-github
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"agent-ready ci setup --provider github"* ]]
  [ ! -e "$workflow" ]
}

@test "the CI script clones the engine outside the repository, passes the token through the environment and keeps the exit status" {
  marketplace="$test_root/marketplace"
  engine_dir="$marketplace/plugins/golfo-agent-ready/skills/agent-ready-setup/scripts"
  mkdir -p "$engine_dir"
  cat > "$engine_dir/agent-ready" <<'PY'
import os, sys
print("args=" + " ".join(sys.argv[1:]))
print("cwd-is-project=" + str(os.path.abspath(os.getcwd()) == os.path.abspath(os.environ["PROJECT_DIR"])))
print("engine-outside=" + str(not os.path.abspath(__file__).startswith(os.path.abspath(os.environ["PROJECT_DIR"]))))
key = os.environ.get("GIT_CONFIG_KEY_0", "")
print("rewrites=" + key.replace(os.environ.get("AGENT_READY_GIT_TOKEN", "<none>"), "<token>"))
sys.exit(4)
PY
  git -C "$marketplace" init -q
  git -C "$marketplace" add -A
  git -C "$marketplace" commit -qm engine
  run_cli ci setup --provider generic
  [ "$status" -eq 0 ]
  run env PROJECT_DIR="$project_dir" AGENT_READY_MARKETPLACE_URL="$marketplace" \
    AGENT_READY_GIT_TOKEN=secret-value AGENT_READY_GIT_URL=https://git.example.com/acme/ sh "$script" --offline
  [ "$status" -eq 4 ]
  [[ "$output" == *"args=check --offline"* ]]
  [[ "$output" == *"cwd-is-project=True"* ]]
  [[ "$output" == *"engine-outside=True"* ]]
  [[ "$output" == *"rewrites=url.https://oauth2:<token>@git.example.com/acme/.insteadOf"* ]]
  ! grep -rq secret-value .agents
}

@test "the CI profiles are not offered for the selection: neither profiles list nor the unknown profile error name them" {
  run_cli profiles list
  [ "$status" -eq 0 ]
  [[ "$output" == *"node"* ]]
  [[ "$output" != *"ci-github"* ]]
  run_cli apply --profiles node,nope
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"unknown profile 'nope'"* ]]
  [[ "$output$stderr" != *"ci-github"* ]]
}

@test "check fails on a manifest whose selection names a CI profile, as apply does" {
  run_cli apply
  [ "$status" -eq 0 ]
  write_manifest '{"profiles": ["node", "ci-github"]}'
  run_cli check --offline
  [ "$status" -ne 0 ]
  [[ "$output$stderr" == *"agent-ready ci setup --provider github"* ]]
}

@test "the CI script skips without the network when the manifest turns the check off" {
  run_cli ci setup --provider generic
  [ "$status" -eq 0 ]
  write_manifest '{"profiles": ["node"], "ci": {"provider": "generic", "enabled": false}}'
  run env AGENT_READY_MARKETPLACE_URL="$test_root/unreachable" sh "$script"
  [ "$status" -eq 0 ]
  [[ "$output" == *"skipped"* ]]
}

@test "the GitHub workflow does not keep the checkout token, which would replace the token of private packs" {
  run_cli ci setup --provider github
  [ "$status" -eq 0 ]
  grep -qx '          persist-credentials: false' "$workflow"
}

# Run the CLI in a real terminal (a pseudoterminal) and type the answers; POSIX only.
run_cli_in_terminal() {
  local answers="$1"
  shift
  run --separate-stderr env PATH="$fake_bin:$PATH" TERM=xterm python3 - "$answers" python3 "$skill_dir/scripts/agent-ready" "$@" <<'PY'
import os, pty, select, sys
answers = sys.argv[1].encode().decode("unicode_escape").encode()
pid, descriptor = pty.fork()
if pid == 0:
    os.execvp(sys.argv[2], sys.argv[2:])
os.write(descriptor, answers)
output = b""
while True:
    ready, _, _ = select.select([descriptor], [], [], 120)
    if not ready:
        break
    try:
        chunk = os.read(descriptor, 4096)
    except OSError:
        break
    if not chunk:
        break
    output += chunk
_, wait_status = os.waitpid(pid, 0)
sys.stdout.write(output.decode("utf-8", "replace"))
sys.exit(os.waitstatus_to_exitcode(wait_status))
PY
}

skip_without_pseudoterminal() {
  if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
    skip "needs a POSIX pseudoterminal"
  fi
}

@test "ci detect names the provider whose files the repository has, ignoring the workflow agent-ready-setup writes" {
  run_cli ci detect
  [ "$status" -eq 0 ]
  [ "$output" = "none" ]
  mkdir -p .github/workflows
  printf 'name: Agent Ready\n' > .github/workflows/agent-ready.yml
  run_cli ci detect
  [ "$output" = "none" ]
  printf "pipeline {\n}\n" > Jenkinsfile
  run_cli ci detect
  [ "$output" = $'jenkins\tJenkinsfile' ]
  printf 'name: Build\n' > .github/workflows/build.yml
  run_cli ci detect --json
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; print(json.load(sys.stdin)["evidence"])')" = ".github/workflows/build.yml" ]
}

@test "init without a terminal never asks for the CI provider: it stays unchosen, and --ci-provider chooses it" {
  rm .agents/agent-ready.json
  run_cli init --profiles node --yes
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json 'document.get("ci")')" = "null" ]
  [ ! -e "$script" ]
  rm .agents/agent-ready.json
  run_cli init --profiles node --ci-provider github --yes
  [ "$status" -eq 0 ]
  [ "$(json_value .agents/agent-ready.json 'document["ci"]["provider"]')" = '"github"' ]
  [ -f "$workflow" ]
}

@test "ci setup with --no-input fails instead of asking" {
  run_cli ci setup --no-input
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"there is no terminal to ask"* ]]
}

@test "with a terminal, ci setup asks once with the detected provider as the default and prints the equivalent command" {
  skip_without_pseudoterminal
  printf "pipeline {\n}\n" > Jenkinsfile
  run_cli_in_terminal '\n' ci setup
  [ "$status" -eq 0 ]
  [[ "$output" == *"Detected CI: jenkins (Jenkinsfile)"* ]]
  [[ "$output" == *"CI provider (jenkins|github|gitlab|generic|none) [jenkins]"* ]]
  [[ "$output" == *"Equivalent command: agent-ready ci setup --provider jenkins"* ]]
  [ "$(json_value .agents/agent-ready.json 'document["ci"]["provider"]')" = '"jenkins"' ]
  [ -f .agents/ci/jenkins-stage.groovy ]
}

@test "the full wizard of init asks for the CI provider, and none is remembered so it is not asked again" {
  skip_without_pseudoterminal
  rm .agents/agent-ready.json
  run_cli_in_terminal 'node\n\nnone\ny\n' init
  [ "$status" -eq 0 ]
  [[ "$output" == *"CI provider ("* ]]
  [[ "$output" == *"--ci-provider none"* ]]
  [ "$(json_value .agents/agent-ready.json 'document["ci"]["provider"]')" = '"none"' ]
  [ ! -e .agents/ci ]
}

@test "init in a repository without stack signals asks what it is for, and other leaves the empty selection" {
  skip_without_pseudoterminal
  rm .agents/agent-ready.json package.json
  # An answer outside the list is asked again; other makes none the default of the profiles.
  run_cli_in_terminal 'web\nother\n\n\nnone\ny\n' init
  [ "$status" -eq 0 ]
  [[ "$output" == *"What is this repository for? (code|other)"* ]]
  [[ "$output" == *"answer one of code, other"* ]]
  [[ "$output" == *"Without code the core applies"* ]]
  [[ "$output" == *"Equivalent command: agent-ready init --profiles none"* ]]
  [ "$(json_value .agents/agent-ready.json 'document["profiles"]')" = '[]' ]
}

@test "check lints the rule files that use atomic rules under ci.conflicts.structural, and skips prose ones" {
  mkdir -p .agents/rules/workspaces/apps/web
  # A prose file the project never migrated: its bullets are not lint errors of the check.
  printf '%s\n' '# Team notes' '' '- Keep the changelog short.' > .agents/rules/team-notes.md
  printf '%s\n' '# Team' '' '<!-- rule id=team/logger -->' '- Log with pino.' > .agents/rules/team.md
  # A workspace file of the project is linted with the root's rules, which it loads too.
  printf '%s\n' '# Web' '' '<!-- rule id=web/logger requires=team/logger -->' '- Log the route.' \
    > .agents/rules/workspaces/apps/web/team.md
  run_cli apply
  [ "$status" -eq 0 ]
  run_cli check --offline
  [ "$status" -eq 0 ]
  [[ "$output" != *"Rules lint"* ]]

  # A file that adopted the format is linted: an untagged bullet and a statement that chains two decisions.
  printf '%s\n' '' '- Log every request.' '' '<!-- rule id=team/errors -->' '- Wrap errors. Never swallow them.' \
    >> .agents/rules/team.md
  run_cli check --offline
  [ "$status" -eq 6 ]
  [[ "$output" == *"Rules lint (ci.conflicts.structural: fail):"* ]]
  [[ "$output" == *".agents/rules/team.md:6: error: [untagged-rule]"* ]]
  [[ "$output" == *"[several-decisions] team/errors"* ]]
  [[ "$output" != *"team-notes.md"* ]]
  [[ "$output" != *"duplicate-id"* ]]
  run_cli check --offline --format json
  [ "$status" -eq 6 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; print(len(json.load(sys.stdin)["conflicts"]["rules"]))' | tr -d '\r')" = "2" ]

  # warn lists them and passes; rules.enabled false does not lint.
  run_cli config set ci.conflicts.structural warn
  run_cli check --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"Rules lint (ci.conflicts.structural: warn):"* ]]
  run_cli config set ci.conflicts.structural fail
  run_cli config set rules.enabled false
  run_cli check --offline
  [ "$status" -eq 0 ]
  [[ "$output" != *"Rules lint"* ]]
}

@test "the rules lint of check keeps two sources apart and a workspace whole, with its rule folders" {
  mkdir -p .agents/rules/workspaces/apps/web/testing
  printf '%s\n' '<!-- rule id=testing/runner -->' '- Use Vitest.' > .agents/rules/alpha-testing.md
  printf '%s\n' '<!-- rule id=testing/runner -->' '- Use the runner of the project.' > .agents/rules/beta-testing.md
  printf '%s\n' '<!-- rule id=web/base -->' '- Keep pages small.' > .agents/rules/workspaces/apps/web/base.md
  printf '%s\n' '<!-- rule id=web/behavior requires=web/base -->' '- Test behavior.' \
    > .agents/rules/workspaces/apps/web/testing/behavior.md
  run python3 -B - "$skill_dir/scripts" "$PWD" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
import agent_ready_cli_rules
from agent_ready_config import resolve_configuration
project = sys.argv[2]
# Two packs publish testing/runner in files of their own, and the workspace apps/web has a rule folder.
lock = {"assets": {
    ".agents/rules/alpha-testing.md": {"profile": "alpha/testing", "sha256": "x", "state": "applied"},
    ".agents/rules/beta-testing.md": {"profile": "beta/testing", "sha256": "x", "state": "applied"},
    ".agents/rules/workspaces/apps/web/base.md": {"profile": "alpha/web", "sha256": "x", "workspace": "apps/web"},
    ".agents/rules/workspaces/apps/web/testing/behavior.md": {"profile": "alpha/web", "sha256": "x",
                                                              "workspace": "apps/web"}},
    "workspaces": {"apps/web": {"profiles": ["alpha/web"], "own": []}}}
with open(os.path.join(project, ".agents", "agent-ready.lock.json"), "w", encoding="utf-8") as handle:
    json.dump(lock, handle)
errors = agent_ready_cli_rules.adopted_rule_errors(project, resolve_configuration(project))
assert errors == [], [error.render() for error in errors]

# A workspace rule may require a root rule of its source, which the workspace loads too; and a rule may
# require one that another rule replaces with overrides, which is not in any file.
with open(os.path.join(project, ".agents", "rules", "workspaces", "apps", "web", "errors.md"), "w", encoding="utf-8") as handle:
    handle.write("<!-- rule id=web/errors requires=testing/runner -->\n- Report errors.\n")
lock["assets"][".agents/rules/workspaces/apps/web/errors.md"] = {"profile": "alpha/web", "sha256": "x",
                                                                 "workspace": "apps/web"}
with open(os.path.join(project, ".agents", "rules", "alpha-logging.md"), "w", encoding="utf-8") as handle:
    handle.write("<!-- rule id=logging/errors requires=logging/logger -->\n- Log errors.\n")
with open(os.path.join(project, ".agents", "rules", "team.md"), "w", encoding="utf-8") as handle:
    handle.write("<!-- rule id=team/logger overrides=alpha:logging/logger -->\n- Log with pino.\n")
lock["assets"][".agents/rules/alpha-logging.md"] = {"profile": "alpha/testing", "sha256": "x"}
with open(os.path.join(project, ".agents", "agent-ready.lock.json"), "w", encoding="utf-8") as handle:
    json.dump(lock, handle)
errors = agent_ready_cli_rules.adopted_rule_errors(project, resolve_configuration(project))
assert errors == [], [error.render() for error in errors]

# The same id twice in one source is still an error, reported once, on the second file.
lock["assets"][".agents/rules/beta-testing.md"]["profile"] = "alpha/other"
with open(os.path.join(project, ".agents", "agent-ready.lock.json"), "w", encoding="utf-8") as handle:
    json.dump(lock, handle)
errors = agent_ready_cli_rules.adopted_rule_errors(project, resolve_configuration(project))
assert [(error.code, error.path) for error in errors] == [("duplicate-id", ".agents/rules/beta-testing.md")],     [error.render() for error in errors]
PY
  [ "$status" -eq 0 ]
}

@test "agent-ready conflicts exits 6 on a conflict, and check fails on it under ci.conflicts.structural" {
  printf '{"devDependencies": {"jest": "29"}}\n' > package.json
  mkdir -p .agents/rules
  printf -- '---\nassumes:\n  testRunner: vitest\n---\n# Ours\n' > .agents/rules/ours.md
  run_cli conflicts --offline
  [ "$status" -eq 6 ]
  [[ "$output" == *"! .agents/rules/ours.md (project) assumes test runner vitest, but the repository uses jest (package.json)"* ]]
  run_cli conflicts --offline --json
  [ "$status" -eq 6 ]
  [ "$(printf '%s' "$output" | python3 -c 'import json, sys; print(json.load(sys.stdin)["found"])' | tr -d '\r')" = "True" ]

  run_cli apply
  [ "$status" -eq 0 ]
  run_cli check --offline
  [ "$status" -eq 6 ]
  [[ "$output" == *"Conflicts (ci.conflicts.structural: fail):"* ]]

  # warn lists them and passes; off does not look.
  run_cli config set ci.conflicts.structural warn
  run_cli check --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"Conflicts (ci.conflicts.structural: warn):"* ]]
  run_cli config set ci.conflicts.structural off
  run_cli check --offline
  [ "$status" -eq 0 ]
  [[ "$output" != *"Conflicts ("* ]]

  rm .agents/rules/ours.md
  run_cli conflicts --offline
  [ "$status" -eq 0 ]
  [[ "$output" == *"No conflicts between the profiles"* ]]
}
