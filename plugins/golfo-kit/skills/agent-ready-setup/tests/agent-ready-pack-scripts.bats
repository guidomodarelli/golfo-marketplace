#!/usr/bin/env bats
# Scripts a profile pack declares: an apply runs the install scripts that are new or changed and
# every post-apply script that the security policy allows; the session hook runs the session-start
# ones in the background, only as the last apply recorded them. Scripts write markers in the
# project, so each test sees exactly what ran.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  example_pack="$skill_dir/assets/examples/acme-profile-pack"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
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
  git config --global protocol.file.allow always
  # GitHub Actions sets CI; these tests are about a developer machine unless they say otherwise.
  unset CI CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES
  for provider_cli in claude codex; do
    printf '#!/bin/bash\nexit 0\n' > "$fake_bin/$provider_cli"
    chmod +x "$fake_bin/$provider_cli"
  done
  publish_pack 'echo install >> ran-install' 'echo post-apply >> ran-post-apply' 60
  git -C "$project_dir" init -q
  cd "$project_dir"
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["acme/kafka-interno"], "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme#main"}]}}' > .agents/agent-ready.json
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

native_path() {
  (cd "$1" && (pwd -W 2>/dev/null || pwd))
}

# The example pack with an install, a post-apply and a session-start script of the given bodies.
publish_pack() {
  local install_body="$1" post_apply_body="$2" install_timeout="$3" session_body="${4:-echo session >> ran-session-start}"
  local pack_repository="$test_root/repositories/acme"
  mkdir -p "$(dirname "$pack_repository")"
  if [ ! -d "$pack_repository" ]; then
    cp -R "$example_pack" "$pack_repository"
    git -C "$pack_repository" init -q
  fi
  mkdir -p "$pack_repository/scripts"
  printf '#!/bin/bash\n%s\n' "$install_body" > "$pack_repository/scripts/install.sh"
  printf '#!/bin/bash\n%s\n' "$post_apply_body" > "$pack_repository/scripts/post-apply.sh"
  printf '#!/bin/bash\n%s\n' "$session_body" > "$pack_repository/scripts/session.sh"
  python3 - "$pack_repository/agent-ready-pack.json" "$install_timeout" <<'PY'
import json, sys
path, timeout = sys.argv[1], int(sys.argv[2])
catalog = json.load(open(path, encoding="utf-8"))
catalog["profiles"]["kafka-interno"]["scripts"] = [
    {"event": "install", "path": "scripts/install.sh", "interpreter": "bash", "timeoutSeconds": timeout},
    {"event": "post-apply", "path": "scripts/post-apply.sh", "interpreter": "bash", "timeoutSeconds": 60},
    {"event": "session-start", "path": "scripts/session.sh", "interpreter": "bash", "timeoutSeconds": 60},
]
json.dump(catalog, open(path, "w", encoding="utf-8"), indent=2)
PY
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm scripts
  git config --global "url.file:///$(native_path "$pack_repository" | sed 's#^/##').insteadOf" "https://packs.example.invalid/acme"
}

run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready" "$@"
}

# Merge a JSON object into the configuration of the user.
set_user_configuration() {
  python3 - "$XDG_CONFIG_HOME/agent-ready-setup/config.json" "$1" <<'PY'
import json, os, sys
path, addition = sys.argv[1], json.loads(sys.argv[2])
current = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
def merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge(target[key], value)
        else:
            target[key] = value
merge(current, addition)
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(current, open(path, "w", encoding="utf-8"), indent=2)
PY
}

count_lines() {
  if [ -f "$1" ]; then wc -l < "$1" | tr -d ' '; else echo 0; fi
}

@test "an apply runs install once and post-apply every time, from the project root" {
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"Script of a profile pack ran: install acme/scripts/install.sh"* ]]
  [[ "$stderr" == *"Script of a profile pack ran: post-apply acme/scripts/post-apply.sh"* ]]
  [ "$(count_lines ran-install)" = 1 ] && [ "$(count_lines ran-post-apply)" = 1 ]
  [ ! -e ran-session-start ]
  python3 - "$(git rev-parse --absolute-git-dir)/agent-ready/scripts/installed.json" <<'PY'
import json, sys
entry = json.load(open(".agents/agent-ready.lock.json", encoding="utf-8"))["scripts"]["install:acme/scripts/install.sh"]
assert len(entry["sha256"]) == 64 and "installed" not in entry, entry
# Whether it ran is of this checkout, never of the committed lock.
assert json.load(open(sys.argv[1], encoding="utf-8"))["install:acme/scripts/install.sh"] == entry["sha256"]
PY

  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(count_lines ran-install)" = 1 ] && [ "$(count_lines ran-post-apply)" = 2 ]
}

@test "a fresh checkout with the committed lock runs install for itself" {
  run_cli trust add acme
  run_cli apply
  [ "$(count_lines ran-install)" = 1 ]
  # A clone has the lock of the repository and nothing of this checkout's Git directory.
  rm -f "$(git rev-parse --absolute-git-dir)/agent-ready/scripts/installed.json"
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(count_lines ran-install)" = 2 ]
}

