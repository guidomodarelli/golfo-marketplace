"""The documents of an office in the team sync (#169h): what is synchronized besides what was learned.

With ``sync.scope`` ``knowledge+documents`` (``auto``: when the selection has the ``documents``
capability), the sync also commits and merges the documents of the repository, under the convention of
that capability (rules/documents.md of the content):

* a Markdown document is the source: Git merges it by line, so changes in different parts of it merge by
  themselves; two changes of the same part are a conflict a person decides, like a rule
  (agent_ready_sync_conflicts.py), with the whole version of each side;
* a PDF or Word file is an input someone uploaded, never edited: when two machines bring two files with
  the same name, both stay, and the one that came from the remote gets its date in the name;
* what is generated from the Markdown (``output/``) and the files of the engine never go in a commit.
"""

import datetime
import difflib
import hashlib
import os
import subprocess

SCOPE_KEY = "sync.scope"
SCOPE_AUTO = "auto"
SCOPE_KNOWLEDGE = "knowledge"
SCOPE_DOCUMENTS = "knowledge+documents"
DOCUMENTS_PROFILE = "documents"
OUTPUT_DIRECTORY = "output"
MARKDOWN_SUFFIX = ".md"
# The files people upload, which are inputs: two of them are never merged, they are both kept.
INPUT_SUFFIXES = (".pdf", ".docx", ".doc", ".odt", ".rtf")
# What a document of the office is, and what is not one even when it is Markdown: the files of the engine
# and of the agents, and what is generated.
DOCUMENT_PATHSPECS = tuple(f":(glob)**/*{suffix}" for suffix in (MARKDOWN_SUFFIX,) + INPUT_SUFFIXES) + (
    ":(exclude,glob).agents/**",
    ":(exclude,glob).claude/**",
    ":(exclude,glob).codex/**",
    f":(exclude,glob){OUTPUT_DIRECTORY}/**",
    ":(exclude,glob)**/AGENTS.md",
    ":(exclude,glob)**/CLAUDE.md",
)
KIND_DOCUMENT = "document"
# How much of the difference of two versions the explanation shows.
DIFFERENCE_LINES = 12


def selected_profiles(lock):
    """The names of the profiles the lock selected, of the root and of each workspace."""
    lock = lock or {}
    selected = list(lock.get("profileOrder") or [])
    for workspace in (lock.get("workspaces") or {}).values():
        selected.extend(workspace.get("own") or [])
    return {name.rsplit("/", 1)[-1] for name in selected}


def effective_scope(configured, lock):
    """knowledge or knowledge+documents: the configured one, or for auto the one of the selection."""
    if configured in (SCOPE_KNOWLEDGE, SCOPE_DOCUMENTS):
        return configured
    return SCOPE_DOCUMENTS if DOCUMENTS_PROFILE in selected_profiles(lock) else SCOPE_KNOWLEDGE


def is_markdown_document(path):
    return path.endswith(MARKDOWN_SUFFIX) and not path.startswith((".agents/", ".claude/", ".codex/")) and \
        os.path.basename(path) not in ("AGENTS.md", "CLAUDE.md")


def is_input(path):
    return path.lower().endswith(INPUT_SUFFIXES)


def text_hash(text):
    return hashlib.sha256((text or "").replace("\r\n", "\n").encode("utf-8")).hexdigest()


def dated_name(path, existing, today=None):
    """``path`` with the date before its extension, and a counter when that name is taken too."""
    today = today or datetime.date.today().isoformat()
    stem, extension = os.path.splitext(path)
    candidate = f"{stem}-{today}{extension}"
    counter = 2
    while candidate in existing:
        candidate = f"{stem}-{today}-{counter}{extension}"
        counter += 1
    return candidate


def difference(mine, theirs):
    """The lines that differ between two versions of a document, as a short unified diff."""
    lines = list(difflib.unified_diff((mine or "").splitlines(), (theirs or "").splitlines(),
                                      "this machine", "the other", lineterm="", n=1))
    shown = lines[2:2 + DIFFERENCE_LINES]
    if len(lines) > 2 + DIFFERENCE_LINES:
        shown.append(f"... {len(lines) - 2 - DIFFERENCE_LINES} more line(s)")
    return shown


def document_conflict(path, mine, theirs, mine_change, theirs_change):
    """The record of a Markdown document changed in the same part on two machines."""
    return {
        "id": path, "path": path, "kind": KIND_DOCUMENT, "personal": False, "scoped": False,
        "mine": {"text": mine, "hash": text_hash(mine), "by": mine_change[0], "at": mine_change[1]},
        "theirs": {"text": theirs, "hash": text_hash(theirs), "by": theirs_change[0], "at": theirs_change[1]},
        "difference": difference(mine, theirs),
    }


def resolution_text(conflict):
    """The whole text a decision keeps for a document."""
    decision = conflict["decision"]
    if decision == "mine":
        return conflict["mine"]["text"]
    if decision == "theirs":
        return conflict["theirs"]["text"]
    return conflict["text"]


def blob(project_root, stage, path):
    """The bytes of ``path`` at a stage of the merge in progress (2 ours, 3 theirs), or None if absent."""
    result = subprocess.run(["git", "-C", project_root, "cat-file", "blob", f":{stage}:{path}"], capture_output=True,
                            check=False)
    return result.stdout if result.returncode == 0 else None


def settle_inputs(project_root, files, git):
    """Keep both sides of each uploaded file in conflict, the remote one with its date in the name.

    Two people uploaded a file with the same name, or one changed an input: an input is never merged, so
    the version of this machine keeps the name and the other one is saved beside it. Returns the files
    it settled; ``git`` runs a Git command in the checkout."""
    tracked = set(git(project_root, "ls-files").stdout.split("\n"))
    settled = []
    for path in files:
        if not is_input(path):
            continue
        ours, theirs = blob(project_root, 2, path), blob(project_root, 3, path)
        absolute = os.path.join(project_root, path)
        if ours is not None and theirs is not None and ours != theirs:
            other = dated_name(path, tracked | set(settled))
            with open(absolute, "wb") as handle:
                handle.write(ours)
            with open(os.path.join(project_root, other), "wb") as handle:
                handle.write(theirs)
            added = git(project_root, "add", "--", path, other)
            settled.append(other)
        else:
            # One side removed it, or both brought the same bytes: the file that exists stays.
            kept = ours if ours is not None else theirs
            with open(absolute, "wb") as handle:
                handle.write(kept)
            added = git(project_root, "add", "--", path)
        if added.returncode != 0:
            return None
        settled.append(path)
    return settled


def decision_holds(resolution, ours, theirs):
    """True while both versions are still the ones the person decided about."""
    return isinstance(resolution, dict) and resolution.get("mine") == text_hash(ours) and \
        resolution.get("theirs") == text_hash(theirs)
