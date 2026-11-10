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
  # A configuration file instead of -subj and -addext: the LibreSSL of macOS has no -addext, and
  # Git Bash would turn /CN=... into a Windows path.
  printf '%s\n' '[req]' 'prompt = no' 'distinguished_name = name' 'x509_extensions = extensions' \
    '[name]' 'CN = 127.0.0.1' '[extensions]' 'subjectAltName = IP:127.0.0.1' > "$test_root/openssl.cnf"
  (cd "$test_root" && openssl req -x509 -newkey rsa:2048 -nodes -days 1 -config openssl.cnf \
    -keyout server.key -out server.crt > openssl.log 2>&1) || { cat "$test_root/openssl.log" >&2; return 1; }
  SSL_CERT_FILE="$(native_path "$test_root")/server.crt"
  export SSL_CERT_FILE
  cat > "$test_root/server.py" <<'PY'
import functools, http.server, os, socketserver, ssl, sys
root, certificate, key, port_file = sys.argv[1:5]

class Server(http.server.ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind resolves the host name with socket.getfqdn, which can stall for
        # many seconds on macOS; the name is never needed here.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=root)
server = Server(("127.0.0.1", 0), handler)
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
  for attempt in $(seq 1 300); do
    [ -f "$test_root/port" ] && break
    sleep 0.1
  done
  if [ ! -f "$test_root/port" ]; then
    kill -0 "$server_pid" 2> /dev/null && echo "the https server is still starting after 30 seconds" >&2
    cat "$test_root/server.log" >&2
    return 1
  fi
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

  # The next apply reuses the cache: it does not even reach the server, nor rewrite what is the same.
  kill "$server_pid" && wait "$server_pid" 2> /dev/null || true
  server_pid=""
  record="$(ls "$XDG_CACHE_HOME"/agent-ready-setup/clis/projects/*.json)"
  touch -t 200101010000 "$record" "$(cli_path_file)"
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"CLIs of profile packs already in the cache: acme 1.4.2"* ]]
  python3 -c 'import os, sys; assert all(os.path.getmtime(path) < 1e9 + 1e8 for path in sys.argv[1:]), "rewritten"' \
    "$record" "$(cli_path_file)"
}

@test "two declarations of the same name and version with different bytes never replace each other" {
  build_release_archive other
  cp "$served/other.tar.gz" "$served/acme-other.tar.gz"
  PYTHONPATH="$skill_dir/scripts" python3 - "$machine_platform" "$server_url" "$(sha256_of "$served/acme.tar.gz")" \
    "$(sha256_of "$served/acme-other.tar.gz")" <<'PY'
import os, sys
import agent_ready_pack_clis as clis
machine_platform, url, first_sha, second_sha = sys.argv[1:5]
def declaration(file_name, sha256, binary):
    return {"name": "acme", "version": "1.4.2", "artifacts": [
        {"platform": machine_platform, "url": f"{url}/{file_name}", "sha256": sha256, "binary": binary}]}
first_key, first_marker, _ = clis.install_one(declaration("acme.tar.gz", first_sha, "acme"), machine_platform)
second_key, second_marker, _ = clis.install_one(declaration("acme-other.tar.gz", second_sha, "other"), machine_platform)
assert first_key != second_key, (first_key, second_key)
assert clis.installed(first_key, first_sha) and clis.installed(second_key, second_sha)
assert os.path.isfile(os.path.join(clis.install_directory(first_key), *first_marker["pathDirectory"].split("/"), "acme"))
PY
}

# A wheel with a console script acme-tool, and a source distribution whose build would leave a mark.
build_python_distributions() {
  mkdir -p "$test_root/wheels"
  python3 - "$test_root/wheels" "$test_root/built-from-source" <<'PY'
import io, os, sys, tarfile, zipfile
directory, mark = sys.argv[1:3]
wheel = os.path.join(directory, "acme_tool-1.0.0-py3-none-any.whl")
files = {
    "acme_tool/__init__.py": "def main():\n    print('acme-tool works')\n",
    "acme_tool-1.0.0.dist-info/METADATA": "Metadata-Version: 2.1\nName: acme-tool\nVersion: 1.0.0\n",
    "acme_tool-1.0.0.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    "acme_tool-1.0.0.dist-info/entry_points.txt": "[console_scripts]\nacme-tool = acme_tool:main\n",
}
files["acme_tool-1.0.0.dist-info/RECORD"] = "".join(f"{name},,\n" for name in files) + "acme_tool-1.0.0.dist-info/RECORD,,\n"
with zipfile.ZipFile(wheel, "w") as bundle:
    for name, text in files.items():
        bundle.writestr(name, text)
setup = f"open({mark!r}, 'w').write('built')\nfrom setuptools import setup\nsetup(name='acme-builder', version='1.0.0')\n"
with tarfile.open(os.path.join(directory, "acme-builder-1.0.0.tar.gz"), "w:gz") as bundle:
    for name, text in {"acme-builder-1.0.0/setup.py": setup,
                       "acme-builder-1.0.0/PKG-INFO": "Metadata-Version: 2.1\nName: acme-builder\nVersion: 1.0.0\n"}.items():
        data = text.encode("utf-8")
        member = tarfile.TarInfo(name)
        member.size = len(data)
        bundle.addfile(member, io.BytesIO(data))
PY
  export PIP_NO_INDEX=1
  PIP_FIND_LINKS="$(native_path "$test_root/wheels")"
  export PIP_FIND_LINKS
}