@test "a changed install script runs again" {
  run_cli trust add acme
  run_cli apply
  publish_pack 'echo install-v2 >> ran-install' 'echo post-apply >> ran-post-apply' 60
  run_cli update
  [ "$status" -eq 0 ]
  [ "$(count_lines ran-install)" = 2 ]
  grep -q install-v2 ran-install
}

@test "a script that fails is reported, the apply is not complete, and install runs again next time" {
  publish_pack 'echo trying >> ran-install; exit 3' 'echo post-apply >> ran-post-apply' 60
  run_cli trust add acme
  run_cli apply
  [[ "$stderr" == *"ERROR: script of a profile pack failed: install acme/scripts/install.sh: exited with 3"* ]]
  [[ "$stderr" == *"partial: a script of a profile pack failed"* ]]
  run_cli apply
  [ "$(count_lines ran-install)" = 2 ]
}

@test "a script that outlives its timeout is stopped" {
  publish_pack 'sleep 30; echo late >> ran-install' 'echo post-apply >> ran-post-apply' 1
  run_cli trust add acme
  started=$SECONDS
  run_cli apply
  [ $((SECONDS - started)) -lt 25 ]
  [[ "$stderr" == *"install acme/scripts/install.sh: did not finish in 1 seconds and was stopped"* ]]
  sleep 1
  [ ! -e ran-install ]
}

@test "without trust, in automated reviews and in plan nothing runs" {
  run_cli apply
  [ "$status" -eq 0 ]
  [ ! -e ran-install ] && [ ! -e ran-post-apply ]

  run_cli trust add acme
  run_cli plan
  [ "$status" -eq 0 ]
  [ ! -e ran-install ] && [ ! -e ran-post-apply ]

  AGENT_READY_SETUP_REVIEW_MODE=1 run_cli apply
  [ ! -e ran-install ] && [ ! -e ran-post-apply ]
}

@test "in continuous integration nothing runs unless security.execution.ci allows it" {
  run_cli trust add acme
  CI=true run_cli plan
  [[ "$output" == *"this runs in continuous integration (CI is set) and security.execution.ci is false"* ]]
  CI=true run_cli apply
  [ ! -e ran-install ] && [ ! -e ran-post-apply ]

  set_user_configuration '{"security": {"execution": {"ci": true}}}'
  CI=true run_cli apply
  [ "$(count_lines ran-install)" = 1 ]
}

@test "scripts find the CLIs of the packs on their PATH" {
  mkdir -p "$test_root/clis"
  printf '#!/bin/sh\necho from-pack-cli >> ran-cli\n' > "$test_root/clis/acme-tool"
  chmod +x "$test_root/clis/acme-tool"
  mkdir -p "$(git rev-parse --absolute-git-dir)/agent-ready"
  native_path "$test_root/clis" > "$(git rev-parse --absolute-git-dir)/agent-ready/cli-path"
  publish_pack 'acme-tool' 'echo post-apply >> ran-post-apply' 60
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  grep -q from-pack-cli ran-cli
}

@test "session-start scripts run from the hook only as the last apply recorded them" {
  set_user_configuration '{"security": {"execution": {"events": ["install", "post-apply", "session-start"]}}}'
  run_cli trust add acme
  run_cli apply
  [ ! -e ran-session-start ]
  run python3 "$skill_dir/scripts/agent-ready-state.py" pack-scripts --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [ "$(count_lines ran-session-start)" = 1 ]

  # A lock that no longer matches the script in the pack: the hook waits for the next apply.
  python3 - <<'PY'
import json
path = ".agents/agent-ready.lock.json"
lock = json.load(open(path, encoding="utf-8"))
lock["scripts"]["session-start:acme/scripts/session.sh"]["sha256"] = "0" * 64
json.dump(lock, open(path, "w", encoding="utf-8"), indent=2)
PY
  run python3 "$skill_dir/scripts/agent-ready-state.py" pack-scripts --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"skipped acme/scripts/session.sh: not the script the last apply recorded"* ]]
  [ "$(count_lines ran-session-start)" = 1 ]
}

# Replace the scripts of kafka-interno with the given JSON list and publish the pack again.
declare_scripts() {
  local pack_repository="$test_root/repositories/acme"
  python3 - "$pack_repository/agent-ready-pack.json" "$1" <<'PY'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path, encoding="utf-8"))
catalog["profiles"]["kafka-interno"]["scripts"] = json.loads(sys.argv[2])
json.dump(catalog, open(path, "w", encoding="utf-8"), indent=2)
PY
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm "declared scripts"
}

@test "one script shared by install and session-start keeps its install state apart" {
  declare_scripts '[{"event": "install", "path": "scripts/install.sh", "interpreter": "bash", "timeoutSeconds": 60},
                    {"event": "session-start", "path": "scripts/install.sh", "interpreter": "bash", "timeoutSeconds": 60}]'
  set_user_configuration '{"security": {"execution": {"events": ["install", "post-apply", "session-start"]}}}'
  run_cli trust add acme
  run_cli apply
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(count_lines ran-install)" = 1 ]
}

