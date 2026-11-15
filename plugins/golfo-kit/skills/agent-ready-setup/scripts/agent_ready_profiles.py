"""Profiles: the catalog of the content, of the engine's CI profiles and of the packs, the effective catalog of a
repository, and how a selection resolves into profiles, with their defaults, exclusions and overrides.
"""

import os

import agent_ready_compatibility as compatibility
import agent_ready_content as content_source
import agent_ready_nested as nested
from agent_ready_common import IncompleteEvaluationError, ProfileError, StateError, read_json_file
from agent_ready_config import ConfigurationError
from agent_ready_content import engine_version_of
from agent_ready_detection import STACK_PROFILE_KIND, DetectionSchemaError, required_layers, validate_catalog_detection
from agent_ready_layout import PROFILE_CATALOG_RELATIVE_PATH
from agent_ready_lockfile import read_lock
from agent_ready_manifest import configuration_of, declared_sources
from agent_ready_options import CI_PROVIDER_KEY, CI_PROVIDER_NONE, EXCLUDED_DEFAULTS_KEY, SOURCES_ENABLED_KEY
from agent_ready_packs import (
    PACK_CATALOG_FILE_NAME,
    PACK_SCHEMA_VERSION,
    SOURCE_AVAILABLE,
    effective_update_mode,
    is_pack_profile,
    load_pack_catalog,
    locate_source,
    source_of_profile,
)

# The CI profiles, part of the engine: their workflows run the CLI of this version.
ENGINE_CI_CATALOG_RELATIVE_PATH = "assets/ci/profiles.json"
BASE_PROFILE_NAME = "common"
# Profiles of the CI files: ci.provider picks one (ci-<provider>), never the profile selection.
CI_PROFILE_KIND = "ci"
CI_PROFILE_PREFIX = "ci-"
# The schemaVersion of the content catalog this engine reads; a newer one asks for a newer plugin.
GOLFO_CATALOG_SCHEMA_VERSION = 1

# A profile's ``defaults``: the profiles it brings unless excludedDefaults leaves them out.
DEFAULTS_KEY = "defaults"
# An asset of another profile of the selection that a profile replaces, as "<profile>:<path>":
# "react:rules/react-testing.md", or "software-development:skills/pr-review-workflow" for a skill.
OVERRIDES_KEY = "overrides"
# Skills of other profiles a skill goes together with, as "<profile>:skills/<name>" (read in #72c).
COMPLEMENTS_KEY = "complements"
ASSET_REFERENCE_SEPARATOR = ":"
OVERRIDABLE_DIRECTORIES = ("rules", "skills", "agents", "commands")
# What complements may name besides assets: the tools of a profile, by kind and name.
COMPLEMENTABLE_DIRECTORIES = OVERRIDABLE_DIRECTORIES + ("mcpServers", "clis")
# A bundle publishes nothing and only groups other profiles through ``requires``.
BUNDLE_PROFILE_KIND = "bundle"
BUNDLE_FORBIDDEN_KEYS = ("assets", "tools", "detect", DEFAULTS_KEY, OVERRIDES_KEY, COMPLEMENTS_KEY, "clis",
                         "mcpServers", "scripts", nested.NESTED_KEY)


def parse_asset_reference(reference, what, directories=None):
    """(profile, path) of "<profile>:<path>", where path is a rule, agent or command file or a skill directory.

    ``directories`` are the first parts the reference may use: what an override can replace by
    default; complements also name the tools of a profile (mcpServers/<name>, clis/<name>).
    """
    directories = directories or OVERRIDABLE_DIRECTORIES
    if not isinstance(reference, str) or reference.count(ASSET_REFERENCE_SEPARATOR) != 1:
        raise ProfileError(f"{what}: '{reference}' must be <profile>:<path>, such as react:rules/react-testing.md")
    profile, path = reference.split(ASSET_REFERENCE_SEPARATOR)
    parts = path.split("/")
    if (not profile or len(parts) < 2 or parts[0] not in directories
            or any(part in ("", ".", "..") for part in parts)):
        raise ProfileError(f"{what}: '{reference}' must name a path under {', '.join(directories)}, "
                           "such as react:rules/react-testing.md or software-development:skills/pr-review-workflow")
    return profile, path


