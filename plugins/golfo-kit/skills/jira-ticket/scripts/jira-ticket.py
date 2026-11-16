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

TRACKING_LEVELS = {
    "story": {"heading": "## Tareas", "title_column": "Tarea", "before_heading": "## Pull requests"},
    "epic": {"heading": "## Stories", "title_column": "Story", "before_heading": None},
}
STATUS_CATEGORY_EMOJI = {"new": "⬜", "indeterminate": "🔄", "done": "✅"}
BLOCKED_EMOJI = "🚫"
PROGRESS_PREFIX = "**Progreso:**"
EMPTY_SECTION_PLACEHOLDER_REGEX = re.compile(r"^_Sin [^_]+ todavía\._\s*$")
EMPTY_CELL = "—"
KEY_COLUMN = "Key"
STATUS_COLUMN = "Estado"
ASSIGNEE_COLUMN = "Responsable"
PR_COLUMN = "PR"
NOTE_COLUMN = "Nota"
SECTION_HEADING_REGEX = re.compile(r"^#{1,2} ")
TABLE_SEPARATOR_REGEX = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")
ROW_KEY_REGEX = re.compile(r"\[(?P<key>[A-Z][A-Z0-9]+-[0-9]+)\]")
LIST_ROW_REGEX = re.compile(r"^- (?P<emoji>\S+) \[(?P<key>[A-Z][A-Z0-9]+-[0-9]+)\]\([^)]*\) (?P<rest>.*)$")
LIST_FIELD_SEPARATOR = " · "
LIST_NOTE_PREFIX = "Nota: "
LIST_PR_REGEX = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+$")


@dataclass
class TrackedChild:
    """Hijo releído en Jira tal como lo necesita la tabla de seguimiento."""

    key: str
    summary: str
    status: str
    category: str
    assignee: str | None = None
    pr: str | None = None
    blocked: bool = False
    note: str | None = None

    @property
    def emoji(self) -> str:
        return BLOCKED_EMOJI if self.blocked else STATUS_CATEGORY_EMOJI[self.category]

    @property
    def status_cell(self) -> str:
        return f"{self.emoji} {self.status}"

    @property
    def note_text(self) -> str:
        return (self.note or EMPTY_CELL) if self.blocked else EMPTY_CELL


def _issue_number(key: str) -> int:
    return int(key.rsplit("-", 1)[1])


def parse_tracked_children(payload: Any) -> list[TrackedChild]:
    if not isinstance(payload, list):
        raise JiraTicketError("jira-ticket: tracking espera `children` como lista de hijos releídos en Jira")
    children: list[TrackedChild] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise JiraTicketError(f"jira-ticket: tracking children[{index}] no es un objeto")
        key = str(raw.get("key") or "")
        if not ISSUE_KEY_REGEX.match(key):
            raise JiraTicketError(f"jira-ticket: tracking children[{index}] tiene key inválida '{key[:30]}'")
        category = str(raw.get("category") or "")
        if category not in STATUS_CATEGORY_EMOJI:
            raise JiraTicketError(
                f"jira-ticket: tracking {key} tiene statusCategory '{category[:30]}'; se espera {', '.join(STATUS_CATEGORY_EMOJI)}",
                EXIT_UNRESOLVED,
            )
        for required in ("summary", "status"):
            if not raw.get(required):
                raise JiraTicketError(f"jira-ticket: tracking {key} no tiene `{required}`")
        children.append(
            TrackedChild(
                key=key,
                summary=str(raw["summary"]),
                status=str(raw["status"]),
                category=category,
                assignee=raw.get("assignee") or None,
                pr=raw.get("pr") or None,
                blocked=bool(raw.get("blocked")),
                note=raw.get("note") or None,
            )
        )
    keys = [child.key for child in children]
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    if duplicated:
        raise JiraTicketError(f"jira-ticket: tracking recibió hijos repetidos: {', '.join(duplicated)}")
    return sorted(children, key=lambda child: (child.key.rsplit("-", 1)[0], _issue_number(child.key)))


def _split_cells(row: str) -> list[tuple[int, int]]:
    """Posiciones (inicio, fin) del contenido de cada celda de una fila `| a | b |`, respetando `\\|`."""
    stripped_end = len(row.rstrip())
    pipes = [index for index, char in enumerate(row[:stripped_end]) if char == "|" and (index == 0 or row[index - 1] != "\\")]
    return [(pipes[position] + 1, pipes[position + 1]) for position in range(len(pipes) - 1)]


def _cell_values(row: str) -> list[str]:
    return [row[start:end].strip() for start, end in _split_cells(row)]


