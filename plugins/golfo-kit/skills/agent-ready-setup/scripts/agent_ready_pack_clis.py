"""Installation of the CLIs that profile packs declare, in the cache of the user, never in the project.

Only an apply installs, and only a CLI the security policy allows (agent_ready_pack_tools.py):

- an artifact is downloaded over https for the platform of this machine and its sha256 checked
  before anything is extracted; an archive (.tar.gz, .tgz or .zip) is extracted without links or
  paths that leave its directory;
- an npm package is packed first, so its tarball is checked against the declared sha256 before
  npm installs it under a prefix of its own; a pip package is downloaded and checked the same way
  before pip installs it in a virtual environment of its own;
- brew and winget install for the whole machine, so they are never run: the apply says how to
  install the CLI and whether it is already on the PATH.

Each version lives once in the cache (``clis/installs/<name>/<version>/<origin>``) and is shared by
every repository of the machine that declares it. Each repository records which installs it uses
(``clis/projects/<key>.json``); an install that no repository uses any more is deleted. The
directories to put on the PATH of a repository go to ``agent-ready/cli-path`` in its Git directory.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

from agent_ready_common import acquire_directory_lock, is_link, sha256_of_text, write_text_if_changed

ORIGIN_ARTIFACT = "artifact"
MANAGER_NPM = "npm"
MANAGER_PIP = "pip"
SYSTEM_MANAGERS = ("brew", "winget")
SYSTEM_MANAGER_COMMANDS = {"brew": "brew install {name}", "winget": "winget install --exact --id {name} --version {version}"}
INSTALL_MARKER = "agent-ready-cli.json"
CLI_PATH_RELATIVE = "agent-ready/cli-path"
DOWNLOAD_TIMEOUT_SECONDS = 120
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
INSTALL_IDENTITY_LENGTH = 16
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
PACKAGE_COMMAND_TIMEOUT_SECONDS = 600
CACHE_LOCK_WAIT_SECONDS = 60
CACHE_LOCK_POLL_SECONDS = 0.2
ARCHIVE_SUFFIXES = (".tar.gz", ".tgz", ".zip")
WINDOWS_EXECUTABLE_SUFFIXES = (".exe", ".cmd", ".bat", ".ps1")
MACHINES = {"x86_64": "x64", "amd64": "x64", "x64": "x64", "aarch64": "arm64", "arm64": "arm64"}
SYSTEMS = {"linux": "linux", "darwin": "darwin", "win32": "windows"}


class InstallError(RuntimeError):
    """A CLI that could not be installed; what was there before stays."""


# ---------------------------------------------------------------------------
# Cache layout
# ---------------------------------------------------------------------------

def cache_root():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.environ.get("HOME") or os.path.expanduser("~"), ".cache")
    return os.path.join(base, "agent-ready-setup", "clis")


def installs_root():
    return os.path.join(cache_root(), "installs")


def projects_root():
    return os.path.join(cache_root(), "projects")


def project_record_path(project_root):
    return os.path.join(projects_root(), sha256_of_text(os.path.realpath(project_root))[:16] + ".json")


def install_key(name, version, origin):
    return f"{name}/{version}/{origin}"


def install_directory(key):
    return os.path.join(installs_root(), *key.split("/"))


def current_platform():
    """The platform name packs use for this machine, such as linux-x64, or None when packs name none."""
    system = SYSTEMS.get(sys.platform) or SYSTEMS.get(sys.platform.rstrip("0123456789"))
    machine = MACHINES.get(platform.machine().lower())
    return f"{system}-{machine}" if system and machine else None


def git_directory(project_root):
    try:
        completed = subprocess.run(["git", "-C", project_root, "rev-parse", "--absolute-git-dir"],
                                   capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def cli_path_file(project_root):
    directory = git_directory(project_root)
    return os.path.join(directory, *CLI_PATH_RELATIVE.split("/")) if directory else None


class CacheLock:
    """Only one apply changes the cache of CLIs at a time; a lock of a dead process expires."""

    def __init__(self):
        self.path = os.path.join(cache_root(), ".lock")

    def __enter__(self):
        deadline = time.monotonic() + CACHE_LOCK_WAIT_SECONDS
        while not acquire_directory_lock(self.path):
            if time.monotonic() > deadline:
                raise InstallError(f"another apply holds {self.path}; try again when it ends")
            time.sleep(CACHE_LOCK_POLL_SECONDS)
        return self

    def __exit__(self, *exception):
        try:
            os.rmdir(self.path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Downloading and extracting
# ---------------------------------------------------------------------------

def sha256_of_bytes_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(DOWNLOAD_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, destination):
    """Save url to destination; https only, and never more than MAX_DOWNLOAD_BYTES."""
    request = urllib.request.Request(url, headers={"User-Agent": "agent-ready-setup"})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, open(destination, "wb") as output:
            if not response.geturl().startswith("https://"):
                raise InstallError(f"{url} redirected to {response.geturl()}, which is not https")
            received = 0
            for chunk in iter(lambda: response.read(DOWNLOAD_CHUNK_BYTES), b""):
                received += len(chunk)
                if received > MAX_DOWNLOAD_BYTES:
                    raise InstallError(f"{url} is larger than {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB")
                output.write(chunk)
    except InstallError:
        raise
    except (OSError, ValueError) as problem:
        raise InstallError(f"could not download {url}: {problem}") from problem


def verify_sha256(path, expected, what):
    actual = sha256_of_bytes_file(path)
    if actual != expected:
        raise InstallError(f"{what} has sha256 {actual}, not the {expected} the pack declares; nothing was installed")


def safe_member_path(root, name):
    """Where an archive member lands, or InstallError when it would leave root."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        raise InstallError(f"the archive has an absolute path {name}")
    target = os.path.realpath(os.path.join(root, *[part for part in normalized.split("/") if part]))
    real_root = os.path.realpath(root)
    if os.path.commonpath([real_root, target]) != real_root:
        raise InstallError(f"the archive has a path {name} that leaves its directory")
    return target