def resolved_overrides(skill_dir, catalog, resolved, skipped=None):
    """{target profile: {path: overriding profile}} of the selection, validated against what it publishes.

    A profile replaces an asset of another selected profile on purpose: only its own asset is
    projected. An override of an asset, or a profile, that the selection does not have is an error.
    ``skipped(name, path)`` leaves out an override that is validated somewhere else.
    """
    overridden = {}
    for name in resolved:
        for reference in catalog["profiles"][name].get(OVERRIDES_KEY, []):
            target, path = parse_asset_reference(reference, f"profile '{name}' {OVERRIDES_KEY}")
            if skipped and skipped(name, path):
                continue
            if target == name:
                raise ProfileError(f"profile '{name}' overrides its own {path}; remove the file instead")
            if target == BASE_PROFILE_NAME:
                raise ProfileError(f"profile '{name}' overrides {reference}: the core cannot be overridden yet; "
                                   f"add a rule of your own next to it")
            if target not in resolved:
                raise ProfileError(f"profile '{name}' overrides {reference}, but the selection does not have "
                                   f"'{target}'; nothing was written")
            target_root = profile_asset_root(skill_dir, catalog, target)
            if not target_root or not os.path.exists(os.path.join(target_root, *path.split("/"))):
                raise ProfileError(f"profile '{name}' overrides {reference}, which '{target}' does not publish; "
                                   f"nothing was written")
            previous = overridden.setdefault(target, {}).setdefault(path, name)
            if previous != name:
                raise ProfileError(f"profiles '{previous}' and '{name}' both override {reference}; keep one")
    return overridden


def is_overridden(overridden, profile, relative_path):
    """True when another profile of the selection replaces this asset (a file, or a file of a skill directory)."""
    return any(relative_path == path or relative_path.startswith(path + "/")
               for path in overridden.get(profile, {}))


def engine_ci_profiles(skill_dir):
    """The CI profiles of the engine (assets/ci/profiles.json): their files run the CLI of this engine.

    A skill directory without that catalog (a trimmed copy of the skill) has no CI profiles.
    """
    path = os.path.join(skill_dir, ENGINE_CI_CATALOG_RELATIVE_PATH)
    if not os.path.isfile(path):
        return {}
    try:
        catalog = read_json_file(path, "CI profile catalog")
    except StateError as caught_error:
        raise ProfileError(str(caught_error)) from caught_error
    profiles = catalog.get("profiles")
    if not isinstance(profiles, dict) or any(not isinstance(entry, dict) or entry.get("kind") != CI_PROFILE_KIND
                                             for entry in profiles.values()):
        raise ProfileError(f"{path} must list profiles of kind {CI_PROFILE_KIND} only")
    return profiles


def load_profile_catalog(skill_dir):
    """Load and validate the profile catalog of the skill source.

    Content that needs a newer engine than the installed one (``minEngine``, ``schemaVersion``)
    stops here, before anything is written.
    """
    catalog_path = os.path.join(skill_dir, PROFILE_CATALOG_RELATIVE_PATH)
    try:
        catalog = read_json_file(catalog_path, "profile catalog")
    except StateError as caught_error:
        raise ProfileError(str(caught_error)) from caught_error
    label = f"the {content_source.CONTENT_SOURCE_NAME} catalog"
    compatibility.require_engine(label, catalog, engine_version_of(skill_dir), GOLFO_CATALOG_SCHEMA_VERSION)
    compatibility.validate_compatibility(label, catalog)
    profiles = catalog.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ProfileError(f"profile catalog {catalog_path} has no profiles")
    # The CI profiles come with the engine (assets/ci/profiles.json): the content declares none.
    ci_profiles = engine_ci_profiles(skill_dir)
    taken_names = sorted(set(profiles) & set(ci_profiles))
    if taken_names:
        raise ProfileError(f"profile catalog {catalog_path}: profile '{taken_names[0]}' takes the name of a CI profile of the engine")
    profiles.update(ci_profiles)
    try:
        validate_catalog_detection(profiles)
    except DetectionSchemaError as caught_error:
        raise ProfileError(f"profile catalog {catalog_path}: {caught_error}") from caught_error
    for name, profile in sorted(profiles.items()):
        validate_selection_fields(name, profile)
        relative_root = profile.get("assets")
        asset_root = os.path.join(skill_dir, relative_root) if relative_root else None
        # A profile whose tree this source does not carry is checked when a selection resolves it
        # (profile_asset_root, nested_contents), not for every catalog load.
        if asset_root is None or os.path.isdir(asset_root):
            nested.validate_published(name, profile, asset_root)
    return catalog


