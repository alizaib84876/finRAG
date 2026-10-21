"""Period length and the fiscal-year label from D-003."""

from __future__ import annotations

from datetime import date

FULL_YEAR_MIN_DAYS = 350
FULL_YEAR_MAX_DAYS = 380


def parse_date(value: str | None) -> date | None:
    """Parse an ISO date. Empty and missing values have no date."""
    if not value:
        return None
    return date.fromisoformat(value)


def period_days(start: str, end: str) -> int:
    """Days from start to end, using the calendar dates as written."""
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def is_full_year(start: str | None, end: str | None) -> bool:
    """A full year is about 350 to 380 days, which covers 52- and 53-week years."""
    if not start or not end:
        return False
    days = period_days(start, end)
    return FULL_YEAR_MIN_DAYS <= days <= FULL_YEAR_MAX_DAYS


def fiscal_label(period_end: str) -> tuple[int, bool]:
    """Calendar year of the period end. January ends are ambiguous, per D-003."""
    year, month, _day = period_end.split("-")
    return int(year), month == "01"
