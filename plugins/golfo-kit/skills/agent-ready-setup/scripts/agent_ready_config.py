"""Layered, schema-driven configuration of agent-ready-setup.

Every option lives in one JSON Schema per feature module under ``assets/config/``: its
type, its default, its description and, for a key that matters to security, how strict
each of its values is. Validation, the reference documentation and the explanation that
``config`` and ``plan`` print all come from those schemas, and this module knows no
option by name: adding a feature means adding its schema.

Layers, from lowest to highest precedence:

* ``defaults``: the ``default`` of each schema;
* ``organization``: an optional file an organization distributes; without it the layer
  does not exist;
* ``user``: ``${XDG_CONFIG_HOME:-~/.config}/agent-ready-setup/config.json``;
* ``project``: ``.agents/agent-ready.json``, versioned with the repository;
* ``environment`` and ``flags``: only for one run.

Objects merge key by key. An array marked ``x-merge: union`` joins across layers; every
other array and every scalar is replaced. A project value that loosens a sensitive key is
taken only when this machine approved the repository, and a key the organization locks
never changes above it. Ignored values are reported, never dropped in silence.
"""

import copy
import json
import os
import re
import sys

from agent_ready_common import StateError, read_json_file

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIRECTORY = os.path.join(SKILL_ROOT, "assets", "config")
SCHEMA_FILE_SUFFIX = ".schema.json"

LAYER_DEFAULTS = "defaults"
LAYER_ORGANIZATION = "organization"
LAYER_USER = "user"
LAYER_PROJECT = "project"
LAYER_ENVIRONMENT = "environment"
LAYER_FLAGS = "flags"
SETTABLE_LAYERS = (LAYER_ORGANIZATION, LAYER_USER, LAYER_PROJECT, LAYER_ENVIRONMENT, LAYER_FLAGS)

PROJECT_CONFIG_RELATIVE_PATH = ".agents/agent-ready.json"
USER_CONFIG_DIRECTORY_NAME = "agent-ready-setup"
CONFIG_FILE_NAME = "config.json"
ORGANIZATION_CONFIG_VARIABLE = "AGENT_READY_SETUP_ORGANIZATION_CONFIG"
LINUX_ORGANIZATION_CONFIG_PATH = "/etc/agent-ready-setup/config.json"
MACOS_ORGANIZATION_CONFIG_PATH = "/Library/Application Support/agent-ready-setup/config.json"
WINDOWS_PROGRAM_DATA_FALLBACK = "C:\\ProgramData"
# Only the organization can lock keys, and it does so with this top-level list.
LOCKED_KEY = "locked"

MERGE_UNION = "union"
ROLE_APPROVAL_SWITCH = "approval-switch"
ROLE_APPROVED_PROJECTS = "approved-projects"
REQUIRED_ROLES = (ROLE_APPROVAL_SWITCH, ROLE_APPROVED_PROJECTS)
MODULE_SWITCH_KEY = "enabled"
SUPPORTED_TYPES = ("object", "array", "string", "boolean", "integer")
SCALAR_TYPES = ("string", "boolean", "integer")
ENVIRONMENT_TRUE_WORDS = ("1", "true", "on")
ENVIRONMENT_FALSE_WORDS = ("0", "false", "off")
ENVIRONMENT_LIST_SEPARATOR = ","
MODULE_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
MOUNT_NAME = re.compile(r"^[a-z][A-Za-z0-9]*$")

IGNORED_LOCKED = "locked"
IGNORED_LOOSENS = "loosens"


class ConfigurationError(StateError):
    """Raised when a schema or a layer is not valid; the message names the key and the layer."""


class InvalidValue(Exception):
    """A value that does not satisfy its schema node; the caller adds the layer."""


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def join_key(prefix, key):
    """Dotted path of a key under a prefix."""
    return f"{prefix}.{key}" if prefix else key


def is_branch(node):
    """True for an object node whose keys are options of their own."""
    return node.get("type") == "object" and isinstance(node.get("properties"), dict)


def collect_leaves(node, prefix, leaves):
    """Map every option (a node that is not a branch) to its dotted path."""
    for key, child in node["properties"].items():
        path = join_key(prefix, key)
        if is_branch(child):
            collect_leaves(child, path, leaves)
        else:
            leaves[path] = child