def validate_selection_fields(name, profile):
    """``defaults`` is a list of other profiles, and a bundle only groups profiles through ``requires``.

    A bundle publishes nothing: no assets, tools, detection or defaults of its own, so what it brings
    is exactly the profiles it requires, each with its own defaults.
    """
    nested.validate_declaration(name, profile)
    for field, directories in ((OVERRIDES_KEY, OVERRIDABLE_DIRECTORIES), (COMPLEMENTS_KEY, COMPLEMENTABLE_DIRECTORIES)):
        for reference in profile.get(field, []) if isinstance(profile.get(field, []), list) else [None]:
            parse_asset_reference(reference, f"profile '{name}' {field}", directories)
    defaults = profile.get(DEFAULTS_KEY, [])
    if not isinstance(defaults, list) or not all(isinstance(item, str) and item for item in defaults):
        raise ProfileError(f"profile '{name}': '{DEFAULTS_KEY}' must be a list of profile names")
    if name in defaults:
        raise ProfileError(f"profile '{name}' cannot list itself in '{DEFAULTS_KEY}'")
    if profile.get("kind") != BUNDLE_PROFILE_KIND:
        return
    published = sorted(key for key in BUNDLE_FORBIDDEN_KEYS if key in profile)
    if published:
        raise ProfileError(f"bundle '{name}' only groups profiles through 'requires'; it cannot declare: {', '.join(published)}")
    requires = profile.get("requires")
    if not isinstance(requires, list) or not requires:
        raise ProfileError(f"bundle '{name}' needs 'requires' with the profiles it groups")


def locked_sources_of(project_root):
    """Profile sources recorded by the last apply."""
    lock = read_lock(project_root)
    return (lock or {}).get("profileSources", {})


def load_effective_catalog(project_root, skill_dir, source_state=None):
    """Golfo's catalog plus the profiles of every source available on this machine.

    Pack profiles are namespaced, so they never replace a Golfo profile, and the global
    fields of Golfo's catalog stay as they are. Nothing here uses the network or runs
    anything from a pack. ``source_state`` holds the commits an apply just adopted.
    """
    catalog = load_profile_catalog(skill_dir)
    golfo_profile_names = set(catalog["profiles"])
    locked_sources = locked_sources_of(project_root)
    configuration = configuration_of(project_root)
    catalog["sources"] = {}
    catalog["packAssetRoots"] = {}
    catalog["sourcesEnabled"] = configuration.value(SOURCES_ENABLED_KEY)
    for declaration in declared_sources(project_root):
        name = declaration["name"]
        update_mode = effective_update_mode(configuration, declaration)
        source = locate_source(declaration, locked_sources.get(name), project_root, update_mode, (source_state or {}).get(name))
        if source["state"] == SOURCE_AVAILABLE:
            pack = load_pack_catalog(source, golfo_profile_names, engine_version_of(skill_dir))
            source["catalogDigest"] = pack["digest"]
            source["version"] = pack["version"]
            source["changes"] = pack["changes"]
            source["availableProfiles"] = sorted(pack["profiles"])
            for profile_name, profile in sorted(pack["profiles"].items()):
                validate_selection_fields(profile_name, profile)
            catalog["profiles"].update(pack["profiles"])
            catalog["packAssetRoots"].update(pack["assetRoots"])
        catalog["sources"][name] = source
    if catalog["sources"]:
        # Stacks of several sources compete in one detection: their priorities cannot form a cycle.
        try:
            validate_catalog_detection(catalog["profiles"])
        except DetectionSchemaError as caught_error:
            raise ProfileError(f"profile sources: {caught_error}") from caught_error
    return catalog