def extract_tar(archive, root):
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            target = safe_member_path(root, member.name)
            if member.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            if not member.isfile():
                raise InstallError(f"the archive has {member.name}, which is a link or a device; packs cannot use them")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with bundle.extractfile(member) as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output)
            os.chmod(target, 0o755 if member.mode & 0o111 else 0o644)


def extract_zip(archive, root):
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = safe_member_path(root, member.filename)
            mode = (member.external_attr >> 16) & 0o170000
            if mode and mode not in (0o100000, 0o040000):
                raise InstallError(f"the archive has {member.filename}, which is a link; packs cannot use them")
            if member.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with bundle.open(member) as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output)
            os.chmod(target, 0o755)


def find_executable(root, binary):
    """The directory under root that holds the executable binary, or None."""
    candidates = {binary} | {binary + suffix for suffix in WINDOWS_EXECUTABLE_SUFFIXES}
    for directory, directory_names, file_names in sorted(os.walk(root)):
        directory_names.sort()
        if candidates & set(file_names):
            return directory
    return None


# ---------------------------------------------------------------------------
# Installing one CLI
# ---------------------------------------------------------------------------

def read_marker(directory):
    try:
        with open(os.path.join(directory, INSTALL_MARKER), encoding="utf-8") as marker_file:
            marker = json.load(marker_file)
    except (OSError, ValueError):
        return None
    return marker if isinstance(marker, dict) else None


def installed(key, sha256):
    """The marker of a complete install of key with that sha256, or None."""
    directory = install_directory(key)
    marker = read_marker(directory)
    if marker and marker.get("sha256") == sha256 and os.path.isdir(os.path.join(directory, marker.get("pathDirectory", ""))):
        return marker
    return None


