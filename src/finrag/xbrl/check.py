"""Compare parsed statement cells with inline XBRL and company-facts."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from finrag.xbrl.companyfacts import Fact, entity_fact
from finrag.xbrl.contexts import Context, header_date
from finrag.xbrl.numbers import (
    apply_scale,
    attribute_is_negative,
    is_rounding,
    is_scale_factor,
    parse_display,
)

CAUSE_HEADER = "header-period parse failure"
CAUSE_SCALE = "scale"
CAUSE_SIGN = "sign"
CAUSE_MISSING = "missing tag"
CAUSE_ROUNDING = "rounding"

_INCOME = re.compile(
    r"(?i)statements? of (?:income|operations|earnings)|income statements?"
)
_BALANCE = re.compile(r"(?i)balance sheets?|statements? of financial position")
_SEGMENT = re.compile(r"(?i)\bsegments?\b")
_AMOUNT = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\(\d|\d+\.\d+")
_YEAR = re.compile(r"\b(20\d{2})\b")


@dataclass(frozen=True)
class Mismatch:
    """One cell that disagrees with its XBRL fact, or has no fact."""

    table_id: str
    cell: str
    expected: str
    parsed: str
    cause: str
    units_source: str | None
    section_role: str | None
    ticker: str
    accession_number: str


@dataclass(frozen=True)
class CellCheck:
    """A numeric statement cell that was compared."""

    table_id: str
    cell: str
    units_source: str | None
    section_role: str | None
    matched: bool
    tag: str | None
    period_end: str | None
    parsed_value: int | None
    element_id: str


def table_kind(element: dict) -> str | None:
    """Income statement, balance sheet, or segment, from the heading or caption."""
    heading = " ".join(element.get("heading_path") or [])
    caption = (element.get("text") or "")[:400]
    blob = f"{heading} {caption}"
    if _INCOME.search(blob):
        return "income"
    if _BALANCE.search(blob):
        return "balance"
    if _SEGMENT.search(blob):
        return "segment"
    return None


def check_filing(
    elements: list[dict],
    contexts: dict[str, Context],
    facts: list[Fact],
    *,
    ticker: str,
    accession: str,
) -> tuple[list[CellCheck], list[Mismatch]]:
    """Check statement cells in one filing. Sign mismatches are their own cause."""
    checks: list[CellCheck] = []
    mismatches: list[Mismatch] = []
    for element in elements:
        if element.get("element_type") != "table" or table_kind(element) is None:
            continue
        grid = element.get("grid") or []
        fact_grid = element.get("facts") or []
        data_at = _first_data_row(grid)
        for row_index, row in enumerate(grid):
            if row_index < data_at:
                continue
            row_facts = fact_grid[row_index] if row_index < len(fact_grid) else []
            for column, text in enumerate(row):
                if column == 0:
                    continue
                cell_facts = row_facts[column] if column < len(row_facts) else []
                if not cell_facts and not _is_amount(text):
                    continue
                period, year_only = _period_for(grid, row_index, column, data_at)
                if _is_blank(text) and not any(
                    parse_display(fact.get("text") or "") for fact in cell_facts
                ):
                    continue
                cell = f"r{row_index}c{column}"
                cell_mismatches, period_end, tag, parsed_value = _compare_cell(
                    text,
                    cell_facts,
                    period,
                    year_only,
                    contexts,
                    facts,
                    accession=accession,
                )
                for cause, expected, parsed in cell_mismatches:
                    mismatches.append(
                        Mismatch(
                            table_id=element["id"],
                            cell=cell,
                            expected=expected,
                            parsed=parsed,
                            cause=cause,
                            units_source=element.get("units_source"),
                            section_role=element.get("section_role"),
                            ticker=ticker,
                            accession_number=accession,
                        )
                    )
                absolute = [item for item in cell_mismatches if item[0] != CAUSE_SIGN]
                checks.append(
                    CellCheck(
                        table_id=element["id"],
                        cell=cell,
                        units_source=element.get("units_source"),
                        section_role=element.get("section_role"),
                        matched=not absolute,
                        tag=tag,
                        period_end=period_end,
                        parsed_value=parsed_value,
                        element_id=element["id"],
                    )
                )
    return checks, mismatches


def match_rates(
    checks: list[CellCheck],
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Absolute match rate by units_source and by section_role."""
    return {
        "by_units_source": _rate(checks, "units_source"),
        "by_section_role": _rate(checks, "section_role"),
    }