# What a source asks of the engine: an engine this one is not (update the plugin), or a catalog it cannot read.
ENGINE_PROBLEM_ENGINE = "engine"
ENGINE_PROBLEM_CATALOG = "catalog"


def engine_requirement(kind, source_name, catalog_path, label, engine_version, supported_schema):
    """What one catalog asks of the engine: the check an apply runs before writing (minEngine, schemaVersion).

    ``problem`` says why an apply would stop on it (None if it would not); ``category`` tells an engine to
    update (``requiredVersion``: the plugin version to install, None for the newest) from a catalog to fix.
    """
    requirement = {"kind": kind, "source": source_name, "version": None, "minEngine": None, "problem": None,
                   "category": None, "requiredVersion": None}
    try:
        catalog = read_json_file(catalog_path, f"{kind} catalog")
    except StateError as catalog_error:
        return dict(requirement, problem=str(catalog_error), category=ENGINE_PROBLEM_CATALOG)
    requirement.update(version=catalog.get("version"), minEngine=catalog.get("minEngine"))
    try:
        compatibility.require_engine(label, catalog, engine_version, supported_schema)
    except compatibility.EngineRequirementError as engine_error:
        requirement.update(problem=str(engine_error), category=ENGINE_PROBLEM_ENGINE, requiredVersion=engine_error.required_version)
    except ProfileError as catalog_error:
        requirement.update(problem=str(catalog_error), category=ENGINE_PROBLEM_CATALOG)
    return requirement


def engine_requirements(project_root, engine_dir, content_dir=None):
    """What the content (when ``content_dir`` has it) and every pack this machine has ask of this engine.

    Only the engine check an apply runs before writing (minEngine, schemaVersion), done ahead of it: the
    rest of a catalog is checked by the apply. A pack this machine has not fetched yet, or a declaration
    that is not valid, is left out: the source checks of doctor report them. No network.
    """
    engine_version = engine_version_of(content_dir or engine_dir)
    requirements = []
    if content_dir:
        requirements.append(engine_requirement(
            "content", content_source.CONTENT_SOURCE_NAME, os.path.join(content_dir, PROFILE_CATALOG_RELATIVE_PATH),
            f"the {content_source.CONTENT_SOURCE_NAME} catalog", engine_version, GOLFO_CATALOG_SCHEMA_VERSION))
    try:
        declarations = declared_sources(project_root) or []
        locked_sources = locked_sources_of(project_root)
        configuration = configuration_of(project_root)
    except (StateError, ConfigurationError):
        return requirements
    for declaration in declarations:
        update_mode = effective_update_mode(configuration, declaration)
        source = locate_source(declaration, locked_sources.get(declaration["name"]), project_root, update_mode)
        if source["state"] != SOURCE_AVAILABLE:
            continue
        requirements.append(engine_requirement(
            "pack", declaration["name"], os.path.join(source["root"], PACK_CATALOG_FILE_NAME),
            f"pack '{declaration['name']}'", engine_version, PACK_SCHEMA_VERSION))
    return requirements