def publish(staging, key, marker):
    """Move a finished install into place; a half-written one never looks installed."""
    with open(os.path.join(staging, INSTALL_MARKER), "w", encoding="utf-8") as marker_file:
        json.dump(marker, marker_file, indent=2, sort_keys=True)
    destination = install_directory(key)
    if os.path.normcase(os.path.abspath(staging)) == os.path.normcase(os.path.abspath(destination)):
        # Built in place (a virtual environment cannot move): the marker written last is the publication.
        return
    remove_install_directory(destination)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    os.replace(staging, destination)


def install_artifact(cli, key, machine_platform, staging):
    artifact = next((item for item in cli["artifacts"] if item["platform"] == machine_platform), None)
    if not artifact:
        platforms = ", ".join(item["platform"] for item in cli["artifacts"])
        raise InstallError(f"the pack has no artifact for {machine_platform or 'this machine'} (only {platforms})")
    binary = artifact.get("binary", cli["name"])
    file_name = artifact["url"].rsplit("/", 1)[-1].split("?", 1)[0] or binary
    download_path = os.path.join(staging, "download")
    download(artifact["url"], download_path)
    verify_sha256(download_path, artifact["sha256"], file_name)
    files = os.path.join(staging, "files")
    os.makedirs(files)
    lowered = file_name.lower()
    if lowered.endswith((".tar.gz", ".tgz")):
        extract_tar(download_path, files)
    elif lowered.endswith(".zip"):
        extract_zip(download_path, files)
    else:
        suffix = next((ending for ending in WINDOWS_EXECUTABLE_SUFFIXES if lowered.endswith(ending)), "")
        if binary.lower().endswith(suffix):
            # binary already names the extension (acme.exe): it is not added twice.
            suffix = ""
        target = os.path.join(files, binary + suffix)
        os.replace(download_path, target)
        os.chmod(target, 0o755)
    if os.path.exists(download_path):
        os.unlink(download_path)
    directory = find_executable(files, binary)
    if not directory:
        raise InstallError(f"{file_name} has no executable named {binary}")
    return {"sha256": artifact["sha256"], "pathDirectory": os.path.relpath(directory, staging).replace(os.sep, "/")}


def run_package_manager(command, what):
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=PACKAGE_COMMAND_TIMEOUT_SECONDS)
    except FileNotFoundError as problem:
        raise InstallError(f"{what} needs {command[0]}, which is not on the PATH") from problem
    except subprocess.TimeoutExpired as problem:
        raise InstallError(f"{what}: {command[0]} did not finish in {PACKAGE_COMMAND_TIMEOUT_SECONDS} seconds") from problem
    if completed.returncode != 0:
        last_line = (completed.stderr.strip().splitlines() or ["no output"])[-1]
        raise InstallError(f"{what}: {' '.join(command[:2])} exited with {completed.returncode}: {last_line}")
    return completed.stdout


def only_file(directory, what):
    files = [name for name in os.listdir(directory) if os.path.isfile(os.path.join(directory, name))]
    if len(files) != 1:
        raise InstallError(f"{what} left {len(files)} files to check instead of one")
    return os.path.join(directory, files[0])


def install_npm(cli, staging):
    package = cli["package"]
    what = f"npm package {package['name']}@{cli['version']}"
    downloads = os.path.join(staging, "download")
    os.makedirs(downloads)
    npm = shutil.which(MANAGER_NPM) or MANAGER_NPM
    # --ignore-scripts: no lifecycle script of the package runs before its sha256 is checked.
    run_package_manager([npm, "pack", f"{package['name']}@{cli['version']}", "--ignore-scripts",
                         "--pack-destination", downloads], what)
    tarball = only_file(downloads, what)
    if package.get("sha256"):
        verify_sha256(tarball, package["sha256"], what)
    prefix = os.path.join(staging, "files")
    run_package_manager([npm, "install", "--prefix", prefix, "--no-save", "--no-audit", "--no-fund", tarball], what)
    shutil.rmtree(downloads)
    binary = package.get("binary", cli["name"])
    directory = find_executable(os.path.join(prefix, "node_modules", ".bin"), binary)
    if not directory:
        raise InstallError(f"{what} installs no executable named {binary}")
    return {"sha256": package.get("sha256"), "pathDirectory": os.path.relpath(directory, staging).replace(os.sep, "/")}


