"""Nested targets: the block a profile publishes in the AGENTS.md of one folder of the repository.

Many instructions belong to a folder, not to the repository: the routes of a Next.js App Router
under app/, the handlers of a BFF under src/server/, one Gradle module. A profile, of golfo-kit or of
a pack, declares each such target in its catalog entry and publishes the block in its asset tree:

    "nested": {"app-router": {"candidates": ["app", "src/app"]}}   ->   nested/app-router.md

The id of a target is "<profile>/<name>" (nextjs-app-router/app-router, acme/backend/handlers). Its
folders come from the manifest (nested.targets), or else from the first candidate folder that exists;
without either, nothing is written and plan says so. In each folder the block goes into AGENTS.md
between the markers of its id, like any managed block (agent_ready_blocks.py), and the apply leaves a
CLAUDE.md proxy next to the AGENTS.md it writes, because Claude Code only loads a nested AGENTS.md
through it. Codex does not load a nested AGENTS.md below the folder it starts in, so the root AGENTS.md
gets an index of them, a section of its own (index_content). The contract, and how each provider loads
nested instructions, are in references/nested-instructions.md.
"""

import os
import subprocess

import agent_ready_blocks as managed_blocks
from agent_ready_common import KEBAB_CASE_NAME, ProfileError, is_link
from agent_ready_detection import is_contained_pattern

NESTED_KEY = "nested"
CANDIDATES_KEY = "candidates"
TARGET_KEYS = (CANDIDATES_KEY,)
NESTED_DIRECTORY = "nested"
NESTED_PREFIX = NESTED_DIRECTORY + "/"
CONTENT_SUFFIX = ".md"
INSTRUCTIONS_FILE = "AGENTS.md"
PROXY_FILE = "CLAUDE.md"
BARE_PROXY = "@AGENTS.md"
# A nested CLAUDE.md only imports its AGENTS.md: the root proxy carries the centralization rule.
NESTED_PROXY_TEXT = BARE_PROXY + "\n"
# The index of the nested AGENTS.md files, a section of the root AGENTS.md. Its id cannot be the name
# of a profile, which is kebab-case.
INDEX_BLOCK_ID = "agent-ready:nested-index"
INDEX_SOURCE = "agent-ready:nested-index"
INDEX_HEADING = "## Nested instructions"
INDEX_LEAD = "Before you read or change files under one of these folders, read and follow its own `AGENTS.md`:"
TARGET_SEPARATOR = "/"
# Folders whose files Git and agent-ready-setup own: a nested target never goes there.
RESERVED_FOLDERS = (".git", ".agents", ".claude", ".codex")
PATTERN_CHARACTERS = "*?[]{}!"
# Where the folders of a target come from, as plan reports it.
ORIGIN_MANIFEST = "manifest"
ORIGIN_DETECTED = "detected"
ORIGIN_NONE = "none"
ORIGIN_DISABLED = "disabled"
ORIGIN_UNKNOWN = "unknown"


def target_id(profile, name):
    """Id of a nested target and of its block: "<profile>/<name>"."""
    return f"{profile}{TARGET_SEPARATOR}{name}"


def content_path(asset_root, name):
    """The file of a profile's asset tree that holds the block of a target."""
    return os.path.join(asset_root, NESTED_DIRECTORY, name + CONTENT_SUFFIX)


def destination_in(folder):
    """The AGENTS.md of a folder, as a repository path."""
    return f"{folder}/{INSTRUCTIONS_FILE}"


def is_nested_destination(destination):
    """True for the AGENTS.md of a folder, not the root one."""
    return destination != INSTRUCTIONS_FILE and destination.rsplit("/", 1)[-1] == INSTRUCTIONS_FILE


def proxy_of(destination):
    """The CLAUDE.md next to an AGENTS.md, as a repository path."""
    folder = os.path.dirname(destination)
    return f"{folder}/{PROXY_FILE}" if folder else PROXY_FILE


