#!/usr/bin/env python3
"""Helpers deterministas de la skill jira-ticket.

Toda la información de la organización (sitio, proyecto, tablero, ids de
campos, responsable, formato de sprint, cómo se identifica un repositorio)
llega por variables de entorno `JIRA_TICKET_*`. Si una variable no está en el
entorno, se busca en el archivo de perfil (`JIRA_TICKET_ENV_FILE`, por defecto
`~/.config/jira-ticket/env`). El entorno siempre tiene prioridad.

No escribe en Jira ni en GitHub: `pr-normalize` solo lee con `gh`; las
escrituras quedan a cargo del agente.

La salida es JSON por stdout; los errores van a stderr en español con exit
code distinto de cero.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import functools
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import adf_document as adf  # noqa: E402  (módulo hermano del script)

# --- Configuración ---------------------------------------------------------

ENV_PREFIX = "JIRA_TICKET_"
ENV_FILE_VARIABLE = "JIRA_TICKET_ENV_FILE"
DEFAULT_ENV_FILE = "~/.config/jira-ticket/env"
REQUIRED_SETTINGS = ("SITE_URL", "CLOUD_ID", "PROJECT_KEY")
DEFAULT_SETTINGS = {
    "STORY_TYPE": "Story",
    "TASK_TYPE": "Task",
    "SUBTASK_TYPE": "Sub-task",
    "QUARTER_FORMAT": "Q{quarter}/{yy}",
    "SPRINT_ACTIVE_STATE": "active",
    "REPO_ID_SOURCES": "package.json:name,basename",
    "REPO_PREFIXES": "",
    "MAX_RESULTS": "50",
    "DEPENDENCY_LINK_TYPE": "Blocks",
}
KNOWN_SETTINGS = (
    "SITE_URL",
    "CLOUD_ID",
    "PROJECT_KEY",
    "PROJECT_NAME",
    "BOARD_ID",
    "ASSIGNEE_ACCOUNT_ID",
    "STORY_TYPE",
    "TASK_TYPE",
    "SUBTASK_TYPE",
    "QUARTER_FIELD",
    "QUARTER_FORMAT",
    "START_DATE_FIELD",
    "SPRINT_FIELD",
    "SPRINT_NAME_REGEX",
    "SPRINT_ACTIVE_STATE",
    "REPO_ID_SOURCES",
    "REPO_PREFIXES",
    "MEMORY_ORG",
    "MAX_RESULTS",
    "DEPENDENCY_LINK_TYPE",
    "BLOCKER_PROJECT_KEYS",
    "BLOCKER_ISSUE_TYPE",
    "BLOCKER_DEFAULT_EPIC",
)
SPRINT_REGEX_YEAR_GROUP = "year"
SPRINT_REGEX_QUARTER_GROUP = "quarter"
ENV_LINE_REGEX = re.compile(r"^\s*(?:export\s+)?(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*(?P<value>.*)$")

# --- Contratos fijos (no dependen de la organización) ---------------------

BACKLINK_PREFIX = "🎫 Jira:"
DESCRIPTION_HEADING = "## 📝 Descripción"
LEGACY_REFERENCE_PREFIX = "> **Referencia:**"
ATX_HEADING_REGEX = re.compile(r"^#{1,6} ")
CODE_FENCE_OPEN_REGEX = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")
CODE_FENCE_CLOSE_REGEX = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})\s*$")
ISSUE_KEY_REGEX = re.compile(r"^[A-Z][A-Z0-9]+-[0-9]+$")
EMBEDDED_ISSUE_KEY_REGEX = re.compile(r"(?<![A-Z0-9-])[A-Z][A-Z0-9]+-[0-9]+(?![0-9])")
PR_NUMBER_REGEX = re.compile(r"^[0-9]+$")
PR_URL_REGEX = re.compile(r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)/pull/(?P<number>[0-9]+)$")
PR_LABEL_TEMPLATE = "{repository_id}/PR-{number}"
MERGED_STATE = "MERGED"
DONE_STATUS_CATEGORY = "done"
GH_PR_FIELDS = "number,url,headRefName,baseRefName,state"
MONTHS_PER_QUARTER = 3

STDIO_ENCODING = "utf-8"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNRESOLVED = 3
EXIT_CONFIG = 4


class JiraTicketError(Exception):
    """Error controlado con mensaje para personas y exit code propio."""

    def __init__(self, message: str, exit_code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class Config:
    """Configuración resuelta: valores, origen de cada uno y faltantes obligatorios."""

    values: dict[str, str]
    sources: dict[str, str] = field(default_factory=dict)
    env_file: str | None = None

    def get(self, name: str) -> str | None:
        value = self.values.get(name)
        return value if value not in (None, "") else None

    def require(self, name: str) -> str:
        value = self.get(name)
        if value is None:
            raise JiraTicketError(f"jira-ticket: falta {ENV_PREFIX}{name} (definila en el entorno o en {self.env_file or DEFAULT_ENV_FILE})", EXIT_CONFIG)
        return value

    @property
    def missing_required(self) -> list[str]:
        return [f"{ENV_PREFIX}{name}" for name in REQUIRED_SETTINGS if self.get(name) is None]

    @property
    def features(self) -> dict[str, bool]:
        return {
            "quarter": self.get("QUARTER_FIELD") is not None,
            "start_date": self.get("START_DATE_FIELD") is not None,
            "sprint": self.get("SPRINT_FIELD") is not None and self.get("BOARD_ID") is not None,
            "default_assignee": self.get("ASSIGNEE_ACCOUNT_ID") is not None,
            "blocker_default_epic": self.get("BLOCKER_DEFAULT_EPIC") is not None,
        }

    @property
    def dependencies(self) -> dict[str, Any]:
        """Valores efectivos de dependencias por bloqueo, con los defaults que dependen de otras variables."""
        project_key = self.get("PROJECT_KEY")
        blocker_projects = [item.strip() for item in (self.get("BLOCKER_PROJECT_KEYS") or "").split(",") if item.strip()]
        return {
            "link_type": self.get("DEPENDENCY_LINK_TYPE") or DEFAULT_SETTINGS["DEPENDENCY_LINK_TYPE"],
            "blocker_project_keys": blocker_projects or ([project_key] if project_key else []),
            "blocker_issue_type": self.get("BLOCKER_ISSUE_TYPE") or self.get("STORY_TYPE") or DEFAULT_SETTINGS["STORY_TYPE"],
            "blocker_default_epic": self.get("BLOCKER_DEFAULT_EPIC"),
        }


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    """Lee líneas `[export] NOMBRE=valor` sin ejecutar nada; ignora comentarios y líneas vacías."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE_REGEX.match(line)
        if not match:
            continue
        raw_value = match["value"].strip()
        try:
            parts = shlex.split(raw_value, comments=True, posix=True)
        except ValueError as error:
            raise JiraTicketError(f"jira-ticket: valor mal citado para {match['name']} en {path}", EXIT_CONFIG) from error
        values[match["name"]] = parts[0] if len(parts) == 1 else " ".join(parts)
    return values


def load_config(environ: dict[str, str] | None = None) -> Config:
    """Combina defaults, archivo de perfil y entorno (en ese orden de prioridad creciente)."""
    environ = dict(os.environ if environ is None else environ)
    env_file = pathlib.Path(os.path.expanduser(environ.get(ENV_FILE_VARIABLE, DEFAULT_ENV_FILE)))
    file_values = parse_env_file(env_file) if env_file.is_file() else {}
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    for name in KNOWN_SETTINGS:
        key = ENV_PREFIX + name
        if environ.get(key, "") != "":
            values[name], sources[name] = environ[key], "env"
        elif file_values.get(key, "") != "":
            values[name], sources[name] = file_values[key], "file"
        elif name in DEFAULT_SETTINGS:
            values[name], sources[name] = DEFAULT_SETTINGS[name], "default"
    return Config(values=values, sources=sources, env_file=str(env_file) if env_file.is_file() else None)