@test "a pip package installs from a wheel checked by pip, and its launcher runs from the cache" {
  build_python_distributions
  wheel_sha="$(sha256_of "$test_root/wheels/acme_tool-1.0.0-py3-none-any.whl")"
  publish_pack "[{\"name\": \"acme-tool\", \"version\": \"1.0.0\", \"package\": {\"manager\": \"pip\", \"name\": \"acme-tool\", \"sha256\": \"$wheel_sha\"}}]"
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"installed in"*"acme-tool 1.0.0"* ]]
  directory="$(first_cli_directory)"
  if [ -f "$directory/acme-tool.exe" ]; then run "$directory/acme-tool.exe"; else run "$directory/acme-tool"; fi
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | tr -d '\r')" = "acme-tool works" ]
}

@test "a pip package with only a source distribution is never built" {
  build_python_distributions
  publish_pack "[{\"name\": \"acme-builder\", \"version\": \"1.0.0\", \"package\": {\"manager\": \"pip\", \"name\": \"acme-builder\", \"sha256\": \"$(printf '2%.0s' $(seq 1 64))\"}}]"
  run_cli trust add acme
  run_cli apply
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"CLI not installed: acme-builder 1.0.0: pip package acme-builder==1.0.0"* ]]
  [ ! -e "$test_root/built-from-source" ]
  [ "$(installed_versions)" = 0 ]
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
# Answers only what the engine runs: npm pack <spec> --ignore-scripts --pack-destination <dir> and
# npm install --prefix <dir> ... <tarball>. A pack that would run the lifecycle scripts fails.
printf '%s\n' "$*" >> "$NPM_CALLS"
case "$1" in
  pack)
    [ "$3" = --ignore-scripts ] || exit 1
    printf 'helper tarball\n' > "$5/acme-helper-2.0.0.tgz" ;;
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

@test "the cleanup never follows a link in the cache of CLIs" {
  mkdir -p "$test_root/user-data/keep" "$XDG_CACHE_HOME/agent-ready-setup/clis/installs/tool"
  printf 'mine\n' > "$test_root/user-data/keep/file.txt"
  link="$XDG_CACHE_HOME/agent-ready-setup/clis/installs/tool/1.0"
  case "$(uname -s)" in
    MINGW* | MSYS*) cmd //c "mklink /J $(cygpath -w "$link") $(cygpath -w "$test_root/user-data")" > /dev/null ;;
    *) ln -s "$test_root/user-data" "$link" ;;
  esac
  PYTHONPATH="$skill_dir/scripts" python3 -c 'import agent_ready_pack_clis as clis; print(clis.clean_unused())'
  [ -f "$test_root/user-data/keep/file.txt" ]
}

@test "the executable name is part of the install, and an extension it already has is not added again" {
  printf '#!/bin/sh\necho raw\n' > "$served/tool.exe"
  PYTHONPATH="$skill_dir/scripts" python3 - "$machine_platform" "$server_url" "$(sha256_of "$served/tool.exe")" <<'PY'
import os, sys
import agent_ready_pack_clis as clis
machine_platform, url, sha256 = sys.argv[1:4]
def declaration(binary):
    return {"name": "tool", "version": "1.0.0", "artifacts": [
        {"platform": machine_platform, "url": f"{url}/tool.exe", "sha256": sha256, "binary": binary}]}
first_key, first_marker, _ = clis.install_one(declaration("tool.exe"), machine_platform)
directory = os.path.join(clis.install_directory(first_key), *first_marker["pathDirectory"].split("/"))
assert sorted(os.listdir(directory)) == ["tool.exe"], os.listdir(directory)
second_key, second_marker, reused = clis.install_one(declaration("acme"), machine_platform)
assert second_key != first_key and not reused, (first_key, second_key, reused)
directory = os.path.join(clis.install_directory(second_key), *second_marker["pathDirectory"].split("/"))
assert sorted(os.listdir(directory)) == ["acme.exe"], os.listdir(directory)
PY
}

@test "a package name that is a path or a URL stops the apply before anything runs" {
  publish_pack '[{"name": "acme-helper", "version": "2.0.0", "package": {"manager": "npm", "name": "./acme-helper@2.0.0", "sha256": "'"$(printf '1%.0s' $(seq 1 64))"'"}}]'
  run_cli trust add acme
  run_cli apply
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"package name must be a npm registry name, not a path or URL"* ]]
}
