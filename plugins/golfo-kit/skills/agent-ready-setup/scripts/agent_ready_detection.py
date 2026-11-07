"""Static project detection for agent-ready-setup profiles.

Evaluates the optional ``detect`` block of a profile catalog against a project
tree. This is the only evaluator: the commands of ``agent-ready-state.py`` share
it. It only reads files inside the project, and it never runs a build, a package
manager or anything a catalog names. Gradle scripts are scanned as text: Groovy
and Kotlin are not interpreted. The contract is documented in
``references/profiles-and-lockfile.md``.
"""

import fnmatch
import json
import os
import re

STACK_PROFILE_KIND = "stack"

SIGNAL_FILE = "file"
SIGNAL_GLOB = "glob"
SIGNAL_PACKAGE_DEPENDENCY = "package-dependency"
SIGNAL_GRADLE_PLUGIN = "gradle-plugin"
SIGNAL_GRADLE_DEPENDENCY = "gradle-dependency"
# The list that each signal type requires, by key.
SIGNAL_VALUE_KEYS = {
    SIGNAL_FILE: "paths",
    SIGNAL_GLOB: "patterns",
    SIGNAL_PACKAGE_DEPENDENCY: "names",
    SIGNAL_GRADLE_PLUGIN: "ids",
    SIGNAL_GRADLE_DEPENDENCY: "coordinates",
}
SIGNAL_TYPE_KEY = "type"
DETECT_SIGNALS_KEY = "signals"
DETECT_SUPERSEDES_KEY = "supersedes"
DETECT_ALLOWED_KEYS = (DETECT_SIGNALS_KEY, DETECT_SUPERSEDES_KEY)

STATUS_RESOLVED = "resolved"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_NONE = "none"

PACKAGE_MANIFEST_PATH = "package.json"
PACKAGE_DEPENDENCY_FIELDS = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
GRADLE_SCRIPT_PATTERNS = (
    "build.gradle", "build.gradle.kts",
    "settings.gradle", "settings.gradle.kts",
    "*/build.gradle", "*/build.gradle.kts",
    "*/*/build.gradle", "*/*/build.gradle.kts",
)
GRADLE_VERSION_CATALOG_PATH = "gradle/libs.versions.toml"
VERSION_CATALOG_PLUGINS_SECTION = "plugins"
VERSION_CATALOG_LIBRARIES_SECTION = "libraries"

# Wildcards never descend into these directories: dependencies, build output and
# the assets Agent Ready itself projected say nothing about the project's stack.
SKIPPED_DIRECTORIES = frozenset((
    ".git", ".agents", ".claude", ".codex", ".gradle", ".idea", ".next", ".venv", "__pycache__",
    "build", "dist", "node_modules", "out", "target", "vendor", "venv",
))
RECURSIVE_WILDCARD = "**"
PATTERN_WILDCARD_CHARACTERS = "*?["
DETECTION_MAX_GLOB_DEPTH = 8
DETECTION_MAX_DIRECTORY_READS = 20000
DETECTION_MAX_FILE_BYTES = 2 * 1024 * 1024