def folder_problem(folder):
    """Why a folder cannot take a nested target, or None: it is a plain relative folder of the repository."""
    if not isinstance(folder, str) or not is_contained_pattern(folder) or any(ord(character) < 32 for character in folder):
        return "is not a relative folder inside the repository (no leading or trailing slash, '.' or '..')"
    if any(character in PATTERN_CHARACTERS for character in folder):
        return "is a pattern, not a folder"
    if folder.split("/", 1)[0].casefold() in RESERVED_FOLDERS:
        return f"is under {', '.join(name + '/' for name in RESERVED_FOLDERS)}, which Git and agent-ready-setup own"
    return None


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def validate_declaration(profile, entry):
    """Raise ProfileError for a ``nested`` field of a catalog profile that is not a set of targets."""
    declared = entry.get(NESTED_KEY)
    if declared is None:
        return
    if not isinstance(declared, dict) or not declared:
        raise ProfileError(f"profile '{profile}': '{NESTED_KEY}' must be an object with one entry per target, "
                           "such as {\"app-router\": {\"candidates\": [\"app\", \"src/app\"]}}")
    for name, target in declared.items():
        if not KEBAB_CASE_NAME.fullmatch(name):
            raise ProfileError(f"profile '{profile}': the nested target '{name}' needs a kebab-case name")
        if not isinstance(target, dict) or set(target) - set(TARGET_KEYS):
            raise ProfileError(f"profile '{profile}': the nested target '{name}' only takes {', '.join(TARGET_KEYS)}")
        candidates = target.get(CANDIDATES_KEY, [])
        if not isinstance(candidates, list):
            raise ProfileError(f"profile '{profile}': '{CANDIDATES_KEY}' of the nested target '{name}' must be a list of folders")
        for candidate in candidates:
            problem = folder_problem(candidate)
            if problem:
                raise ProfileError(f"profile '{profile}': the candidate {candidate!r} of the nested target '{name}' {problem}")


def validate_published(profile, entry, asset_root):
    """Each declared target has its block in nested/<name>.md, and each file there is a declared target."""
    declared = entry.get(NESTED_KEY) or {}
    directory = os.path.join(asset_root, NESTED_DIRECTORY) if asset_root else None
    published = set()
    if directory and os.path.lexists(directory):
        if is_link(directory) or not os.path.isdir(directory):
            raise ProfileError(f"profile '{profile}': {NESTED_DIRECTORY} must be a directory of its assets")
        for file_name in sorted(os.listdir(directory)):
            name = file_name[:-len(CONTENT_SUFFIX)] if file_name.endswith(CONTENT_SUFFIX) else None
            path = os.path.join(directory, file_name)
            if name not in declared or is_link(path) or not os.path.isfile(path):
                raise ProfileError(f"profile '{profile}': {NESTED_PREFIX}{file_name} is not the block of a nested "
                                   f"target it declares in '{NESTED_KEY}'")
            published.add(name)
    missing = sorted(set(declared) - published)
    if missing:
        raise ProfileError(f"profile '{profile}' declares the nested target '{missing[0]}' but does not publish "
                           f"{NESTED_PREFIX}{missing[0]}{CONTENT_SUFFIX}")


def declarations(catalog, resolved):
    """[(id, profile, name, candidates)] of every nested target the selection publishes, in its order."""
    return [(target_id(profile, name), profile, name, list(target.get(CANDIDATES_KEY, [])))
            for profile in resolved
            for name, target in (catalog["profiles"][profile].get(NESTED_KEY) or {}).items()]


# ---------------------------------------------------------------------------
# Destinations
# ---------------------------------------------------------------------------

def configured_targets(entries, manifest_path):
    """{id: entry} of nested.targets; an id listed twice is an error."""
    configured = {}
    for entry in entries or []:
        if entry["id"] in configured:
            raise ProfileError(f"{manifest_path}: nested.targets lists {entry['id']} twice; keep one entry per target")
        configured[entry["id"]] = entry
    return configured