def describe_config(config: Config) -> dict[str, Any]:
    return {
        "env_file": config.env_file,
        "missing_required": config.missing_required,
        "features": config.features,
        "dependencies": config.dependencies,
        "settings": {f"{ENV_PREFIX}{name}": {"value": value, "source": config.sources[name]} for name, value in sorted(config.values.items())},
    }


# --- Utilidades ------------------------------------------------------------


def parse_date(value: str | None) -> dt.date:
    if value is None:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError as error:
        raise JiraTicketError(f"jira-ticket: fecha inválida '{value[:20]}', se espera YYYY-MM-DD") from error


def read_json_stdin() -> Any:
    raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise JiraTicketError(f"jira-ticket: stdin no es JSON válido ({error.msg}, línea {error.lineno})") from error


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


# --- quarter ---------------------------------------------------------------


def quarter_for(date: dt.date, quarter_format: str = DEFAULT_SETTINGS["QUARTER_FORMAT"]) -> dict[str, Any]:
    quarter_number = (date.month - 1) // MONTHS_PER_QUARTER + 1
    try:
        value = quarter_format.format(quarter=quarter_number, yy=f"{date.year % 100:02d}", yyyy=date.year)
    except (KeyError, IndexError) as error:
        raise JiraTicketError(f"jira-ticket: {ENV_PREFIX}QUARTER_FORMAT inválido; placeholders válidos: {{quarter}}, {{yy}}, {{yyyy}}", EXIT_CONFIG) from error
    return {"year": date.year, "quarter": quarter_number, "quarters_value": value}


def quarter_option(metadata: Any, quarter_field: str, quarters_value: str) -> dict[str, str] | None:
    for meta_field in metadata.get("fields", []):
        if meta_field.get("fieldId") != quarter_field:
            continue
        for allowed in meta_field.get("allowedValues", []):
            if allowed.get("value") == quarters_value:
                return {"id": str(allowed["id"]), "value": allowed["value"]}
    return None


# --- sprint ----------------------------------------------------------------


def collect_sprints(jql_result: Any, sprint_field: str) -> list[dict[str, Any]]:
    sprints: dict[int, dict[str, Any]] = {}
    for issue in jql_result.get("issues", []):
        for sprint in (issue.get("fields") or {}).get(sprint_field) or []:
            sprints[sprint["id"]] = sprint
    return sorted(sprints.values(), key=lambda sprint: sprint["id"])


def pick_sprint(jql_result: Any, date: dt.date, config: Config) -> dict[str, Any]:
    """Sprint activo del tablero configurado.

    Si `SPRINT_NAME_REGEX` tiene los grupos `year` y `quarter`, además exige que
    coincidan con la fecha. Nunca calcula nombres: sin un único candidato
    devuelve `none` o `ambiguous` para que el agente pregunte.
    """
    sprint_field = config.require("SPRINT_FIELD")
    board_id = int(config.require("BOARD_ID"))
    active_state = config.get("SPRINT_ACTIVE_STATE") or DEFAULT_SETTINGS["SPRINT_ACTIVE_STATE"]
    name_pattern = config.get("SPRINT_NAME_REGEX")
    try:
        name_regex = re.compile(name_pattern) if name_pattern else None
    except re.error as error:
        raise JiraTicketError(f"jira-ticket: {ENV_PREFIX}SPRINT_NAME_REGEX inválida ({error})", EXIT_CONFIG) from error
    checks_quarter = bool(name_regex) and {SPRINT_REGEX_YEAR_GROUP, SPRINT_REGEX_QUARTER_GROUP} <= set(name_regex.groupindex)
    expected = quarter_for(date)
    candidates = []
    for sprint in collect_sprints(jql_result, sprint_field):
        if sprint.get("boardId") != board_id or sprint.get("state") != active_state:
            continue
        match = name_regex.fullmatch(sprint.get("name", "")) if name_regex else None
        if name_regex and not match:
            continue
        if checks_quarter and (int(match[SPRINT_REGEX_YEAR_GROUP]) != expected["year"] or int(match[SPRINT_REGEX_QUARTER_GROUP]) != expected["quarter"]):
            continue
        candidates.append({"id": sprint["id"], "name": sprint["name"], "endDate": sprint.get("endDate")})
    status = "ok" if len(candidates) == 1 else ("none" if not candidates else "ambiguous")
    return {"status": status, "sprint": candidates[0] if status == "ok" else None, "candidates": candidates, "quarter_checked": checks_quarter}


# --- repo-id ---------------------------------------------------------------


def strip_prefixes(name: str, prefixes: list[str]) -> str:
    for prefix in prefixes:
        if prefix and name.startswith(prefix):
            return name[len(prefix):]
    return name


def config_list(config: Config, name: str) -> list[str]:
    return [item.strip() for item in (config.get(name) or "").split(",") if item.strip()]


def _read_key_value_file(path: pathlib.Path, key: str) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition(":")
        if not separator:
            name, separator, value = line.partition("=")
        if separator and name.strip() == key and value.strip():
            return value.strip().strip("'\"")
    return None


def repository_id(root: pathlib.Path, config: Config) -> dict[str, str]:
    """Recorre `REPO_ID_SOURCES` (`archivo:clave`, `package.json:name` o `basename`) en orden."""
    prefixes = config_list(config, "REPO_PREFIXES")
    for source in config_list(config, "REPO_ID_SOURCES"):
        if source == "basename":
            return {"repository_id": strip_prefixes(root.resolve().name, prefixes), "source": "basename"}
        file_name, _, key = source.partition(":")
        path = root / file_name
        if not key or not path.is_file():
            continue
        if file_name.endswith(".json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8")).get(key) or ""
            except json.JSONDecodeError:
                value = ""
            value = value.split("/")[-1]
        else:
            value = _read_key_value_file(path, key) or ""
        if value:
            return {"repository_id": value, "source": source}
    return {"repository_id": strip_prefixes(root.resolve().name, prefixes), "source": "basename"}


# --- pr-normalize ----------------------------------------------------------


def validate_pr_input(value: str) -> str:
    if PR_NUMBER_REGEX.match(value) or PR_URL_REGEX.match(value):
        return value
    raise JiraTicketError(f"jira-ticket: PR inválido '{value[:80]}'; se acepta un número o https://github.com/<owner>/<repo>/pull/<n>")


def gh_executable() -> str:
    """Ruta de `gh` según `PATH` (y `PATHEXT` en Windows, donde puede ser un shim `.cmd`)."""
    executable = shutil.which("gh")
    if executable is None:
        raise JiraTicketError("jira-ticket: no se encontró el ejecutable 'gh' en PATH; instalá GitHub CLI para usar pr-normalize", EXIT_UNRESOLVED)
    return executable


def gh_pr_view(pr_input: str, cwd: pathlib.Path | None = None) -> dict[str, Any]:
    """Lee el PR con `gh pr view`; `cwd` define el repositorio donde se resuelve un número de PR."""
    completed = subprocess.run([gh_executable(), "pr", "view", pr_input, "--json", GH_PR_FIELDS], capture_output=True, text=True, encoding=STDIO_ENCODING, check=False, cwd=cwd)
    if completed.returncode != 0:
        raise JiraTicketError(f"jira-ticket: gh pr view {pr_input} falló en {cwd or pathlib.Path.cwd()} (exit {completed.returncode}): {completed.stderr.strip()[:200]}", EXIT_UNRESOLVED)
    return json.loads(completed.stdout)