def raise_unknown_profile(catalog, name, requested_by):
    """Explain a profile that is not in the catalog, naming the source when it has one."""
    origin = f" (required by {requested_by})" if requested_by else ""
    if is_pack_profile(name):
        source_name = source_of_profile(name)
        source = catalog.get("sources", {}).get(source_name)
        if source is None and not catalog.get("sourcesEnabled", True):
            raise ProfileError(f"profile '{name}'{origin} comes from the source '{source_name}', and profile sources are off ({SOURCES_ENABLED_KEY}: false)")
        if source is None:
            raise ProfileError(f"profile '{name}'{origin} needs the source '{source_name}', which the manifest does not declare; packs cannot bring sources of their own")
        if source["state"] != SOURCE_AVAILABLE:
            raise IncompleteEvaluationError(f"profile '{name}'{origin} needs the source '{source_name}': {source['reason']}")
    known = ", ".join(selectable_profile_names(catalog))
    raise ProfileError(f"unknown profile '{name}'{origin}; available profiles: {known}")


def selectable_profile_names(catalog):
    """Profiles a selection can name: every one but the CI profiles, which ci.provider picks."""
    return sorted(name for name, profile in catalog["profiles"].items() if profile.get("kind") != CI_PROFILE_KIND)
# The selection with no profile at all: the core only, for a repository without code.
EMPTY_SELECTION_TOKEN = "none"


def split_profile_names(raw_profiles):
    """Split a comma separated profile list, keeping order and dropping blanks; "none" is no profile."""
    if (raw_profiles or "").strip() == EMPTY_SELECTION_TOKEN:
        return []
    names = []
    for name in (raw_profiles or "").split(","):
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


def profiles_for_stack(catalog, stack):
    """The --stack alias: the selection with only that stack; its ``defaults`` come at resolution."""
    if catalog["profiles"].get(stack, {}).get("kind") != STACK_PROFILE_KIND:
        known = ", ".join(sorted(name for name, profile in catalog["profiles"].items()
                                 if profile.get("kind") == STACK_PROFILE_KIND))
        raise ProfileError(f"unknown stack '{stack}'; expected one of: {known}")
    return [stack]


def resolve_profiles(catalog, requested_names, ci_profile=None, excluded_defaults=()):
    """Expand requires and defaults in declaration order and validate conflicts.

    Returns the ordered list of profile names, each one after the layers it requires and
    before the profiles it brings by default. ``defaults`` are the profiles a profile brings
    unless the repository leaves them out (``excluded_defaults``, from excludedDefaults);
    ``requires`` always come. The
    primary stack is the most specific layer (primary_stack); every stack adds its section to
    AGENTS.md. ``ci_profile`` is the CI profile
    that ci.provider picks (ci_profile_of); a selection cannot name one itself.
    """
    profiles = catalog["profiles"]
    resolved = []
    visiting = []

    pending_defaults = []

    def visit(name, requested_by):
        if name in resolved:
            return
        if name in visiting:
            cycle = " -> ".join(visiting + [name])
            raise ProfileError(f"profile dependency cycle: {cycle}")
        if name not in profiles:
            raise_unknown_profile(catalog, name, requested_by)
        visiting.append(name)
        for dependency in profiles[name].get("requires", []):
            visit(dependency, name)
        visiting.pop()
        resolved.append(name)
        pending_defaults.extend((default, name) for default in profiles[name].get(DEFAULTS_KEY, []))

    def visit_defaults():
        # Defaults come after every requested profile, so a requested profile keeps its place.
        while pending_defaults:
            default, brought_by = pending_defaults.pop(0)
            if default in excluded_defaults or default in resolved:
                continue
            if profiles.get(default, {}).get("kind") == CI_PROFILE_KIND:
                raise ProfileError(f"profile '{brought_by}' lists the CI profile '{default}' in '{DEFAULTS_KEY}'; "
                                   f"CI profiles come from {CI_PROVIDER_KEY}")
            visit(default, brought_by)

    # An empty selection is valid: the core only, for a repository without code.
    for requested_name in requested_names:
        if profiles.get(requested_name, {}).get("kind") == CI_PROFILE_KIND:
            provider = requested_name[len(CI_PROFILE_PREFIX):] if requested_name.startswith(CI_PROFILE_PREFIX) else "generic"
            raise ProfileError(f"profile '{requested_name}' comes from {CI_PROVIDER_KEY}, not from the selection; "
                               f"drop it and run: agent-ready ci setup --provider {provider}")
        visit(requested_name, None)
    visit_defaults()
    if ci_profile:
        visit(ci_profile, None)

    for name in excluded_defaults:
        if name in resolved:
            requirers = sorted(other for other in resolved if name in profiles[other].get("requires", []))
            reason = f"required by {', '.join(requirers)}" if requirers else "selected"
            raise ProfileError(f"{EXCLUDED_DEFAULTS_KEY} lists '{name}', but the selection needs it ({reason}); "
                               f"only a profile that comes by default can be left out")

    for name in resolved:
        for conflicting_name in profiles[name].get("conflicts", []):
            if conflicting_name in resolved:
                raise ProfileError(
                    f"profiles '{name}' and '{conflicting_name}' are declared incompatible; select only one"
                )

    # A stack is optional: a repository without code (documents, research) selects capabilities only,
    # and gets the base assets with the neutral AGENTS.md template.
    return resolved