def validate_value(value, node, path):
    """Raise InvalidValue when ``value`` does not satisfy ``node``."""
    expected = node.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise InvalidValue(f"'{path}' must be an object")
        properties = node.get("properties", {})
        for key in value:
            if key not in properties:
                raise InvalidValue(f"unknown key '{join_key(path, key)}'")
        for key in node.get("required", []):
            if key not in value:
                raise InvalidValue(f"'{join_key(path, key)}' is required")
        for key, item in value.items():
            validate_value(item, properties[key], join_key(path, key))
    elif expected == "array":
        if not isinstance(value, list):
            raise InvalidValue(f"'{path}' must be a list")
        if len(value) < node.get("minItems", 0):
            raise InvalidValue(f"'{path}' needs at least {node['minItems']} item(s)")
        if node.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise InvalidValue(f"'{path}' repeats an item")
        for index, item in enumerate(value):
            validate_value(item, node.get("items", {}), f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(value, str):
            raise InvalidValue(f"'{path}' must be a string")
        if len(value) < node.get("minLength", 0):
            raise InvalidValue(f"'{path}' must not be empty")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise InvalidValue(f"'{path}' must be true or false")
    elif expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidValue(f"'{path}' must be an integer")
    if "enum" in node and value not in node["enum"]:
        allowed = ", ".join(json.dumps(item) if not isinstance(item, str) else item for item in node["enum"])
        raise InvalidValue(f"'{path}' must be one of {allowed} (got {json.dumps(value)})")


class Schema:
    """Every module schema mounted into one tree, with its options indexed by dotted path."""

    def __init__(self, root, modules):
        self.root = root
        self.modules = modules
        self.leaves = {}
        collect_leaves(root, "", self.leaves)
        self.roles = {}
        self._validate_options()

    def _fail(self, message):
        raise ConfigurationError(f"configuration schema under {SCHEMA_DIRECTORY}: {message}")

    def _validate_node(self, node, path):
        if node.get("type") not in SUPPORTED_TYPES:
            self._fail(f"'{path}' declares an unsupported type {node.get('type')!r}")
        if node.get("type") == "object" and node.get("additionalProperties") is not False:
            self._fail(f"'{path}' must set additionalProperties to false, so a typo never passes")
        for child_key, child in (node.get("properties") or {}).items():
            self._validate_node(child, join_key(path, child_key))
        if node.get("type") == "array":
            self._validate_node(node.get("items") or {}, f"{path}[]")

    def _validate_options(self):
        self._validate_node(self.root, "")
        environment_variables = {}
        for path, node in self.leaves.items():
            if not node.get("description"):
                self._fail(f"'{path}' needs a description")
            if "default" in node:
                try:
                    validate_value(node["default"], node, path)
                except InvalidValue as invalid_default:
                    self._fail(f"the default of {invalid_default}")
            for layer in node.get("x-layers", SETTABLE_LAYERS):
                if layer not in SETTABLE_LAYERS:
                    self._fail(f"'{path}' names an unknown layer {layer!r} in x-layers")
            variable = node.get("x-env")
            if variable is not None:
                if node.get("type") not in SCALAR_TYPES + ("array",) or variable in environment_variables:
                    self._fail(f"'{path}' declares x-env {variable!r}, which is repeated or not a scalar option")
                environment_variables[variable] = path
            if node.get("x-merge") not in (None, MERGE_UNION) or (node.get("x-merge") and node.get("type") != "array"):
                self._fail(f"'{path}' declares x-merge, which only accepts {MERGE_UNION!r} on a list")
            self._validate_security(path, node)
            role = node.get("x-role")
            if role is not None:
                if role not in REQUIRED_ROLES or role in self.roles:
                    self._fail(f"'{path}' declares the role {role!r}, which is unknown or already taken")
                self.roles[role] = path
        for role in REQUIRED_ROLES:
            if role not in self.roles:
                self._fail(f"no option declares the role {role!r}")
        if self.leaves[self.roles[ROLE_APPROVAL_SWITCH]].get("type") != "boolean":
            self._fail(f"the {ROLE_APPROVAL_SWITCH} option must be a boolean")
        approved = self.leaves[self.roles[ROLE_APPROVED_PROJECTS]]
        if approved.get("x-merge") != MERGE_UNION or LAYER_PROJECT in approved.get("x-layers", SETTABLE_LAYERS):
            self._fail(f"the {ROLE_APPROVED_PROJECTS} option must join across layers and never come from the project")
        for path, node in self.leaves.items():
            self._validate_presets(path, node)

    def _validate_security(self, path, node):
        security = node.get("x-security")
        if security is None:
            return
        strictness = security.get("strictness") if isinstance(security, dict) else None
        if node.get("type") == "boolean":
            expected = [True, False]
        else:
            expected = node.get("enum")
        if not isinstance(strictness, list) or expected is None or sorted(map(json.dumps, strictness)) != sorted(map(json.dumps, expected)):
            self._fail(f"'{path}' x-security.strictness must order every value it accepts, from the loosest to the strictest")
        if "default" not in node:
            self._fail(f"'{path}' is sensitive, so it needs a default to compare against")

    def _validate_presets(self, path, node):
        presets = node.get("x-presets")
        if presets is None:
            return
        if node.get("type") != "string" or sorted(presets) != sorted(node.get("enum", [])):
            self._fail(f"'{path}' x-presets must define every value of its enum")
        for preset_value, assignments in presets.items():
            for target, value in assignments.items():
                target_node = self.leaves.get(target)
                if target_node is None or target_node.get("x-presets") is not None:
                    self._fail(f"preset {path}={preset_value} sets '{target}', which is not an option or is another preset")
                try:
                    validate_value(value, target_node, target)
                except InvalidValue as invalid_preset:
                    self._fail(f"preset {path}={preset_value}: {invalid_preset}")
        default_assignments = presets.get(node.get("default"), {})
        for target, value in default_assignments.items():
            if self.leaves[target].get("default") != value:
                self._fail(f"the default preset {path}={node.get('default')} must match the default of '{target}'")

    def default(self, key):
        """Default of an option, or None when it has none."""
        return copy.deepcopy(self.leaves[key].get("default"))

    def flatten(self, document, path=""):
        """Dotted assignments of a validated layer document, one per option it sets."""
        assignments = {}
        for key, value in document.items():
            dotted = join_key(path, key)
            node = self.leaves.get(dotted)
            if node is None:
                assignments.update(self.flatten(value, dotted))
            else:
                assignments[dotted] = value
        return assignments

    def is_known_prefix(self, key):
        """True for an option or for a namespace that holds options."""
        return key in self.leaves or any(leaf.startswith(key + ".") for leaf in self.leaves)


def load_schema(schema_directory=SCHEMA_DIRECTORY):
    """Mount every ``*.schema.json`` of a directory into one validated schema."""
    root = {"type": "object", "additionalProperties": False, "properties": {}}
    modules = []
    try:
        file_names = sorted(name for name in os.listdir(schema_directory) if name.endswith(SCHEMA_FILE_SUFFIX))
    except OSError as listing_error:
        raise ConfigurationError(f"could not read the configuration schemas under {schema_directory}: {listing_error}") from listing_error
    for file_name in file_names:
        path = os.path.join(schema_directory, file_name)
        document = read_json_file(path, "configuration schema")
        module_name, mount = document.get("x-module"), document.get("x-mount")
        if not isinstance(module_name, str) or not MODULE_NAME.fullmatch(module_name) or not isinstance(mount, str):
            raise ConfigurationError(f"configuration schema {path} needs x-module (kebab-case) and x-mount")
        properties = document.get("properties")
        if document.get("type") != "object" or not isinstance(properties, dict):
            raise ConfigurationError(f"configuration schema {path} must describe an object with properties")
        if mount:
            if not MOUNT_NAME.fullmatch(mount):
                raise ConfigurationError(f"configuration schema {path} has an invalid x-mount {mount!r}")
            switch = properties.get(MODULE_SWITCH_KEY) or {}
            if switch.get("type") != "boolean" or not isinstance(switch.get("default"), bool):
                raise ConfigurationError(
                    f"configuration schema {path}: the module '{module_name}' must declare '{MODULE_SWITCH_KEY}', "
                    "a boolean with a default, so it can be turned off on its own"
                )
            mounted = {mount: document}
        else:
            mounted = properties
        for key, node in mounted.items():
            if key in root["properties"] or key == LOCKED_KEY:
                raise ConfigurationError(f"configuration schema {path} declares '{key}', which another module or the engine already uses")
            root["properties"][key] = node
        modules.append({"name": module_name, "mount": mount, "title": document.get("title", module_name),
                        "description": document.get("description", ""), "file": file_name})
    return Schema(root, modules)


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------

def user_config_path(environment):
    """Per-user configuration file; it lives outside every repository."""
    base = environment.get("XDG_CONFIG_HOME") or os.path.join(environment.get("HOME") or os.path.expanduser("~"), ".config")
    return os.path.join(base, USER_CONFIG_DIRECTORY_NAME, CONFIG_FILE_NAME)


def organization_config_path(environment):
    """File an organization distributes (for example through MDM); optional."""
    explicit = environment.get(ORGANIZATION_CONFIG_VARIABLE)
    if explicit:
        return explicit
    if sys.platform == "win32":
        program_data = environment.get("ProgramData") or environment.get("PROGRAMDATA") or WINDOWS_PROGRAM_DATA_FALLBACK
        return os.path.join(program_data, USER_CONFIG_DIRECTORY_NAME, CONFIG_FILE_NAME)
    if sys.platform == "darwin":
        return MACOS_ORGANIZATION_CONFIG_PATH
    return LINUX_ORGANIZATION_CONFIG_PATH


def describe_layer(layer, location=None):
    """How an error or a report names a layer."""
    return f"{layer} layer ({location})" if location else f"{layer} layer"


def read_layer_file(path, layer):
    """Document of a configuration file, or None when the layer does not exist."""
    if not os.path.exists(path) and not os.path.islink(path):
        return None
    if os.path.islink(path):
        raise ConfigurationError(f"{describe_layer(layer, path)}: the file is a symlink; Agent Ready does not follow it")
    try:
        return read_json_file(path, f"{layer} configuration")
    except StateError as read_error:
        raise ConfigurationError(f"{describe_layer(layer, path)}: {read_error}") from read_error


def validate_locked(schema, locked, label):
    """The keys an organization locks: options or whole namespaces."""
    if not isinstance(locked, list) or not all(isinstance(key, str) for key in locked):
        raise ConfigurationError(f"{label}: '{LOCKED_KEY}' must be a list of keys")
    for key in locked:
        if not schema.is_known_prefix(key):
            raise ConfigurationError(f"{label}: '{LOCKED_KEY}' names the unknown key '{key}'")
    return tuple(locked)


def validate_layer(schema, document, layer, label):
    """Validate one layer and return its dotted assignments (and its locked keys)."""
    document = dict(document)
    locked = ()
    if LOCKED_KEY in document:
        if layer != LAYER_ORGANIZATION:
            raise ConfigurationError(f"{label}: '{LOCKED_KEY}' can only come from the organization layer")
        locked = validate_locked(schema, document.pop(LOCKED_KEY), label)
    try:
        validate_value(document, schema.root, "")
    except InvalidValue as invalid:
        raise ConfigurationError(f"{label}: {invalid}") from invalid
    assignments = schema.flatten(document)
    for key in assignments:
        allowed = schema.leaves[key].get("x-layers", SETTABLE_LAYERS)
        if layer not in allowed:
            raise ConfigurationError(f"{label}: '{key}' cannot be set in the {layer} layer; only in: {', '.join(allowed)}")
    return assignments, locked


def parse_environment_value(raw, node):
    """Value of an option from the text of its environment variable."""
    if node.get("type") == "boolean":
        word = raw.strip().lower()
        if word in ENVIRONMENT_TRUE_WORDS:
            return True
        if word in ENVIRONMENT_FALSE_WORDS:
            return False
        return raw
    if node.get("type") == "integer":
        try:
            return int(raw)
        except ValueError:
            return raw
    if node.get("type") == "array":
        return [item.strip() for item in raw.split(ENVIRONMENT_LIST_SEPARATOR) if item.strip()]
    return raw


def environment_assignments(schema, environment):
    """Assignments of the options whose x-env variable is set for this run."""
    assignments = {}
    for key, node in schema.leaves.items():
        variable = node.get("x-env")
        raw = environment.get(variable) if variable else None
        if raw in (None, ""):
            continue
        value = parse_environment_value(raw, node)
        label = describe_layer(LAYER_ENVIRONMENT, variable)
        try:
            validate_value(value, node, key)
        except InvalidValue as invalid:
            raise ConfigurationError(f"{label}: {invalid}") from invalid
        if LAYER_ENVIRONMENT not in node.get("x-layers", SETTABLE_LAYERS):
            raise ConfigurationError(f"{label}: '{key}' cannot be set in the {LAYER_ENVIRONMENT} layer")
        assignments[key] = value
    return assignments


def flag_assignments(schema, flags):
    """Assignments a command line passes for this run, validated like any layer."""
    assignments = {}
    for key, value in (flags or {}).items():
        node = schema.leaves.get(key)
        label = describe_layer(LAYER_FLAGS)
        if node is None:
            raise ConfigurationError(f"{label}: unknown key '{key}'")
        try:
            validate_value(value, node, key)
        except InvalidValue as invalid:
            raise ConfigurationError(f"{label}: {invalid}") from invalid
        assignments[key] = value
    return assignments


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def normalized_project_path(path):
    """Comparable form of a repository root on this machine."""
    return os.path.normcase(os.path.realpath(path))


def is_locked(key, locked):
    """True when the organization locked the key or a namespace that holds it."""
    return any(key == prefix or key.startswith(prefix + ".") for prefix in locked)


def loosens(node, value, previous):
    """True when ``value`` is looser than ``previous`` for a sensitive option."""
    security = node.get("x-security")
    if not security:
        return False
    order = [json.dumps(item) for item in security["strictness"]]
    return order.index(json.dumps(value)) < order.index(json.dumps(previous))


class Configuration:
    """Effective configuration of one repository, with the origin of every value."""

    def __init__(self, schema, project_root):
        self.schema = schema
        self.project_root = project_root
        self.values = {key: schema.default(key) for key, node in schema.leaves.items() if "default" in node}
        self.origins = {key: [LAYER_DEFAULTS] for key in self.values}
        self.ignored = []
        self.layers = []
        self.locked = ()
        self.project_document = None
        self.project_approved = False
        self.baseline = {}

    def value(self, key):
        """Effective value of an option (None when it has no default and no layer sets it)."""
        if key not in self.schema.leaves:
            raise KeyError(key)
        return copy.deepcopy(self.values.get(key))

    def origin(self, key):
        """Layers that gave an option its effective value, joined with '+'."""
        return "+".join(self.origins.get(key, ["unset"]))

    def blocked_reason(self, layer, key, value, previous):
        """Why a layer cannot set this value, or None when it can."""
        if layer != LAYER_ORGANIZATION and is_locked(key, self.locked):
            return IGNORED_LOCKED
        if layer == LAYER_PROJECT and not self.project_approved and loosens(self.schema.leaves[key], value, previous):
            return IGNORED_LOOSENS
        return None

    def check_project_value(self, key, value):
        """Whether a project value scoped to one item (such as one pack) may loosen ``key``."""
        return self.blocked_reason(LAYER_PROJECT, key, value, self.baseline.get(key, self.values.get(key)))

    def _assign(self, key, value, label):
        node = self.schema.leaves[key]
        if node.get("x-merge") == MERGE_UNION:
            current = self.values.get(key) or []
            self.values[key] = current + [item for item in value if item not in current]
            origins = [origin for origin in self.origins.get(key, []) if origin != LAYER_DEFAULTS]
            self.origins[key] = origins + ([label] if label not in origins else [])
        else:
            self.values[key] = copy.deepcopy(value)
            self.origins[key] = [label]

    def apply_layer(self, layer, assignments):
        """Apply one layer: its presets first, then its explicit keys, each through the gates."""
        before = dict(self.values)
        preset_keys = [key for key in assignments if self.schema.leaves[key].get("x-presets")]
        ordered = []
        for key in preset_keys:
            ordered.append((key, assignments[key], None))
            for target, value in self.schema.leaves[key]["x-presets"][assignments[key]].items():
                ordered.append((target, value, key))
        ordered += [(key, value, None) for key, value in assignments.items() if key not in preset_keys]
        skipped_presets = set()
        for key, value, preset in ordered:
            if preset in skipped_presets:
                continue
            reason = self.blocked_reason(layer, key, value, before.get(key))
            if reason:
                self.ignored.append({"key": key, "value": value, "layer": layer, "reason": reason,
                                     "preset": f"{preset}={assignments[preset]}" if preset else None})
                if key in preset_keys:
                    skipped_presets.add(key)
                continue
            label = f"{layer} (preset {preset}={assignments[preset]})" if preset else layer
            self._assign(key, value, label)

    def tree(self):
        """Effective values as nested objects, the shape of a configuration file."""
        document = {}
        for key in sorted(self.values):
            target = document
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = copy.deepcopy(self.values[key])
        return document


def resolve_configuration(project_root, environment=None, flags=None, schema=None):
    """Effective configuration of a repository; fails before anything is written."""
    schema = schema or load_schema()
    environment = os.environ if environment is None else environment
    configuration = Configuration(schema, project_root)
    file_layers = (
        (LAYER_ORGANIZATION, organization_config_path(environment)),
        (LAYER_USER, user_config_path(environment)),
        (LAYER_PROJECT, os.path.join(project_root, PROJECT_CONFIG_RELATIVE_PATH)),
    )
    layer_assignments = []
    for layer, path in file_layers:
        path = os.path.normpath(path)
        document = read_layer_file(path, layer)
        configuration.layers.append({"name": layer, "path": path, "present": document is not None})
        if document is None:
            continue
        assignments, locked = validate_layer(schema, document, layer, describe_layer(layer, path))
        if layer == LAYER_ORGANIZATION:
            configuration.locked = locked
        if layer == LAYER_PROJECT:
            configuration.project_document = document
        layer_assignments.append((layer, assignments))
    layer_assignments.append((LAYER_ENVIRONMENT, environment_assignments(schema, environment)))
    layer_assignments.append((LAYER_FLAGS, flag_assignments(schema, flags)))
    configuration.layers += [{"name": LAYER_ENVIRONMENT, "path": None, "present": bool(layer_assignments[-2][1])},
                             {"name": LAYER_FLAGS, "path": None, "present": bool(layer_assignments[-1][1])}]

    project_applied = False
    for layer, assignments in layer_assignments:
        if layer in (LAYER_PROJECT, LAYER_ENVIRONMENT, LAYER_FLAGS) and not project_applied:
            configuration.baseline = dict(configuration.values)
            switch = configuration.values[schema.roles[ROLE_APPROVAL_SWITCH]]
            approved = {normalized_project_path(path) for path in configuration.values[schema.roles[ROLE_APPROVED_PROJECTS]]}
            configuration.project_approved = (not switch) or normalized_project_path(project_root) in approved
            project_applied = True
        configuration.apply_layer(layer, assignments)
    return configuration


# ---------------------------------------------------------------------------
# Writing the sparse project layer
# ---------------------------------------------------------------------------

def set_sparse(document, key, value, schema):
    """Set an option in a layer document, or remove it when the value is its default.

    A layer only holds what someone changed, so a default that improves reaches every
    repository without touching its files. Empty namespaces are removed too.
    """
    parts = key.split(".")
    if value is None or value == schema.default(key):
        chain = [document]
        for part in parts[:-1]:
            child = chain[-1].get(part)
            if not isinstance(child, dict):
                return document
            chain.append(child)
        chain[-1].pop(parts[-1], None)
        for depth in range(len(parts) - 1, 0, -1):
            if not chain[depth]:
                chain[depth - 1].pop(parts[depth - 1], None)
        return document
    target = document
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = copy.deepcopy(value)
    return document


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def format_value(value):
    """Short readable form of a value for reports and tab separated lines."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(item.get("name", json.dumps(item, sort_keys=True)) if isinstance(item, dict) else format_value(item) for item in value)
    return str(value)


def describe_ignored(item, approval_hint):
    """One line about a value a layer could not set."""
    source = f" (preset {item['preset']})" if item.get("preset") else ""
    text = f"{item['key']}={format_value(item['value'])} from the {item['layer']} layer{source} was ignored: "
    if item["reason"] == IGNORED_LOCKED:
        return text + "the organization locked it"
    return text + f"it loosens security and this machine has not approved this repository; {approval_hint}"


def markdown_cell(text):
    """Text that fits in one Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def describe_type(node):
    """Type column of the reference: the type, its values and how it merges."""
    items = node.get("items") or {}
    if "enum" in node:
        text = " | ".join(f"`{format_value(item)}`" for item in node["enum"])
    elif node.get("type") == "array" and is_branch(items):
        text = "lista de objetos"
    elif node.get("type") == "array":
        text = f"lista de {items.get('type', 'any')}"
        if items.get("enum"):
            text += " (" + ", ".join(f"`{item}`" for item in items["enum"]) + ")"
    else:
        text = node.get("type", "")
    if node.get("x-merge") == MERGE_UNION:
        text += "; se une entre capas"
    return text


def render_reference(schema):
    """Markdown reference of every option, generated from the schemas."""
    lines = [
        "<!-- Generado por `scripts/agent-ready-state.py config-reference` desde `assets/config/*.schema.json`. No editar a mano. -->",
        "",
        "# Claves de configuración",
        "",
        "Referencia generada desde los schemas de `assets/config/`. Capas, precedencia, aprobación de la máquina,",
        "`locked` y presets: [configuration.md](configuration.md).",
        "",
        "Columnas: **Capas** dice desde dónde se puede declarar la clave; **Variable** la pisa en una corrida;",
        "**Seguridad** ordena los valores de la más floja a la más estricta, y aflojar desde el proyecto requiere",
        "la aprobación de la máquina.",
    ]
    for module in sorted(schema.modules, key=lambda item: (item["mount"] != "", item["mount"])):
        prefix = module["mount"]
        heading = f"`{prefix}`" if prefix else "Raíz del manifest"
        lines += ["", f"## {heading}: {module['title']}", "", module["description"], "",
                  "| Clave | Tipo | Default | Capas | Variable | Seguridad | Descripción |",
                  "|---|---|---|---|---|---|---|"]
        presets = []
        item_fields = []
        for key, node in schema.leaves.items():
            in_module = key.startswith(prefix + ".") if prefix else key in schema.root["properties"] and not is_branch(schema.root["properties"][key])
            if not in_module:
                continue
            default = f"`{json.dumps(node['default'], ensure_ascii=False)}`" if "default" in node else "—"
            layers = ", ".join(node.get("x-layers", ())) or "todas"
            variable = f"`{node['x-env']}`" if node.get("x-env") else "—"
            security = node.get("x-security")
            strictness = " < ".join(f"`{format_value(item)}`" for item in security["strictness"]) if security else "—"
            lines.append(f"| `{key}` | {markdown_cell(describe_type(node))} | {markdown_cell(default)} | {layers} | {variable} | "
                         f"{markdown_cell(strictness)} | {markdown_cell(node['description'])} |")
            for preset_value, assignments in (node.get("x-presets") or {}).items():
                values = ", ".join(f"`{target}: {format_value(value)}`" for target, value in assignments.items()) or "sin cambios"
                presets.append(f"- `{key}: {preset_value}` → {values}")
            items = node.get("items") or {}
            if is_branch(items):
                item_fields.append(f"Campos de cada elemento de `{key}`:")
                item_fields.append("")
                for field, field_node in items["properties"].items():
                    required = "obligatorio" if field in items.get("required", []) else "opcional"
                    item_fields.append(f"- `{field}` ({describe_type(field_node)}, {required}): {field_node.get('description', '')}")
        if presets:
            lines += ["", "Presets:", ""] + presets
        if item_fields:
            lines += [""] + item_fields
    lines += ["", "`locked` es una lista de claves (o namespaces enteros) que solo declara la organización.", ""]
    return "\n".join(lines)
