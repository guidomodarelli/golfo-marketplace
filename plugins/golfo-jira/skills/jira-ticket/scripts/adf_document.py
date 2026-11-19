"""Documento ADF (Atlassian Document Format) de la skill jira-ticket.

Compila el Markdown enriquecido de `references/rich-format.md` a nodos ADF y
opera sobre secciones de un documento ADF ya existente. No conoce tickets ni
seguimiento: esa lógica vive en `jira-ticket.py`.
"""

from __future__ import annotations

import copy
import datetime as dt
import re
import uuid
from typing import Any

ADF_VERSION = 1
SECTION_HEADING_LEVEL = 2
PANEL_TYPES = {"INFO": "info", "NOTE": "note", "SUCCESS": "success", "WARNING": "warning", "ERROR": "error"}
DECISION_MARKER = "DECISION"
DECISION_STATE = "DECIDED"
PLAIN_CALLOUT_EMOJI = {"INFO": "ℹ️", "NOTE": "📝", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "🚫", DECISION_MARKER: "🧭"}
PLAIN_DECISION_TITLE = "Decisiones"
STATUS_COLORS = ("neutral", "purple", "blue", "red", "yellow", "green")
DEFAULT_STATUS_COLOR = "neutral"
MILLISECONDS_PER_SECOND = 1000
LIST_INDENT_WIDTH = 2
ERROR_EXCERPT_LENGTH = 40

HEADING_REGEX = re.compile(r"^(?P<marks>#{1,6}) (?P<text>.+?)\s*$")
RULE_REGEX = re.compile(r"^ {0,3}(-{3,}|\*{3,}|_{3,})\s*$")
FENCE_REGEX = re.compile(r"^(?P<fence>`{3,}|~{3,})(?P<language>[\w+-]*)\s*$")
QUOTE_REGEX = re.compile(r"^> ?(?P<text>.*)$")
CALLOUT_REGEX = re.compile(r"^\[!(?P<marker>[A-Z]+)\]\s*(?P<title>.*)$")
LIST_ITEM_REGEX = re.compile(r"^(?P<indent> *)(?P<marker>[-*]|\d+\.) (?P<text>.*)$")
TABLE_SEPARATOR_REGEX = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")
DETAILS_OPEN_REGEX = re.compile(r"^<details>\s*(?:<summary>(?P<title>.*?)</summary>)?\s*$")
SUMMARY_REGEX = re.compile(r"^<summary>(?P<title>.*?)</summary>\s*$")
DETAILS_CLOSE = "</details>"
BARE_URL_REGEX = re.compile(r"https?://\S+")
SMART_LINK_TYPES = ("inlineCard", "blockCard", "embedCard")
CODE_BLOCK_TYPE = "codeBlock"
CODE_MARK_TYPE = "code"
INLINE_TOKEN_REGEX = re.compile(
    r"(?P<code>`(?P<code_text>[^`]+)`)"
    r"|(?P<status>\{status:(?:(?P<status_color>[a-z]+):)?(?P<status_text>[^:}][^}]*)\})"
    r"|(?P<date>\{date:(?P<date_value>[0-9]{4}-[0-9]{2}-[0-9]{2})\})"
    r"|(?P<link>\[(?P<link_text>[^\]]+)\]\((?P<link_href>[^)\s]+)\))"
    r"|(?P<strong>\*\*(?P<strong_text>.+?)\*\*)"
    r"|(?P<em>(?<![\w*])_(?P<em_text>[^_]+)_(?!\w))"
)


class AdfError(ValueError):
    """Markdown enriquecido o documento ADF que no se puede procesar."""


# --- Nodos -----------------------------------------------------------------


