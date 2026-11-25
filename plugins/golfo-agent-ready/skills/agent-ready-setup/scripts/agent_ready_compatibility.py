"""Compatibility a catalog declares: its version, the minimum engine it needs and its changelog.

golfo-agent-ready's catalog (``assets/profiles.json``) and every pack catalog (``agent-ready-pack.json``)
can declare, all optional:

- ``version``: semver of the content.
- ``minEngine``: the oldest engine (the golfo-agent-ready plugin that runs agent-ready-setup) with the
  features the content uses. There is no upper bound: a newer engine keeps reading the current
  ``schemaVersion``, and an incompatible schema raises ``schemaVersion`` instead.
- ``changes``: the changelog, ``[{"version", "summary", "breaking"?}]``.

An engine below ``minEngine``, or one that does not know the ``schemaVersion``, stops before
anything is written and says which plugin version to install. So does an engine older than the one that
wrote the lock (``generator.version``), or one without a readable version in a repository whose lock has one.
"""

import re

from agent_ready_common import ProfileError

COMPATIBILITY_KEYS = ("version", "minEngine", "changes")
CHANGE_KEYS = ("version", "summary", "breaking")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
ENGINE_PLUGIN = "golfo-agent-ready"


class EngineRequirementError(ProfileError):
    """A catalog this engine is too old for; ``required_version`` is the plugin to install (None: the newest)."""

    def __init__(self, message, required_version=None):
        super().__init__(message)
        self.required_version = required_version


def semver_key(text):
    """A key that orders versions by semver precedence, or None when ``text`` is not one.

    A pre-release sorts before its release and its identifiers compare one by one: numbers by
    value and below text, and a shorter list first when the rest is equal. Build metadata does
    not count.
    """
    match = SEMVER.fullmatch(text or "") if isinstance(text, str) else None
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    core = text.split("+", 1)[0]
    if "-" not in core:
        return major, minor, patch, 1, ()
    identifiers = tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in core.split("-", 1)[1].split("."))
    return major, minor, patch, 0, identifiers


def validate_compatibility(label, catalog):
    """Check the types of the compatibility fields of a catalog; ``label`` names it in errors."""
    for key in ("version", "minEngine"):
        if key in catalog and semver_key(catalog[key]) is None:
            raise ProfileError(f"{label}: {key} must be a semantic version such as 1.2.0, not {catalog[key]!r}")
    changes = catalog.get("changes", [])
    if not isinstance(changes, list):
        raise ProfileError(f"{label}: changes must be a list of {{version, summary, breaking}}")
    for position, change in enumerate(changes, start=1):
        where = f"{label}: change {position}"
        if not isinstance(change, dict):
            raise ProfileError(f"{where} must be an object with version, summary and an optional breaking")
        unknown = sorted(set(change) - set(CHANGE_KEYS))
        if unknown:
            raise ProfileError(f"{where} has unknown fields: {', '.join(unknown)}")
        if semver_key(change.get("version")) is None:
            raise ProfileError(f"{where}: version must be a semantic version, not {change.get('version')!r}")
        if not isinstance(change.get("summary"), str) or not change["summary"].strip():
            raise ProfileError(f"{where}: summary must be a non-empty text")
        if "breaking" in change and not isinstance(change["breaking"], bool):
            raise ProfileError(f"{where}: breaking must be true or false")


def require_engine(label, catalog, engine_version, supported_schema):
    """Stop before writing when this engine cannot apply the catalog, saying what to install."""
    schema = catalog.get("schemaVersion")
    if isinstance(schema, int) and not isinstance(schema, bool) and schema > supported_schema:
        raise EngineRequirementError(f"{label} uses catalog schemaVersion {schema}, and this engine ({ENGINE_PLUGIN} "
                                     f"{engine_version or 'unknown'}) reads up to {supported_schema}: update the "
                                     f"{ENGINE_PLUGIN} plugin and run it again; nothing was changed")
    minimum = catalog.get("minEngine")
    if minimum is None:
        return
    minimum_key = semver_key(minimum)
    if minimum_key is None:
        raise ProfileError(f"{label}: minEngine must be a semantic version such as 1.2.0, not {minimum!r}")
    engine_key = semver_key(engine_version)
    if engine_key and engine_key < minimum_key:
        raise EngineRequirementError(f"{label} needs the agent-ready-setup engine {minimum} or newer, and this installation "
                                     f"runs {ENGINE_PLUGIN} {engine_version}: install the {ENGINE_PLUGIN} plugin {minimum} "
                                     "or newer and run it again; nothing was changed", required_version=minimum)


def require_engine_not_older_than_lock(lock, engine_version):
    """Stop before writing when the lock was written by a newer engine than this one, or this one has no version.

    An older engine (a stale checkout, a copied skill folder) projects its own assets over the ones the
    newer engine wrote and reverts them; without a readable version it cannot prove it is not older.
    """
    locked_version = ((lock or {}).get("generator") or {}).get("version")
    locked_key = semver_key(locked_version)
    if locked_key is None:
        return
    engine_key = semver_key(engine_version)
    if engine_key is not None and engine_key >= locked_key:
        return
    running = f"{ENGINE_PLUGIN} {engine_version}" if engine_key else f"a {ENGINE_PLUGIN} of unknown version"
    raise EngineRequirementError(f"this repository was set up by {ENGINE_PLUGIN} {locked_version}, and this installation "
                                 f"runs {running}, which would revert its files: install the {ENGINE_PLUGIN} plugin "
                                 f"{locked_version} or newer and run it again; nothing was changed",
                                 required_version=locked_version)


def changes_between(changes, current, new):
    """The declared changes after ``current`` up to ``new``, newest first."""
    current_key, new_key = semver_key(current), semver_key(new)
    if not current_key or not new_key:
        return []
    selected = [change for change in changes or [] if current_key < semver_key(change["version"]) <= new_key]
    return sorted(selected, key=lambda change: semver_key(change["version"]), reverse=True)


def is_major_jump(current, new):
    """A new major version; in 0.x, where every minor may break, a new minor counts as one."""
    current_key, new_key = semver_key(current), semver_key(new)
    if not current_key or not new_key or new_key <= current_key:
        return False
    if current_key[0] == 0 and new_key[0] == 0:
        return new_key[1] > current_key[1]
    return new_key[0] > current_key[0]


def version_change(source, current, new, changes):
    """What a plan reports for a source whose version moves, or None when it does not."""
    if not current or not new or current == new:
        return None
    selected = changes_between(changes, current, new)
    return {
        "source": source,
        "from": current,
        "to": new,
        "majorJump": is_major_jump(current, new),
        "changes": selected,
        "breaking": [change for change in selected if change.get("breaking")],
    }