def progress_line(emojis: list[str]) -> str:
    total = len(emojis)
    counts = {emoji: emojis.count(emoji) for emoji in (*STATUS_CATEGORY_EMOJI.values(), BLOCKED_EMOJI)}
    parts = [
        f"{counts[STATUS_CATEGORY_EMOJI['done']]}/{total} {STATUS_CATEGORY_EMOJI['done']}",
        f"{counts[STATUS_CATEGORY_EMOJI['indeterminate']]} {STATUS_CATEGORY_EMOJI['indeterminate']}",
        f"{counts[STATUS_CATEGORY_EMOJI['new']]} {STATUS_CATEGORY_EMOJI['new']}",
    ]
    if counts[BLOCKED_EMOJI]:
        parts.append(f"{counts[BLOCKED_EMOJI]} {BLOCKED_EMOJI}")
    return f"{PROGRESS_PREFIX} {' · '.join(parts)}"


def _table_row(child: TrackedChild, columns: list[str], site_url: str) -> str:
    values = {
        KEY_COLUMN: f"[{child.key}]({browse_url(site_url, child.key)})",
        STATUS_COLUMN: child.status_cell,
        ASSIGNEE_COLUMN: child.assignee or EMPTY_CELL,
        PR_COLUMN: child.pr or EMPTY_CELL,
        NOTE_COLUMN: child.note_text,
    }
    title_columns = {level["title_column"] for level in TRACKING_LEVELS.values()}
    cells = [values.get(column, child.summary if column in title_columns else EMPTY_CELL) for column in columns]
    return "| " + " | ".join(_escape_cell(cell) for cell in cells) + " |"


def _escape_cell(value: str) -> str:
    """Escapa los `|` sin escapar para que el texto no parta la fila en otra celda."""
    return re.sub(r"(?<!\\)\|", r"\\|", value)


def _replace_cell(row: str, column: int, value: str) -> str:
    start, end = _split_cells(row)[column]
    return f"{row[:start]} {_escape_cell(value)} {row[end:]}"


@dataclass
class ListEntry:
    """Línea de la lista de respaldo: `<título> · <estado> · <responsable>[ · <PR>][ · Nota: <nota>]`.

    El título puede contener ` · `: los campos se leen desde la derecha, donde el
    PR y la nota se reconocen por su forma, así que el título es todo lo que queda.
    """

    summary: str
    status: str
    assignee: str
    pr: str | None
    note: str | None

    @classmethod
    def parse(cls, rest: str) -> "ListEntry | None":
        fields = rest.split(LIST_FIELD_SEPARATOR)
        note = fields.pop()[len(LIST_NOTE_PREFIX):] if fields and fields[-1].startswith(LIST_NOTE_PREFIX) else None
        pr = fields.pop() if fields and LIST_PR_REGEX.match(fields[-1]) else None
        if len(fields) < 3:
            return None
        assignee = fields.pop()
        status = fields.pop()
        return cls(LIST_FIELD_SEPARATOR.join(fields), status, assignee, pr, note)

    def render(self) -> str:
        fields = [self.summary, self.status, self.assignee]
        if self.pr:
            fields.append(self.pr)
        if self.note:
            fields.append(f"{LIST_NOTE_PREFIX}{self.note}")
        return LIST_FIELD_SEPARATOR.join(fields)


def _list_row(child: TrackedChild, site_url: str) -> str:
    note = child.note if child.blocked else None
    entry = ListEntry(child.summary, child.status, child.assignee or EMPTY_CELL, child.pr, note)
    return f"- {child.emoji} [{child.key}]({browse_url(site_url, child.key)}) {entry.render()}"


def _new_section_lines(level: str, children: list[TrackedChild], site_url: str) -> list[str]:
    columns = [KEY_COLUMN, TRACKING_LEVELS[level]["title_column"], STATUS_COLUMN, ASSIGNEE_COLUMN]
    if level == "story" and any(child.pr for child in children):
        columns.append(PR_COLUMN)
    columns.append(NOTE_COLUMN)
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join("---" for _ in columns) + "|"
    rows = [_table_row(child, columns, site_url) for child in children]
    return [TRACKING_LEVELS[level]["heading"], progress_line([child.emoji for child in children]), "", header, separator, *rows]


def _section_bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    fenced = _fenced_line_flags(lines)
    start = next((index for index, line in enumerate(lines) if not fenced[index] and line.rstrip() == heading), None)
    if start is None:
        return None
    end = next((index for index in range(start + 1, len(lines)) if not fenced[index] and SECTION_HEADING_REGEX.match(lines[index])), len(lines))
    return start, end


