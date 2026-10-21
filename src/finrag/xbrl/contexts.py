"""XBRL contexts from a filing: period dates and dimension members."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import lxml.etree as ET

from finrag.xbrl.periods import parse_date


@dataclass(frozen=True)
class Context:
    """One xbrli:context."""

    context_id: str
    start: str | None
    end: str | None
    instant: str | None
    dimensions: tuple[tuple[str, str], ...]

    @property
    def has_dimensions(self) -> bool:
        """True when the fact is broken out by a member, such as a segment."""
        return bool(self.dimensions)

    @property
    def period_end(self) -> str | None:
        """Instant date, or the end of a duration."""
        return self.instant or self.end


def parse_contexts(html: str) -> dict[str, Context]:
    """Read every context in the filing, keyed by its id."""
    root = ET.fromstring(html.encode("utf-8"), ET.XMLParser(huge_tree=True))
    found: dict[str, Context] = {}
    for node in root.iter():
        if ET.QName(node).localname != "context":
            continue
        context_id = node.get("id")
        if not context_id:
            continue
        start = _child_text(node, "startDate")
        end = _child_text(node, "endDate")
        instant = _child_text(node, "instant")
        dimensions = tuple(_members(node))
        found[context_id] = Context(context_id, start, end, instant, dimensions)
    return found


def _child_text(node: ET._Element, name: str) -> str | None:
    for child in node.iter():
        if ET.QName(child).localname == name and child.text:
            return child.text.strip()
    return None


def _members(node: ET._Element) -> list[tuple[str, str]]:
    members: list[tuple[str, str]] = []
    for child in node.iter():
        local = ET.QName(child).localname
        if local not in {"explicitMember", "typedMember"}:
            continue
        dimension = child.get("dimension") or ""
        member = "".join(child.itertext()).strip()
        if dimension and member:
            members.append((dimension, member))
    return members


def header_date(cells: list[str]) -> date | None:
    """The period date written in a column header, if the header has one."""
    pattern = re.compile(
        r"(?i)\b("
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?"
        r")\.?\s+(\d{1,2}),\s+(20\d{2})\b"
    )
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    found = _last_date(pattern, months, cells)
    if found is not None:
        return found
    joined = " ".join(cell for cell in cells if cell)
    if not joined:
        return None
    return _last_date(pattern, months, [joined])


def _last_date(
    pattern: re.Pattern[str], months: dict[str, int], cells: list[str]
) -> date | None:
    found = None
    for text in cells:
        for match in pattern.finditer(text):
            month = months[match.group(1)[:3].lower()]
            found = parse_date(
                f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(2)):02d}"
            )
    return found
