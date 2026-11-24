"""check, the CI gate: whether the checkout, the sources and the lock agree, and the conflicts between the
selected profiles, with the report plan and status print of them and agent-ready conflicts --pack.
"""

import os
import shutil
import sys
import tempfile
import types

import agent_ready_cli_rules as project_rules
import agent_ready_conflicts as conflicts_review
import agent_ready_content as content_source
import agent_ready_memory as memory
import agent_ready_skill_overlap as skill_overlap
from agent_ready_actions import ACTION_UNCHANGED
from agent_ready_common import (
    IncompleteEvaluationError,
    ProfileError,
    StateError,
    bash_executable,
    find_repository_root,
    read_json_file,
    run_quiet,
    serialize_json,
    write_text_atomically,
)
from agent_ready_content import content_dir_of
from agent_ready_desired_assets import compose_stack_directory
from agent_ready_layout import (
    ENGINE_SKILL_DIRECTORY,
    MANIFEST_RELATIVE_PATH,
    PROVIDER_RESOLVER_RELATIVE_PATH,
    review_cache_module,
)
from agent_ready_lockfile import LOCK_RELATIVE_PATH, read_lock
from agent_ready_manifest import configuration_of, declared_sources
from agent_ready_merged_files import claude_proxy_drift, merged_file_changes
from agent_ready_options import (
    CI_CONFLICTS_FAIL,
    CI_CONFLICTS_OFF,
    CI_CONFLICTS_SEMANTIC_KEY,
    CI_CONFLICTS_STRUCTURAL_KEY,
    CI_ENABLED_KEY,
    CI_MODE_KEY,
    CI_WARN,
    COMPETING_SKILLS_ENABLED_KEY,
    CONFLICTS_ENABLED_KEY,
    PROFILES_KEY,
    REVIEWS_ENABLED_KEY,
    SUPPORTED_PROVIDERS,
)
from agent_ready_output import paint, write_line
from agent_ready_packs import KEBAB_CASE_NAME, NAMESPACE_SEPARATOR, PACK_CATALOG_FILE_NAME, is_pack_profile, refresh_declared_sources
from agent_ready_plan import (
    blocking_hook_documents,
    compute_plan,
    compute_status,
    nested_instruction_files,
    semantic_conflicts,
)
from agent_ready_profiles import load_effective_catalog, locked_sources_of
from agent_ready_review_findings import project_owned_instructions
from agent_ready_selection import resolve_selection
from agent_ready_state_contract import (
    CHECK_CONFIG_ERROR,
    CHECK_CONFLICTS,
    CHECK_EXIT_STATUSES,
    CHECK_OUTDATED,
    CHECK_PRIVATE_FILES,
    CHECK_SKIPPED,
    CHECK_SOURCE_UNAVAILABLE,
    CHECK_UP_TO_DATE,
    CONFLICTS_STATUS,
    PROFILE_ERROR_STATUS,
)
from agent_ready_status import describe_source, pack_tools_report
from agent_ready_structural import competing_skills_report, structural_conflict_lines, structural_conflicts


def merged_file_problems(project_root, skill_dir, plan):
    """Merged files and CLAUDE.md proxies that an apply would change."""
    catalog = load_effective_catalog(project_root, skill_dir)
    with tempfile.TemporaryDirectory(prefix="agent-ready-check.") as compose_root:
        previous_stack_dir = os.environ.get("AGENT_READY_SETUP_STACK_DIR")
        os.environ["AGENT_READY_SETUP_STACK_DIR"] = compose_stack_directory(skill_dir, catalog, plan["profiles"], compose_root)
        try:
            changes = merged_file_changes(project_root, skill_dir, plan)
        finally:
            if previous_stack_dir is None:
                del os.environ["AGENT_READY_SETUP_STACK_DIR"]
            else:
                os.environ["AGENT_READY_SETUP_STACK_DIR"] = previous_stack_dir
    problems = [f"{destination}: {reason}" for destination, action, reason in changes if action != ACTION_UNCHANGED]
    problems += [f"{path}: an apply would normalize it to the proxy" for path in claude_proxy_drift(project_root, skill_dir)]
    return problems