class DetectionSchemaError(Exception):
    """Raised when the ``detect`` block of a catalog is not valid."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def is_contained_pattern(pattern):
    """True for a relative POSIX pattern that cannot leave the project root."""
    if not pattern or "\\" in pattern or pattern.startswith("/") or re.match(r"^[A-Za-z]:", pattern):
        return False
    return all(segment not in ("", ".", "..") for segment in pattern.split("/"))


def validate_signal(profile_name, signal):
    """Reject a signal with an unknown type, an extra key or a value outside the project."""
    if not isinstance(signal, dict):
        raise DetectionSchemaError(f"profile '{profile_name}' has a detect signal that is not an object")
    signal_type = signal.get(SIGNAL_TYPE_KEY)
    if signal_type not in SIGNAL_VALUE_KEYS:
        known = ", ".join(sorted(SIGNAL_VALUE_KEYS))
        raise DetectionSchemaError(f"profile '{profile_name}' has an unknown detect signal '{signal_type}'; expected one of: {known}")
    value_key = SIGNAL_VALUE_KEYS[signal_type]
    extra_keys = sorted(set(signal) - {SIGNAL_TYPE_KEY, value_key})
    if extra_keys:
        raise DetectionSchemaError(f"profile '{profile_name}' detect signal '{signal_type}' has unknown keys: {', '.join(extra_keys)}")
    values = signal.get(value_key)
    if not isinstance(values, list) or not values or not all(isinstance(value, str) and value for value in values):
        raise DetectionSchemaError(f"profile '{profile_name}' detect signal '{signal_type}' needs '{value_key}' as a non-empty list of strings")
    if signal_type in (SIGNAL_FILE, SIGNAL_GLOB):
        for value in values:
            if not is_contained_pattern(value):
                raise DetectionSchemaError(f"profile '{profile_name}' detect path '{value}' must be relative to the project and stay inside it")
    if signal_type == SIGNAL_FILE:
        for value in values:
            if any(character in value for character in PATTERN_WILDCARD_CHARACTERS):
                raise DetectionSchemaError(f"profile '{profile_name}' detect path '{value}' has a wildcard; use a '{SIGNAL_GLOB}' signal")
    if signal_type == SIGNAL_GLOB:
        for value in values:
            if any(RECURSIVE_WILDCARD in segment and segment != RECURSIVE_WILDCARD for segment in value.split("/")):
                raise DetectionSchemaError(f"profile '{profile_name}' detect pattern '{value}' must use {RECURSIVE_WILDCARD} as a whole path segment")


def validate_detect_block(profile_name, profile, stack_names):
    """Validate one profile's ``detect`` block against the stacks of its catalog."""
    detect = profile["detect"]
    if not isinstance(detect, dict):
        raise DetectionSchemaError(f"profile '{profile_name}' detect must be an object")
    extra_keys = sorted(set(detect) - set(DETECT_ALLOWED_KEYS))
    if extra_keys:
        raise DetectionSchemaError(f"profile '{profile_name}' detect has unknown keys: {', '.join(extra_keys)}")
    signals = detect.get(DETECT_SIGNALS_KEY)
    if not isinstance(signals, list) or not signals:
        raise DetectionSchemaError(f"profile '{profile_name}' detect needs '{DETECT_SIGNALS_KEY}' as a non-empty list")
    for signal in signals:
        validate_signal(profile_name, signal)
    if DETECT_SUPERSEDES_KEY not in detect:
        return
    if profile.get("kind") != STACK_PROFILE_KIND:
        raise DetectionSchemaError(f"profile '{profile_name}' is not a stack, so it cannot declare '{DETECT_SUPERSEDES_KEY}'")
    superseded = detect[DETECT_SUPERSEDES_KEY]
    if not isinstance(superseded, list) or not all(isinstance(name, str) for name in superseded):
        raise DetectionSchemaError(f"profile '{profile_name}' '{DETECT_SUPERSEDES_KEY}' must be a list of stack names")
    for name in superseded:
        if name not in stack_names or name == profile_name:
            raise DetectionSchemaError(f"profile '{profile_name}' cannot supersede '{name}': it must name another stack of the catalog")


def validate_catalog_detection(profiles):
    """Validate every ``detect`` block and reject a cycle in the stack priorities."""
    stack_names = {name for name, profile in profiles.items() if profile.get("kind") == STACK_PROFILE_KIND}
    for name, profile in sorted(profiles.items()):
        if "detect" in profile:
            validate_detect_block(name, profile, stack_names)

    def superseded_by(name):
        return sorted(profiles[name].get("detect", {}).get(DETECT_SUPERSEDES_KEY, []))

    finished = set()

    def visit(name, path):
        if name in path:
            cycle = " -> ".join(path[path.index(name):] + [name])
            raise DetectionSchemaError(f"stack priorities form a cycle: {cycle}")
        if name in finished:
            return
        for superseded in superseded_by(name):
            visit(superseded, path + [name])
        finished.add(name)

    for name in sorted(stack_names):
        visit(name, [])


# ---------------------------------------------------------------------------
# Project inspection (read-only)
# ---------------------------------------------------------------------------

def strip_source_comments(text, line_comment="//", block_comments=True):
    """Remove comments from Gradle or TOML text, keeping string literals intact.

    A commented-out plugin is not a signal, and ``https://`` inside a string is
    not a comment. This is a lexical pass, not a Groovy or Kotlin parser.
    """
    output = []
    position = 0
    length = len(text)
    string_delimiter = None
    while position < length:
        character = text[position]
        if string_delimiter:
            if character == "\\" and position + 1 < length:
                output.append(text[position:position + 2])
                position += 2
                continue
            if text.startswith(string_delimiter, position):
                output.append(string_delimiter)
                position += len(string_delimiter)
                string_delimiter = None
                continue
            # A single-line string never spans lines; an unmatched quote ends here.
            if character == "\n" and len(string_delimiter) == 1:
                string_delimiter = None
            output.append(character)
            position += 1
            continue
        if text.startswith(line_comment, position):
            newline = text.find("\n", position)
            position = length if newline < 0 else newline
            continue
        if block_comments and text.startswith("/*", position):
            end = text.find("*/", position + 2)
            position = length if end < 0 else end + 2
            continue
        if character in "\"'":
            triple = character * 3
            string_delimiter = triple if text.startswith(triple, position) else character
            output.append(string_delimiter)
            position += len(string_delimiter)
            continue
        output.append(character)
        position += 1
    return "".join(output)


