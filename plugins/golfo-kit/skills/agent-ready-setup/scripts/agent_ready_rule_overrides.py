"""Overrides of one atomic rule by another rule of the selection (#168).

A rule of a selected profile with ``overrides=<source>:<id>`` replaces that single rule of another
selected profile: the file that holds the replaced rule is projected without it, and its other rules
stay. ``<source>`` is the pack name of a namespaced profile, or ``golfo`` for the official content.
A rule the project wrote itself in ``.agents/rules/`` replaces a managed rule the same way: its source
is ``project``. A rule marked ``locked`` cannot be replaced. The file without the rule is kept in the
per-user cache by its sha256 and given to the plan and the projection as a shared text, so both read the
same bytes.
"""

import os

import agent_ready_rules
from agent_ready_common import (
    ProfileError,
    is_link,
    sha256_of_text,
    skill_cache_directory,
    walk_content_files,
    walk_files,
    write_text_atomically,
)
from agent_ready_lockfile import read_lock, was_applied
from agent_ready_packs import is_pack_profile, source_of_profile
from agent_ready_profiles import BASE_PROFILE_NAME, is_overridden, profile_asset_root, resolved_overrides

OFFICIAL_RULE_SOURCE = "golfo"
# The source and the owner of the rules the project wrote itself, as the structural reports name them.
PROJECT_RULE_SOURCE = "project"
PROJECT_RULES_DIRECTORY = ".agents/rules/"
MANAGED_DESTINATION_PREFIX = ".agents/"
RULE_SOURCE_SEPARATOR = ":"
RULES_PREFIX = "rules/"
RULE_FILE_SUFFIX = ".md"
RULE_OVERRIDES_CACHE = "rule-overrides"
CRLF = "\r\n"
LF = "\n"


def rule_source(profile_name):
    """Source that qualifies the ids of a profile's rules: its pack, or golfo for the official content."""
    return source_of_profile(profile_name) if is_pack_profile(profile_name) else OFFICIAL_RULE_SOURCE


def profile_rule_files(root):
    """(relative path, absolute path) of the rule files of an asset root."""
    return [(relative_path, absolute_path) for relative_path, absolute_path in walk_content_files(root)
            if relative_path.startswith(RULES_PREFIX) and relative_path.endswith(RULE_FILE_SUFFIX)]


def selection_rules(skill_dir, catalog, resolved):
    """{qualified id: (profile, relative path, absolute path, rule)} of the core and the selected profiles.

    A file another profile replaces whole (the profile's overrides) is not projected, so its rules are
    left out; a locked rule in it is an error, because replacing the file would remove the rule.
    """
    roots = [(BASE_PROFILE_NAME, os.path.join(skill_dir, catalog.get("baseAssets", "assets/common")))]
    roots += [(name, profile_asset_root(skill_dir, catalog, name)) for name in resolved]
    replaced_files = resolved_overrides(skill_dir, catalog, resolved)
    published = {}
    for profile_name, root in roots:
        if not root or not os.path.isdir(root):
            continue
        for relative_path, absolute_path in profile_rule_files(root):
            with open(absolute_path, encoding="utf-8", newline="") as rule_file:
                rules, _ = agent_ready_rules.parse_rule_text(rule_file.read(), relative_path)
            if is_overridden(replaced_files, profile_name, relative_path):
                locked = [rule.id for rule in rules if rule.locked]
                if locked:
                    replacing = replaced_files[profile_name].get(relative_path, "another profile")
                    raise ProfileError(f"profile '{replacing}' overrides {profile_name}:{relative_path}, which has the "
                                       f"locked rule {rule_source(profile_name)}{RULE_SOURCE_SEPARATOR}{locked[0]}; "
                                       "a locked rule cannot be replaced")
                continue
            for rule in rules:
                qualified = f"{rule_source(profile_name)}{RULE_SOURCE_SEPARATOR}{rule.id}"
                previous = published.setdefault(qualified, (profile_name, relative_path, absolute_path, rule))
                if previous[0] != profile_name or previous[1] != relative_path:
                    raise ProfileError(f"the rule {qualified} is published twice, by '{previous[0]}' ({previous[1]}) "
                                       f"and by '{profile_name}' ({relative_path}); give one of them another id")
    return published


def selection_rule_paths(skill_dir, catalog, resolved):
    """The relative paths (rules/...) of every rule file of the core and the selected profiles."""
    roots = [os.path.join(skill_dir, catalog.get("baseAssets", "assets/common"))]
    roots += [profile_asset_root(skill_dir, catalog, name) for name in resolved]
    return {relative_path for root in roots if root and os.path.isdir(root)
            for relative_path, _ in profile_rule_files(root)}