def text_node(value: str, marks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": value}
    if marks:
        node["marks"] = marks
    return node


def strong_text(value: str) -> dict[str, Any]:
    return text_node(value, [{"type": "strong"}])


def link_text(value: str, href: str) -> dict[str, Any]:
    return text_node(value, [{"type": "link", "attrs": {"href": href}}])


def status_node(label: str, color: str) -> dict[str, Any]:
    if color not in STATUS_COLORS:
        raise AdfError(f"jira-ticket: color de status '{color[:ERROR_EXCERPT_LENGTH]}' inválido; se espera {', '.join(STATUS_COLORS)}")
    return {"type": "status", "attrs": {"text": label, "color": color}}


def date_node(iso_date: str) -> dict[str, Any]:
    try:
        day = dt.date.fromisoformat(iso_date)
    except ValueError as error:
        raise AdfError(f"jira-ticket: fecha '{iso_date[:ERROR_EXCERPT_LENGTH]}' inválida en {{date:...}}; se espera YYYY-MM-DD") from error
    midnight_utc = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
    return {"type": "date", "attrs": {"timestamp": str(int(midnight_utc.timestamp()) * MILLISECONDS_PER_SECOND)}}


def paragraph(inlines: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "paragraph", "content": inlines}


def heading(level: int, inlines: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "heading", "attrs": {"level": level}, "content": inlines}


def rule() -> dict[str, Any]:
    return {"type": "rule"}


def table_cell(inlines: list[dict[str, Any]], header: bool = False) -> dict[str, Any]:
    return {"type": "tableHeader" if header else "tableCell", "attrs": {}, "content": [paragraph(inlines)]}


def table_row(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "tableRow", "content": cells}


def table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "table", "attrs": {"isNumberColumnEnabled": False, "layout": "default"}, "content": rows}