def check_problems(project_root, skill_dir):
    """Everything that shows the committed assets are not up to date. Returns (problems, incomplete)."""
    status = compute_status(project_root, skill_dir)
    # A catalog, a selection or a provider that cannot be evaluated is not an outdated repository.
    if status["errors"]:
        raise ProfileError("; ".join(status["errors"]))
    problems = []
    if status["manifest"] is None:
        problems.append(f"{MANIFEST_RELATIVE_PATH} is missing")
    if not status["hasLock"]:
        problems.append(f"{LOCK_RELATIVE_PATH} is missing")
    labels = (("modified", "modified"), ("missing", "missing"), ("conflict", "preserved conflict"),
              ("failed", "failed to apply"), ("retiredPreserved", "retired but preserved"))
    for key, label in labels:
        problems += [f"{destination}: {label}" for destination in status["checkout"][key]]
    if status["incomplete"]:
        return sorted(set(problems)), status["incomplete"]
    for name, item in status["sources"].items():
        problems += [f"profile source {name}: {difference}" for difference in item["differences"]]
        if item["pendingUpdate"]:
            problems.append(f"profile source {name}: {item['pendingUpdate']}")
    problems += status["selectionDifferences"]
    problems += status["workspaceDifferences"]
    update = status["update"]
    if update and update["available"]:
        plan = status["plan"]
        locked_digest = (status["lockedSource"] or {}).get("contentDigest")
        if locked_digest != plan["source"]["contentDigest"]:
            problems.append(f"{content_source.CONTENT_SOURCE_NAME}: the lock has {describe_source(status['lockedSource'])}; the source is {describe_source(plan['source'])}")
        problems += [f"{destination}: an apply would change it" for destination in update["changedDestinations"]]
    if status.get("plan") and status["hasLock"]:
        problems += merged_file_problems(project_root, skill_dir, status["plan"])
    return sorted(set(problems)), None


def evaluate_check(project_root, skill_dir, offline):
    """Result of the check, before the ``ci`` mode decides the exit status."""
    configuration = configuration_of(project_root, offline)
    ci = {"enabled": configuration.value(CI_ENABLED_KEY), "mode": configuration.value(CI_MODE_KEY)}
    if not ci["enabled"]:
        return {"status": CHECK_SKIPPED, "ci": ci, "problems": [], "unavailable": []}
    unavailable = []
    if not offline:
        unavailable = refresh_declared_sources(declared_sources(project_root), locked_sources_of(project_root))
    # The repository is checked against the content of its revision, like an apply.
    locked_source = (read_lock(project_root) or {}).get("source")
    content_source.declaration_of(configuration)  # an invalid declaration is a configuration error
    try:
        content_dir, missing_content = content_source.content_skill_dir(
            configuration, skill_dir, locked_source, offline=offline, read_only=True,
        )
    except ProfileError as fetch_error:
        # The revision or its ref could not be fetched: like a pack that cannot refresh.
        content_dir, missing_content = skill_dir, str(fetch_error)
    if missing_content:
        # Comparing with the installed content would report changes an apply never makes.
        return {"status": CHECK_SOURCE_UNAVAILABLE, "ci": ci, "problems": [], "unavailable": unavailable + [missing_content]}
    problems, incomplete = check_problems(project_root, content_dir)
    if incomplete:
        unavailable.append(incomplete)
    conflicts, failing_conflicts = {}, False
    if not unavailable:
        # With a source missing the selection cannot be evaluated: source-unavailable already says so.
        try:
            conflicts, failing_conflicts = check_conflicts(project_root, content_dir, offline)
        except IncompleteEvaluationError as incomplete_error:
            unavailable.append(str(incomplete_error))
    if unavailable:
        status = CHECK_SOURCE_UNAVAILABLE
    elif problems:
        status = CHECK_OUTDATED
    elif failing_conflicts:
        status = CHECK_CONFLICTS
    else:
        status = CHECK_UP_TO_DATE
    return {"status": status, "ci": ci, "problems": problems, "unavailable": unavailable, "conflicts": conflicts}


def semantic_conflict_lines(report):
    """One line per finding of the AI reviews, and how many pairs they could not review."""
    module = review_cache_module()
    lines, unchecked = [], 0
    for key in ("semanticConflicts", "competingSkills"):
        review = report.get(key) or {}
        lines += [f"  {module.finding_line(finding)}" for finding in review.get("findings", [])]
        unchecked += review.get("unchecked", 0)
    return lines, unchecked


