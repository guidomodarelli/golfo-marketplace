"""How a run picks its selection: --profiles, --stack, the manifest or the detection, in that order, and the
source state bootstrap leaves for the next steps.
"""

from agent_ready_common import ProfileError, read_json_file
from agent_ready_detection import (
    STACK_PROFILE_KIND,
    STATUS_AMBIGUOUS,
    STATUS_NONE,
    STATUS_RESOLVED,
    detect_profiles,
    format_evidence_list,
)
from agent_ready_manifest import configuration_of
from agent_ready_options import DETECTION_ENABLED_KEY, PROFILES_KEY
from agent_ready_profiles import profiles_for_stack, rejecting_ci_profiles, split_profile_names
from agent_ready_state_contract import (
    SELECTION_DETECTION,
    SELECTION_MANIFEST,
    SELECTION_PROFILES_FLAG,
    SELECTION_STACK_FLAG,
)


def read_source_state(arguments):
    """Commits an apply just adopted, or None outside an apply."""
    state_path = getattr(arguments, "source_state", None)
    return read_json_file(state_path, "profile source state") if state_path else None


def stack_names_of(catalog):
    """Names of the stack profiles of a catalog, sorted."""
    return sorted(name for name, profile in catalog["profiles"].items() if profile.get("kind") == STACK_PROFILE_KIND)


def stack_from_initial_detection(catalog, detection):
    """The stack a repository without a selection starts with, None without any stack signal.

    Without signals the repository gets the core only (no stack is optional); several stacks
    that match without a priority still need an explicit selection.
    """
    if detection["status"] == STATUS_RESOLVED:
        return detection["primaryStack"]
    if detection["status"] == STATUS_NONE:
        return None
    selection_hint = f"select one with --stack {'|'.join(stack_names_of(catalog))} or --profiles <a,b>"
    if detection["status"] == STATUS_AMBIGUOUS:
        matches = ", ".join(f"{name} ({format_evidence_list(detection['stacks'][name])})" for name in detection["candidates"])
        raise ProfileError(f"could not detect project stack: several stacks match and none has priority: {matches}; {selection_hint}")
    raise ProfileError(f"could not detect project stack: no signal matched; {selection_hint}")


def resolve_selection(arguments, catalog):
    """Requested profiles and their origin: flags, then the manifest, then initial detection."""
    if getattr(arguments, "profiles", None):
        return rejecting_ci_profiles(catalog, split_profile_names(arguments.profiles)), SELECTION_PROFILES_FLAG
    if getattr(arguments, "stack", None):
        return profiles_for_stack(catalog, arguments.stack), SELECTION_STACK_FLAG
    configuration = configuration_of(arguments.project)
    # An empty list in the manifest is a selection too: the core only, which detection never changes.
    if configuration.value(PROFILES_KEY) is not None:
        return rejecting_ci_profiles(catalog, configuration.value(PROFILES_KEY)), SELECTION_MANIFEST
    if not configuration.value(DETECTION_ENABLED_KEY):
        raise ProfileError(f"detection is off ({DETECTION_ENABLED_KEY}: false): select the profiles with --stack or --profiles")
    detection = detect_profiles(catalog["profiles"], arguments.project)
    stack = stack_from_initial_detection(catalog, detection)
    return (profiles_for_stack(catalog, stack) if stack else []), SELECTION_DETECTION