def install_pip(cli, staging):
    package = cli["package"]
    what = f"pip package {package['name']}=={cli['version']}"
    downloads = os.path.join(staging, "download")
    os.makedirs(downloads)
    # Wheels only: a source distribution runs its build backend before any hash could reject it. With
    # a declared sha256, pip itself checks it as a hash-checking requirement before keeping the file.
    requirement = f"{package['name']}=={cli['version']}"
    if package.get("sha256"):
        requirement += f" --hash=sha256:{package['sha256']}"
    requirements = os.path.join(staging, "requirements.txt")
    with open(requirements, "w", encoding="utf-8") as requirements_file:
        requirements_file.write(requirement + "\n")
    command = [sys.executable, "-m", MANAGER_PIP]
    run_package_manager(command + ["download", "--no-deps", "--only-binary=:all:", "--disable-pip-version-check",
                                   "--dest", downloads, "-r", requirements], what)
    distribution = only_file(downloads, what)
    if package.get("sha256"):
        verify_sha256(distribution, package["sha256"], what)
    # A virtual environment of its own, created where it stays: its launchers name its interpreter
    # by absolute path, so it is never moved after pip installs.
    target = os.path.join(staging, "files")
    run_package_manager([sys.executable, "-m", "venv", target], what)
    scripts = os.path.join(target, "Scripts" if os.name == "nt" else "bin")
    environment_python = os.path.join(scripts, "python.exe" if os.name == "nt" else "python")
    run_package_manager([environment_python, "-m", MANAGER_PIP, "install", "--only-binary=:all:",
                         "--disable-pip-version-check", "--no-warn-script-location", distribution], what)
    os.unlink(requirements)
    shutil.rmtree(downloads)
    binary = package.get("binary", cli["name"])
    directory = find_executable(scripts, binary)
    if not directory:
        raise InstallError(f"{what} installs no executable named {binary}")
    return {"sha256": package.get("sha256"), "pathDirectory": os.path.relpath(directory, staging).replace(os.sep, "/")}


def origin_of(cli, machine_platform):
    return cli["package"]["manager"] if "package" in cli else f"{ORIGIN_ARTIFACT}-{machine_platform or 'unknown'}"


def declaration_identity(cli, machine_platform):
    """Short stable id of what is installed: the sha256 when declared, else the package or url.

    Two packs that declare the same name and version with different bytes get different installs,
    so one never replaces the files another repository runs.
    """
    if "package" in cli:
        declared = cli["package"]
        source = f"{declared['manager']}:{declared['name']}"
    else:
        declared = next((item for item in cli["artifacts"] if item["platform"] == machine_platform), {})
        source = declared.get("url", "")
    # The executable is part of what is installed: the same bytes under another binary name are
    # another layout, so they never reuse an install that lacks the executable they need.
    identity = {"sha256": expected_sha256(cli, machine_platform) or source,
                "binary": declared.get("binary", cli["name"])}
    return sha256_of_text(json.dumps(identity, sort_keys=True))[:INSTALL_IDENTITY_LENGTH]


def expected_sha256(cli, machine_platform):
    if "package" in cli:
        return cli["package"].get("sha256")
    artifact = next((item for item in cli["artifacts"] if item["platform"] == machine_platform), None)
    return artifact["sha256"] if artifact else None