def redundancy_lines(report):
    """One line per pair of redundant rules: a warning, never part of the conflicts nor of an exit status."""
    module = review_cache_module()
    review = report.get("semanticConflicts") or {}
    return [f"  {module.finding_line(finding)}" for finding in review.get("redundancies", [])]


def report_conflicts(plan, as_json):
    """agent-ready conflicts: every conflict of the selection, and exit 6 when there is one."""
    structural = structural_conflict_lines(plan)
    semantic, unchecked = semantic_conflict_lines(plan)
    # Redundant rules are listed but are no conflict: they never change the exit status.
    redundant = redundancy_lines(plan)
    found = bool(structural or semantic)
    if as_json:
        keys = ("machine", "repoReality", "ruleKeys", "parity", "competingTools", "settingsConflicts", "semanticConflicts",
                "competingSkills", "missingAgents")
        write_line(serialize_json({"structural": structural, "semantic": semantic, "redundant": redundant,
                                   "unchecked": unchecked, "found": found,
                                   "details": {key: plan[key] for key in keys if key in plan}})
                   .rstrip("\n"))
        return CONFLICTS_STATUS if found else 0
    stream = sys.stdout
    if not found:
        write_line(paint("No conflicts between the profiles", "ok", stream))
    for title, lines in (("Structural conflicts", structural), ("AI review findings", semantic),
                         ("Redundant rules (a warning, not a conflict)", redundant)):
        if lines:
            write_line(paint(f"{title}:", "warning", stream))
            for line in lines:
                write_line(line)
    if unchecked:
        write_line(f"{unchecked} pair(s) of the AI reviews could not be reviewed in this run.")
    return CONFLICTS_STATUS if found else 0


def has_review_pairs(project_root, plan, catalog):
    """True when the AI reviews of agent-ready check have a pair to review: without one there is
    nothing to check, and no provider is needed."""
    configuration = configuration_of(project_root)
    module = review_cache_module()
    if configuration.value(CONFLICTS_ENABLED_KEY):
        lock = read_lock(project_root)
        directions, _ = conflicts_review.conflict_pairs(
            project_root, plan["entries"], (lock or {}).get("assets", {}), module.normalized_text,
            project_owned_instructions, ENGINE_SKILL_DIRECTORY, is_pack_profile, True, nested_instruction_files(plan),
            blocking_hook_documents(project_root, configuration))
        if directions:
            return True
    if configuration.value(COMPETING_SKILLS_ENABLED_KEY):
        directions, _ = skill_overlap.skill_pairs(project_root, plan["entries"], catalog, is_pack_profile,
                                                  module.normalized_text)
        if directions:
            return True
    return False


def session_provider():
    """The provider of this run as resolve-provider.sh infers it (the environment, then the
    installation), the same as every other command; None when it cannot tell."""
    from_environment = os.environ.get("AGENT_READY_SETUP_ACTIVE_PROVIDER")
    if from_environment in SUPPORTED_PROVIDERS:
        return from_environment
    resolved = run_quiet([bash_executable(), os.path.join(ENGINE_SKILL_DIRECTORY, PROVIDER_RESOLVER_RELATIVE_PATH),
                          "--skill-dir", ENGINE_SKILL_DIRECTORY])
    return resolved if resolved in SUPPORTED_PROVIDERS else None
# Pack-author mode of agent-ready conflicts: the pack is copied into a throwaway consumer repository,
# under this folder, and every profile it publishes is checked there with the base of the content and its requires.
PACK_CHECK_DIRECTORY = "agent-packs"