def version_catalog_section(text, section):
    """Lines of one ``[section]`` of a Gradle version catalog."""
    lines = []
    current = None
    for line in strip_source_comments(text, line_comment="#", block_comments=False).splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1].strip()
            continue
        if current == section:
            lines.append(line)
    return "\n".join(lines)


def gradle_script_declares_plugin(text, plugin_id):
    """``id 'x'``, ``id("x")``, ``apply plugin: 'x'`` and ``apply(plugin = "x")``."""
    quoted = rf"""["']{re.escape(plugin_id)}["']"""
    return bool(
        re.search(rf"\bid\s*\(?\s*{quoted}", text)
        or re.search(rf"\bapply\s*\(?\s*plugin\s*[:=]\s*{quoted}", text)
    )


def gradle_script_declares_dependency(text, coordinate):
    """A dependency in string notation: ``'group:artifact'``, with or without version."""
    return bool(re.search(rf"""["']{re.escape(coordinate)}(?::[^"'\n]*)?["']""", text))


def version_catalog_declares_plugin(text, plugin_id):
    """``{ id = "x", ... }`` or the ``"x:version"`` shorthand under ``[plugins]``."""
    section = version_catalog_section(text, VERSION_CATALOG_PLUGINS_SECTION)
    escaped = re.escape(plugin_id)
    return bool(
        re.search(rf"""\bid\s*=\s*["']{escaped}["']""", section)
        or re.search(rf"""=\s*["']{escaped}:[^"'\n]*["']""", section)
    )


def version_catalog_declares_library(text, coordinate):
    """``module = "g:a"``, ``group = "g", name = "a"`` or ``"g:a:version"`` under ``[libraries]``."""
    section = version_catalog_section(text, VERSION_CATALOG_LIBRARIES_SECTION)
    if re.search(rf"""=\s*["']{re.escape(coordinate)}(?::[^"'\n]*)?["']""", section):
        return True
    group, _, artifact = coordinate.partition(":")
    group_part = rf"""\bgroup\s*=\s*["']{re.escape(group)}["']"""
    name_part = rf"""\bname\s*=\s*["']{re.escape(artifact)}["']"""
    return any(
        re.search(group_part, line) and re.search(name_part, line)
        for line in section.splitlines()
    )