def is_ignored(project_root, path):
    """True when Git ignores the path. When Git cannot tell, it counts as ignored: nothing is written there."""
    completed = subprocess.run(["git", "check-ignore", "-q", "--", path], cwd=project_root,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return completed.returncode != 1


def is_folder(project_root, folder):
    return os.path.isdir(os.path.join(project_root, *folder.split("/")))


def configured_folder_problem(project_root, folder):
    """Why a folder of the manifest cannot take a target, or None. A symlink on its path is a conflict of
    the block instead (agent_ready_blocks.classify), like for any other block."""
    problem = folder_problem(folder)
    if problem is None and not is_folder(project_root, folder):
        problem = "does not exist in the repository"
    # Git cannot tell whether a path beyond a symlink is ignored; classify reports the link itself.
    if problem is None and not managed_blocks.has_linked_directory(project_root, destination_in(folder)) \
            and is_ignored(project_root, destination_in(folder)):
        problem = "is ignored by Git"
    return problem


def detected_folder(project_root, candidates):
    """The first candidate that is a folder of the repository Git does not ignore, reached without a symlink."""
    for folder in candidates:
        destination = destination_in(folder)
        if is_folder(project_root, folder) and not managed_blocks.has_linked_directory(project_root, destination) \
                and not is_ignored(project_root, destination):
            return folder
    return None


def resolve(project_root, targets, enabled, configured, manifest_path):
    """The folders of each nested target of the selection, and what plan reports of them.

    ``targets`` are the declarations of the selection and ``configured`` the entries of nested.targets
    by id. Returns ({id: [folder]}, report): the manifest wins over the candidates, a folder of the
    manifest that cannot take the block stops before anything is written, and the report lists each
    target with where its folders came from, plus each configured id no selected profile publishes.
    """
    folders, report = {}, []
    for identifier, profile, _, candidates in targets:
        entry = {"id": identifier, "profile": profile, "candidates": candidates, "paths": []}
        setting = configured.get(identifier, {})
        if not enabled or setting.get("enabled") is False:
            entry.update(origin=ORIGIN_DISABLED, disabledBy="nested.enabled" if not enabled else "nested.targets")
        elif "paths" in setting:
            for folder in setting["paths"]:
                problem = configured_folder_problem(project_root, folder)
                if problem:
                    raise ProfileError(f"{manifest_path}: the folder {folder!r} of the nested target {identifier} "
                                       f"{problem}; nothing was written")
            entry.update(origin=ORIGIN_MANIFEST, paths=list(setting["paths"]))
        else:
            found = detected_folder(project_root, candidates)
            entry.update(origin=ORIGIN_DETECTED if found else ORIGIN_NONE, paths=[found] if found else [])
        folders[identifier] = entry["paths"]
        report.append(entry)
    published = {identifier for identifier, _, _, _ in targets}
    report += [{"id": identifier, "origin": ORIGIN_UNKNOWN, "paths": []} for identifier in sorted(set(configured) - published)]
    return folders, report


def index_content(destinations):
    """The section of the root AGENTS.md that sends Codex to each nested AGENTS.md before it works there."""
    lines = [INDEX_HEADING, "", INDEX_LEAD, ""] + [f"- `{destination}`" for destination in sorted(destinations)]
    return "\n".join(lines) + "\n"


def describe(entry):
    """One line of plan for a nested target."""
    identifier = entry["id"]
    if entry["origin"] == ORIGIN_UNKNOWN:
        return f"{identifier}: in nested.targets, but no selected profile publishes it"
    if entry["origin"] == ORIGIN_DISABLED:
        return f"{identifier}: off ({entry['disabledBy']}); nothing is written and the apply retires its blocks"
    if entry["origin"] == ORIGIN_NONE:
        tried = ", ".join(entry["candidates"]) or "no candidate folders"
        return f"{identifier}: no folder, nothing is written (tried {tried}; set one in nested.targets)"
    destinations = ", ".join(destination_in(folder) for folder in entry["paths"]) or "no folder (nested.targets)"
    origin = "nested.targets" if entry["origin"] == ORIGIN_MANIFEST else "detected"
    line = f"{identifier} -> {destinations} ({origin})"
    for folder in entry.get("waiting", []):
        line += (f"; waits in {folder}: its {PROXY_FILE} has instructions of its own that the normalization does not "
                 f"move to {INSTRUCTIONS_FILE} (they differ, or Git ignores it); merge them into {INSTRUCTIONS_FILE}")
    return line


# ---------------------------------------------------------------------------
# Proxies
# ---------------------------------------------------------------------------

def is_bare_proxy(path):
    """True for a CLAUDE.md that is @AGENTS.md alone, read as is_plain_claude_proxy in
    instruction-normalization.sh reads it: a command substitution drops every final line end."""
    with open(path, "rb") as file_handle:
        return file_handle.read().rstrip(b"\n") == BARE_PROXY.encode("utf-8")


def is_proxy(path, proxy_text):
    """True for a CLAUDE.md that only points to its AGENTS.md: the proxy or a bare @AGENTS.md."""
    if is_link(path) or not os.path.isfile(path):
        return False
    text = managed_blocks.read_text(path).replace("\r\n", "\n")
    return text == proxy_text.replace("\r\n", "\n") or text.strip() == BARE_PROXY


def place_proxies(project_root, written, deleted, proxy_text):
    """A CLAUDE.md proxy next to each nested AGENTS.md the apply wrote, and none next to one it deleted.

    The proxy it writes only imports its AGENTS.md; ``proxy_text`` is the root proxy, which also counts
    as a proxy when one goes. Returns (created, removed, failed). A CLAUDE.md that is not a proxy stays:
    the normalization of the instructions reports it.
    """
    created, removed, failed = [], [], []
    for destination in written:
        if not is_nested_destination(destination):
            continue
        proxy = proxy_of(destination)
        path = os.path.join(project_root, *proxy.split("/"))
        if os.path.lexists(path):
            continue
        try:
            managed_blocks.write_atomically(path, NESTED_PROXY_TEXT)
            created.append(proxy)
        except OSError as write_error:
            failed.append(f"{proxy}: {write_error.strerror or write_error}")
    for destination in deleted:
        if not is_nested_destination(destination):
            continue
        proxy = proxy_of(destination)
        path = os.path.join(project_root, *proxy.split("/"))
        if not is_proxy(path, proxy_text):
            continue
        try:
            os.unlink(path)
            removed.append(proxy)
        except OSError as remove_error:
            failed.append(f"{proxy}: {remove_error.strerror or remove_error}")
    return created, removed, failed