@test "the interpreter a pack installs wins over the one of the host" {
  mkdir -p "$test_root/clis"
  printf '#!/bin/sh\necho pack-node >> ran-node\n' > "$test_root/clis/node"
  chmod +x "$test_root/clis/node"
  # On Windows the runner finds the interpreter as node.cmd, as an installed node has it.
  printf '@bash "%%~dp0node" %%*\r\n' > "$test_root/clis/node.cmd"
  mkdir -p "$(git rev-parse --absolute-git-dir)/agent-ready"
  native_path "$test_root/clis" > "$(git rev-parse --absolute-git-dir)/agent-ready/cli-path"
  declare_scripts '[{"event": "post-apply", "path": "scripts/post-apply.sh", "interpreter": "node", "timeoutSeconds": 60}]'
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  grep -q pack-node ran-node
}

@test "a second session never runs the session-start scripts while another one does" {
  set_user_configuration '{"security": {"execution": {"events": ["install", "post-apply", "session-start"]}}}'
  run_cli trust add acme
  run_cli apply
  mkdir -p "$(git rev-parse --absolute-git-dir)/agent-ready/scripts/.session-start.lock"
  run python3 "$skill_dir/scripts/agent-ready-state.py" pack-scripts --project . --skill-dir "$skill_dir"
  [ "$status" -eq 0 ]
  [[ "$output" == *"another session of this checkout is running the session-start scripts"* ]]
  [ ! -e ran-session-start ]
}

@test "a child that ignores SIGTERM is killed with its script" {
  case "$(uname -s)" in MINGW* | MSYS*) skip "process groups are POSIX; Windows uses a job object" ;; esac
  publish_pack '( trap "" TERM; while true; do echo x >> ran-child; sleep 0.2; done ) & sleep 30' 'true' 1
  run_cli trust add acme
  run_cli apply
  [[ "$stderr" == *"did not finish in 1 seconds and was stopped"* ]]
  lines="$(count_lines ran-child)"
  sleep 2
  [ "$(count_lines ran-child)" = "$lines" ]
}

@test "an install script two selected profiles declare runs once per apply" {
  python3 - "$test_root/repositories/acme/agent-ready-pack.json" <<'PY'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path, encoding="utf-8"))
shared = [{"event": "install", "path": "scripts/install.sh", "interpreter": "bash", "timeoutSeconds": 60}]
catalog["profiles"]["kafka-interno"]["scripts"] = shared
catalog["profiles"]["base"]["scripts"] = shared
json.dump(catalog, open(path, "w", encoding="utf-8"), indent=2)
PY
  git -C "$test_root/repositories/acme" commit -qam "shared install"
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [ "$(count_lines ran-install)" = 1 ]
}

@test "a failed session-start script is shown once in the next session" {
  publish_pack 'echo install >> ran-install' 'true' 60 'exit 4'
  set_user_configuration '{"security": {"execution": {"events": ["install", "post-apply", "session-start"]}}}'
  run_cli trust add acme
  run_cli apply
  run python3 "$skill_dir/scripts/agent-ready-state.py" pack-scripts --project . --skill-dir "$skill_dir"
  [ "$status" -ne 0 ]
  run python3 "$skill_dir/scripts/agent-ready-state.py" pack-scripts --project . --skill-dir "$skill_dir" --previous-report
  [[ "$output" == *"A session-start script of a profile pack failed: session-start acme/scripts/session.sh: exited with 4"* ]]
  run python3 "$skill_dir/scripts/agent-ready-state.py" pack-scripts --project . --skill-dir "$skill_dir" --previous-report
  [ -z "$output" ]
}

@test "stopping a sync stops the pack scripts it left running in their own session" {
  case "$(uname -s)" in MINGW* | MSYS*) skip "sessions are POSIX; Windows stops the tree with taskkill" ;; esac
  # Without the pipe of $(...): a child that keeps it open would make the substitution wait for it.
  launch='import subprocess; print(subprocess.Popen(["sleep", "30"], start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).pid)'
  stopped="$(python3 -c "$launch")"
  other="$(python3 -c "$launch")"
  scripts_directory="$(git rev-parse --absolute-git-dir)/agent-ready/scripts"
  mkdir -p "$scripts_directory"
  printf '%s\n' "$stopped" > "$scripts_directory/running-sync-1"
  # Another invocation (a session-start run) owns this one: the timeout of sync-1 leaves it alone.
  printf '%s\n' "$other" > "$scripts_directory/running-session"
  PYTHONPATH="$skill_dir/scripts" python3 -c 'import agent_ready_pack_scripts as scripts; scripts.stop_running_scripts(".", "sync-1")'
  sleep 0.5
  ! kill -0 "$stopped" 2> /dev/null
  [ ! -e "$scripts_directory/running-sync-1" ]
  kill -0 "$other"
  kill "$other"
}
