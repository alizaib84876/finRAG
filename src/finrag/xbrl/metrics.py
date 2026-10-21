"""Normalize entity-wide metrics, including comparatives and restatements."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from finrag.xbrl.companyfacts import Fact, entity_fact
from finrag.xbrl.periods import fiscal_label, is_full_year


@dataclass(frozen=True)
class MetricSpec:
    """One metric in the tag map."""

    name: str
    kind: str
    tags: tuple[str, ...]
    minuend: str | None = None
    subtrahend: str | None = None


@dataclass(frozen=True)
class MetricRow:
    """One metric for one period, as reported in one filing."""

    ticker: str
    cik: str
    fiscal_year: int
    fiscal_year_ambiguous: bool
    period_start: str | None
    period_end: str
    accession_number: str
    metric: str
    tag: str | None
    tag_rank: int | None
    value: int
    unit: str
    derived: bool
    comparative: bool
    reported_in_fiscal_year: int


def load_tag_map(path: Path) -> list[MetricSpec]:
    """Read the metric tag map. The first tag in each list is preferred."""
    payload = yaml.safe_load(path.read_text())
    specs: list[MetricSpec] = []
    for item in payload["metrics"]:
        derive = item.get("derive") or {}
        specs.append(
            MetricSpec(
                name=item["name"],
                kind=item["kind"],
                tags=tuple(item.get("tags") or []),
                minuend=derive.get("minuend"),
                subtrahend=derive.get("subtrahend"),
            )
        )
    return specs


def build_metrics(
    facts: list[Fact],
    specs: list[MetricSpec],
    *,
    ticker: str,
    cik: str,
    accession: str,
    period_end: str,
) -> list[MetricRow]:
    """Own-year facts and full-year comparatives reported in one filing."""
    reported_year, _ambiguous = fiscal_label(period_end)
    periods = _periods(facts, accession, period_end, specs)
    rows: list[MetricRow] = []
    for start, end, instant in periods:
        built: dict[str, MetricRow] = {}
        for spec in specs:
            row = _one_metric(
                facts,
                spec,
                built,
                ticker=ticker,
                cik=cik,
                accession=accession,
                filing_end=period_end,
                start=start,
                end=end,
                instant=instant,
                reported_year=reported_year,
            )
            if row is not None:
                built[spec.name] = row
                rows.append(row)
    return rows


def restatements(rows: list[MetricRow]) -> list[dict]:
    """Periods where the same metric has more than one value across filings."""
    groups: dict[tuple, list[MetricRow]] = {}
    for row in rows:
        if row.derived:
            continue
        key = (row.ticker, row.metric, row.period_end, row.period_start)
        groups.setdefault(key, []).append(row)
    found: list[dict] = []
    for key, group in groups.items():
        values = {item.value for item in group}
        if len(values) < 2:
            continue
        ticker, metric, period_end, period_start = key
        found.append(
            {
                "ticker": ticker,
                "metric": metric,
                "period_start": period_start,
                "period_end": period_end,
                "reports": [
                    {
                        "accession_number": item.accession_number,
                        "value": item.value,
                        "tag": item.tag,
                    }
                    for item in group
                ],
            }
        )
    return found


def _periods(
    facts: list[Fact],
    accession: str,
    filing_end: str,
    specs: list[MetricSpec],
) -> list[tuple[str | None, str, bool]]:
    names = {tag for spec in specs for tag in spec.tags}
    duration: set[tuple[str, str]] = set()
    instant: set[str] = set()
    for fact in facts:
        if fact.accession != accession or fact.name not in names or fact.unit != "USD":
            continue
        if fact.start is None:
            instant.add(fact.end)
        elif is_full_year(fact.start, fact.end):
            duration.add((fact.start, fact.end))
    duration_ends = {end for _start, end in duration}
    periods: list[tuple[str | None, str, bool]] = [
        (start, end, False) for start, end in sorted(duration)
    ]
    periods.extend(
        (None, end, True)
        for end in sorted(instant)
        if end in duration_ends or end == filing_end
    )
    return periods


def _one_metric(
    facts: list[Fact],
    spec: MetricSpec,
    built: dict[str, MetricRow],
    *,
    ticker: str,
    cik: str,
    accession: str,
    start: str | None,
    end: str,
    filing_end: str,
    instant: bool,
    reported_year: int,
) -> MetricRow | None:
    if (spec.kind == "instant") != instant:
        return None
    chosen: Fact | None = None
    rank: int | None = None
    for index, tag in enumerate(spec.tags):
        chosen = entity_fact(
            facts,
            name=tag,
            accession=accession,
            end=end,
            start=start,
            full_year=spec.kind == "duration",
        )
        if chosen is not None:
            rank = index
            break
    derived = False
    tag = chosen.name if chosen else None
    value = chosen.value if chosen else None
    if value is None and spec.minuend and spec.subtrahend:
        left = built.get(spec.minuend)
        right = built.get(spec.subtrahend)
        if left is None or right is None:
            return None
        if left.period_end != end or right.period_end != end:
            return None
        value = left.value - right.value
        derived = True
        tag = None
        rank = None
        start = left.period_start
    if value is None:
        return None
    year, ambiguous = fiscal_label(end)
    return MetricRow(
        ticker=ticker,
        cik=cik,
        fiscal_year=year,
        fiscal_year_ambiguous=ambiguous,
        period_start=start,
        period_end=end,
        accession_number=accession,
        metric=spec.name,
        tag=tag,
        tag_rank=rank,
        value=value,
        unit="USD",
        derived=derived,
        comparative=end != filing_end,
        reported_in_fiscal_year=reported_year,
    )
