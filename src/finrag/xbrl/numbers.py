"""Displayed amounts, scale, and the sign attribute."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

_POWER = Decimal(10)


def parse_display(text: str) -> tuple[Decimal, bool] | None:
    """Absolute displayed number, and whether parentheses wrap it.

    A leading minus is a displayed negative. Parentheses are recorded and are
    not treated as the XBRL sign by themselves.
    """
    cleaned = text.replace(",", "").replace("$", "").replace("%", "").strip()
    if not cleaned:
        return None
    parentheses = cleaned.startswith("(") and cleaned.endswith(")")
    if parentheses:
        cleaned = cleaned[1:-1].strip()
    displayed_negative = parentheses or cleaned.startswith("-")
    cleaned = cleaned.removeprefix("-")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    return abs(amount), displayed_negative


def apply_scale(amount: Decimal, scale: int | None) -> Decimal:
    """Multiply a displayed amount by 10^scale. A missing scale is 10^0."""
    power = scale or 0
    return amount * (_POWER**power)


def attribute_is_negative(sign: str | None) -> bool:
    """The XBRL sign is the sign attribute. Anything else is positive."""
    return sign == "-"


def is_natural_positive(company_value: int | Decimal | None, sign: str | None) -> bool:
    """True when an answer for this concept is compared on absolute value.

    A company-facts value of zero or more is natural-positive, per D-010.
    With no company-facts value, a missing sign attribute means the same thing.
    """
    if company_value is not None:
        return Decimal(company_value) >= 0
    return not attribute_is_negative(sign)


def answer_values_match(
    expected: Decimal,
    actual: Decimal,
    *,
    natural_positive: bool,
) -> bool:
    """Compare two answer amounts under D-010."""
    if natural_positive:
        return abs(expected) == abs(actual)
    return expected == actual


def is_rounding(parsed: Decimal, expected: Decimal, scale: int | None) -> bool:
    """True when the two raw amounts differ by at most half of one displayed unit."""
    if expected == 0:
        return parsed == 0
    half_unit = _POWER ** (scale or 0) / 2
    return abs(parsed - expected) <= half_unit


def is_scale_factor(parsed: Decimal, expected: Decimal) -> bool:
    """True when the ratio is a power of ten other than 1."""
    if parsed == 0 or expected == 0:
        return False
    ratio = abs(parsed / expected)
    if ratio == 1:
        return False
    exponent = ratio.ln() / _POWER.ln()
    return abs(exponent - exponent.to_integral_value()) < Decimal("0.01")
