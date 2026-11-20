"""The Markdown shape of a file of atomic rules (references/atomic-rules.md, section 1), in one place.

agent_ready_rules.py reads the rules and their metadata with it, and review-cache.py splits a rule file
into the documents of the AI review with it, so both see the same rules, the same code blocks and the
same end of each rule. It lives next to the hooks because the projected hooks only have this folder.
"""

import re

MARKER = re.compile(r"^<!--\s*rule(?:\s+(?P<attributes>.*?))?\s*-->\s*$")
# A line that starts like a marker but does not close on its line, which the lint reports.
MARKER_LIKE = re.compile(r"^<!--\s*rule\b")
TOP_LEVEL_BULLET = re.compile(r"^(?:[-*+]|\d+[.)])\s+(?P<text>.*)$")
# A fence closes only with the character that opened it, at least as many times, and nothing after it.
FENCE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<rest>.*)$")
HEADING = re.compile(r"^(?P<level>#{1,6})(?:\s|$)")
FRONTMATTER_DELIMITER = "---"
INDENTATION = (" ", "\t")

BLOCK_TEXT = "text"
BLOCK_CODE = "code"
BLOCK_MARKER = "marker"


class Block:
    """A stretch of a rule file: a line of text, a line of a code block, or a marker with its rule.

    For a marker, ``marker`` is its match (None when it does not close on its line) and ``bullet`` the
    index of the bullet of its rule (None when no top-level bullet follows it); ``end`` is the index of
    the line after the block.
    """

    def __init__(self, kind, start, end, marker=None, bullet=None):
        self.kind = kind
        self.start = start
        self.end = end
        self.marker = marker
        self.bullet = bullet


def frontmatter_end(lines):
    """Index of the first line after a leading YAML frontmatter, or 0 without one."""
    if lines and lines[0].strip() == FRONTMATTER_DELIMITER:
        for index in range(1, len(lines)):
            if lines[index].strip() == FRONTMATTER_DELIMITER:
                return index + 1
    return 0


def rule_end(lines, bullet_index):
    """Index of the line after the rule whose bullet is at ``bullet_index``: its indented lines belong to
    it, and a blank line only when an indented line follows it."""
    cursor = bullet_index + 1
    while cursor < len(lines):
        current = lines[cursor]
        if current.strip() and current.startswith(INDENTATION):
            cursor += 1
            continue
        if not current.strip():
            following = cursor + 1
            while following < len(lines) and not lines[following].strip():
                following += 1
            if following < len(lines) and lines[following].startswith(INDENTATION):
                cursor = following
                continue
        break
    return cursor


def blocks(lines):
    """The blocks of the lines of a rule file after its frontmatter, in order."""
    index = frontmatter_end(lines)
    open_fence = None
    while index < len(lines):
        line = lines[index]
        fence = FENCE.match(line)
        if open_fence is None and fence and not (fence.group("fence")[0] == "`" and "`" in fence.group("rest")):
            open_fence = fence.group("fence")
            yield Block(BLOCK_CODE, index, index + 1)
            index += 1
            continue
        if open_fence is not None:
            if (fence and fence.group("fence")[0] == open_fence[0] and len(fence.group("fence")) >= len(open_fence)
                    and not fence.group("rest").strip()):
                open_fence = None
            yield Block(BLOCK_CODE, index, index + 1)
            index += 1
            continue
        marker = MARKER.match(line)
        if not marker and not MARKER_LIKE.match(line):
            yield Block(BLOCK_TEXT, index, index + 1)
            index += 1
            continue
        bullet = index + 1
        while bullet < len(lines) and not lines[bullet].strip():
            bullet += 1
        if not marker or bullet >= len(lines) or not TOP_LEVEL_BULLET.match(lines[bullet]):
            yield Block(BLOCK_MARKER, index, index + 1, marker, None)
            index += 1
            continue
        end = rule_end(lines, bullet)
        yield Block(BLOCK_MARKER, index, end, marker, bullet)
        index = end