def install_one(cli, machine_platform):
    """(key, marker, reused) of one CLI in the cache; raises InstallError and leaves the cache as it was."""
    key = install_key(cli["name"], cli["version"],
                      f"{origin_of(cli, machine_platform)}-{declaration_identity(cli, machine_platform)}")
    sha256 = expected_sha256(cli, machine_platform)
    marker = installed(key, sha256)
    if marker and (sha256 or "package" in cli):
        return key, marker, True
    os.makedirs(installs_root(), exist_ok=True)
    if "package" in cli and cli["package"]["manager"] == MANAGER_PIP:
        # Built where it stays (see install_pip); the marker, written last, makes it installed.
        staging = install_directory(key)
        remove_install_directory(staging)
        os.makedirs(staging)
    else:
        staging = tempfile.mkdtemp(prefix=".install-", dir=installs_root())
    try:
        if "artifacts" in cli:
            details = install_artifact(cli, key, machine_platform, staging)
        elif cli["package"]["manager"] == MANAGER_NPM:
            details = install_npm(cli, staging)
        else:
            details = install_pip(cli, staging)
        marker = dict(details, name=cli["name"], version=cli["version"], origin=origin_of(cli, machine_platform))
        publish(staging, key, marker)
    except (InstallError, OSError, tarfile.TarError, zipfile.BadZipFile) as problem:
        shutil.rmtree(staging, ignore_errors=True)
        if isinstance(problem, InstallError):
            raise
        raise InstallError(f"could not install {cli['name']} {cli['version']}: {problem}") from problem
    return key, marker, False


# ---------------------------------------------------------------------------
# Apply and remove
# ---------------------------------------------------------------------------

def desired_clis(report):
    """{name: tool} for each CLI the policy allows, and the names two packs declare."""
    desired, duplicated = {}, []
    for tool in (report or {}).get("tools", []):
        if tool.get("type") != "cli" or tool.get("decision") != "allowed":
            continue
        if tool["name"] in desired:
            # The plan already failed on two different declarations: this one is alike, installed once.
            continue
        desired[tool["name"]] = tool
    return desired, duplicated


def read_project_record(project_root):
    try:
        with open(project_record_path(project_root), encoding="utf-8") as record_file:
            record = json.load(record_file)
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def write_project_record(project_root, keys):
    path = project_record_path(project_root)
    if not keys:
        if os.path.exists(path):
            os.unlink(path)
        return
    write_text_if_changed(path, json.dumps({"project": os.path.realpath(project_root), "clis": sorted(keys)},
                                           indent=2, sort_keys=True) + "\n")


def keys_in_use():
    """The installs some repository of the machine still uses; a record of a repository gone counts for nothing."""
    used = set()
    if not os.path.isdir(projects_root()):
        return used
    for name in os.listdir(projects_root()):
        path = os.path.join(projects_root(), name)
        try:
            with open(path, encoding="utf-8") as record_file:
                record = json.load(record_file)
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict) or not os.path.isdir(str(record.get("project", ""))):
            try:
                os.unlink(path)
            except OSError:
                pass
            continue
        used.update(key for key in record.get("clis", []) if isinstance(key, str))
    return used


def managed_directory(path):
    """A real directory of the cache of CLIs: no symlink or junction, and inside installs_root."""
    if is_link(path) or not os.path.isdir(path):
        return False
    root = os.path.normcase(os.path.realpath(installs_root()))
    real = os.path.normcase(os.path.realpath(path))
    try:
        return os.path.commonpath([root, real]) == root and real != root
    except ValueError:
        return False


def remove_install_directory(path):
    """Delete an install directory to rebuild it; a link or a path outside the cache is refused."""
    if not os.path.lexists(path):
        return
    if not managed_directory(path):
        raise InstallError(f"{path} is a link or leaves the cache of CLIs, so it was not deleted")
    shutil.rmtree(path)


