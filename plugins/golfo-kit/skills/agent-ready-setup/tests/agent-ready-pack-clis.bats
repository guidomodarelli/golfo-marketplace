#!/usr/bin/env bats
# CLIs a profile pack declares: an apply installs the ones the security policy allows in the cache
# of the user, never in the project, after checking the sha256 of what it downloaded. The release
# files come from a local https server with a certificate of its own, trusted through
# SSL_CERT_FILE; npm and brew are fakes that answer only the subcommands the engine uses.

bats_require_minimum_version 1.5.0

setup() {
  repository_root="$(cd "$BATS_TEST_DIRNAME/../../../../.." && pwd)"
  skill_dir="$repository_root/plugins/golfo-kit/skills/agent-ready-setup"
  example_pack="$skill_dir/assets/examples/acme-profile-pack"
  test_root="$(mktemp -d)"
  test_root="$(cd "$test_root" && pwd -P)"
  project_dir="$test_root/project"
  fake_bin="$test_root/bin"
  served="$test_root/served"
  mkdir -p "$project_dir" "$fake_bin" "$served" "$test_root/tmp"
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
  unset CODEX_HOME AGENT_READY_SETUP_UPDATES AGENT_READY_SETUP_STACK_DIR AGENT_READY_SETUP_STACK AGENT_READY_SETUP_PROFILES
  for provider_cli in claude codex; do
    printf '#!/bin/bash\nexit 0\n' > "$fake_bin/$provider_cli"
    chmod +x "$fake_bin/$provider_cli"
  done
  machine_platform="$(PYTHONPATH="$skill_dir/scripts" python3 -c 'import agent_ready_pack_clis as clis; print(clis.current_platform())')"
  start_https_server
  build_release_archive acme
  git -C "$project_dir" init -q
  cd "$project_dir"
  write_manifest
}

teardown() {
  cd "$repository_root"
  if [ -n "${server_pid:-}" ]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
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

# A self-signed certificate for 127.0.0.1 and an https server of $served on a free port.
start_https_server() {
  # Git Bash would turn /CN=... into a Windows path.
  MSYS2_ARG_CONV_EXCL='/CN=' openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=127.0.0.1" \
    -addext "subjectAltName=IP:127.0.0.1" -keyout "$test_root/server.key" -out "$test_root/server.crt" 2> /dev/null
  SSL_CERT_FILE="$(native_path "$test_root")/server.crt"
  export SSL_CERT_FILE
  cat > "$test_root/server.py" <<'PY'
import functools, http.server, os, ssl, sys
root, certificate, key, port_file = sys.argv[1:5]
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certificate, key)
server.socket = context.wrap_socket(server.socket, server_side=True)
with open(port_file + ".partial", "w") as port_output:
    port_output.write(str(server.server_address[1]))
os.replace(port_file + ".partial", port_file)
server.serve_forever()
PY
  # Relative paths: a Windows Python does not read the POSIX paths of Git Bash in every argument.
  (cd "$test_root" && exec python3 server.py served server.crt server.key port > server.log 2>&1) &
  server_pid=$!
  local attempt
  for attempt in $(seq 1 100); do
    [ -f "$test_root/port" ] && break
    sleep 0.1
  done
  server_url="https://127.0.0.1:$(cat "$test_root/port")"
}

# A release archive with an executable bin/<name> that prints "<name> works".
build_release_archive() {
  local name="$1" staging="$test_root/release-$1"
  mkdir -p "$staging/bin"
  printf '#!/bin/sh\necho "%s works"\n' "$name" > "$staging/bin/$name"
  chmod +x "$staging/bin/$name"
  tar -czf "$served/$name.tar.gz" -C "$staging" bin
}

sha256_of() {
  python3 -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"
}