class ProjectInspector:
    """Read-only, memoized view of the files that detection may inspect.

    Everything stays inside the project: a symlink directory is never traversed
    and a file that resolves outside the root does not exist for detection.
    """

    def __init__(self, project_root):
        self.project_root = os.path.abspath(project_root)
        self.real_root = os.path.normcase(os.path.realpath(self.project_root))
        self.warnings = []
        self.directory_reads = 0
        self.pattern_matches = {}
        self.file_texts = {}
        self.package_manifest_cache = None
        self.package_manifest_loaded = False
        self.gradle_scripts_cache = None

    def warn_once(self, message):
        """Record a limit of this evaluation once."""
        if message not in self.warnings:
            self.warnings.append(message)

    def absolute_path(self, relative_path):
        """Absolute path of a project-relative POSIX path."""
        return os.path.join(self.project_root, *relative_path.split("/"))

    def is_contained_file(self, relative_path):
        """True for a regular file whose real path stays inside the project."""
        real_path = os.path.normcase(os.path.realpath(self.absolute_path(relative_path)))
        try:
            is_inside = os.path.commonpath([self.real_root, real_path]) == self.real_root
        except ValueError:
            is_inside = False
        return is_inside and os.path.isfile(real_path)

    def directory_entries(self, relative_directory):
        """Sorted (name, is_real_directory) pairs; symlinks never count as directories."""
        if self.directory_reads >= DETECTION_MAX_DIRECTORY_READS:
            self.warn_once(f"detection stopped after reading {DETECTION_MAX_DIRECTORY_READS} directories; some signals may be missing")
            return []
        self.directory_reads += 1
        directory = self.absolute_path(relative_directory) if relative_directory else self.project_root
        try:
            with os.scandir(directory) as scan:
                return sorted((entry.name, entry.is_dir(follow_symlinks=False)) for entry in scan)
        except OSError:
            return []

    def expand_pattern(self, relative_directory, segments, depth, matches):
        """Collect the files under a directory that match the remaining segments."""
        segment, remaining = segments[0], segments[1:]
        if segment == RECURSIVE_WILDCARD:
            if remaining:
                self.expand_pattern(relative_directory, remaining, depth, matches)
            if depth >= DETECTION_MAX_GLOB_DEPTH:
                return
            for name, is_directory in self.directory_entries(relative_directory):
                child = f"{relative_directory}/{name}" if relative_directory else name
                if is_directory and name not in SKIPPED_DIRECTORIES:
                    self.expand_pattern(child, segments, depth + 1, matches)
                elif not is_directory and not remaining and self.is_contained_file(child):
                    matches.add(child)
            return
        is_literal = not any(character in segment for character in PATTERN_WILDCARD_CHARACTERS)
        for name, is_directory in self.directory_entries(relative_directory):
            if not fnmatch.fnmatchcase(name, segment):
                continue
            child = f"{relative_directory}/{name}" if relative_directory else name
            if not remaining:
                if self.is_contained_file(child):
                    matches.add(child)
            elif is_directory and (is_literal or name not in SKIPPED_DIRECTORIES):
                self.expand_pattern(child, remaining, depth + 1, matches)

    def match_pattern(self, pattern):
        """Files matching a path or glob, sorted, with the same casing on every system."""
        if pattern not in self.pattern_matches:
            matches = set()
            self.expand_pattern("", pattern.split("/"), 0, matches)
            self.pattern_matches[pattern] = sorted(matches)
        return self.pattern_matches[pattern]

    def read_text(self, relative_path):
        """UTF-8 text of a contained file, or None with a warning when it cannot be used."""
        if relative_path in self.file_texts:
            return self.file_texts[relative_path]
        text = None
        if self.is_contained_file(relative_path):
            absolute_path = self.absolute_path(relative_path)
            try:
                if os.path.getsize(absolute_path) > DETECTION_MAX_FILE_BYTES:
                    self.warn_once(f"{relative_path} is larger than {DETECTION_MAX_FILE_BYTES} bytes; it was not inspected")
                else:
                    with open(absolute_path, encoding="utf-8-sig") as file_handle:
                        text = file_handle.read()
            except (OSError, UnicodeDecodeError) as read_error:
                self.warn_once(f"{relative_path} could not be read as UTF-8 ({read_error}); its signals were not evaluated")
        self.file_texts[relative_path] = text
        return text

    def package_manifest(self):
        """The parsed root package.json, or None."""
        if not self.package_manifest_loaded:
            self.package_manifest_loaded = True
            text = self.read_text(PACKAGE_MANIFEST_PATH)
            if text is not None:
                try:
                    parsed = json.loads(text)
                except ValueError:
                    self.warn_once(f"{PACKAGE_MANIFEST_PATH} is not valid JSON; its dependencies were not evaluated")
                else:
                    if isinstance(parsed, dict):
                        self.package_manifest_cache = parsed
                    else:
                        self.warn_once(f"{PACKAGE_MANIFEST_PATH} is not a JSON object; its dependencies were not evaluated")
        return self.package_manifest_cache

    def gradle_scripts(self):
        """(relative path, text without comments) of every recognized Gradle script."""
        if self.gradle_scripts_cache is None:
            scripts = []
            for pattern in GRADLE_SCRIPT_PATTERNS:
                for relative_path in self.match_pattern(pattern):
                    text = self.read_text(relative_path)
                    if text is not None:
                        scripts.append((relative_path, strip_source_comments(text)))
            self.gradle_scripts_cache = sorted(scripts)
        return self.gradle_scripts_cache

    def version_catalog(self):
        """Text of the Gradle version catalog, or None."""
        return self.read_text(GRADLE_VERSION_CATALOG_PATH)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evidence_item(signal_type, relative_path, match, field=None):
    """One piece of evidence: the signal, the inspected file and what was found."""
    item = {"signal": signal_type, "file": relative_path, "match": match}
    if field:
        item["field"] = field
    return item