def clean_unused():
    """Delete every install no repository uses; returns their keys."""
    used = keys_in_use()
    removed = []
    root = installs_root()
    if not os.path.isdir(root):
        return removed
    for name in sorted(os.listdir(root)):
        name_directory = os.path.join(root, name)
        if name.startswith(".") or not managed_directory(name_directory):
            continue
        for version in sorted(os.listdir(name_directory)):
            # A link anywhere in the cache leads outside it: it is never followed nor deleted through.
            if not managed_directory(os.path.join(name_directory, version)):
                continue
            for origin in sorted(os.listdir(os.path.join(name_directory, version))):
                key = install_key(name, version, origin)
                if key not in used and managed_directory(install_directory(key)):
                    shutil.rmtree(install_directory(key), ignore_errors=True)
                    removed.append(key)
            try:
                os.rmdir(os.path.join(name_directory, version))
            except OSError:
                pass
        try:
            os.rmdir(name_directory)
        except OSError:
            pass
    return removed


def write_cli_path(project_root, directories):
    """The directories to put on the PATH of the repository, one per line, in its Git directory."""
    path = cli_path_file(project_root)
    if not path:
        return
    if not directories:
        if os.path.exists(path):
            os.unlink(path)
        return
    write_text_if_changed(path, "".join(directory + "\n" for directory in directories))


def system_package_note(cli):
    package = cli["package"]
    command = SYSTEM_MANAGER_COMMANDS[package["manager"]].format(name=package["name"], version=cli["version"])
    binary = package.get("binary", cli["name"])
    present = "it is on the PATH" if shutil.which(binary) else "it is not on the PATH yet"
    return f"{cli['name']}: {package['manager']} installs for the whole machine, so install it yourself with {command} ({present})"


def install(project_root, report, previous):
    """Install the allowed CLIs and stop using the ones that are no longer allowed.

    ``previous`` is the clis of the lock. Returns what changed and the entries the new lock records.
    """
    desired, duplicated = desired_clis(report)
    result = {"installed": [], "reused": [], "removed": [], "manual": [], "conflicts": duplicated, "failed": [],
              "lock": {}, "path": []}
    if not desired and not previous and not read_project_record(project_root):
        # Nothing of the packs to install or clean: the cache is not even opened.
        return result
    machine_platform = current_platform()
    keys = []
    previous_keys = set(read_project_record(project_root).get("clis", []))
    try:
        with CacheLock():
            for name, tool in sorted(desired.items()):
                cli = tool["cli"]
                if "package" in cli and cli["package"]["manager"] in SYSTEM_MANAGERS:
                    result["manual"].append(system_package_note(cli))
                    continue
                try:
                    key, marker, reused = install_one(cli, machine_platform)
                except InstallError as problem:
                    result["failed"].append(f"{name} {cli['version']}: {problem}")
                    # What this repository used stays in use until an install replaces it.
                    kept = previous.get(name)
                    kept_marker = read_marker(install_directory(kept["key"])) if kept and kept.get("key") in previous_keys else None
                    if kept_marker:
                        keys.append(kept["key"])
                        result["lock"][name] = kept
                        result["path"].append(os.path.join(install_directory(kept["key"]),
                                                           *kept_marker.get("pathDirectory", "").split("/")))
                    continue
                keys.append(key)
                (result["reused"] if reused else result["installed"]).append(f"{name} {cli['version']}")
                result["path"].append(os.path.join(install_directory(key), *marker["pathDirectory"].split("/")))
                result["lock"][name] = {"source": tool["source"], "profile": tool["profile"], "version": cli["version"],
                                        "origin": marker["origin"], "key": key, "sha256": marker.get("sha256")}
            result["removed"] = sorted(f"{name} {entry.get('version')}" for name, entry in previous.items()
                                       if name not in result["lock"])
            write_project_record(project_root, keys)
            clean_unused()
    except (InstallError, OSError) as problem:
        result["failed"].append(str(problem))
        result["lock"] = dict(previous)
        return result
    write_cli_path(project_root, result["path"])
    return result


def uninstall_all(project_root):
    """What agent-ready remove does: this repository uses no CLI, and the ones nobody uses go."""
    with CacheLock():
        write_project_record(project_root, [])
        removed = clean_unused()
    write_cli_path(project_root, [])
    return removed