def _insert_column(body: list[str], first_row: int, last_row: int, position: int, name: str, values: list[str]) -> None:
    """Agrega una columna en `position` al header, al separador y a cada fila, sin tocar las otras celdas."""
    def insert(row: str, value: str) -> str:
        cells = _split_cells(row)
        cut = cells[position][0] if position < len(cells) else cells[-1][1] + 1
        return f"{row[:cut]} {value} |{row[cut:]}"

    body[first_row] = insert(body[first_row], name)
    body[first_row + 1] = insert(body[first_row + 1], "---").replace("| --- |", "|---|", 1)
    for index, value in zip(range(first_row + 2, last_row), values):
        body[index] = insert(body[index], _escape_cell(value))


def _update_table(body: list[str], fenced: list[bool], header_index: int, children: list[TrackedChild], level: str, site_url: str, result: dict[str, Any], heading: str) -> list[str]:
    by_key = {child.key: child for child in children}
    columns = _cell_values(body[header_index])
    if KEY_COLUMN not in columns or STATUS_COLUMN not in columns:
        raise JiraTicketError(f"jira-ticket: la tabla de '{heading}' no tiene columnas {KEY_COLUMN} y {STATUS_COLUMN}", EXIT_UNRESOLVED)
    table_end = header_index + 2
    while table_end < len(body) and not fenced[table_end] and body[table_end].startswith("|"):
        table_end += 1

    def row_key(index: int) -> str | None:
        cells = _cell_values(body[index])
        match = ROW_KEY_REGEX.search(cells[columns.index(KEY_COLUMN)]) if len(cells) > columns.index(KEY_COLUMN) else None
        return match.group("key") if match else None

    known_keys = {row_key(index) for index in range(header_index + 2, table_end)}
    if level == "story" and PR_COLUMN not in columns and any(child.pr for child in children if child.key not in known_keys):
        position = columns.index(NOTE_COLUMN) if NOTE_COLUMN in columns else len(columns)
        values = [(by_key[key].pr if (key := row_key(index)) in by_key and by_key[key].pr else EMPTY_CELL) for index in range(header_index + 2, table_end)]
        _insert_column(body, header_index, table_end, position, PR_COLUMN, values)
        columns = _cell_values(body[header_index])
        result["columns_added"] = [PR_COLUMN]
    status_column = columns.index(STATUS_COLUMN)
    note_column = columns.index(NOTE_COLUMN) if NOTE_COLUMN in columns else None

    row_indexes: list[int] = []
    row_keys: list[str] = []
    for index in range(header_index + 2, table_end):
        key = row_key(index)
        if key is None:
            continue
        row_indexes.append(index)
        row_keys.append(key)
        child = by_key.get(key)
        if child is None:
            result["rows_without_child"].append(key)
            continue
        row = body[index]
        cells = _cell_values(row)
        was_blocked = cells[status_column].startswith(BLOCKED_EMOJI)
        if cells[status_column] != child.status_cell:
            row = _replace_cell(row, status_column, child.status_cell)
        if note_column is not None and was_blocked != child.blocked:
            row = _replace_cell(row, note_column, child.note_text)
        if row != body[index]:
            body[index] = row
            result["updated"].append(key)
    for child in [child for child in children if child.key not in row_keys]:
        prefix = child.key.rsplit("-", 1)[0]
        later = [index for index, key in zip(row_indexes, row_keys) if key.rsplit("-", 1)[0] == prefix and _issue_number(key) > _issue_number(child.key)]
        insert_at = min(later) if later else table_end
        body.insert(insert_at, _table_row(child, columns, site_url))
        fenced.insert(insert_at, False)
        row_indexes = [index + 1 if index >= insert_at else index for index in row_indexes] + [insert_at]
        row_keys.append(child.key)
        table_end += 1
        result["added"].append(child.key)
    return [_cell_values(body[index])[status_column].split(" ", 1)[0] for index in row_indexes]


def _update_list(body: list[str], list_indexes: list[int], children: list[TrackedChild], site_url: str, result: dict[str, Any]) -> list[str]:
    by_key = {child.key: child for child in children}
    row_keys: list[str] = []
    emojis: list[str] = []
    for index in list_indexes:
        match = LIST_ROW_REGEX.match(body[index])
        key = match.group("key")
        row_keys.append(key)
        child = by_key.get(key)
        entry = ListEntry.parse(match.group("rest"))
        if child is None or entry is None:
            if child is None:
                result["rows_without_child"].append(key)
            else:
                raise JiraTicketError(f"jira-ticket: la línea de {key} en la lista de seguimiento no tiene título, estado y responsable", EXIT_UNRESOLVED)
            emojis.append(match.group("emoji"))
            continue
        was_blocked = match.group("emoji") == BLOCKED_EMOJI
        entry.status = child.status
        if was_blocked != child.blocked:
            entry.note = child.note if child.blocked else None
        line = f"{body[index][: match.start('emoji')]}{child.emoji}{body[index][match.end('emoji'): match.start('rest')]}{entry.render()}"
        if line != body[index]:
            body[index] = line
            result["updated"].append(key)
        emojis.append(child.emoji)
    last = list_indexes[-1]
    for child in [child for child in children if child.key not in row_keys]:
        body.insert(last + 1, _list_row(child, site_url))
        last += 1
        result["added"].append(child.key)
        emojis.append(child.emoji)
    return emojis