def ci_profile_of(catalog, project_root):
    """The CI profile that ci.provider picks, or None without a provider or with none."""
    provider = configuration_of(project_root).value(CI_PROVIDER_KEY)
    if not provider or provider == CI_PROVIDER_NONE:
        return None
    name = CI_PROFILE_PREFIX + provider
    if catalog["profiles"].get(name, {}).get("kind") != CI_PROFILE_KIND:
        raise ProfileError(f"{CI_PROVIDER_KEY}: {provider} needs the profile '{name}', which this engine does not "
                           "have; update the golfo-kit plugin or choose another provider")
    return name


def resolve_project_profiles(catalog, names, project_root):
    """resolve_profiles of a repository: its selection plus the CI profile of ci.provider.

    ``names`` may come from the lock, whose profileOrder already lists the CI profiles of the
    last apply: they are dropped and taken again from ci.provider, which can have changed.
    """
    selection = [name for name in names if catalog["profiles"].get(name, {}).get("kind") != CI_PROFILE_KIND]
    excluded = configuration_of(project_root).value(EXCLUDED_DEFAULTS_KEY) or []
    return resolve_profiles(catalog, selection, ci_profile_of(catalog, project_root), excluded)


def primary_stack(catalog, resolved):
    """Return the first stack in resolution order that no other resolved profile requires.

    That is the most specific layer, the one detection settles on: with ``nextjs-app-router``
    selected, ``react`` and ``nextjs`` come first only because it requires them.
    """
    profiles = catalog["profiles"]
    # Only another stack makes a stack less specific: a capability or a pack profile that requires
    # one does not replace it.
    required = {layer for name in resolved if profiles[name].get("kind") == STACK_PROFILE_KIND
                for layer in required_layers(profiles, name)}
    for name in resolved:
        if profiles[name].get("kind") == STACK_PROFILE_KIND and name not in required:
            return name
    # A selection without a stack has no primary one.
    return None


def profile_asset_root(skill_dir, catalog, name):
    """Absolute asset directory of a profile, or None when it has no assets."""
    if is_pack_profile(name):
        return catalog["packAssetRoots"].get(name)
    relative_root = catalog["profiles"][name].get("assets")
    if not relative_root:
        return None
    root = os.path.join(skill_dir, relative_root)
    if not os.path.isdir(root):
        raise ProfileError(f"profile '{name}' assets directory is missing: {root}")
    return root


def resolved_tools(catalog, resolved):
    """Tools that the selected profiles need installed."""
    tools = []
    for name in resolved:
        for tool in catalog["profiles"][name].get("tools", []):
            if tool not in tools:
                tools.append(tool)
    return tools


def rejecting_ci_profiles(catalog, names):
    """A selection, or the error of resolve_profiles when it names a CI profile."""
    for name in names:
        if catalog["profiles"].get(name, {}).get("kind") == CI_PROFILE_KIND:
            resolve_profiles(catalog, [name])
    return names
