"""Entity-wide facts from the SEC company-facts JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from finrag.xbrl.periods import is_full_year

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


@dataclass(frozen=True)
class Fact:
    """One company-facts value. These facts have no dimension members."""

    name: str
    accession: str
    start: str | None
    end: str
    value: int
    form: str
    unit: str


def companyfacts_url(cik: str) -> str:
    """Company-facts URL for a CIK, padded to ten digits."""
    return COMPANYFACTS_URL.format(cik=str(cik).zfill(10))


def load_companyfacts(path: Path) -> list[Fact]:
    """Read a company-facts snapshot into a flat list of USD and shares facts."""
    payload = json.loads(path.read_text())
    facts: list[Fact] = []
    for taxonomy, tags in payload.get("facts", {}).items():
        for tag, body in tags.items():
            name = f"{taxonomy}:{tag}"
            for unit, rows in body.get("units", {}).items():
                if unit not in {"USD", "shares"}:
                    continue
                for row in rows:
                    facts.append(
                        Fact(
                            name=name,
                            accession=row["accn"],
                            start=row.get("start"),
                            end=row["end"],
                            value=int(row["val"]),
                            form=row.get("form", ""),
                            unit=unit,
                        )
                    )
    return facts


def entity_fact(
    facts: list[Fact],
    *,
    name: str,
    accession: str,
    end: str,
    start: str | None,
    full_year: bool,
) -> Fact | None:
    """The entity-wide fact for one tag, accession, and period.

    Durations must be a full year. Instants have no start. When the same
    period is stored more than once with the same value, one copy is kept.
    """
    matches = [
        fact
        for fact in facts
        if fact.name == name
        and fact.accession == accession
        and fact.end == end
        and fact.unit == "USD"
    ]
    if start is None:
        matches = [fact for fact in matches if fact.start is None]
    else:
        matches = [fact for fact in matches if fact.start == start]
    if full_year:
        matches = [fact for fact in matches if is_full_year(fact.start, fact.end)]
    if not matches:
        return None
    values = {fact.value for fact in matches}
    if len(values) > 1:
        return None
    return matches[0]