# The example pack whose kafka-interno profile declares the CLIs given as JSON.
publish_pack() {
  local clis="$1" pack_repository="$test_root/repositories/acme"
  rm -rf "$pack_repository"
  mkdir -p "$(dirname "$pack_repository")"
  cp -R "$example_pack" "$pack_repository"
  python3 - "$pack_repository/agent-ready-pack.json" "$clis" <<'PY'
import json, sys
path = sys.argv[1]
catalog = json.load(open(path, encoding="utf-8"))
catalog["profiles"]["kafka-interno"]["clis"] = json.loads(sys.argv[2])
json.dump(catalog, open(path, "w", encoding="utf-8"), indent=2)
PY
  git -C "$pack_repository" init -q
  git -C "$pack_repository" add -A
  git -C "$pack_repository" commit -qm initial
  git config --global "url.file:///$(native_path "$pack_repository" | sed 's#^/##').insteadOf" "https://packs.example.invalid/acme"
}

artifact_cli() {
  printf '[{"name": "acme", "version": "1.4.2", "artifacts": [{"platform": "%s", "url": "%s/acme.tar.gz", "sha256": "%s"}]}]' \
    "$machine_platform" "$server_url" "${1:-$(sha256_of "$served/acme.tar.gz")}"
}

write_manifest() {
  mkdir -p .agents
  printf '%s\n' '{"profiles": ["acme/kafka-interno"], "sources": {"packs": [{"name": "acme", "source": "git+https://packs.example.invalid/acme#main"}]}}' > .agents/agent-ready.json
}

run_cli() {
  run --separate-stderr env PATH="$fake_bin:$PATH" python3 "$skill_dir/scripts/agent-ready" "$@"
}

cli_path_file() {
  printf '%s/agent-ready/cli-path' "$(git rev-parse --absolute-git-dir)"
}

# The first directory the repository puts on the PATH, as a path this shell can run from.
first_cli_directory() {
  local directory
  directory="$(head -n 1 "$(cli_path_file)" | tr -d '\r')"
  if command -v cygpath > /dev/null; then
    cygpath -u "$directory"
  else
    printf '%s\n' "$directory"
  fi
}

installed_versions() {
  find "$XDG_CACHE_HOME/agent-ready-setup/clis/installs" -name agent-ready-cli.json 2> /dev/null | wc -l | tr -d ' '
}

@test "an apply installs an allowed CLI in the cache of the user, checked by its sha256, and puts it on the PATH of the repository" {
  publish_pack "$(artifact_cli)"
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"CLIs of profile packs installed in"*"acme 1.4.2"* ]]
  [ "$(installed_versions)" = 1 ]
  [ -z "$(find . -path ./.git -prune -o \( -name 'acme.tar.gz' -o -name acme -type f \) -print)" ]
  directory="$(first_cli_directory)"
  [[ "$directory" == "$XDG_CACHE_HOME/agent-ready-setup/clis/installs/acme/1.4.2/"* ]]
  run sh "$directory/acme"
  [ "$output" = "acme works" ]
  python3 - <<'PY'
import json
entry = json.load(open(".agents/agent-ready.lock.json", encoding="utf-8"))["clis"]["acme"]
assert entry["version"] == "1.4.2" and entry["source"] == "acme" and len(entry["sha256"]) == 64, entry
PY

  # The next apply reuses the cache: it does not even reach the server.
  kill "$server_pid" && wait "$server_pid" 2> /dev/null || true
  server_pid=""
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"CLIs of profile packs already in the cache: acme 1.4.2"* ]]
}

@test "a file whose sha256 is not the declared one is never installed" {
  publish_pack "$(artifact_cli "$(printf '0%.0s' $(seq 1 64))")"
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"CLI not installed: acme 1.4.2: acme.tar.gz has sha256"*"nothing was installed"* ]]
  [ "$(installed_versions)" = 0 ]
  [ ! -e "$(cli_path_file)" ]
  ! grep -q '"clis"' .agents/agent-ready.lock.json
}

@test "an archive with a path that leaves its directory is refused" {
  mkdir -p "$test_root/evil/inner"
  printf 'x\n' > "$test_root/evil/escape"
  python3 - "$test_root/evil" "$served/acme.tar.gz" <<'PY'
import os, sys, tarfile
root, archive = sys.argv[1:3]
with tarfile.open(archive, "w:gz") as bundle:
    bundle.add(os.path.join(root, "escape"), arcname="../escape")
PY
  publish_pack "$(artifact_cli)"
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"has a path ../escape that leaves its directory"* ]]
  [ ! -e "$XDG_CACHE_HOME/agent-ready-setup/clis/escape" ]
  [ "$(installed_versions)" = 0 ]
}

