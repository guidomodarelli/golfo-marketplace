"""The memory of what happened (Engram): the content profile that every selection brings by default,
the key that turns it off, and the files of Engram that must never be versioned.

Engram keeps facts and context (people, clients, case files, decisions) on the machine of the user, by
project. agent-ready-setup never exports that base: it never runs ``engram sync`` on the repository,
the content ignores ``.engram/`` in the managed block of ``.gitignore``, and ``agent-ready check``
fails when a file of ``.engram/`` is versioned, whatever the configuration of the repository says.
How to work (rules and skills) is the learning of agent_ready_learning, never this memory.
"""

import os
import subprocess

# memory.enabled and memory.engram: both on, every selection brings the profile memory-engram of the
# content by default.
MEMORY_ENABLED_KEY = "memory.enabled"
MEMORY_ENGRAM_KEY = "memory.engram"
MEMORY_ENGRAM_PROFILE = "memory-engram"
# Where `engram sync` writes the chunks it shares through Git: never versioned.
ENGRAM_DIRECTORY = ".engram"


def selection_effects(catalog, engram_enabled):
    """What memory.engram does to a selection: (profiles every selection brings by default, profiles
    left out of it). Nothing when the catalog does not publish the profile."""
    if MEMORY_ENGRAM_PROFILE not in catalog["profiles"]:
        return (), ()
    if engram_enabled:
        return (MEMORY_ENGRAM_PROFILE,), ()
    return (), (MEMORY_ENGRAM_PROFILE,)


def versioned_engram_files(project_root):
    """The files of .engram/ that Git tracks in the repository, sorted. Empty outside Git.

    Without .engram/ in the working tree Git is never run: a checkout has every file Git tracks, so
    nothing of it can be versioned, and a check with ci.enabled false keeps running nothing.
    """
    if not os.path.lexists(os.path.join(project_root, ENGRAM_DIRECTORY)):
        return []
    completed = subprocess.run(["git", "-C", project_root, "ls-files", "-z", "--", ENGRAM_DIRECTORY],
                               capture_output=True, check=False)
    if completed.returncode != 0:
        return []
    return sorted(path for path in completed.stdout.decode("utf-8", "replace").split("\0") if path)