def normalize_prs(
    pr_inputs: list[str],
    local_repo: dict[str, str],
    local_slug: str | None,
    prefixes: list[str],
    viewer: Callable[[str], dict[str, Any]] = gh_pr_view,
) -> dict[str, Any]:
    pull_requests: dict[str, dict[str, Any]] = {}
    for pr_input in pr_inputs:
        data = viewer(validate_pr_input(pr_input))
        match = PR_URL_REGEX.match(data["url"])
        if not match:
            raise JiraTicketError(f"jira-ticket: gh devolvió una URL no canónica: {data['url'][:120]}", EXIT_UNRESOLVED)
        slug = f"{match['owner']}/{match['repo']}"
        if local_slug and slug.lower() == local_slug.lower():
            repo_id, source = local_repo["repository_id"], local_repo["source"]
        else:
            repo_id, source = strip_prefixes(match["repo"], prefixes), "basename"
        pull_requests[data["url"]] = {
            "number": data["number"],
            "url": data["url"],
            "repo": slug,
            "repository_id": repo_id,
            "repository_id_source": source,
            "headRefName": data.get("headRefName"),
            "baseRefName": data.get("baseRefName"),
            "state": data["state"],
        }
    ordered = sorted(pull_requests.values(), key=lambda pr: (pr["repo"].lower(), pr["number"]))
    return {
        "pull_requests": ordered,
        "pr_labels": sorted({PR_LABEL_TEMPLATE.format(**pr) for pr in ordered}),
        "all_prs_merged": bool(ordered) and all(pr["state"] == MERGED_STATE for pr in ordered),
    }