def document(content: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": ADF_VERSION, "type": "doc", "content": content}


def ensure_document(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("type") != "doc" or not isinstance(value.get("content"), list):
        raise AdfError("jira-ticket: la descripción ADF debe ser un objeto `doc` con `content` como lista")
    return value


def node_text(node: dict[str, Any]) -> str:
    """Texto visible de un nodo: lo que una persona lee, sin marcas ni atributos."""
    node_type = node.get("type")
    attrs = node.get("attrs") or {}
    if node_type == "text":
        return str(node.get("text", ""))
    if node_type in ("status", "emoji", "mention"):
        return str(attrs.get("text", ""))
    if node_type == "date":
        timestamp = str(attrs.get("timestamp", ""))
        if not timestamp.isdigit():
            return ""
        return dt.datetime.fromtimestamp(int(timestamp) / MILLISECONDS_PER_SECOND, tz=dt.timezone.utc).date().isoformat()
    if node_type == "inlineCard":
        return str(attrs.get("url", ""))
    if node_type == "hardBreak":
        return "\n"
    return "".join(node_text(child) for child in node.get("content") or [])


# --- Markdown enriquecido → ADF --------------------------------------------


def parse_inline(source: str, marks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Convierte una línea a nodos inline: negrita, cursiva, código, links, `{status:}` y `{date:}`."""
    inherited = marks or []
    nodes: list[dict[str, Any]] = []
    position = 0
    for match in INLINE_TOKEN_REGEX.finditer(source):
        if match.start() > position:
            nodes.append(text_node(source[position:match.start()], list(inherited)))
        if match.group("code"):
            nodes.append(text_node(match.group("code_text"), [*inherited, {"type": "code"}]))
        elif match.group("status"):
            nodes.append(status_node(match.group("status_text").strip(), match.group("status_color") or DEFAULT_STATUS_COLOR))
        elif match.group("date"):
            nodes.append(date_node(match.group("date_value")))
        elif match.group("link"):
            nodes.append(text_node(match.group("link_text"), [*inherited, {"type": "link", "attrs": {"href": match.group("link_href")}}]))
        elif match.group("strong"):
            nodes.extend(parse_inline(match.group("strong_text"), [*inherited, {"type": "strong"}]))
        else:
            nodes.extend(parse_inline(match.group("em_text"), [*inherited, {"type": "em"}]))
        position = match.end()
    if position < len(source):
        nodes.append(text_node(source[position:], list(inherited)))
    return nodes


def _paragraph_from_lines(lines: list[str]) -> dict[str, Any]:
    inlines: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if index:
            inlines.append({"type": "hardBreak"})
        inlines.extend(parse_inline(line.strip()))
    return paragraph(inlines)


def _split_table_row(row: str) -> list[str]:
    stripped = row.strip()
    pipes = [index for index, char in enumerate(stripped) if char == "|" and (index == 0 or stripped[index - 1] != "\\")]
    return [stripped[pipes[position] + 1:pipes[position + 1]].strip().replace("\\|", "|") for position in range(len(pipes) - 1)]


def _table_from_lines(lines: list[str]) -> dict[str, Any]:
    rows = [table_row([table_cell(parse_inline(cell), header=True) for cell in _split_table_row(lines[0])])]
    rows.extend(table_row([table_cell(parse_inline(cell)) for cell in _split_table_row(line)]) for line in lines[2:])
    return table(rows)


def _list_from_items(items: list[tuple[int, bool, str]], start: int, indent: int) -> tuple[list[dict[str, Any]], int]:
    """Arma las listas de un nivel de indentación; una lista nueva empieza cuando cambia entre viñetas y números."""
    lists: list[dict[str, Any]] = []
    index = start
    while index < len(items) and items[index][0] >= indent:
        item_indent, ordered, item_text = items[index]
        if item_indent > indent:
            nested, index = _list_from_items(items, index, item_indent)
            if lists:
                lists[-1]["content"][-1]["content"].extend(nested)
            else:
                lists.extend(nested)
            continue
        list_type = "orderedList" if ordered else "bulletList"
        if not lists or lists[-1]["type"] != list_type:
            lists.append({"type": list_type, "attrs": {"order": 1}, "content": []} if ordered else {"type": list_type, "content": []})
        lists[-1]["content"].append({"type": "listItem", "content": [paragraph(parse_inline(item_text))]})
        index += 1
    return lists, index


def _decision_list(lines: list[str]) -> dict[str, Any]:
    decisions = [match.group("text") for line in lines if (match := LIST_ITEM_REGEX.match(line))] or [line.strip() for line in lines if line.strip()]
    if not decisions:
        raise AdfError("jira-ticket: el bloque [!DECISION] no tiene ninguna decisión")
    items = [
        {
            "type": "decisionItem",
            "attrs": {"localId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"jira-ticket:decision:{index}:{decision}")), "state": DECISION_STATE},
            "content": parse_inline(decision),
        }
        for index, decision in enumerate(decisions)
    ]
    return {"type": "decisionList", "attrs": {"localId": str(uuid.uuid5(uuid.NAMESPACE_URL, "jira-ticket:decisions:" + "|".join(decisions)))}, "content": items}


def _quote_block(lines: list[str]) -> dict[str, Any]:
    callout = CALLOUT_REGEX.match(lines[0].strip()) if lines else None
    if callout is None:
        return {"type": "blockquote", "content": _blocks(lines)}
    marker = callout.group("marker")
    body = lines[1:]
    if marker == DECISION_MARKER:
        return _decision_list(body)
    if marker not in PANEL_TYPES:
        raise AdfError(f"jira-ticket: bloque [!{marker[:ERROR_EXCERPT_LENGTH]}] desconocido; se espera {', '.join([*PANEL_TYPES, DECISION_MARKER])}")
    title = [paragraph([strong_text(callout.group("title"))])] if callout.group("title") else []
    content = title + _blocks(body)
    if not content:
        raise AdfError(f"jira-ticket: el panel [!{marker}] no tiene contenido")
    return {"type": "panel", "attrs": {"panelType": PANEL_TYPES[marker]}, "content": content}


def _starts_block(line: str, next_line: str | None) -> bool:
    return bool(
        HEADING_REGEX.match(line)
        or RULE_REGEX.match(line)
        or FENCE_REGEX.match(line)
        or QUOTE_REGEX.match(line)
        or LIST_ITEM_REGEX.match(line)
        or DETAILS_OPEN_REGEX.match(line)
        or (line.startswith("|") and next_line is not None and TABLE_SEPARATOR_REGEX.match(next_line.rstrip()))
    )


def _first_link(nodes: list[dict[str, Any]]) -> str | None:
    """Primer link de los nodos (marca `link`, smart link o URL suelta en el texto), o `None` si no hay.

    Una URL escrita como código (marca `code` o bloque de código) es un literal
    que Jira nunca vuelve clickeable, así que no cuenta como link.
    """
    for node in nodes:
        if node.get("type") == CODE_BLOCK_TYPE:
            continue
        if node.get("type") in SMART_LINK_TYPES:
            return str((node.get("attrs") or {}).get("url") or node.get("type"))
        marks = node.get("marks") or []
        for mark in marks:
            if mark.get("type") == "link":
                return str((mark.get("attrs") or {}).get("href") or node.get("text") or "")
        is_code_text = any(mark.get("type") == CODE_MARK_TYPE for mark in marks)
        if node.get("type") == "text" and not is_code_text and (bare := BARE_URL_REGEX.search(node.get("text") or "")):
            return bare.group(0)
        if found := _first_link(node.get("content") or []):
            return found
    return None


def _blocks(lines: list[str]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if not line.strip():
            index += 1
        elif fence := FENCE_REGEX.match(line):
            end = next((position for position in range(index + 1, len(lines)) if lines[position].strip() == fence.group("fence")), len(lines))
            code = "\n".join(lines[index + 1:end])
            attrs = {"language": fence.group("language")} if fence.group("language") else {}
            nodes.append({"type": "codeBlock", "attrs": attrs, "content": [text_node(code)] if code else []})
            index = end + 1
        elif opening := DETAILS_OPEN_REGEX.match(line):
            end = next((position for position in range(index + 1, len(lines)) if lines[position].strip() == DETAILS_CLOSE), None)
            if end is None:
                raise AdfError("jira-ticket: bloque <details> sin </details> de cierre")
            body = lines[index + 1:end]
            title = opening.group("title")
            if title is None and body and (summary := SUMMARY_REGEX.match(body[0].strip())):
                title, body = summary.group("title"), body[1:]
            content = _blocks(body)
            if not title or not content:
                raise AdfError("jira-ticket: un bloque <details> necesita <summary> con título y contenido")
            if link := _first_link(content):
                raise AdfError(
                    f"jira-ticket: el expand '{title.strip()[:ERROR_EXCERPT_LENGTH]}' contiene el link '{link[:ERROR_EXCERPT_LENGTH]}': "
                    "Jira no lo vuelve clickeable dentro de un expand; moverlo fuera del bloque <details>"
                )
            nodes.append({"type": "expand", "attrs": {"title": title.strip()}, "content": content})
            index = end + 1
        elif heading_match := HEADING_REGEX.match(line):
            nodes.append(heading(len(heading_match.group("marks")), parse_inline(heading_match.group("text"))))
            index += 1
        elif RULE_REGEX.match(line):
            nodes.append(rule())
            index += 1
        elif QUOTE_REGEX.match(line):
            end = index
            while end < len(lines) and QUOTE_REGEX.match(lines[end]):
                end += 1
            nodes.append(_quote_block([QUOTE_REGEX.match(quoted).group("text") for quoted in lines[index:end]]))
            index = end
        elif line.startswith("|") and next_line is not None and TABLE_SEPARATOR_REGEX.match(next_line.rstrip()):
            end = index + 2
            while end < len(lines) and lines[end].startswith("|"):
                end += 1
            nodes.append(_table_from_lines(lines[index:end]))
            index = end
        elif LIST_ITEM_REGEX.match(line):
            items: list[tuple[int, bool, str]] = []
            while index < len(lines):
                item = LIST_ITEM_REGEX.match(lines[index])
                if item is None:
                    following = next((position for position in range(index, len(lines)) if lines[position].strip()), None)
                    if lines[index].strip() or following is None or not LIST_ITEM_REGEX.match(lines[following]):
                        break
                    index = following
                    continue
                items.append((len(item.group("indent")) // LIST_INDENT_WIDTH, item.group("marker")[0].isdigit(), item.group("text")))
                index += 1
            consumed = 0
            while consumed < len(items):
                lists, consumed = _list_from_items(items, consumed, items[consumed][0])
                nodes.extend(lists)
        else:
            end = index + 1
            while end < len(lines) and lines[end].strip() and not _starts_block(lines[end], lines[end + 1] if end + 1 < len(lines) else None):
                end += 1
            nodes.append(_paragraph_from_lines(lines[index:end]))
            index = end
    return nodes


def markdown_to_nodes(markdown: str) -> list[dict[str, Any]]:
    return _blocks(markdown.splitlines())


def markdown_to_document(markdown: str) -> dict[str, Any]:
    return document(markdown_to_nodes(markdown))


# --- Markdown enriquecido → Markdown plano ----------------------------------

PLAIN_STATUS_REGEX = re.compile(r"\{status:(?:[a-z]+:)?(?P<text>[^:}][^}]*)\}")
PLAIN_DATE_REGEX = re.compile(r"\{date:(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\}")
PLAIN_CALLOUT_REGEX = re.compile(r"^> ?\[!(?P<marker>[A-Z]+)\]\s*(?P<title>.*)$")
PLAIN_DETAILS_REGEX = re.compile(r"^<details>\s*(?:<summary>(?P<title>.*?)</summary>)?\s*$")


def markdown_to_plain(markdown: str) -> str:
    """Mismo contenido sin elementos que solo existen en ADF, para escribir con `contentFormat: "markdown"`.

    Un panel queda como cita con emoji y título en negrita, un expand como
    título en negrita seguido de su contenido, y los status y fechas como
    texto. Los bloques de código no se tocan.
    """
    newline = "\r\n" if "\r\n" in markdown else "\n"
    plain: list[str] = []
    open_fence: str | None = None
    for line in markdown.splitlines():
        fence = FENCE_REGEX.match(line)
        if open_fence is not None or fence:
            if open_fence is None:
                open_fence = fence.group("fence")
            elif line.strip() == open_fence:
                open_fence = None
            plain.append(line)
            continue
        stripped = line.strip()
        if stripped == DETAILS_CLOSE:
            continue
        if (details := PLAIN_DETAILS_REGEX.match(stripped)) or (details := SUMMARY_REGEX.match(stripped)):
            if details.group("title"):
                plain.append(f"**{details.group('title').strip()}**")
            continue
        if callout := PLAIN_CALLOUT_REGEX.match(line):
            marker = callout.group("marker")
            if marker not in PLAIN_CALLOUT_EMOJI:
                raise AdfError(f"jira-ticket: bloque [!{marker[:ERROR_EXCERPT_LENGTH]}] desconocido; se espera {', '.join(PLAIN_CALLOUT_EMOJI)}")
            title = callout.group("title") or (PLAIN_DECISION_TITLE if marker == DECISION_MARKER else "")
            plain.append(f"> {PLAIN_CALLOUT_EMOJI[marker]} **{title}**" if title else f"> {PLAIN_CALLOUT_EMOJI[marker]}")
            continue
        plain.append(PLAIN_DATE_REGEX.sub(lambda match: match.group("date"), PLAIN_STATUS_REGEX.sub(lambda match: match.group("text").strip(), line)))
    return newline.join(plain) + (newline if markdown.endswith(("\n", "\r\n")) else "")


# --- Secciones -------------------------------------------------------------


def _is_section_heading(node: dict[str, Any]) -> bool:
    return node.get("type") == "heading" and int((node.get("attrs") or {}).get("level", 0)) <= SECTION_HEADING_LEVEL


def section_bounds(content: list[dict[str, Any]], heading_text: str) -> tuple[int, int] | None:
    """Índices (heading, fin) de la sección: desde su heading hasta el siguiente de nivel 1 o 2."""
    start = next((index for index, node in enumerate(content) if _is_section_heading(node) and node_text(node).strip() == heading_text), None)
    if start is None:
        return None
    end = next((index for index in range(start + 1, len(content)) if _is_section_heading(content[index])), len(content))
    return start, end


def replace_section(doc: dict[str, Any], heading_text: str, body: list[dict[str, Any]], before: str | None = None) -> tuple[dict[str, Any], str]:
    """Reemplaza el cuerpo de una sección, la crea (antes de `before`, o al final) o, con cuerpo vacío, la quita; el resto no cambia."""
    result = copy.deepcopy(ensure_document(doc))
    content = result["content"]
    bounds = section_bounds(content, heading_text)
    if not body:
        if bounds is None:
            return result, "unchanged"
        del content[bounds[0]:bounds[1]]
        return result, "removed"
    if bounds is not None:
        start, end = bounds
        if content[start + 1:end] == body:
            return result, "unchanged"
        content[start + 1:end] = body
        return result, "replaced"
    section = [heading(SECTION_HEADING_LEVEL, [text_node(heading_text)]), *body]
    anchor = section_bounds(content, before) if before else None
    insert_at = anchor[0] if anchor is not None else len(content)
    content[insert_at:insert_at] = section
    return result, "created"