def _compare_cell(
    text: str,
    cell_facts: list[dict],
    period,
    year_only: int | None,
    contexts: dict[str, Context],
    facts: list[Fact],
    *,
    accession: str,
) -> tuple[list[tuple[str, str, str]], str | None, str | None, int | None]:
    if not cell_facts:
        return [(CAUSE_MISSING, "", text)], None, None, None
    found: list[tuple[str, str, str]] = []
    period_end = None
    tag = None
    parsed_value = None
    displayed = parse_display(text)
    for fact in cell_facts:
        tag = fact.get("name")
        context = contexts.get(fact.get("context_ref") or "")
        context_end = context.period_end if context else None
        period_end = context_end
        if not _period_matches(period, year_only, context_end):
            expected = context_end or ""
            parsed = (
                period.isoformat()
                if period is not None
                else (str(year_only) if year_only else "unparsed header")
            )
            found.append((CAUSE_HEADER, expected, parsed))
            continue
        scale = fact.get("scale")
        if displayed is None:
            found.append((CAUSE_MISSING, fact.get("text") or "", text))
            continue
        parsed_abs, displayed_negative = displayed
        parsed_raw = apply_scale(parsed_abs, scale)
        expected_raw, expected_negative = _expected(
            fact, context, facts, accession, scale
        )
        if expected_raw is None:
            found.append((CAUSE_MISSING, "", text))
            continue
        parsed_value = (
            int(parsed_raw) if parsed_raw == parsed_raw.to_integral_value() else None
        )
        if parsed_raw != expected_raw:
            cause = (
                CAUSE_ROUNDING
                if is_rounding(parsed_raw, expected_raw, scale)
                else CAUSE_SCALE
            )
            if cause == CAUSE_SCALE and not is_scale_factor(parsed_raw, expected_raw):
                cause = (
                    CAUSE_ROUNDING
                    if _relative_close(parsed_raw, expected_raw)
                    else CAUSE_SCALE
                )
            found.append((cause, _format(expected_raw), _format(parsed_raw)))
        if displayed_negative != attribute_is_negative(fact.get("sign")):
            found.append(
                (CAUSE_SIGN, _sign_label(attribute_is_negative(fact.get("sign"))), text)
            )
        elif (
            expected_negative is not None
            and expected_negative != attribute_is_negative(fact.get("sign"))
        ):
            found.append(
                (
                    CAUSE_SIGN,
                    _sign_label(expected_negative),
                    _sign_label(attribute_is_negative(fact.get("sign"))),
                )
            )
    return found, period_end, tag, parsed_value


def _expected(
    fact: dict,
    context: Context | None,
    facts: list[Fact],
    accession: str,
    scale: int | None,
) -> tuple[Decimal | None, bool | None]:
    inline = parse_display(fact.get("text") or "")
    inline_raw = apply_scale(inline[0], scale) if inline else None
    if (
        context is None
        or context.has_dimensions
        or not fact.get("name")
        or not _is_usd(fact)
    ):
        return inline_raw, None
    company = entity_fact(
        facts,
        name=fact["name"],
        accession=accession,
        end=context.period_end or "",
        start=None if context.instant else context.start,
        full_year=context.instant is None,
    )
    if company is None:
        return inline_raw, None
    return abs(Decimal(company.value)), company.value < 0


def _period_for(grid: list[list[str]], row_index: int, column: int, data_at: int):
    """Nearest period date for one cell.

    A date in the same column wins, so a later block in the table does not keep
    the first header. Otherwise the column header is read as a whole, because
    filers split "December 31," and "2025" across two rows. A year alone, such
    as "2025", is returned when the header has no month.
    """
    for index in range(row_index, -1, -1):
        cell = grid[index][column] if column < len(grid[index]) else ""
        found = header_date([cell])
        if found is not None:
            return found, None
    header_cells = [
        grid[i][column] for i in range(min(data_at, len(grid))) if column < len(grid[i])
    ]
    found = header_date(header_cells)
    if found is not None:
        return found, None
    for index in range(row_index, -1, -1):
        label = grid[index][0] if grid[index] else ""
        found = header_date([label])
        if found is not None:
            return found, None
    return None, _header_year(header_cells)


def _period_matches(period, year_only: int | None, context_end: str | None) -> bool:
    if context_end is None:
        return False
    if period is not None:
        return period.isoformat() == context_end
    return year_only is not None and context_end.startswith(f"{year_only:04d}-")


def _header_year(cells: list[str]) -> int | None:
    years = _YEAR.findall(" ".join(cells))
    if not years:
        return None
    return int(years[-1])


def _is_blank(text: str) -> bool:
    cleaned = (text or "").replace("$", "").replace("%", "").strip()
    return cleaned in {"", "—", "–", "-"}


def _first_data_row(grid: list[list[str]]) -> int:
    for index, row in enumerate(grid):
        if any(_is_amount(cell) for cell in row[1:]):
            return index
    return len(grid)


def _is_amount(text: str) -> bool:
    return _AMOUNT.search(text or "") is not None


def _is_usd(fact: dict) -> bool:
    unit = (fact.get("unit_ref") or "usd").lower()
    return unit in {"usd", "iso4217:usd"}


def _relative_close(parsed: Decimal, expected: Decimal) -> bool:
    if expected == 0:
        return parsed == 0
    return abs(parsed - expected) / abs(expected) <= Decimal("0.001")


def _format(value: Decimal) -> str:
    return format(value, "f")


def _sign_label(negative: bool) -> str:
    return "negative" if negative else "positive"


def _rate(checks: list[CellCheck], field: str) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[CellCheck]] = defaultdict(list)
    for check in checks:
        groups[str(getattr(check, field) or "none")].append(check)
    rates: dict[str, dict[str, float | int]] = {}
    for key, group in sorted(groups.items()):
        matched = sum(1 for item in group if item.matched)
        rates[key] = {
            "checked": len(group),
            "matched": matched,
            "match_rate": matched / len(group) if group else 0.0,
        }
    return rates