def evaluate_signal(signal, inspector):
    """Evidence that one signal finds in the project; empty when it does not match."""
    signal_type = signal[SIGNAL_TYPE_KEY]
    values = signal[SIGNAL_VALUE_KEYS[signal_type]]
    found = []
    if signal_type in (SIGNAL_FILE, SIGNAL_GLOB):
        for pattern in values:
            # The first sorted match is enough to explain the signal.
            for relative_path in inspector.match_pattern(pattern)[:1]:
                found.append(evidence_item(signal_type, relative_path, pattern))
    elif signal_type == SIGNAL_PACKAGE_DEPENDENCY:
        manifest = inspector.package_manifest()
        if manifest is not None:
            for name in values:
                for field in PACKAGE_DEPENDENCY_FIELDS:
                    dependencies = manifest.get(field)
                    if isinstance(dependencies, dict) and name in dependencies:
                        found.append(evidence_item(signal_type, PACKAGE_MANIFEST_PATH, name, field))
                        break
    elif signal_type == SIGNAL_GRADLE_PLUGIN:
        catalog_text = inspector.version_catalog()
        for plugin_id in values:
            for relative_path, text in inspector.gradle_scripts():
                if gradle_script_declares_plugin(text, plugin_id):
                    found.append(evidence_item(signal_type, relative_path, plugin_id))
                    break
            if catalog_text and version_catalog_declares_plugin(catalog_text, plugin_id):
                found.append(evidence_item(signal_type, GRADLE_VERSION_CATALOG_PATH, plugin_id))
    elif signal_type == SIGNAL_GRADLE_DEPENDENCY:
        catalog_text = inspector.version_catalog()
        for coordinate in values:
            for relative_path, text in inspector.gradle_scripts():
                if gradle_script_declares_dependency(text, coordinate):
                    found.append(evidence_item(signal_type, relative_path, coordinate))
                    break
            if catalog_text and version_catalog_declares_library(catalog_text, coordinate):
                found.append(evidence_item(signal_type, GRADLE_VERSION_CATALOG_PATH, coordinate))
    return found


def evaluate_detect_block(detect, inspector):
    """All the evidence of one profile, in an order that depends only on the evidence."""
    found = []
    for signal in detect[DETECT_SIGNALS_KEY]:
        found.extend(evaluate_signal(signal, inspector))
    return sorted(found, key=lambda item: (item["file"], item["signal"], item["match"]))


def detect_profiles(profiles, project_root):
    """Evaluate a validated catalog against a project.

    A stack that another matched stack supersedes drops out. One stack left is the
    primary stack; several are ambiguous and need an explicit selection, because
    picking one would depend on an arbitrary order. Capabilities are only reported.
    """
    inspector = ProjectInspector(project_root)
    stacks = {}
    capabilities = {}
    for name, profile in sorted(profiles.items()):
        detect = profile.get("detect")
        if not detect:
            continue
        evidence = evaluate_detect_block(detect, inspector)
        if evidence:
            (stacks if profile.get("kind") == STACK_PROFILE_KIND else capabilities)[name] = evidence
    superseded_by = {}
    for name in stacks:
        winners = sorted(
            other for other in stacks
            if other != name and name in profiles[other]["detect"].get(DETECT_SUPERSEDES_KEY, [])
        )
        if winners:
            superseded_by[name] = winners
    candidates = sorted(name for name in stacks if name not in superseded_by)
    if len(candidates) == 1:
        status = STATUS_RESOLVED
    elif candidates:
        status = STATUS_AMBIGUOUS
    else:
        status = STATUS_NONE
    return {
        "status": status,
        "primaryStack": candidates[0] if status == STATUS_RESOLVED else None,
        "candidates": candidates,
        "stacks": stacks,
        "supersededBy": superseded_by,
        "capabilities": capabilities,
        "warnings": sorted(inspector.warnings),
    }


def format_evidence(item):
    """One readable clause: the inspected file and the signal found in it."""
    signal_type = item["signal"]
    if signal_type == SIGNAL_FILE:
        return f"{item['file']} exists"
    if signal_type == SIGNAL_GLOB:
        return f"{item['file']} matches {item['match']}"
    if signal_type == SIGNAL_PACKAGE_DEPENDENCY:
        return f"{item['file']} declares {item['match']} in {item['field']}"
    if signal_type == SIGNAL_GRADLE_PLUGIN:
        return f"{item['file']} declares the Gradle plugin {item['match']}"
    return f"{item['file']} declares the Gradle dependency {item['match']}"


def format_evidence_list(evidence):
    """Every piece of evidence of one profile in one line."""
    return "; ".join(format_evidence(item) for item in evidence)
