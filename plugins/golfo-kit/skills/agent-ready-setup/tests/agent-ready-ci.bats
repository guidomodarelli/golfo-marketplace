#!/usr/bin/env bats
# CI files per provider (ci.provider, agent-ready ci setup): the neutral script every provider
# calls, the GitHub Actions workflow, the GitLab job with its managed include, the Jenkins stage to
# copy, how changing the provider retires the files of the previous one, and the script itself.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  export MSYS="${MSYS:+$MSYS }winsymlinks:nativestrict"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  mkdir -p "$project_dir" "$fake_bin" "$test_root/tmp"
  export TMPDIR="$test_root/tmp"
  export XDG_CACHE_HOME="$test_root/cache"
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
  engine_dir="$marketplace/plugins/golfo-kit/skills/agent-ready-setup/scripts"
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