def pack_profile_conflicts(run, profile):
    """The conflicts of one pack profile with the base and its requires: (structural, semantic, unchecked).

    The author's machine is not the consumer's: shadowing, the user's MCP servers and settings stay out.
    """
    catalog = load_effective_catalog(run.project, run.skill_dir)
    plan = compute_plan(run.project, run.skill_dir, catalog, [profile])
    configuration = configuration_of(run.project, run.offline)
    tools_report = pack_tools_report(plan, catalog, configuration)
    if tools_report:
        plan["packTools"] = tools_report
    report = structural_conflicts(run.project, run.skill_dir, plan, catalog, configuration, with_context=False,
                                  with_machine=False)
    # The rules the pack publishes are the author's to fix; the ones of the content it builds on are not.
    pack_prefix = profile.split(NAMESPACE_SEPARATOR, 1)[0] + NAMESPACE_SEPARATOR
    parity_section = report.get("parity") or {}
    if "antigravityDropped" in parity_section:
        parity_section["antigravityDropped"] = [rule for rule in parity_section["antigravityDropped"]
                                                if str(rule["profile"]).startswith(pack_prefix)]
    report["semanticConflicts"] = semantic_conflicts(run, plan)
    report["competingSkills"] = competing_skills_report(run, plan, catalog, configuration)
    semantic, unchecked = semantic_conflict_lines(report)
    return structural_conflict_lines(report), semantic, unchecked


def command_pack_conflicts(arguments):
    """agent-ready conflicts --pack: each profile of a pack against the base of the content and its requires,
    without a consumer repository. Exits 6 when one has a conflict, 2 when the pack cannot resolve."""
    pack_root = os.path.abspath(arguments.pack)
    catalog_path = os.path.join(pack_root, PACK_CATALOG_FILE_NAME)
    if not os.path.isfile(catalog_path):
        raise ProfileError(f"{pack_root} has no {PACK_CATALOG_FILE_NAME}: --pack takes the root of a profile pack")
    pack_catalog = read_json_file(catalog_path, "pack catalog")
    pack_name = pack_catalog.get("name") or os.path.basename(pack_root)
    # The name becomes a folder of the throwaway repository: only a source name, never a path.
    if not isinstance(pack_name, str) or not KEBAB_CASE_NAME.fullmatch(pack_name):
        raise ProfileError(f"{catalog_path} has an invalid pack name {pack_name!r}; use kebab-case")
    results = {}
    with tempfile.TemporaryDirectory(prefix="agent-ready-pack-check.") as scratch:
        project = os.path.join(scratch, "project")
        shutil.copytree(pack_root, os.path.join(project, PACK_CHECK_DIRECTORY, pack_name),
                        ignore=shutil.ignore_patterns(".git"), symlinks=True)
        if run_quiet(["git", "init", "-q", project]) is None:
            raise StateError(f"git init failed in {project}: the pack check needs Git")
        run = types.SimpleNamespace(project=project, skill_dir=arguments.skill_dir, offline=arguments.offline,
                                    profiles=None, stack=None, format="text",
                                    provider=arguments.provider or session_provider())
        source = {"name": pack_name, "source": f"path:./{PACK_CHECK_DIRECTORY}/{pack_name}"}
        manifest_path = os.path.join(project, *MANIFEST_RELATIVE_PATH.split("/"))
        # The whole catalog is validated first, as a consumer loads it: an empty or invalid pack fails
        # here even when it publishes no profile to check.
        # Every provider, Antigravity included: a rule Antigravity would drop is a conflict of the pack.
        write_text_atomically(manifest_path, serialize_json({"profiles": [], "providers": list(SUPPORTED_PROVIDERS),
                                                             "sources": {"packs": [source]}}))
        run.skill_dir = content_dir_of(project, arguments.skill_dir, offline=arguments.offline, read_only=False)
        load_effective_catalog(project, run.skill_dir)
        profiles = [f"{pack_name}/{name}" for name in pack_catalog.get("profiles", {})]
        for profile in profiles:
            write_text_atomically(manifest_path, serialize_json({"profiles": [profile],
                                                                 "providers": list(SUPPORTED_PROVIDERS),
                                                                 "sources": {"packs": [source]}}))
            try:
                structural, semantic, unchecked = pack_profile_conflicts(run, profile)
                results[profile] = {"structural": structural, "semantic": semantic, "unchecked": unchecked}
            except (ProfileError, IncompleteEvaluationError) as caught_error:
                results[profile] = {"error": str(caught_error)}
    errors = any("error" in result for result in results.values())
    found = any(result.get("structural") or result.get("semantic") for result in results.values())
    if arguments.format == "json":
        write_line(serialize_json({"pack": pack_name, "profiles": results, "found": found}).rstrip("\n"))
    else:
        print_pack_conflicts(pack_name, results)
    if errors:
        return PROFILE_ERROR_STATUS
    return CONFLICTS_STATUS if found else 0


