"""Draw the open hand-check sample from located metric values."""

from __future__ import annotations

import random

from finrag.xbrl.check import CellCheck
from finrag.xbrl.metrics import MetricRow
from finrag.xbrl.periods import fiscal_label


def locate_rows(
    metrics: list[MetricRow],
    checks: list[CellCheck],
    *,
    filing_url: str,
    section_roles: dict[str, str | None],
    units_sources: dict[str, str | None],
    restated: set[tuple[str, str, str]],
) -> list[dict]:
    """Metric rows that sit on a checked statement cell, plus derived rows."""
    by_key: dict[tuple, CellCheck] = {}
    for check in checks:
        if not check.matched or check.tag is None or check.period_end is None:
            continue
        by_key.setdefault((check.tag, check.period_end, check.parsed_value), check)
    located: list[dict] = []
    for row in metrics:
        if row.derived:
            continue
        check = by_key.get((row.tag, row.period_end, abs(row.value)))
        if check is None:
            continue
        located.append(_record(row, check, filing_url, restated))
    for row in metrics:
        if not row.derived:
            continue
        anchor = next(
            (
                item
                for item in located
                if item["ticker"] == row.ticker
                and item["period_end"] == row.period_end
                and item["accession_number"] == row.accession_number
                and item["metric"] == "revenue"
            ),
            None,
        )
        if anchor is None:
            continue
        located.append(
            {
                **_record(row, None, filing_url, restated),
                "element_id": anchor["element_id"],
                "section_role": anchor["section_role"],
                "units_source": anchor["units_source"],
                "cell": anchor["cell"],
            }
        )
    for item in located:
        item["section_role"] = item["section_role"] or section_roles.get(
            item["element_id"]
        )
        item["units_source"] = item["units_source"] or units_sources.get(
            item["element_id"]
        )
    return located


def fallback_rows(
    checks: list[CellCheck],
    *,
    ticker: str,
    filing_url: str,
    accession: str,
) -> list[dict]:
    """Matched cells from tables whose units source is the filing-wide fallback."""
    rows: list[dict] = []
    for check in checks:
        if (
            check.units_source != "fallback"
            or not check.matched
            or check.parsed_value is None
        ):
            continue
        if not check.period_end:
            continue
        year, ambiguous = fiscal_label(check.period_end)
        rows.append(
            {
                "ticker": ticker,
                "fiscal_year": year,
                "fiscal_year_ambiguous": ambiguous,
                "metric": (check.tag or "").split(":")[-1],
                "value": check.parsed_value,
                "unit": "USD",
                "section_role": check.section_role,
                "element_id": check.element_id,
                "cell": check.cell,
                "filing_url": filing_url,
                "period_end": check.period_end,
                "accession_number": accession,
                "units_source": "fallback",
                "tag": check.tag,
                "tag_rank": None,
                "tag_changed": False,
                "derived": False,
                "restated": False,
                "comparative": False,
                "status": "open",
            }
        )
    return rows


def sample_hand_check(
    rows: list[dict], *, seed: int = 13, size: int = 25
) -> list[dict]:
    """25 rows, with the coverage the hand check requires.

    The draw keeps each distinct derived or restated value, one row for each company
    and metric that used a later tag, both FY2024 and FY2025 for each company,
    at least three rows per company, and at least five rows from tables whose
    units source is fallback. If those requirements need more than `size`
    rows, the extra rows stay in the file. The other company-years that used
    a later tag stay in the metrics table.
    """
    rng = random.Random(seed)
    chosen: list[dict] = []
    seen: set[tuple] = set()

    def add(row: dict) -> None:
        key = _key(row)
        if key in seen:
            return
        seen.add(key)
        chosen.append(row)

    seen_values: set[tuple] = set()
    for row in rows:
        if not (row.get("restated") or row.get("derived")):
            continue
        value_key = (
            row["ticker"],
            row["metric"],
            row.get("period_end"),
            row["value"],
        )
        if value_key in seen_values:
            continue
        seen_values.add(value_key)
        add(row)
    seen_tags: set[tuple] = set()
    for row in rows:
        if not row.get("tag_changed"):
            continue
        key = (row["ticker"], row["metric"])
        if key in seen_tags:
            continue
        seen_tags.add(key)
        add(row)

    companies = sorted({row["ticker"] for row in rows})
    for ticker in companies:
        for year in (2024, 2025):
            candidates = [
                row
                for row in rows
                if row["ticker"] == ticker
                and row["fiscal_year"] == year
                and _key(row) not in seen
            ]
            pick = next(
                (row for row in candidates if row.get("units_source") == "fallback"),
                None,
            )
            if pick is None and candidates:
                pick = candidates[0]
            if pick is not None:
                add(pick)
        while sum(1 for row in chosen if row["ticker"] == ticker) < 3:
            options = [
                row for row in rows if row["ticker"] == ticker and _key(row) not in seen
            ]
            if not options:
                break
            fallback_options = [
                row for row in options if row.get("units_source") == "fallback"
            ]
            add(rng.choice(fallback_options or options))

    fallback = [
        row
        for row in rows
        if row.get("units_source") == "fallback" and _key(row) not in seen
    ]
    rng.shuffle(fallback)
    while (
        sum(1 for row in chosen if row.get("units_source") == "fallback") < 5
        and fallback
    ):
        add(fallback.pop())

    rest = [row for row in rows if _key(row) not in seen]
    rng.shuffle(rest)
    for row in rest:
        if len(chosen) >= size:
            break
        add(row)
    return chosen


def _key(row: dict) -> tuple:
    return (
        row["ticker"],
        row["fiscal_year"],
        row["metric"],
        row["accession_number"],
        row["element_id"],
        row["cell"],
    )


def _record(
    row: MetricRow,
    check: CellCheck | None,
    filing_url: str,
    restated: set[tuple[str, str, str]],
) -> dict:
    return {
        "ticker": row.ticker,
        "fiscal_year": row.fiscal_year,
        "fiscal_year_ambiguous": row.fiscal_year_ambiguous,
        "metric": row.metric,
        "value": row.value,
        "unit": row.unit,
        "section_role": check.section_role if check else None,
        "element_id": check.element_id if check else None,
        "cell": check.cell if check else None,
        "filing_url": filing_url,
        "period_end": row.period_end,
        "accession_number": row.accession_number,
        "units_source": check.units_source if check else None,
        "tag": row.tag,
        "tag_rank": row.tag_rank,
        "tag_changed": row.tag_rank is not None and row.tag_rank > 0,
        "derived": row.derived,
        "restated": (row.ticker, row.metric, row.period_end) in restated,
        "comparative": row.comparative,
        "status": "open",
    }