def update_tracking(description: str, children_payload: Any, level: str, site_url: str, create: bool = False) -> dict[str, Any]:
    """Actualiza solo la sección de seguimiento: estado de cada fila, filas nuevas y `Progreso`.

    Todo lo que está fuera de la sección queda idéntico byte a byte, y dentro de
    ella solo cambian la celda `Estado` (y `Nota` cuando un hijo se bloquea o se
    desbloquea) de los hijos que cambiaron, las filas que se insertan, la columna
    `PR` cuando un hijo nuevo la necesita y la línea `Progreso`. Los bloques de
    código de la sección se ignoran. Sin sección, la crea solo con `create`.
    """
    if level not in TRACKING_LEVELS:
        raise JiraTicketError(f"jira-ticket: tracking --level debe ser {' o '.join(TRACKING_LEVELS)}")
    children = parse_tracked_children(children_payload)
    newline = "\r\n" if "\r\n" in description else "\n"
    had_final_newline = description.endswith(("\n", "\r\n"))
    lines = description.splitlines()
    heading = TRACKING_LEVELS[level]["heading"]
    result: dict[str, Any] = {"level": level, "section": "updated", "added": [], "updated": [], "rows_without_child": [], "format": "table"}

    bounds = _section_bounds(lines, heading)
    if bounds is None:
        if not create:
            return {**result, "section": "missing", "changed": False, "description": description}
        section = _new_section_lines(level, children, site_url)
        before = TRACKING_LEVELS[level]["before_heading"]
        anchor = _section_bounds(lines, before) if before else None
        if anchor is not None:
            new_lines = lines[: anchor[0]] + section + [""] + lines[anchor[0]:]
        else:
            new_lines = lines + ([""] if lines and lines[-1].strip() else []) + section
        result.update(section="created", added=[child.key for child in children])
    else:
        start, end = bounds
        body = lines[start + 1:end]
        fenced = _fenced_line_flags(body)
        header_index = next(
            (index for index, line in enumerate(body[:-1]) if not fenced[index] and not fenced[index + 1] and line.startswith("|") and TABLE_SEPARATOR_REGEX.match(body[index + 1].rstrip())),
            None,
        )
        list_indexes = [index for index, line in enumerate(body) if not fenced[index] and LIST_ROW_REGEX.match(line)]
        if header_index is not None:
            emojis = _update_table(body, fenced, header_index, children, level, site_url, result, heading)
        elif list_indexes:
            result["format"] = "list"
            emojis = _update_list(body, list_indexes, children, site_url, result)
        else:
            placeholder = next((index for index, line in enumerate(body) if not fenced[index] and EMPTY_SECTION_PLACEHOLDER_REGEX.match(line.strip())), None)
            if placeholder is None and any(line.strip() and not fenced[index] and not line.startswith(PROGRESS_PREFIX) for index, line in enumerate(body)):
                raise JiraTicketError(f"jira-ticket: la sección '{heading}' no tiene tabla ni lista de seguimiento reconocibles", EXIT_UNRESOLVED)
            table = _new_section_lines(level, children, site_url)[3:]
            if placeholder is not None:
                body[placeholder:placeholder + 1] = table
            else:
                body = [line for line in body if not line.startswith(PROGRESS_PREFIX)]
                body = ([""] if not body or body[0].strip() else []) + table + body
            result["added"] = [child.key for child in children]
            emojis = [child.emoji for child in children]
        progress = progress_line(emojis)
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
    tracking_cmd = sub.add_parser("tracking", help="Actualiza la sección de seguimiento de una descripción (stdin JSON: description y children).")
    tracking_cmd.add_argument("--level", required=True, choices=sorted(TRACKING_LEVELS))
    tracking_cmd.add_argument("--create", action="store_true", help="Crea la sección si la descripción no la tiene.")
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
            if not isinstance(payload, dict) or not isinstance(payload.get("description"), str):
                raise JiraTicketError("jira-ticket: tracking espera por stdin un objeto con `description` (texto) y `children` (lista)")
            emit(update_tracking(payload["description"], payload.get("children", []), args.level, config.require("SITE_URL"), args.create))
        elif args.command == "slim":
            emit(slim(read_json_stdin(), [item.strip() for item in args.fields.split(",") if item.strip()]))
    except JiraTicketError as error:
        print(error, file=sys.stderr)
        return error.exit_code
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