def print_pack_conflicts(pack_name, results):
    """One block per profile of the pack: its conflicts, or that it has none."""
    stream = sys.stdout
    write_line(f"Pack {pack_name}: {len(results)} profile(s) checked against the golfo base and their requires")
    for profile, result in results.items():
        if "error" in result:
            write_line(paint(f"{profile}: does not resolve: {result['error']}", "error", stream))
            continue
        lines = result["structural"] + result["semantic"]
        if not lines:
            write_line(paint(f"{profile}: no conflicts", "ok", stream))
        else:
            write_line(paint(f"{profile}:", "warning", stream))
            for line in lines:
                write_line(paint(line, "warning", stream))
        if result["unchecked"]:
            write_line(f"  {result['unchecked']} pair(s) of the AI reviews could not be reviewed in this run.")


def check_conflicts(project_root, content_dir, offline):
    """The conflicts agent-ready check reports under ci.conflicts: (result, whether they fail the check)."""
    configuration = configuration_of(project_root, offline)
    structural_mode = configuration.value(CI_CONFLICTS_STRUCTURAL_KEY)
    semantic_mode = configuration.value(CI_CONFLICTS_SEMANTIC_KEY)
    result = {"structuralMode": structural_mode, "semanticMode": semantic_mode, "structural": [], "semantic": [],
              "redundant": [], "rules": [], "unchecked": 0}
    if structural_mode == CI_CONFLICTS_OFF and semantic_mode == CI_CONFLICTS_OFF:
        return result, False
    if structural_mode != CI_CONFLICTS_OFF:
        # agent-ready rules lint of the project's rule files that use atomic rules: deterministic, like the
        # structural checks, and under their mode (references/atomic-rules.md, section 3).
        result["rules"] = [f"  {finding.render()}"
                           for finding in project_rules.adopted_rule_errors(project_root, configuration)]
    catalog = load_effective_catalog(project_root, content_dir)
    run = types.SimpleNamespace(project=project_root, skill_dir=content_dir, offline=offline, profiles=None, stack=None,
                                format="text", provider=session_provider())
    # The same selection the rest of the check evaluated: the manifest, else the lock's, and only then
    # detection, so a repository that relies on its lock never needs detection here.
    requested = configuration.value(PROFILES_KEY)
    if requested is None:
        requested = (read_lock(project_root) or {}).get("profileOrder")
    if requested is None:
        requested, _ = resolve_selection(run, catalog)
    plan = compute_plan(project_root, content_dir, catalog, requested)
    tools_report = pack_tools_report(plan, catalog, configuration)
    if tools_report:
        plan["packTools"] = tools_report
    if structural_mode != CI_CONFLICTS_OFF:
        result["structural"] = structural_conflict_lines(
            structural_conflicts(project_root, content_dir, plan, catalog, configuration))
    # The reviews this configuration runs at all: none, and there is nothing to check or to call.
    reviews_on = configuration.value(REVIEWS_ENABLED_KEY) and (
        configuration.value(CONFLICTS_ENABLED_KEY) or configuration.value(COMPETING_SKILLS_ENABLED_KEY))
    reviewing = semantic_mode != CI_CONFLICTS_OFF and reviews_on and has_review_pairs(project_root, plan, catalog)
    if reviewing and run.provider is None:
        # Without a provider the reviews cannot even read their cache, whose keys include it.
        result["unchecked"] = 1
        result["semanticProblem"] = "no provider could be inferred; set AGENT_READY_SETUP_ACTIVE_PROVIDER"
    elif reviewing:
        reviews = {"semanticConflicts": semantic_conflicts(run, plan, instructions_with_applied=True),
                   "competingSkills": competing_skills_report(run, plan, catalog, configuration)}
        result["semantic"], result["unchecked"] = semantic_conflict_lines(reviews)
        # Shown, never failing: ci.conflicts.semantic only counts the conflicts.
        result["redundant"] = redundancy_lines(reviews)
    failing = ((structural_mode == CI_CONFLICTS_FAIL and bool(result["structural"] or result["rules"]))
               or (semantic_mode == CI_CONFLICTS_FAIL and bool(result["semantic"] or result["unchecked"])))
    return result, failing