@test "without trust nothing is downloaded and the cache of CLIs is not even created" {
  publish_pack "$(artifact_cli)"
  run_cli apply
  [ "$status" -eq 0 ]
  [ ! -e "$XDG_CACHE_HOME/agent-ready-setup/clis" ]
  ! grep -q 'acme.tar.gz' "$test_root/server.log"
}

@test "automated reviews install nothing" {
  publish_pack "$(artifact_cli)"
  run_cli trust add acme
  AGENT_READY_SETUP_REVIEW_MODE=1 run_cli apply
  [ "$status" -eq 0 ]
  [ "$(installed_versions)" = 0 ]
}

@test "repositories share an install, and it goes when no repository of the machine uses it" {
  publish_pack "$(artifact_cli)"
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  second_project="$test_root/second"
  mkdir -p "$second_project"
  git -C "$second_project" init -q
  mkdir -p "$second_project/.agents"
  cp .agents/agent-ready.json "$second_project/.agents/"
  cd "$second_project"
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"already in the cache: acme 1.4.2"* ]]

  run_cli remove --yes
  [ "$status" -eq 0 ]
  [ "$(installed_versions)" = 1 ]

  cd "$project_dir"
  run_cli trust remove acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"CLIs this repository no longer uses: acme 1.4.2"* ]]
  [ "$(installed_versions)" = 0 ]
  [ ! -e "$(cli_path_file)" ]
}

@test "an npm package is checked by the sha256 of its tarball before npm installs it" {
  cat > "$fake_bin/npm" <<'SH'
#!/bin/bash
# Answers only what the engine runs: npm pack <spec> --pack-destination <dir> and npm install --prefix <dir> ... <tarball>.
printf '%s\n' "$*" >> "$NPM_CALLS"
case "$1" in
  pack) printf 'helper tarball\n' > "$4/acme-helper-2.0.0.tgz" ;;
  install)
    mkdir -p "$3/node_modules/.bin"
    printf '#!/bin/sh\necho "helper works"\n' > "$3/node_modules/.bin/acme-helper"
    chmod +x "$3/node_modules/.bin/acme-helper" ;;
  *) exit 1 ;;
esac
SH
  chmod +x "$fake_bin/npm"
  # On Windows the engine finds npm as npm.cmd, as a real installation has it.
  printf '@bash "%%~dp0npm" %%*\r\n' > "$fake_bin/npm.cmd"
  export NPM_CALLS="$test_root/npm-calls.log"
  printf 'helper tarball\n' > "$test_root/expected.tgz"
  good="$(sha256_of "$test_root/expected.tgz")"
  publish_pack "[{\"name\": \"acme-helper\", \"version\": \"2.0.0\", \"package\": {\"manager\": \"npm\", \"name\": \"@acme/helper\", \"sha256\": \"$(printf '1%.0s' $(seq 1 64))\"}}]"
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"CLI not installed: acme-helper 2.0.0: npm package @acme/helper@2.0.0 has sha256"* ]]
  ! grep -q '^install' "$NPM_CALLS"

  publish_pack "[{\"name\": \"acme-helper\", \"version\": \"2.0.0\", \"package\": {\"manager\": \"npm\", \"name\": \"@acme/helper\", \"sha256\": \"$good\"}}]"
  run_cli update
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"installed in"*"acme-helper 2.0.0"* ]]
  run sh "$(first_cli_directory)/acme-helper"
  [ "$output" = "helper works" ]
}

@test "brew and winget are never run: the apply says how to install the CLI" {
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >> "%s"\nexit 1\n' "$test_root/brew-calls.log" > "$fake_bin/brew"
  chmod +x "$fake_bin/brew"
  publish_pack '[{"name": "acme", "version": "1.4.2", "package": {"manager": "brew", "name": "acme/tap/acme", "sha256": "'"$(printf 'a%.0s' $(seq 1 64))"'"}}]'
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"acme: brew installs for the whole machine, so install it yourself with brew install acme/tap/acme"* ]]
  [ ! -e "$test_root/brew-calls.log" ]
}