def project_rules(project_root, catalog_rule_paths, managed_destinations=()):
    """[rule] of the rules the project wrote itself in .agents/rules, each with its path in the repository.

    A file is the project's own when no profile of the selection publishes it (``catalog_rule_paths``,
    relative to an asset root), it is not in ``managed_destinations`` (the rules of the workspaces) and
    no apply wrote it (the lock). A link is never read.
    """
    rules_root = os.path.join(project_root, *PROJECT_RULES_DIRECTORY.strip("/").split("/"))
    if not os.path.isdir(rules_root):
        return []
    lock = read_lock(project_root) or {"assets": {}}
    managed = {MANAGED_DESTINATION_PREFIX + relative_path for relative_path in catalog_rule_paths}
    managed |= set(managed_destinations)
    managed |= {destination for destination, entry in lock["assets"].items() if was_applied(entry)}
    found = []
    for relative_path, absolute_path in walk_files(rules_root):
        destination = PROJECT_RULES_DIRECTORY + relative_path
        if not relative_path.endswith(RULE_FILE_SUFFIX) or is_link(absolute_path) or destination in managed:
            continue
        with open(absolute_path, encoding="utf-8", errors="replace", newline="") as rule_file:
            rules, _ = agent_ready_rules.parse_rule_text(rule_file.read(), destination)
        found += rules
    return found


def resolved_rule_overrides(skill_dir, catalog, resolved, project_root=None, managed_destinations=()):
    """The rule overrides of the selection and of the project's own rules, validated:
    [{profile, rule, replaces, targetProfile, targetPath}].

    ``project_root`` adds the rules the project wrote itself (project_rules), with profile ``project``;
    ``managed_destinations`` are the rule files the workspaces get, which are not the project's own.
    """
    published = selection_rules(skill_dir, catalog, resolved)
    overriders = [(qualified, profile_name, rule) for qualified, (profile_name, _, _, rule) in sorted(published.items())]
    if project_root:
        project_owned = project_rules(project_root, selection_rule_paths(skill_dir, catalog, resolved),
                                      managed_destinations)
        overriders += [(f"{PROJECT_RULE_SOURCE}{RULE_SOURCE_SEPARATOR}{rule.id}", PROJECT_RULE_SOURCE, rule)
                       for rule in project_owned]
    overrides = []
    replaced_by = {}
    for qualified, profile_name, rule in overriders:
        for reference in rule.overrides:
            where = f" ({rule.path}:{rule.line})" if profile_name == PROJECT_RULE_SOURCE else ""
            what = f"the rule {qualified} of '{profile_name}'{where} overrides {reference}"
            if RULE_SOURCE_SEPARATOR not in reference:
                raise ProfileError(f"{what}: name the rule with its source, such as "
                                   f"{OFFICIAL_RULE_SOURCE}{RULE_SOURCE_SEPARATOR}{reference}")
            target = published.get(reference)
            if target is None:
                raise ProfileError(f"{what}, which no selected profile publishes; nothing was written")
            target_profile, target_path, _, target_rule = target
            if target_profile == BASE_PROFILE_NAME:
                raise ProfileError(f"{what}: the core cannot be overridden yet; add a rule of your own next to it")
            if target_profile == profile_name:
                raise ProfileError(f"{what}, a rule of the same profile; edit or remove that rule instead")
            if target_rule.locked:
                raise ProfileError(f"{what}, which is locked; it cannot be replaced")
            previous = replaced_by.setdefault(reference, qualified)
            if previous != qualified:
                raise ProfileError(f"the rules {previous} and {qualified} both override {reference}; keep one")
            overrides.append({"profile": profile_name, "rule": qualified, "replaces": reference,
                              "targetProfile": target_profile, "targetPath": target_path})
    # A rule that replaces another and is itself replaced (a chain, or two rules replacing each other)
    # would leave no instruction where the author expected one: keep the replacements one level deep.
    for override in overrides:
        if override["rule"] in replaced_by:
            raise ProfileError(f"the rule {override['rule']} overrides {override['replaces']} and is overridden by "
                               f"{replaced_by[override['rule']]}; a rule that replaces another cannot be replaced")
    return overrides


def rule_override_texts(skill_dir, catalog, resolved, project_root=None, managed_destinations=()):
    """{(profile, relative path): (text path, sha256)} of each file that loses a rule to an override
    (resolved_rule_overrides, with the same ``project_root`` and ``managed_destinations``)."""
    published = selection_rules(skill_dir, catalog, resolved)
    removals = {}
    for override in resolved_rule_overrides(skill_dir, catalog, resolved, project_root, managed_destinations):
        target_profile, target_path, absolute_path, rule = published[override["replaces"]]
        removals.setdefault((target_profile, target_path, absolute_path), set()).add(rule.id)
    texts = {}
    for (profile_name, relative_path, absolute_path), rule_ids in sorted(removals.items()):
        with open(absolute_path, encoding="utf-8", newline="") as rule_file:
            # LF, like the hash of a projected file (sha256_of_file), so the lock compares the same bytes.
            text = agent_ready_rules.remove_rules(rule_file.read(), rule_ids).replace(CRLF, LF)
        sha256 = sha256_of_text(text)
        text_path = skill_cache_directory(RULE_OVERRIDES_CACHE, f"{sha256}{RULE_FILE_SUFFIX}")
        if not os.path.isfile(text_path):
            write_text_atomically(text_path, text)
        texts[(profile_name, relative_path)] = (text_path, sha256)
    return texts