def print_check_text(result):
    """Readable result of the check; the text is not a contract, the exit status is."""
    stream = sys.stdout
    headlines = {
        CHECK_UP_TO_DATE: ("up to date", "ok"),
        CHECK_OUTDATED: ("updates pending", "warning"),
        CHECK_SOURCE_UNAVAILABLE: ("source not available", "error"),
        CHECK_CONFIG_ERROR: ("configuration error", "error"),
        CHECK_SKIPPED: ("skipped", "muted"),
        CHECK_CONFLICTS: ("conflicts between the profiles or rule lint errors", "error"),
        CHECK_PRIVATE_FILES: ("files of the memory of Engram are versioned", "error"),
    }
    headline, color = headlines[result["status"]]
    ci = result["ci"]
    if not ci:
        mode = ""
    elif ci["enabled"]:
        mode = f" ({CI_MODE_KEY}: {ci['mode']})"
    else:
        mode = f" ({CI_ENABLED_KEY}: false)"
    write_line(paint(f"Agent Ready check: {headline}{mode}", color, stream))
    for message in result["unavailable"] + result["problems"]:
        write_line(f"  ! {message}")
    conflicts = result.get("conflicts") or {}
    for kind, mode_key in (("structural", CI_CONFLICTS_STRUCTURAL_KEY), ("semantic", CI_CONFLICTS_SEMANTIC_KEY)):
        if conflicts.get(kind):
            write_line(f"Conflicts ({mode_key}: {conflicts[kind + 'Mode']}):")
            for line in conflicts[kind]:
                write_line(line)
    if conflicts.get("redundant"):
        write_line("Redundant rules (a warning, it never fails the check):")
        for line in conflicts["redundant"]:
            write_line(line)
    if conflicts.get("rules"):
        write_line(f"Rules lint ({CI_CONFLICTS_STRUCTURAL_KEY}: {conflicts['structuralMode']}):")
        for line in conflicts["rules"]:
            write_line(line)
    if conflicts.get("semanticProblem"):
        write_line(f"  ! the AI reviews could not run: {conflicts['semanticProblem']} "
                   f"({CI_CONFLICTS_SEMANTIC_KEY}: {conflicts['semanticMode']})")
    elif conflicts.get("unchecked"):
        write_line(f"  ! {conflicts['unchecked']} pair(s) of the AI reviews could not be reviewed "
                   f"({CI_CONFLICTS_SEMANTIC_KEY}: {conflicts['semanticMode']})")
    if result["status"] in (CHECK_OUTDATED, CHECK_SOURCE_UNAVAILABLE):
        write_line("Apply with bootstrap.sh, review the diff of the assets and the lockfile, and commit it.")


def private_files_result(paths):
    """The memory of Engram stays on the machine of the user: a versioned file of it fails the check before
    anything else, with no ci key able to skip it or to turn it into a warning."""
    problems = [f"{path} is a file of the memory of Engram: remove it from Git with git rm --cached and keep "
                f"{memory.ENGRAM_DIRECTORY}/ in .gitignore" for path in paths]
    return {"status": CHECK_PRIVATE_FILES, "ci": None, "problems": problems, "unavailable": []}


def command_check(arguments):
    """Compare sources, lock and committed assets; any CI provider can run this.

    It needs python3, git and bash, and reaches private sources only through Git.
    """
    project_root = find_repository_root(arguments.project)
    private_files = memory.versioned_engram_files(project_root)
    if private_files:
        result = private_files_result(private_files)
    else:
        try:
            result = evaluate_check(project_root, arguments.skill_dir, arguments.offline)
        except (ProfileError, StateError) as configuration_error:
            result = {"status": CHECK_CONFIG_ERROR, "ci": None, "problems": [str(configuration_error)], "unavailable": []}
    exit_status = CHECK_EXIT_STATUSES[result["status"]]
    if result["ci"] and result["ci"]["mode"] == CI_WARN:
        exit_status = 0
    result["exitStatus"] = exit_status
    if arguments.format == "json":
        write_line(serialize_json(result).rstrip("\n"))
    else:
        print_check_text(result)
    return exit_status
