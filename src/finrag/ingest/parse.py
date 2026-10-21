"""Turn a 10-K XHTML filing into headings, paragraphs, and tables."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass

import lxml.etree as ET

_XHTML = "http://www.w3.org/1999/xhtml"
_SKIP_TAGS = {"header", "hidden", "script", "style"}
_ITEM_RE = re.compile(r"(?i)^item\s+(\d+[a-z]?)\b\.?\s*(.*)$")
_UNITS_RE = re.compile(
    r"(?ix)"
    r"(?:"
    r"\(?\s*(?:(?:\$|dollars)\s+)?"
    r"in\s+(?:thousands|millions|billions)"
    r"(?!\s+of\s+(?:u\.s\.\s+)?dollars)"
    r"(?:\s*,?\s*except\s+[^)]{0,80})?"
    r"\s*\)?"
    r"|"
    r"(?:thousands|millions|billions)\s+of\s+(?:u\.s\.\s+)?dollars"
    r")"
)
_MONEY_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
_NOT_FINANCIAL_RE = re.compile(
    r"(?i)sq\.?\s*ft|square feet|trading symbol|title of each class|defined terms|"
    r"shares of common stock to be sold|shares purchased|"
    r"\$\s*100 invested"
)
_HIDDEN_BLOCK_RE = re.compile(
    r"<!--.*?-->"
    r"|<(?:ix:)?header\b[^>]*>.*?</(?:ix:)?header>"
    r"|<(?:ix:)?hidden\b[^>]*>.*?</(?:ix:)?hidden>"
    r"|<script\b[^>]*>.*?</script>"
    r"|<style\b[^>]*>.*?</style>",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_PER_SHARE_RE = re.compile(r"(?i)per[\s-]share")
_UNIT_PHRASE_RE = re.compile(
    r"(?i)(?:in\s+(?:thousands|millions|billions)|per[\s-]share|\bpercent\b|%)"
)
_NEGATIVE_RE = re.compile(
    r"^(?:\$?\(\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)|\-\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?)$"
)


@dataclass(frozen=True)
class FilingMeta:
    """Identity fields copied onto every parsed element."""

    ticker: str
    cik: str
    accession_number: str
    fiscal_year: int
    period_end: str


def raw_html_text(html: str) -> str:
    """Return the filing's text with tags removed.

    Tags are deleted rather than replaced with spaces, and a line break becomes
    a space. Comments, the XBRL header, hidden facts, scripts, and styles are
    removed first. This does not use the parser's cell or block walker.
    """
    without_hidden = _HIDDEN_BLOCK_RE.sub(" ", html)
    with_breaks = re.sub(r"(?i)<br\s*/?>", " ", without_hidden)
    without_tags = _TAG_RE.sub("", with_breaks)
    unescaped = html_lib.unescape(without_tags).replace("\xa0", " ")
    return " ".join(unescaped.split())


def word_count(text: str) -> int:
    """Count whitespace-separated words."""
    return len(text.split()) if text else 0


def alphanumeric_count(text: str) -> int:
    """Count letters and digits, ignoring punctuation and split differences."""
    return sum(character.isalnum() for character in text)


def parse_filing(html: str, meta: FilingMeta) -> list[dict]:
    """Parse one 10-K document into ordered elements."""
    root = ET.fromstring(html.encode("utf-8"), ET.XMLParser(huge_tree=True))
    body = next(element for element in root.iter() if _local(element) == "body")
    elements: list[dict] = []
    heading_path: list[str] = []
    item: str | None = None
    section_role: str | None = None
    recent_blocks: list[str] = []
    current_units: str | None = None
    for child in body:
        if _skipped(child):
            continue
        tables = _outer_tables(child)
        if tables:
            caption = _text_outside_tables(child)
            if caption:
                kind, item, heading_path = _classify(caption, child, item, heading_path)
                section_role = _next_section_role(caption, section_role)
                elements.append(
                    _element(
                        meta,
                        len(elements),
                        kind,
                        item,
                        heading_path,
                        text=caption,
                        section_role=section_role,
                    )
                )
            for table in tables:
                rows, row_facts = table_cells(table)
                if not rows:
                    continue
                grid = collapse_grid(rows)
                facts = collapse_facts(rows, row_facts)
                units, units_source = resolve_units(
                    caption, recent_blocks, grid, current_units
                )
                if units and units_source != "fallback":
                    current_units = units
                elements.append(
                    _element(
                        meta,
                        len(elements),
                        "table",
                        item,
                        heading_path,
                        text=_flat(grid),
                        rows=rows,
                        grid=grid,
                        row_facts=row_facts,
                        facts=facts,
                        markdown=rows_to_markdown(grid),
                        units=units,
                        units_source=units_source,
                        section_role=section_role,
                        column_units=column_units(grid),
                    )
                )
            if caption:
                recent_blocks.append(caption)
                statement = units_statement(caption)
                if statement:
                    current_units = statement
            continue
        block = _visible_text(child)
        if not block:
            continue
        recent_blocks.append(block)
        statement = units_statement(block)
        if statement:
            current_units = statement
        kind, item, heading_path = _classify(block, child, item, heading_path)
        section_role = _next_section_role(block, section_role)
        elements.append(
            _element(
                meta,
                len(elements),
                kind,
                item,
                heading_path,
                text=block,
                section_role=section_role,
            )
        )
    return elements


def table_rows(table: ET._Element) -> list[list[str]]:
    """Return a rectangular grid whose columns follow colspan.

    Spacer columns that never start a visible cell are removed. A merged
    header is repeated across every logical column it covers, and an empty
    data cell stays in the grid so each row has the same width.
    """
    rows, _facts = table_cells(table)
    return rows


def table_cells(
    table: ET._Element,
) -> tuple[list[list[str]], list[list[list[dict]]]]:
    """Return the logical grid and the inline facts that start in each cell."""
    matrix, starts, fact_matrix = _cell_matrix(table)
    if not matrix or not starts:
        return [], []
    boundaries = sorted(starts)
    max_col = len(matrix[0])
    ranges = [
        (start, boundaries[index + 1] if index + 1 < len(boundaries) else max_col)
        for index, start in enumerate(boundaries)
    ]
    paired = [
        (
            _row_values(matrix[row_index], ranges),
            _row_facts(fact_matrix[row_index], ranges),
        )
        for row_index in range(len(matrix))
    ]
    kept = [(row, facts) for row, facts in paired if any(row)]
    if not kept:
        return [], []
    rows, facts = zip(*kept, strict=True)
    return list(rows), list(facts)


def rows_are_aligned(rows: list[list[str]]) -> bool:
    """True when every row has the same number of logical columns."""
    if not rows:
        return True
    width = len(rows[0])
    return all(len(row) == width for row in rows)


def collapse_grid(rows: list[list[str]]) -> list[list[str]]:
    """One column per header period.

    A ``$`` or ``%`` sub-column is joined into the amount, and a colspan that
    repeated the same text is kept once. ``rows`` stays the wider logical grid.
    """
    return _merge_money_columns(rows) if rows else []


def collapse_facts(
    rows: list[list[str]], facts: list[list[list[dict]]]
) -> list[list[list[dict]]]:
    """Carry inline facts onto the collapsed grid, in the same column grouping."""
    if not rows:
        return []
    mask = _merge_mask(rows)
    collapsed: list[list[list[dict]]] = []
    for row, row_facts in zip(rows, facts, strict=True):
        cells: list[list[dict]] = []
        column = 0
        while column < len(row):
            if column < len(mask) and mask[column]:
                cells.append([*row_facts[column], *row_facts[column + 1]])
                column += 2
            else:
                cells.append(list(row_facts[column]))
                column += 1
        collapsed.append(cells)
    return collapsed


def expand_grid(grid: list[list[str]], rows: list[list[str]]) -> list[list[str]]:
    """Place each collapsed cell back on the logical columns it came from.

    ``rows`` supplies only the grouping. The values come from ``grid``, in
    order: a joined amount splits into the symbol and the number, and a
    repeated span is copied onto each logical column.
    """
    if not rows:
        return []
    mask = _merge_mask(rows)
    expanded: list[list[str]] = []
    for grid_row, raw_row in zip(grid, rows, strict=True):
        cells: list[str] = []
        grid_index = 0
        column = 0
        while column < len(raw_row):
            if column < len(mask) and mask[column]:
                left, right = _split_joined(
                    grid_row[grid_index], raw_row[column], raw_row[column + 1]
                )
                cells.extend((left, right))
                column += 2
            else:
                cells.append(grid_row[grid_index])
                column += 1
            grid_index += 1
        expanded.append(cells)
    return expanded


def rows_to_markdown(rows: list[list[str]]) -> str:
    """Render a collapsed grid as a markdown table."""
    if not rows:
        return ""
    display = rows
    width = max(len(row) for row in display)

    def line(cells: list[str]) -> str:
        padded = cells + [""] * (width - len(cells))
        return "| " + " | ".join(cell.replace("|", "\\|") for cell in padded) + " |"

    header = line(display[0])
    rule = "| " + " | ".join("---" for _ in range(width)) + " |"
    body = [line(row) for row in display[1:]]
    return "\n".join([header, rule, *body])


def column_units(rows: list[list[str]]) -> list[str | None]:
    """Unit phrase on each collapsed column, taken from the header rows."""
    if not rows:
        return []
    data_at = _first_amount_row(rows)
    width = len(rows[0])
    found: list[str | None] = []
    for column in range(width):
        blob = " ".join(
            rows[row][column] for row in range(data_at) if rows[row][column]
        )
        found.append(_header_unit(blob))
    return found


def _cell_matrix(
    table: ET._Element,
) -> tuple[list[list[str]], set[int], list[list[list[dict]]]]:
    """Fill a colspan/rowspan grid and record columns where visible text starts."""
    raw_rows: list[list[tuple[str, list[dict], int, int]]] = []
    for row in table:
        if _local(row) != "tr" or _skipped(row):
            continue
        cells: list[tuple[str, list[dict], int, int]] = []
        for cell in row:
            if _local(cell) not in {"td", "th"} or _skipped(cell):
                continue
            span = int(cell.get("colspan") or 1)
            down = int(cell.get("rowspan") or 1)
            cells.append((_visible_text(cell), _inline_facts(cell), span, down))
        raw_rows.append(cells)
    occupied: set[tuple[int, int]] = set()
    values: dict[tuple[int, int], str] = {}
    fact_at: dict[tuple[int, int], list[dict]] = {}
    starts: set[int] = set()
    row_index = 0
    max_col = 0
    for cells in raw_rows:
        column = 0
        for text, facts, span, down in cells:
            while (row_index, column) in occupied:
                column += 1
            if text:
                starts.add(column)
            for down_offset in range(down):
                for across in range(span):
                    occupied.add((row_index + down_offset, column + across))
                    values[(row_index + down_offset, column + across)] = text
                    max_col = max(max_col, column + across + 1)
            fact_at[(row_index, column)] = facts
            column += span
        row_index += 1
    if row_index == 0 or max_col == 0:
        return [], set(), []
    matrix = [
        [values.get((row, column), "") for column in range(max_col)]
        for row in range(row_index)
    ]
    fact_matrix = [
        [fact_at.get((row, column), []) for column in range(max_col)]
        for row in range(row_index)
    ]
    return matrix, starts, fact_matrix


def _row_values(row: list[str], ranges: list[tuple[int, int]]) -> list[str]:
    return [row[start] if start < len(row) else "" for start, _end in ranges]


def _row_facts(
    row: list[list[dict]], ranges: list[tuple[int, int]]
) -> list[list[dict]]:
    return [list(row[start]) if start < len(row) else [] for start, _end in ranges]


def _inline_facts(cell: ET._Element) -> list[dict]:
    """Inline nonFraction attributes on a cell. The text stays in the grid."""
    facts: list[dict] = []
    for node in cell.iter():
        if _local(node) != "nonFraction" or _skipped(node):
            continue
        scale_text = node.get("scale")
        scale = int(scale_text) if scale_text and _is_int(scale_text) else None
        facts.append(
            {
                "name": node.get("name"),
                "context_ref": node.get("contextRef"),
                "scale": scale,
                "sign": node.get("sign"),
                "decimals": node.get("decimals"),
                "unit_ref": node.get("unitRef"),
                "fact_id": node.get("id"),
                "text": _visible_text(node),
            }
        )
    return facts


def _is_int(text: str) -> bool:
    return text.lstrip("-").isdigit() and text not in {"", "-"}


def _first_amount_row(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows):
        if any(_is_amount_cell(cell) for cell in row):
            return index
    return len(rows)


def _is_amount_cell(text: str) -> bool:
    token = text.strip()
    if not token or re.fullmatch(r"20\d{2}", token):
        return False
    return (
        re.fullmatch(
            r"\$?\(?\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?|\$?\(?\d+\.\d+\)?%?",
            token,
        )
        is not None
    )


def _header_unit(text: str) -> str | None:
    if not text:
        return None
    found: list[str] = []
    for phrase in (
        "in billions",
        "in millions",
        "in thousands",
        "per share",
        "percent",
    ):
        if re.search(phrase, text, re.IGNORECASE):
            found.append(phrase)
    if "%" in text and "percent" not in found:
        found.append("percent")
    if not found:
        return None
    return ", ".join(found)


def _merge_mask(rows: list[list[str]]) -> list[bool]:
    """True when a logical column is joined into the following one."""
    if not rows:
        return []
    width = len(rows[0])
    mask = [False] * width
    for column in range(width - 1):
        if all(_money_pair(row[column], row[column + 1]) for row in rows):
            mask[column] = True
    return mask


def _merge_money_columns(rows: list[list[str]]) -> list[list[str]]:
    """Join a $ or % column into the adjacent amount in every row."""
    if not rows:
        return rows
    width = len(rows[0])
    merge_with_next = _merge_mask(rows)
    merged: list[list[str]] = []
    for row in rows:
        cells: list[str] = []
        column = 0
        while column < len(row):
            if column < width and merge_with_next[column]:
                cells.append(_join_money(row[column], row[column + 1]))
                column += 2
                continue
            cells.append(row[column])
            column += 1
        merged.append(cells)
    return merged


def _money_pair(left: str, right: str) -> bool:
    if left == "$":
        return True
    if right == "%":
        return True
    return left == right


def _split_joined(joined: str, left: str, right: str) -> tuple[str, str]:
    """Undo ``_join_money`` using the grouping from the logical row."""
    if left == "$":
        if not right:
            return "$", ""
        return "$", joined.removeprefix("$")
    if right == "%":
        if not left:
            return "", "%"
        return joined.removesuffix("%"), "%"
    return joined, joined


def _join_money(left: str, right: str) -> str:
    if left == "$":
        return f"${right}" if right else "$"
    if right == "%":
        return f"{left}%" if left else "%"
    return left


def _next_section_role(text: str, current: str | None) -> str | None:
    """Map a heading onto a role that is the same for every company."""
    if len(text) > 220 and not _ITEM_RE.match(text):
        return current
    if re.match(r"(?i)^item\s+1a\b", text):
        return "risk_factors"
    if re.match(r"(?i)^item\s+7a\b", text):
        return "other"
    if re.match(r"(?i)^item\s+7\b", text):
        return "mdna"
    if re.match(r"(?i)^item\s+8\b", text):
        return "financial_statements"
    if re.match(r"(?i)^item\s+1\b", text):
        if re.search(r"(?i)financial statement", text):
            return "financial_statements"
        return "business"
    if re.match(r"(?i)^item\s+\d", text):
        return "other"
    if re.match(
        r"(?i)^(notes to (the )?(consolidated )?financial statements|note \d+\b)",
        text,
    ) and current in {"financial_statements", "notes", "other"}:
        return "notes"
    if re.match(
        r"(?i)^(consolidated )?(statements of |statement of |balance sheets)",
        text,
    ) and current not in {"mdna", "risk_factors", "business"}:
        return "financial_statements"
    return current


def units_statement(text: str) -> str | None:
    """Return a units caption when the block is the statement, not a narrative aside."""
    if len(text) > 320 or not _UNITS_RE.search(text):
        return None
    if len(text) <= 180:
        match = _UNITS_RE.search(text)
        return _clean_units(match.group(0)) if match else None
    if re.search(
        r"(?i)amounts?.{0,40}(?:stated in|in millions|in thousands)|dollars in millions",
        text,
    ):
        match = _UNITS_RE.search(text)
        return _clean_units(match.group(0)) if match else None
    return None


def resolve_units(
    caption: str,
    preceding: list[str],
    rows: list[list[str]],
    current_units: str | None,
) -> tuple[str | None, str | None]:
    """Pick the units string and name the place it was found.

    Order is caption, then the previous eight blocks, then the table text,
    then the filing-wide fallback for a table that contains a dollar sign.
    """
    if caption:
        statement = units_statement(caption)
        if statement:
            return statement, "caption"
    for text in reversed(preceding[-8:]):
        statement = units_statement(text)
        if statement:
            return statement, "preceding"
    match = _UNITS_RE.search(_flat(rows))
    if match:
        return _clean_units(match.group(0)), "table_text"
    if current_units and _has_dollar(rows):
        return current_units, "fallback"
    return None, None


def table_markup(html: str) -> list[str]:
    """Return the raw HTML of each table `parse_filing` emits, in that order."""
    root = ET.fromstring(html.encode("utf-8"), ET.XMLParser(huge_tree=True))
    body = next(element for element in root.iter() if _local(element) == "body")
    markup: list[str] = []
    for child in body:
        if _skipped(child):
            continue
        for table in _outer_tables(child):
            if table_rows(table):
                markup.append(ET.tostring(table, encoding=str))
    return markup


def is_per_share_table(rows: list[list[str]]) -> bool:
    """True when the table text says the figures are per share."""
    return _PER_SHARE_RE.search(_flat(rows)) is not None


def is_percentage_table(rows: list[list[str]]) -> bool:
    """True when percent cells are a large part of the numeric cells."""
    cells = [cell for row in rows for cell in row]
    percent_cells = [cell for cell in cells if "%" in cell]
    numeric_cells = [cell for cell in cells if re.search(r"\d", cell)]
    if len(percent_cells) < 3 or not numeric_cells:
        return False
    return len(percent_cells) / len(numeric_cells) >= 0.4


def has_negative_amount(rows: list[list[str]]) -> bool:
    """True when a cell is a parenthesized or leading-minus amount."""
    return any(_NEGATIVE_RE.search(cell) for row in rows for cell in row)


def has_merged_header(markup: str) -> bool:
    """True when the table HTML uses a colspan on a header cell."""
    return bool(re.search(r"(?i)<t[dh][^>]*colspan\s*=\s*[\"']?[2-9]", markup))


def _has_dollar(rows: list[list[str]]) -> bool:
    return any("$" in cell for row in rows for cell in row)


def has_dollar_or_units_phrase(rows: list[list[str]]) -> bool:
    """True when any cell contains ``$`` or a units phrase.

    A units phrase is ``in thousands``, ``in millions``, ``in billions``,
    ``per share``, ``percent``, or a percent sign.
    """
    for cell in (cell for row in rows for cell in row):
        if "$" in cell or _UNIT_PHRASE_RE.search(cell):
            return True
    return False


def is_financial_table(rows: list[list[str]]) -> bool:
    """A financial table has at least two rows and comma-grouped amounts."""
    if len(rows) < 2:
        return False
    blob = " ".join(cell for row in rows for cell in row)
    if _NOT_FINANCIAL_RE.search(blob):
        return False
    if re.search(r"\$\s*100\.00", blob) and re.search(r"S&P", blob):
        return False
    return _MONEY_RE.search(blob) is not None


def cells_follow_source(rows: list[list[str]], source_text: str) -> bool:
    """True when each cell appears, in order, in the given source text."""
    position = 0
    previous_row: list[str] | None = None
    for row in rows:
        previous = None
        for index, cell in enumerate(row):
            above = (
                previous_row[index]
                if previous_row is not None and index < len(previous_row)
                else None
            )
            # Colspan and rowspan repeat one source string across the grid.
            if not cell or cell == previous or cell == above:
                previous = cell
                continue
            found = source_text.find(cell, position)
            if found < 0:
                return False
            position = found + len(cell)
            previous = cell
        previous_row = row
    return True


def _classify(
    block: str,
    element: ET._Element,
    item: str | None,
    heading_path: list[str],
) -> tuple[str, str | None, list[str]]:
    item_match = _ITEM_RE.match(block)
    if item_match:
        code = item_match.group(1).upper()
        return "heading", code, [block]
    if _UNITS_RE.search(block) and len(block) < 240:
        return "paragraph", item, heading_path
    if _is_heading(element, block):
        path = _push_heading(heading_path, block)
        return "heading", item, path
    return "paragraph", item, heading_path


def _push_heading(path: list[str], text: str) -> list[str]:
    """Keep the current Item heading and the latest subsection title."""
    if not path:
        return [text]
    if _ITEM_RE.match(path[0]):
        return [path[0], text]
    return [text]


def _is_heading(element: ET._Element, text: str) -> bool:
    if len(text) > 180 or len(text) < 3:
        return False
    styles = " ".join(
        node.get("style") or "" for node in element.iter() if _local(node) == "span"
    )
    return "font-weight:700" in styles or "font-weight:bold" in styles.lower()


def _text_outside_tables(element: ET._Element) -> str:
    """Visible text in a block that is not inside one of its tables."""
    parts: list[str] = []

    def walk(node: ET._Element) -> None:
        if _skipped(node) or _local(node) == "table":
            return
        if _local(node) == "br":
            parts.append(" ")
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            if _local(child) == "table":
                if child.tail and not _skipped(child):
                    parts.append(child.tail)
                continue
            walk(child)
            if child.tail and not _skipped(child):
                parts.append(child.tail)

    walk(element)
    return " ".join("".join(parts).split())


def _outer_tables(element: ET._Element) -> list[ET._Element]:
    tables = [node for node in element.iter() if _local(node) == "table"]
    return [
        table
        for table in tables
        if not any(_local(ancestor) == "table" for ancestor in table.iterancestors())
    ]


def _element(
    meta: FilingMeta,
    index: int,
    kind: str,
    item: str | None,
    heading_path: list[str],
    *,
    text: str,
    rows: list[list[str]] | None = None,
    grid: list[list[str]] | None = None,
    row_facts: list[list[list[dict]]] | None = None,
    facts: list[list[list[dict]]] | None = None,
    markdown: str | None = None,
    units: str | None = None,
    units_source: str | None = None,
    section_role: str | None = None,
    column_units: list[str | None] | None = None,
) -> dict:
    return {
        "id": f"{meta.ticker}-{meta.fiscal_year}-{index:05d}",
        "ticker": meta.ticker,
        "cik": meta.cik,
        "accession_number": meta.accession_number,
        "fiscal_year": meta.fiscal_year,
        "period_end": meta.period_end,
        "element_type": kind,
        "item": item,
        "heading_path": list(heading_path),
        "text": text,
        "rows": rows,
        "grid": grid,
        "row_facts": row_facts,
        "facts": facts,
        "markdown": markdown,
        "units": units,
        "units_source": units_source,
        "column_units": column_units,
        "section_role": section_role,
    }


def _visible_text(element: ET._Element) -> str:
    parts: list[str] = []

    def walk(node: ET._Element) -> None:
        if _skipped(node):
            return
        if _local(node) == "br":
            parts.append(" ")
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail and not _skipped(child):
                parts.append(child.tail)

    walk(element)
    return " ".join("".join(parts).split())


def _skipped(element: ET._Element) -> bool:
    if _local(element) in _SKIP_TAGS:
        return True
    style = (element.get("style") or "").replace(" ", "").lower()
    return "display:none" in style or "visibility:hidden" in style


def _local(element: ET._Element) -> str:
    return ET.QName(element).localname


def _flat(rows: list[list[str]]) -> str:
    return " ".join(cell for row in rows for cell in row)


def _clean_units(value: str) -> str:
    return " ".join(value.split())
