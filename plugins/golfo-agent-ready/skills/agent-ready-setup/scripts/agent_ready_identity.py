"""Who uses this machine, apart from the Git account: the identity of the learning and the sync (#169).

The identity lives in the configuration of the user of the operating system, never in the repository
nor in the hardware: two people can share a computer with their own users, and one person can use two
computers (``agent-ready identity link`` gives the second one the same id). The commits can go out with
a shared Git account; the person is the ``Learned-by:`` trailer of each learning.

``collaboration`` says how the people of a repository share what is learned: ``business`` (an
office: personal and team learning, the repository synchronized for them) or ``software`` (a code
repository: team learning only, inside the work of each branch). ``auto`` picks it from the selection.
"""

import getpass
import json
import os
import re
import socket

from agent_ready_common import StateError, read_json_file, write_text_atomically
from agent_ready_config import user_config_path

IDENTITY_FILE_NAME = "identity.json"
IDENTITY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._@-]{0,63}$")
IDENTITY_NAME_MAX_LENGTH = 80
SOURCE_FILE = "file"
SOURCE_DEFAULT = "default"
LEARNED_BY_TRAILER = "Learned-by"

COLLABORATION_PRESET_KEY = "collaboration"
PRESET_AUTO = "auto"
PRESET_BUSINESS = "business"
PRESET_SOFTWARE = "software"
# The capability every software stack requires: a selection with it is a code repository.
SOFTWARE_PROFILE = "software-development"


def identity_path(environment=None):
    """``${XDG_CONFIG_HOME:-~/.config}/agent-ready-setup/identity.json`` of this user of the system."""
    configuration_file = user_config_path(os.environ if environment is None else environment)
    return os.path.join(os.path.dirname(configuration_file), IDENTITY_FILE_NAME)


def slug(text):
    """Lowercase, with anything outside ``[a-z0-9._-]`` turned into a hyphen."""
    # Only a letter or a digit opens it, as validate_id asks: a user such as _ana becomes ana.
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9._-]", "-", text.lower())).strip("-._") or "user"


def default_identity():
    """``user-of-the-system@name-of-the-machine``, the identity of a machine nobody configured."""
    try:
        user = getpass.getuser()
    except (OSError, KeyError):
        user = "user"
    host = socket.gethostname().split(".")[0] or "machine"
    identity_id = f"{slug(user)}@{slug(host)}"[:64]
    return {"id": identity_id, "name": user, "source": SOURCE_DEFAULT}


def validate_id(identity_id):
    if not isinstance(identity_id, str) or not IDENTITY_ID_PATTERN.match(identity_id):
        raise StateError(f"identity id {identity_id!r} must be 1 to 64 lowercase letters, digits, '.', '_', '-' or '@', "
                         "starting with a letter or a digit")
    return identity_id


def validate_name(name):
    if not isinstance(name, str) or not name.strip() or len(name) > IDENTITY_NAME_MAX_LENGTH or "\n" in name:
        raise StateError(f"identity name must be one line of 1 to {IDENTITY_NAME_MAX_LENGTH} characters")
    return name.strip()


def read_identity(environment=None):
    """The identity of this user of the system: the file, else the default. A broken file is an error."""
    path = identity_path(environment)
    if not os.path.exists(path):
        return default_identity()
    content = read_json_file(path, "the identity")
    try:
        return {"id": validate_id(content.get("id")), "name": validate_name(content.get("name")), "source": SOURCE_FILE}
    except StateError as invalid:
        raise StateError(f"{path}: {invalid}; fix it with agent-ready identity set") from invalid


def write_identity(identity_id=None, name=None, environment=None):
    """Store the identity, keeping what is not given from the current one. Returns it.

    With both fields given, the current file is not read: that is how a broken one is replaced."""
    current = {} if identity_id and name else read_identity(environment)
    stored = {"id": validate_id(identity_id or current["id"]), "name": validate_name(name or current["name"])}
    write_text_atomically(identity_path(environment), json.dumps(stored, indent=2, ensure_ascii=False) + "\n")
    return dict(stored, source=SOURCE_FILE)


def learned_by_trailer(environment=None):
    """The ``Learned-by:`` line of a learning commit, with the id of this user of the system."""
    return f"{LEARNED_BY_TRAILER}: {read_identity(environment)['id']}\n"


def collaboration_preset(configured, lock):
    """The effective preset: the configured one, or for ``auto`` the one of the selection.

    The selection is the one the lock resolved, of the root (``profileOrder``) and of each workspace
    (``workspaces[*].own``): a monorepo may select its code stacks only in its workspaces. One with
    software-development (a stack of code, or that capability alone) is a code repository.
    """
    if configured in (PRESET_BUSINESS, PRESET_SOFTWARE):
        return configured
    lock = lock or {}
    selected = list(lock.get("profileOrder") or [])
    for workspace in (lock.get("workspaces") or {}).values():
        selected.extend(workspace.get("own") or [])
    names = {name.rsplit("/", 1)[-1] for name in selected}
    return PRESET_SOFTWARE if SOFTWARE_PROFILE in names else PRESET_BUSINESS