def current_repo_slug(cwd: pathlib.Path | None = None) -> str | None:
    """`owner/repo` del repositorio en `cwd` según `gh repo view`, o None si gh no lo resuelve."""
    completed = subprocess.run([gh_executable(), "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], capture_output=True, text=True, encoding=STDIO_ENCODING, check=False, cwd=cwd)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


# --- backlink --------------------------------------------------------------


def browse_url(site_url: str, key: str) -> str:
    return f"{site_url.rstrip('/')}/browse/{key}"


def backlink_line(key: str, site_url: str) -> str:
    if not ISSUE_KEY_REGEX.match(key):
        raise JiraTicketError(f"jira-ticket: key Jira inválida '{key[:30]}'")
    return f"{BACKLINK_PREFIX} [{key}]({browse_url(site_url, key)})"


def _is_same_ticket_line(line: str, key: str) -> bool:
    """Reemplazable solo si es backlink/referencia legacy cuyas keys Jira son únicamente la key objetivo."""
    stripped = line.strip()
    if not (stripped.startswith(BACKLINK_PREFIX) or stripped.startswith(LEGACY_REFERENCE_PREFIX)):
        return False
    referenced_keys = set(EMBEDDED_ISSUE_KEY_REGEX.findall(stripped))
    return referenced_keys == {key}


def _fenced_line_flags(lines: list[str]) -> list[bool]:
    """Marca las líneas dentro de bloques de código fenced (delimitadores incluidos); un fence sin cerrar llega al final."""
    flags: list[bool] = []
    open_fence: str | None = None
    for line in lines:
        if open_fence is None:
            opening = CODE_FENCE_OPEN_REGEX.match(line)
            if opening and not (opening.group("fence").startswith("`") and "`" in line[opening.end():]):
                open_fence = opening.group("fence")
            flags.append(open_fence is not None)
            continue
        flags.append(True)
        closing = CODE_FENCE_CLOSE_REGEX.match(line)
        if closing and closing.group("fence")[0] == open_fence[0] and len(closing.group("fence")) >= len(open_fence):
            open_fence = None
    return flags


def apply_backlink(body: str, key: str, site_url: str) -> str:
    """Inserta el backlink canónico una sola vez fuera de bloques de código; idempotente y sin tocar el resto del body."""
    link = backlink_line(key, site_url)
    newline = "\r\n" if "\r\n" in body else "\n"
    had_final_newline = body.endswith(("\n", "\r\n"))
    original_lines = body.splitlines()
    kept_lines = [
        (line, is_fenced)
        for line, is_fenced in zip(original_lines, _fenced_line_flags(original_lines))
        if is_fenced or not _is_same_ticket_line(line, key)
    ]
    lines = [line for line, _ in kept_lines]
    heading_indexes = [index for index, (line, is_fenced) in enumerate(kept_lines) if not is_fenced and ATX_HEADING_REGEX.match(line)]
    description_index = next((index for index in heading_indexes if lines[index] == DESCRIPTION_HEADING), None)
    if description_index is not None:
        insert_at: int | None = description_index + 1
    else:
        insert_at = heading_indexes[0] + 1 if heading_indexes else None
    head, rest = (lines[:insert_at], lines[insert_at:]) if insert_at is not None else ([], lines)
    while rest and not rest[0].strip():
        rest = rest[1:]
    separator_after_link = [""] if rest else []
    new_lines = (head + ["", link] + separator_after_link + rest) if insert_at is not None else ([link] + separator_after_link + rest)
    result = newline.join(new_lines)
    return result + newline if had_final_newline else result


def verify_backlink(body: str, key: str, site_url: str) -> dict[str, Any]:
    link = backlink_line(key, site_url)
    lines = body.splitlines()
    count = sum(1 for line, is_fenced in zip(lines, _fenced_line_flags(lines)) if not is_fenced and line == link)
    return {"key": key, "occurrences": count, "canonical": count == 1 and apply_backlink(body, key, site_url) == body}


# --- slim ------------------------------------------------------------------


def slim(payload: Any, field_ids: list[str]) -> Any:
    """Reduce respuestas de Jira (JQL, createmeta o issue) a los campos pedidos."""
    wanted = set(field_ids)
    if isinstance(payload, dict) and "issues" in payload:
        return {
            "issues": [{"key": issue.get("key"), "fields": {k: v for k, v in (issue.get("fields") or {}).items() if k in wanted}} for issue in payload["issues"]],
            "isLast": payload.get("isLast"),
            "nextPageToken": payload.get("nextPageToken"),
        }
    if isinstance(payload, dict) and isinstance(payload.get("fields"), list):
        reduced = [
            {
                "fieldId": meta_field.get("fieldId"),
                "name": meta_field.get("name"),
                "required": meta_field.get("required"),
                "hasDefaultValue": meta_field.get("hasDefaultValue"),
                "type": (meta_field.get("schema") or {}).get("type"),
                "allowedValues": [{"id": str(value.get("id")), "value": value.get("value", value.get("name"))} for value in meta_field.get("allowedValues", [])],
            }
            for meta_field in payload["fields"]
            if (wanted and meta_field.get("fieldId") in wanted) or (not wanted and meta_field.get("required"))
        ]
        return {"total": payload.get("total"), "fields": reduced}
    if isinstance(payload, dict) and "key" in payload:
        return {"key": payload["key"], "fields": {k: v for k, v in (payload.get("fields") or {}).items() if k in wanted}}
    raise JiraTicketError("jira-ticket: formato de entrada no reconocido para slim (se espera JQL, createmeta o issue)")


# --- tracking --------------------------------------------------------------
#
# La tabla de estados vive solo en la subtarea: es la unidad más chica de Jira,
# así que sus pasos no tienen issue propio que muestre el estado. Épicas y
# Stories no llevan tabla: el panel de hijos de Jira ya muestra sus hijos.

STEPS_HEADING = "## Pasos"
STEP_COLUMN = "Paso"
STATUS_COLUMN = "Estado"
NOTE_COLUMN = "Nota"
STEP_COLUMNS = (STEP_COLUMN, STATUS_COLUMN, NOTE_COLUMN)
EMPTY_CELL = "—"


@dataclass(frozen=True)
class StepState:
    """Estado posible de un paso: emoji, nombre visible, color del lozenge y leyenda del contador."""

    emoji: str
    label: str
    color: str
    singular: str
    plural: str

    def count_text(self, count: int) -> str:
        return f"{self.emoji} {count} {self.singular if count == 1 else self.plural}"


STEP_STATES = {
    "done": StepState("✅", "Hecho", "green", "hecho", "hechos"),
    "in_progress": StepState("🔄", "En curso", "blue", "en curso", "en curso"),
    "todo": StepState("⬜", "Pendiente", "neutral", "pendiente", "pendientes"),
    "blocked": StepState("🚫", "Bloqueado", "red", "bloqueado", "bloqueados"),
}
ALWAYS_COUNTED_STATES = ("done", "in_progress", "todo")
STATE_BY_EMOJI = {state.emoji: name for name, state in STEP_STATES.items()}
PROGRESS_LABEL = "Progreso:"
PROGRESS_PREFIX = f"**{PROGRESS_LABEL}**"
PROGRESS_SEPARATOR = " · "
SECTION_HEADING_REGEX = re.compile(r"^#{1,2} ")
TABLE_SEPARATOR_REGEX = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")
STEP_EMOJI_PATTERN = "|".join(re.escape(state.emoji) for state in STEP_STATES.values())
LIST_ROW_REGEX = re.compile(rf"^- (?P<emoji>{STEP_EMOJI_PATTERN}) (?P<title>\S.*)$")
NESTED_FIELD_LABELS = (STATUS_COLUMN, NOTE_COLUMN)
NESTED_FIELD_REGEX = re.compile(rf"^(?P<indent> {{2,}})- (?P<label>{'|'.join(NESTED_FIELD_LABELS)}): (?P<value>.*)$")
NESTED_FIELD_INDENT = "  "


@dataclass
class Step:
    """Paso de una subtarea con su estado deseado. `note` es `None` cuando la entrada no la trae."""

    title: str
    state: str
    note: str | None = None

    @property
    def emoji(self) -> str:
        return STEP_STATES[self.state].emoji

    @property
    def status_cell(self) -> str:
        return f"{self.emoji} {STEP_STATES[self.state].label}"


def step_identity(title: str) -> str:
    """Identidad de un paso para cruzar la entrada con las filas: sin mayúsculas ni espacios repetidos."""
    return " ".join(title.replace("\\|", "|").split()).casefold()


def parse_steps(payload: Any) -> list[Step]:
    if not isinstance(payload, list):
        raise JiraTicketError("jira-ticket: tracking espera `steps` como lista de pasos de la subtarea")
    steps: list[Step] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise JiraTicketError(f"jira-ticket: tracking steps[{index}] no es un objeto")
        title = " ".join(str(raw.get("title") or "").split())
        if not title:
            raise JiraTicketError(f"jira-ticket: tracking steps[{index}] no tiene `title`")
        state = str(raw.get("state") or "")
        if state not in STEP_STATES:
            raise JiraTicketError(
                f"jira-ticket: tracking paso '{title[:40]}' tiene state '{state[:30]}'; se espera {', '.join(STEP_STATES)}",
                EXIT_UNRESOLVED,
            )
        note = raw.get("note")
        steps.append(Step(title=title, state=state, note=" ".join(str(note).split()) if note is not None else None))
    identities = [step_identity(step.title) for step in steps]
    duplicated = sorted({step.title for step, identity in zip(steps, identities) if identities.count(identity) > 1})
    if duplicated:
        raise JiraTicketError(f"jira-ticket: tracking recibió pasos repetidos: {', '.join(duplicated)}")
    return steps


def progress_line(states: list[str]) -> str:
    """`**Progreso:** <hechos>/<total> · ✅ n hechos · 🔄 n en curso · ⬜ n pendientes[ · 🚫 n bloqueados]`."""
    counts = {name: states.count(name) for name in STEP_STATES}
    parts = [f"{counts['done']}/{len(states)}", *(STEP_STATES[name].count_text(counts[name]) for name in ALWAYS_COUNTED_STATES)]
    if counts["blocked"]:
        parts.append(STEP_STATES["blocked"].count_text(counts["blocked"]))
    return f"{PROGRESS_PREFIX} {PROGRESS_SEPARATOR.join(parts)}"


def _state_of_cell(text: str) -> str | None:
    return STATE_BY_EMOJI.get(text.strip().split(" ", 1)[0]) if text.strip() else None


def _split_cells(row: str) -> list[tuple[int, int]]:
    """Posiciones (inicio, fin) del contenido de cada celda de una fila `| a | b |`, respetando `\\|`."""
    stripped_end = len(row.rstrip())
    pipes = [index for index, char in enumerate(row[:stripped_end]) if char == "|" and (index == 0 or row[index - 1] != "\\")]
    return [(pipes[position] + 1, pipes[position + 1]) for position in range(len(pipes) - 1)]


def _cell_values(row: str) -> list[str]:
    return [row[start:end].strip() for start, end in _split_cells(row)]


def _escape_cell(value: str) -> str:
    """Escapa los `|` sin escapar para que el texto no parta la fila en otra celda."""
    return re.sub(r"(?<!\\)\|", r"\\|", value)


def _replace_cell(row: str, column: int, value: str) -> str:
    start, end = _split_cells(row)[column]
    return f"{row[:start]} {_escape_cell(value)} {row[end:]}"


def _note_after(step: Step, previous_state: str | None, current_note: str) -> str:
    """Nota que queda en la fila: la de la entrada si vino; si no, la actual, salvo al salir de bloqueado."""
    if step.note is not None:
        return step.note or EMPTY_CELL
    if previous_state == "blocked" and step.state != "blocked":
        return EMPTY_CELL
    return current_note or EMPTY_CELL


def _step_values(step: Step) -> dict[str, str]:
    return {STEP_COLUMN: step.title, STATUS_COLUMN: step.status_cell, NOTE_COLUMN: step.note or EMPTY_CELL}


def _table_row(step: Step, columns: list[str] | tuple[str, ...] = STEP_COLUMNS) -> str:
    """Fila del paso con las celdas en el orden de `columns`; una columna ajena queda con `—`."""
    values = _step_values(step)
    cells = [values.get(column, EMPTY_CELL) for column in columns]
    return "| " + " | ".join(_escape_cell(cell) for cell in cells) + " |"


def _nested_field(label: str, value: str, indent: str = NESTED_FIELD_INDENT) -> str:
    return f"{indent}- {label}: {value}"


def _nested_rows(step: Step) -> list[str]:
    rows = [f"- {step.emoji} {step.title}", _nested_field(STATUS_COLUMN, STEP_STATES[step.state].label)]
    if step.note:
        rows.append(_nested_field(NOTE_COLUMN, step.note))
    return rows


def _new_section_body(steps: list[Step], as_list: bool = False) -> list[str]:
    top = [progress_line([step.state for step in steps]), ""]
    if as_list:
        return top + [row for step in steps for row in _nested_rows(step)]
    header = "| " + " | ".join(STEP_COLUMNS) + " |"
    separator = "|" + "|".join("---" for _ in STEP_COLUMNS) + "|"
    return [*top, header, separator, *[_table_row(step) for step in steps]]


def _table_end(body: list[str], fenced: list[bool], header_index: int) -> int:
    end = header_index + 2
    while end < len(body) and not fenced[end] and body[end].startswith("|"):
        end += 1
    return end


def _section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    fenced = _fenced_line_flags(lines)
    start = next((index for index, line in enumerate(lines) if not fenced[index] and line.rstrip() == heading), None)
    if start is None:
        return None
    end = next((index for index in range(start + 1, len(lines)) if not fenced[index] and SECTION_HEADING_REGEX.match(lines[index])), len(lines))
    return start, end


def _is_flattened_table_line(line: str) -> bool:
    """Tabla de pasos que Jira devolvió aplanada: una línea de texto con barras que nombra las columnas `Paso` y `Estado`."""
    return "|" in line and not line.startswith(PROGRESS_PREFIX) and STEP_COLUMN in line and STATUS_COLUMN in line


def _table_columns(columns: list[str]) -> tuple[int, int, int | None]:
    if STEP_COLUMN not in columns or STATUS_COLUMN not in columns:
        raise JiraTicketError(f"jira-ticket: la tabla de '{STEPS_HEADING}' no tiene columnas {STEP_COLUMN} y {STATUS_COLUMN}", EXIT_UNRESOLVED)
    return columns.index(STEP_COLUMN), columns.index(STATUS_COLUMN), columns.index(NOTE_COLUMN) if NOTE_COLUMN in columns else None


def _update_table(body: list[str], fenced: list[bool], header_index: int, steps: list[Step], result: dict[str, Any]) -> list[str]:
    by_identity = {step_identity(step.title): step for step in steps}
    columns = _cell_values(body[header_index])
    step_column, status_column, note_column = _table_columns(columns)
    table_end = _table_end(body, fenced, header_index)
    states: list[str] = []
    seen: set[str] = set()
    for index in range(header_index + 2, table_end):
        cells = _cell_values(body[index])
        if len(cells) <= max(step_column, status_column) or not cells[step_column]:
            continue
        identity = step_identity(cells[step_column])
        seen.add(identity)
        previous_state = _state_of_cell(cells[status_column])
        step = by_identity.get(identity)
        if step is None:
            result["rows_without_step"].append(cells[step_column].replace("\\|", "|"))
            states.append(previous_state or "todo")
            continue
        row = body[index]
        if cells[status_column] != step.status_cell:
            row = _replace_cell(row, status_column, step.status_cell)
        if note_column is not None and len(cells) > note_column:
            note = _note_after(step, previous_state, cells[note_column].replace("\\|", "|"))
            if cells[note_column] != _escape_cell(note):
                row = _replace_cell(row, note_column, note)
        if row != body[index]:
            body[index] = row
            result["updated"].append(step.title)
        states.append(step.state)
    for step in [step for step in steps if step_identity(step.title) not in seen]:
        body.insert(table_end, _table_row(step, columns))
        fenced.insert(table_end, False)
        table_end += 1
        result["added"].append(step.title)
        states.append(step.state)
    return states


def _update_list(body: list[str], list_indexes: list[int], steps: list[Step], result: dict[str, Any]) -> list[str]:
    """Actualiza la lista de respaldo: emoji de la línea del paso, su sub-item `Estado` y su `Nota`."""
    by_identity = {step_identity(step.title): step for step in steps}
    states_by_index: dict[int, str] = {}
    seen: set[str] = set()
    for index in reversed(list_indexes):
        match = LIST_ROW_REGEX.match(body[index])
        block_end = index + 1
        while block_end < len(body) and NESTED_FIELD_REGEX.match(body[block_end]):
            block_end += 1
        identity = step_identity(match.group("title"))
        seen.add(identity)
        previous_state = STATE_BY_EMOJI[match.group("emoji")]
        step = by_identity.get(identity)
        if step is None:
            result["rows_without_step"].insert(0, match.group("title"))
            states_by_index[index] = previous_state
            continue
        fields = body[index + 1:block_end]
        indent = NESTED_FIELD_REGEX.match(fields[0]).group("indent") if fields else NESTED_FIELD_INDENT
        current_note = next((NESTED_FIELD_REGEX.match(line).group("value") for line in fields if NESTED_FIELD_REGEX.match(line).group("label") == NOTE_COLUMN), "")
        note = _note_after(step, previous_state, current_note)
        block = [f"- {step.emoji} {match.group('title')}", _nested_field(STATUS_COLUMN, STEP_STATES[step.state].label, indent)]
        if note != EMPTY_CELL:
            block.append(_nested_field(NOTE_COLUMN, note, indent))
        if block != body[index:block_end]:
            body[index:block_end] = block
            result["updated"].insert(0, step.title)
        states_by_index[index] = step.state
    states = [states_by_index[index] for index in sorted(states_by_index)]
    fenced = _fenced_line_flags(body)
    last = max(index for index, line in enumerate(body) if not fenced[index] and LIST_ROW_REGEX.match(line))
    while last + 1 < len(body) and NESTED_FIELD_REGEX.match(body[last + 1]):
        last += 1
    for step in [step for step in steps if step_identity(step.title) not in seen]:
        rows = _nested_rows(step)
        body[last + 1:last + 1] = rows
        last += len(rows)
        result["added"].append(step.title)
        states.append(step.state)
    return states


def _table_to_nested_list(body: list[str], fenced: list[bool], header_index: int) -> None:
    """Reemplaza la tabla de pasos por la lista anidada, con los valores que ya tenía cada fila."""
    step_column, status_column, note_column = _table_columns(_cell_values(body[header_index]))
    table_end = _table_end(body, fenced, header_index)
    rows: list[str] = []
    for index in range(header_index + 2, table_end):
        cells = [value.replace("\\|", "|") for value in _cell_values(body[index])]
        if len(cells) <= max(step_column, status_column) or not cells[step_column]:
            continue
        emoji, _, label = cells[status_column].partition(" ")
        rows.append(f"- {emoji} {cells[step_column]}")
        rows.append(_nested_field(STATUS_COLUMN, label))
        if note_column is not None and len(cells) > note_column and cells[note_column] not in ("", EMPTY_CELL):
            rows.append(_nested_field(NOTE_COLUMN, cells[note_column]))
    body[header_index:table_end] = rows


def update_tracking(description: str, steps_payload: Any, create: bool = False, as_list: bool = False) -> dict[str, Any]:
    """Actualiza solo la sección `## Pasos` de una subtarea: estado de cada paso, pasos nuevos y `Progreso`.

    Todo lo que está fuera de la sección queda idéntico byte a byte. Dentro, solo
    cambian la celda `Estado` (y `Nota`) de los pasos que cambiaron, las filas
    que se agregan al final y la línea `Progreso`. Las filas cuyo paso no vino
    en la entrada se conservan y se informan. Sin sección, la crea solo con
    `create`, al final de la descripción. Con `as_list` la sección queda como
    lista anidada: se crea así y, si ya era una tabla, se convierte.
    """
    steps = parse_steps(steps_payload)
    newline = "\r\n" if "\r\n" in description else "\n"
    had_final_newline = description.endswith(("\n", "\r\n"))
    lines = description.splitlines()
    result: dict[str, Any] = {"section": "updated", "added": [], "updated": [], "rows_without_step": [], "format": "list" if as_list else "table"}

    bounds = _section_bounds(lines, STEPS_HEADING)
    if bounds is None:
        if not create:
            return {**result, "section": "missing", "changed": False, "progress": None, "description": description}
        new_lines = lines + ([""] if lines and lines[-1].strip() else []) + [STEPS_HEADING, *_new_section_body(steps, as_list)]
        result.update(section="created", added=[step.title for step in steps])
    else:
        start, end = bounds
        body = lines[start + 1:end]
        fenced = _fenced_line_flags(body)
        header_index = next(
            (index for index, line in enumerate(body[:-1]) if not fenced[index] and not fenced[index + 1] and line.startswith("|") and TABLE_SEPARATOR_REGEX.match(body[index + 1].rstrip())),
            None,
        )
        if header_index is not None and as_list:
            _table_to_nested_list(body, fenced, header_index)
            fenced = _fenced_line_flags(body)
            header_index = None
            result["converted_from"] = "table"
        list_indexes = [index for index, line in enumerate(body) if not fenced[index] and LIST_ROW_REGEX.match(line)]
        if header_index is not None:
            result["format"] = "table"
            states = _update_table(body, fenced, header_index, steps, result)
        elif list_indexes:
            result["format"] = "list"
            states = _update_list(body, list_indexes, steps, result)
        else:
            if as_list:
                flattened = [index for index, line in enumerate(body) if not fenced[index] and _is_flattened_table_line(line)]
                if flattened:
                    body = [line for index, line in enumerate(body) if index not in flattened]
                    fenced = _fenced_line_flags(body)
                    result["converted_from"] = "flattened-table"
            if any(line.strip() and not fenced[index] and not line.startswith(PROGRESS_PREFIX) for index, line in enumerate(body)):
                raise JiraTicketError(f"jira-ticket: la sección '{STEPS_HEADING}' no tiene tabla ni lista de pasos reconocibles", EXIT_UNRESOLVED)
            trailing = [""] if end < len(lines) else []
            body = _new_section_body(steps, as_list) + trailing
            result["added"] = [step.title for step in steps]
            states = [step.state for step in steps]
        progress = progress_line(states)
        fenced = _fenced_line_flags(body)
        progress_index = next((index for index, line in enumerate(body) if not fenced[index] and line.startswith(PROGRESS_PREFIX)), None)
        if progress_index is None:
            while body and not body[0].strip():
                body = body[1:]
            body = [progress, "", *body]
        elif body[progress_index] != progress:
            body[progress_index] = progress
        new_lines = lines[: start + 1] + body + lines[end:]
    new_description = newline.join(new_lines)
    if had_final_newline:
        new_description += newline
    progress_text = next((line for line in new_lines if line.startswith(PROGRESS_PREFIX)), None)
    return {**result, "changed": new_description != description, "progress": progress_text, "description": new_description}


# --- tracking sobre ADF ----------------------------------------------------


def _adf_status_cell(step: Step) -> list[dict[str, Any]]:
    """Emoji como texto (se lee en notificaciones y exports) más el lozenge de color con el nombre del estado."""
    state = STEP_STATES[step.state]
    return [adf.text_node(f"{state.emoji} "), adf.status_node(state.label, state.color)]


def _adf_row(step: Step, columns: list[str] | tuple[str, ...] = STEP_COLUMNS) -> dict[str, Any]:
    """Fila ADF del paso con las celdas en el orden de `columns`; una columna ajena queda con `—`."""
    values = {
        STEP_COLUMN: [adf.text_node(step.title)],
        STATUS_COLUMN: _adf_status_cell(step),
        NOTE_COLUMN: [adf.text_node(step.note or EMPTY_CELL)],
    }
    return adf.table_row([adf.table_cell(values.get(column, [adf.text_node(EMPTY_CELL)])) for column in columns])


def _adf_table(steps: list[Step]) -> dict[str, Any]:
    header = adf.table_row([adf.table_cell([adf.text_node(column)], header=True) for column in STEP_COLUMNS])
    return adf.table([header, *[_adf_row(step) for step in steps]])


def _adf_progress(states: list[str]) -> dict[str, Any]:
    return adf.paragraph([adf.strong_text(PROGRESS_LABEL), adf.text_node(progress_line(states)[len(PROGRESS_PREFIX):])])


def _adf_update_table(table: dict[str, Any], steps: list[Step], result: dict[str, Any]) -> list[str]:
    by_identity = {step_identity(step.title): step for step in steps}
    rows = table.get("content") or []
    columns = [adf.node_text(cell).strip() for cell in (rows[0].get("content") or [])] if rows else []
    step_column, status_column, note_column = _table_columns(columns)
    states: list[str] = []
    seen: set[str] = set()
    for row in rows[1:]:
        cells = row.get("content") or []
        if len(cells) <= max(step_column, status_column) or not adf.node_text(cells[step_column]).strip():
            continue
        title = adf.node_text(cells[step_column]).strip()
        identity = step_identity(title)
        seen.add(identity)
        current_status = adf.node_text(cells[status_column]).strip()
        previous_state = _state_of_cell(current_status)
        step = by_identity.get(identity)
        if step is None:
            result["rows_without_step"].append(title)
            states.append(previous_state or "todo")
            continue
        row_changed = False
        if current_status != step.status_cell:
            cells[status_column]["content"] = [adf.paragraph(_adf_status_cell(step))]
            row_changed = True
        if note_column is not None and len(cells) > note_column:
            note = _note_after(step, previous_state, adf.node_text(cells[note_column]).strip())
            if adf.node_text(cells[note_column]).strip() != note:
                cells[note_column]["content"] = [adf.paragraph([adf.text_node(note)])]
                row_changed = True
        if row_changed:
            result["updated"].append(step.title)
        states.append(step.state)
    for step in [step for step in steps if step_identity(step.title) not in seen]:
        rows.append(_adf_row(step, columns))
        result["added"].append(step.title)
        states.append(step.state)
    return states


def update_tracking_adf(description: dict[str, Any], steps_payload: Any, create: bool = False) -> dict[str, Any]:
    """Mismo contrato que `update_tracking` sobre una descripción ADF.

    Los nodos fuera de `Pasos` quedan idénticos. Dentro, solo cambian las celdas
    `Estado` y `Nota` de los pasos que cambiaron, las filas nuevas y el párrafo
    `Progreso`. Al crear la sección la separa del resto con un divisor.
    """
    steps = parse_steps(steps_payload)
    doc = copy.deepcopy(adf.ensure_document(description))
    content = doc["content"]
    heading = STEPS_HEADING.lstrip("# ")
    result: dict[str, Any] = {"section": "updated", "added": [], "updated": [], "rows_without_step": [], "format": "adf-table"}

    bounds = adf.section_bounds(content, heading)
    if bounds is None:
        if not create:
            return {**result, "section": "missing", "changed": False, "progress": None, "description": description}
        states = [step.state for step in steps]
        section = [adf.heading(adf.SECTION_HEADING_LEVEL, [adf.text_node(heading)]), _adf_progress(states), _adf_table(steps)]
        if content and content[-1].get("type") != "rule":
            section.insert(0, adf.rule())
        content.extend(section)
        result.update(section="created", added=[step.title for step in steps])
    else:
        start, end = bounds
        body = content[start + 1:end]
        table_index = next((index for index, node in enumerate(body) if node.get("type") == "table"), None)
        if table_index is not None:
            states = _adf_update_table(body[table_index], steps, result)
        elif all(node.get("type") == "rule" or (node.get("type") == "paragraph" and (not adf.node_text(node).strip() or adf.node_text(node).startswith(PROGRESS_LABEL))) for node in body):
            position = next((index + 1 for index, node in enumerate(body) if node.get("type") == "paragraph" and adf.node_text(node).startswith(PROGRESS_LABEL)), 0)
            body.insert(position, _adf_table(steps))
            result["added"] = [step.title for step in steps]
            states = [step.state for step in steps]
        else:
            raise JiraTicketError(f"jira-ticket: la sección '{heading}' no tiene tabla de pasos reconocible", EXIT_UNRESOLVED)
        progress = _adf_progress(states)
        progress_index = next((index for index, node in enumerate(body) if node.get("type") == "paragraph" and adf.node_text(node).startswith(PROGRESS_LABEL)), None)
        if progress_index is None:
            body.insert(0, progress)
        elif adf.node_text(body[progress_index]) != adf.node_text(progress):
            body[progress_index] = progress
        content[start + 1:end] = body
    return {**result, "changed": doc != description, "progress": progress_line(states), "description": doc}



# --- section ---------------------------------------------------------------


def update_section(description: Any, heading: str, markdown: str, before: str | None = None) -> dict[str, Any]:
    """Reescribe una sola sección (`## <heading>` hasta el siguiente heading de nivel 1 o 2) y deja igual el resto.

    Con descripción ADF, el contenido se compila desde Markdown enriquecido;
    con descripción Markdown se inserta tal cual. Si la sección no existe la
    crea antes de `before`, o al final. Con `markdown` vacío quita la sección.
    """
    if isinstance(description, dict):
        doc, action = adf.replace_section(description, heading, adf.markdown_to_nodes(markdown), before)
        return {"heading": heading, "action": action, "changed": action != "unchanged", "description": doc if action != "unchanged" else description}
    newline = "\r\n" if "\r\n" in description else "\n"
    had_final_newline = description.endswith(("\n", "\r\n"))
    lines = description.splitlines()
    body = markdown.strip("\r\n").splitlines()
    heading_line = f"## {heading}"
    bounds = _section_bounds(lines, heading_line)
    if not body:
        new_lines = lines if bounds is None else lines[: bounds[0]] + lines[bounds[1]:]
        while bounds is not None and bounds[1] >= len(lines) and new_lines and not new_lines[-1].strip():
            new_lines.pop()
        action = "unchanged" if bounds is None else "removed"
    elif bounds is not None:
        start, end = bounds
        new_lines = lines[: start + 1] + body + ([""] if end < len(lines) else []) + lines[end:]
        action = "unchanged" if new_lines == lines else "replaced"
    else:
        anchor = _section_bounds(lines, f"## {before}") if before else None
        if anchor is not None:
            new_lines = lines[: anchor[0]] + [heading_line, *body, ""] + lines[anchor[0]:]
        else:
            new_lines = lines + ([""] if lines and lines[-1].strip() else []) + [heading_line, *body]
        action = "created"
    new_description = newline.join(new_lines) + (newline if had_final_newline else "")
    return {"heading": heading, "action": action, "changed": action != "unchanged", "description": new_description if action != "unchanged" else description}


# --- dependency ------------------------------------------------------------
#
# Una dependencia por bloqueo es un issue link del tipo `<DEPENDENCY_LINK_TYPE>`
# (por defecto `Blocks`), el que el timeline de Jira dibuja como flecha entre
# barras. En la respuesta de `getJiraIssue` del issue bloqueado, cada link trae
# el otro issue como `inwardIssue` (el otro aplica la descripción outward sobre
# este: "BLOCKER blocks ESTE", que se lee "ESTE is blocked by BLOCKER") o como
# `outwardIssue` (al revés). La dirección se lee de ahí y no del nombre del tipo,
# porque cada sitio puede renombrar `inward`/`outward`.


def _link_type_entries(link_types_payload: Any) -> list[dict[str, Any]]:
    if isinstance(link_types_payload, dict):
        entries = link_types_payload.get("issueLinkTypes", link_types_payload.get("values"))
    else:
        entries = link_types_payload
    if not isinstance(entries, list):
        raise JiraTicketError("jira-ticket: dependency espera `link_types` como la respuesta de getIssueLinkTypes (lista o `issueLinkTypes`)")
    return [entry for entry in entries if isinstance(entry, dict)]


def resolve_link_type(link_types_payload: Any, wanted_name: str) -> dict[str, str]:
    """Busca el tipo de link configurado por nombre (sin distinguir mayúsculas) o por id."""
    wanted = wanted_name.strip().casefold()
    for entry in _link_type_entries(link_types_payload):
        if str(entry.get("name", "")).casefold() == wanted or str(entry.get("id", "")) == wanted_name.strip():
            return {"id": str(entry.get("id", "")), "name": str(entry.get("name")), "inward": str(entry.get("inward", "")), "outward": str(entry.get("outward", ""))}
    available = ", ".join(sorted(str(entry.get("name")) for entry in _link_type_entries(link_types_payload)))
    raise JiraTicketError(
        f"jira-ticket: el tipo de link '{wanted_name}' ({ENV_PREFIX}DEPENDENCY_LINK_TYPE) no existe en el sitio; tipos disponibles: {available or 'ninguno'}",
        EXIT_UNRESOLVED,
    )


def _issue_key(issue: Any) -> str | None:
    return issue.get("key") if isinstance(issue, dict) and isinstance(issue.get("key"), str) else None


def _status_category(issue: Any) -> str | None:
    fields = issue.get("fields") if isinstance(issue, dict) else None
    status = (fields or {}).get("status") if isinstance(fields, dict) else None
    category = (status or {}).get("statusCategory") if isinstance(status, dict) else None
    key = (category or {}).get("key") if isinstance(category, dict) else None
    return key if isinstance(key, str) else None


def existing_dependency_links(issue: Any, link_type: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Links del tipo de dependencia ya presentes en el issue, separados por dirección."""
    fields = issue.get("fields") if isinstance(issue, dict) else None
    links = (fields or {}).get("issuelinks") if isinstance(fields, dict) else None
    if not isinstance(links, list):
        raise JiraTicketError("jira-ticket: dependency espera `issue` como la respuesta de getJiraIssue con fields [\"issuelinks\"]")
    blocked_by: dict[str, Any] = {}
    blocks: dict[str, Any] = {}
    for link in links:
        if not isinstance(link, dict):
            continue
        link_kind = link.get("type") or {}
        if str(link_kind.get("name", "")).casefold() != link_type["name"].casefold() and str(link_kind.get("id", "")) != link_type["id"]:
            continue
        if _issue_key(link.get("inwardIssue")):
            blocked_by[link["inwardIssue"]["key"]] = {"link_id": link.get("id"), "status_category": _status_category(link["inwardIssue"])}
        elif _issue_key(link.get("outwardIssue")):
            blocks[link["outwardIssue"]["key"]] = {"link_id": link.get("id"), "status_category": _status_category(link["outwardIssue"])}
    return {"blocked_by": blocked_by, "blocks": blocks}


def _normalize_blockers(blockers: Any) -> list[dict[str, Any]]:
    if not isinstance(blockers, list):
        raise JiraTicketError("jira-ticket: dependency espera `blockers` como lista de keys o de issues de getJiraIssue")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for blocker in blockers:
        key = blocker if isinstance(blocker, str) else _issue_key(blocker)
        if key is None or not ISSUE_KEY_REGEX.match(key):
            raise JiraTicketError(f"jira-ticket: key de bloqueante inválida '{str(blocker)[:40]}', se espera PROYECTO-123")
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"key": key, "status_category": None if isinstance(blocker, str) else _status_category(blocker)})
    return normalized


def blocker_project_keys(config: Config) -> list[str]:
    config.require("PROJECT_KEY")
    return config.dependencies["blocker_project_keys"]


def plan_dependencies(payload: Any, blocked_key: str, config: Config) -> dict[str, Any]:
    """Qué links `is blocked by` crear sobre `blocked_key`, cuáles ya existen y cuáles se rechazan.

    Cada link a crear trae el payload de `createIssueLink`: `inwardIssue` es el
    bloqueante y `outwardIssue` el bloqueado. Nunca escribe en Jira.
    """
    if not ISSUE_KEY_REGEX.match(blocked_key):
        raise JiraTicketError(f"jira-ticket: key inválida '{blocked_key[:40]}', se espera PROYECTO-123")
    if not isinstance(payload, dict):
        raise JiraTicketError("jira-ticket: dependency espera por stdin un objeto con `issue`, `link_types` y `blockers`")
    link_type = resolve_link_type(payload.get("link_types"), config.get("DEPENDENCY_LINK_TYPE") or DEFAULT_SETTINGS["DEPENDENCY_LINK_TYPE"])
    existing = existing_dependency_links(payload.get("issue"), link_type)
    allowed_projects = blocker_project_keys(config)
    create: list[dict[str, Any]] = []
    already_linked: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for blocker in _normalize_blockers(payload.get("blockers", [])):
        key = blocker["key"]
        project = key.rsplit("-", 1)[0]
        if key == blocked_key:
            rejected.append({"key": key, "reason": "un issue no puede bloquearse a sí mismo"})
        elif project not in allowed_projects:
            rejected.append({"key": key, "reason": f"proyecto {project} fuera de {ENV_PREFIX}BLOCKER_PROJECT_KEYS ({', '.join(allowed_projects)})"})
        elif key in existing["blocks"]:
            rejected.append({"key": key, "reason": f"{blocked_key} ya bloquea a {key}; el link inverso crearía un ciclo"})
        elif key in existing["blocked_by"]:
            already_linked.append({"key": key, "status_category": existing["blocked_by"][key]["status_category"] or blocker["status_category"]})
        else:
            create.append(
                {
                    "key": key,
                    "status_category": blocker["status_category"],
                    "create_issue_link": {"type": link_type["name"], "inwardIssue": key, "outwardIssue": blocked_key},
                }
            )
    open_blockers = sorted(
        {item["key"] for item in [*create, *already_linked] if item["status_category"] not in (DONE_STATUS_CATEGORY, None)}
        | {key for key, info in existing["blocked_by"].items() if info["status_category"] not in (DONE_STATUS_CATEGORY, None)}
    )
    unknown_status = sorted(item["key"] for item in [*create, *already_linked] if item["status_category"] is None)
    return {
        "blocked": blocked_key,
        "link_type": link_type,
        "create": create,
        "already_linked": already_linked,
        "rejected": rejected,
        "open_blockers": open_blockers,
        "unknown_status": unknown_status,
        "is_blocked": bool(open_blockers),
    }


def verify_dependencies(payload: Any, blocked_key: str, config: Config) -> dict[str, Any]:
    """Relectura: cada bloqueante pedido aparece como `is blocked by` sobre `blocked_key`, sin links invertidos."""
    if not isinstance(payload, dict):
        raise JiraTicketError("jira-ticket: dependency verify espera por stdin un objeto con `issue`, `link_types` y `blockers`")
    link_type = resolve_link_type(payload.get("link_types"), config.get("DEPENDENCY_LINK_TYPE") or DEFAULT_SETTINGS["DEPENDENCY_LINK_TYPE"])
    existing = existing_dependency_links(payload.get("issue"), link_type)
    keys = [blocker["key"] for blocker in _normalize_blockers(payload.get("blockers", []))]
    linked = [key for key in keys if key in existing["blocked_by"]]
    inverted = [key for key in keys if key not in existing["blocked_by"] and key in existing["blocks"]]
    missing = [key for key in keys if key not in existing["blocked_by"] and key not in existing["blocks"]]
    return {"blocked": blocked_key, "link_type": link_type["name"], "linked": linked, "inverted": inverted, "missing": missing, "ok": not inverted and not missing}


# --- CLI -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jira-ticket", description="Helpers deterministas de la skill jira-ticket.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config", help="Muestra la configuración resuelta, su origen y lo que falta.")
    quarter_cmd = sub.add_parser("quarter", help="Quarter de una fecha; con --metadata (stdin) resuelve la opción del campo configurado.")
    quarter_cmd.add_argument("--date")
    quarter_cmd.add_argument("--metadata", action="store_true")
    sprint_cmd = sub.add_parser("sprint-pick", help="Elige el sprint activo desde una respuesta JQL por stdin.")
    sprint_cmd.add_argument("--date")
    repo_cmd = sub.add_parser("repo-id", help="repository_id del repositorio según JIRA_TICKET_REPO_ID_SOURCES.")
    repo_cmd.add_argument("--root", default=".")
    pr_cmd = sub.add_parser("pr-normalize", help="Normaliza PRs con gh (solo lectura).")
    pr_cmd.add_argument("prs", nargs="+")
    pr_cmd.add_argument("--root", default=".")
    backlink_cmd = sub.add_parser("backlink", help="Aplica o verifica el backlink PR→Jira sobre un body por stdin.")
    backlink_cmd.add_argument("action", choices=["apply", "verify"])
    backlink_cmd.add_argument("--key", required=True)
    tracking_cmd = sub.add_parser("tracking", help="Actualiza la tabla de pasos (`## Pasos`) de la descripción de una subtarea (stdin JSON: description y steps).")
    tracking_cmd.add_argument("--create", action="store_true", help="Crea la sección si la descripción no la tiene.")
    tracking_cmd.add_argument("--list", dest="as_list", action="store_true", help="Solo descripciones Markdown: deja los pasos como lista anidada en vez de tabla.")
    sub.add_parser("adf", help="Compila Markdown enriquecido (stdin) a un documento ADF.")
    sub.add_parser("plain", help="Convierte Markdown enriquecido (stdin) a Markdown plano, sin elementos que solo existen en ADF.")
    section_cmd = sub.add_parser("section", help="Reescribe una sola sección de una descripción (stdin JSON: description y markdown).")
    section_cmd.add_argument("--heading", required=True, help="Texto del heading de la sección, sin `##`.")
    section_cmd.add_argument("--before", help="Heading antes del cual crear la sección si no existe.")
    dependency_cmd = sub.add_parser("dependency", help="Planifica o verifica links de bloqueo sobre un issue (stdin JSON: issue, link_types y blockers).")
    dependency_cmd.add_argument("action", choices=["plan", "verify"])
    dependency_cmd.add_argument("--key", required=True, help="Key del issue bloqueado.")
    slim_cmd = sub.add_parser("slim", help="Reduce una respuesta grande de Jira (stdin) a los campos pedidos.")
    slim_cmd.add_argument("--fields", default="")
    return parser


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(environ)
        if args.command == "config":
            description = describe_config(config)
            emit(description)
            return EXIT_CONFIG if description["missing_required"] else EXIT_OK
        if args.command == "quarter":
            result = quarter_for(parse_date(args.date), config.get("QUARTER_FORMAT") or DEFAULT_SETTINGS["QUARTER_FORMAT"])
            if args.metadata:
                option = quarter_option(read_json_stdin(), config.require("QUARTER_FIELD"), result["quarters_value"])
                if option is None:
                    raise JiraTicketError(f"jira-ticket: no existe la opción {result['quarters_value']} en {config.require('QUARTER_FIELD')}", EXIT_UNRESOLVED)
                result["option"] = option
            emit(result)
        elif args.command == "sprint-pick":
            result = pick_sprint(read_json_stdin(), parse_date(args.date), config)
            emit(result)
            return EXIT_OK if result["status"] == "ok" else EXIT_UNRESOLVED
        elif args.command == "repo-id":
            emit(repository_id(pathlib.Path(args.root), config))
        elif args.command == "pr-normalize":
            root = pathlib.Path(args.root).resolve()
            if not root.is_dir():
                raise JiraTicketError(f"jira-ticket: pr-normalize --root '{args.root}' no es un directorio existente ({root})", EXIT_UNRESOLVED)
            local = repository_id(root, config)
            viewer = functools.partial(gh_pr_view, cwd=root)
            emit(normalize_prs(args.prs, local, current_repo_slug(root), config_list(config, "REPO_PREFIXES"), viewer))
        elif args.command == "backlink":
            body = sys.stdin.read()
            site_url = config.require("SITE_URL")
            if args.action == "apply":
                sys.stdout.write(apply_backlink(body, args.key, site_url))
            else:
                result = verify_backlink(body, args.key, site_url)
                emit(result)
                return EXIT_OK if result["canonical"] else EXIT_UNRESOLVED
        elif args.command == "tracking":
            payload = read_json_stdin()
            description = payload.get("description") if isinstance(payload, dict) else None
            if not isinstance(description, (str, dict)):
                raise JiraTicketError("jira-ticket: tracking espera por stdin un objeto con `description` (Markdown o documento ADF) y `steps` (lista)")
            if isinstance(description, dict):
                if args.as_list:
                    raise JiraTicketError("jira-ticket: tracking --list solo aplica a descripciones Markdown; en ADF los pasos son siempre una tabla")
                emit(update_tracking_adf(description, payload.get("steps", []), args.create))
            else:
                emit(update_tracking(description, payload.get("steps", []), args.create, args.as_list))
        elif args.command == "adf":
            emit(adf.markdown_to_document(sys.stdin.read()))
        elif args.command == "plain":
            sys.stdout.write(adf.markdown_to_plain(sys.stdin.read()))
        elif args.command == "section":
            payload = read_json_stdin()
            description = payload.get("description") if isinstance(payload, dict) else None
            if not isinstance(description, (str, dict)) or not isinstance(payload.get("markdown"), str):
                raise JiraTicketError("jira-ticket: section espera por stdin un objeto con `description` (Markdown o documento ADF) y `markdown` (contenido de la sección)")
            emit(update_section(description, args.heading, payload["markdown"], args.before))
        elif args.command == "dependency":
            payload = read_json_stdin()
            if args.action == "plan":
                emit(plan_dependencies(payload, args.key, config))
            else:
                result = verify_dependencies(payload, args.key, config)
                emit(result)
                return EXIT_OK if result["ok"] else EXIT_UNRESOLVED
        elif args.command == "slim":
            emit(slim(read_json_stdin(), [item.strip() for item in args.fields.split(",") if item.strip()]))
    except JiraTicketError as error:
        print(error, file=sys.stderr)
        return error.exit_code
    except adf.AdfError as error:
        print(error, file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


def configure_stdio() -> None:
    """Usa UTF-8 sin traducir fines de línea en stdin, stdout y stderr.

    En Windows la consola y las tuberías usan la code page local (por ejemplo
    cp1252), que no puede escribir el emoji del backlink, y el modo texto
    convierte `\\r\\n` y `\\n` entre sí. Sin esto, `backlink apply` falla o
    altera el estilo de fin de línea del body del PR.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding=STDIO_ENCODING, newline="")


if __name__ == "__main__":
    configure_stdio()
    sys.exit(main())
