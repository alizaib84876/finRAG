"""Write parsed 10-K elements to data/parsed and report table checks."""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from finrag.ingest.manifest import read_manifest
from finrag.ingest.parse import (
    FilingMeta,
    alphanumeric_count,
    cells_follow_source,
    has_dollar_or_units_phrase,
    has_merged_header,
    has_negative_amount,
    is_financial_table,
    is_per_share_table,
    is_percentage_table,
    parse_filing,
    raw_html_text,
    rows_are_aligned,
    table_markup,
    word_count,
)

_TRACKED_ITEMS = ("1", "1A", "7", "8")


def main(argv: list[str] | None = None) -> int:
    """Parse every filing in the manifest and print the Step 2 checks."""
    parser = argparse.ArgumentParser(description="Parse 10-K HTML into JSONL elements.")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--sample", type=int, default=10)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument(
        "--examples",
        action="store_true",
        help="Print six hard tables as raw HTML next to the parsed rows.",
    )
    args = parser.parse_args(argv)
    root = _repo_root(args.root)
    filings = read_manifest(root / "data" / "manifest.json")
    parsed_root = root / "data" / "parsed"
    financial_total = 0
    financial_with_units = 0
    source_counts: dict[str, int] = {}
    sample_failures: list[str] = []
    all_failures: list[str] = []
    fallback_special: list[str] = []
    no_units: list[str] = []
    examples: list[tuple[dict, dict, str]] = []
    misaligned = 0
    fallback_tables = 0
    money_tables = 0
    money_with_units = 0

    print(
        "spot_check=10 tables per filing "
        f"seed={args.seed} source=raw HTML text after tags are removed"
    )
    for filing in filings:
        html = (root / filing["path"]).read_text(encoding="utf-8", errors="replace")
        meta = FilingMeta(
            ticker=filing["ticker"],
            cik=filing["cik"],
            accession_number=filing["accession_number"],
            fiscal_year=int(filing["fiscal_year"]),
            period_end=filing["period_end"],
        )
        elements = parse_filing(html, meta)
        destination = (
            parsed_root / filing["ticker"] / f"{filing['accession_number']}.jsonl"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(element, ensure_ascii=False) for element in elements]
        destination.write_text("\n".join(lines) + "\n")

        tables = [element for element in elements if element["element_type"] == "table"]
        for element in tables:
            if not rows_are_aligned(element["rows"]) or not rows_are_aligned(
                element["grid"]
            ):
                misaligned += 1
            if element["units_source"] == "fallback":
                fallback_tables += 1
            if has_dollar_or_units_phrase(element["grid"]):
                money_tables += 1
                if element["units"]:
                    money_with_units += 1
        financial = [
            element for element in tables if is_financial_table(element["grid"])
        ]
        with_units = [element for element in financial if element["units"]]
        financial_total += len(financial)
        financial_with_units += len(with_units)
        for element in financial:
            source = element["units_source"] or "none"
            source_counts[source] = source_counts.get(source, 0) + 1
            if source == "none":
                no_units.append(_table_line(filing, element))
            elif source == "fallback" and (
                is_per_share_table(element["grid"])
                or is_percentage_table(element["grid"])
            ):
                kind = _special_kind(element["grid"])
                fallback_special.append(f"{kind} {_table_line(filing, element)}")

        raw_text = raw_html_text(html)
        sample = _sample(tables, args.sample, args.seed)
        sample_missed = [
            element["id"]
            for element in sample
            if not cells_follow_source(element["rows"], raw_text)
        ]
        every_missed = [
            element["id"]
            for element in tables
            if not cells_follow_source(element["rows"], raw_text)
        ]
        sample_failures.extend(sample_missed)
        all_failures.extend(every_missed)
        item_counts = {
            code: sum(1 for element in elements if element["item"] == code)
            for code in _TRACKED_ITEMS
        }
        source_words = word_count(raw_text)
        parsed_words = sum(word_count(element["text"]) for element in elements)
        source_chars = alphanumeric_count(raw_text)
        parsed_chars = sum(alphanumeric_count(element["text"]) for element in elements)
        ratio = (parsed_words / source_words) if source_words else 0.0
        char_ratio = (parsed_chars / source_chars) if source_chars else 0.0
        item_report = " ".join(
            f"{code}={'yes' if item_counts[code] else 'NO'}:{item_counts[code]}"
            for code in _TRACKED_ITEMS
        )
        role_counts = Counter(element["section_role"] or "none" for element in elements)
        role_report = " ".join(
            f"{name}={role_counts[name]}" for name in sorted(role_counts)
        )
        print(
            f"{filing['ticker']} {filing['period_end']} elements={len(elements)} "
            f"tables={len(tables)} financial={len(financial)} "
            f"units={len(with_units)} sample_misses={len(sample_missed)} "
            f"all_table_misses={len(every_missed)} words={parsed_words}/{source_words} "
            f"word_coverage={ratio:.4f} chars={parsed_chars}/{source_chars} "
            f"char_coverage={char_ratio:.4f} items {item_report} "
            f"section_role {role_report}"
        )
        if args.examples:
            markup = table_markup(html)
            if len(markup) != len(tables):
                raise RuntimeError(
                    f"{filing['ticker']} {filing['accession_number']} "
                    f"emitted {len(tables)} tables but found {len(markup)} markup blocks"
                )
            examples.extend(zip([filing] * len(tables), tables, markup))

    rate = (financial_with_units / financial_total) if financial_total else 0.0
    without = financial_total - len(no_units)
    rate_without = (financial_with_units / without) if without else 0.0
    print(
        "units_by_source "
        + " ".join(
            f"{name}={source_counts.get(name, 0)}"
            for name in (
                "caption",
                "preceding",
                "table_text",
                "fallback",
                "none",
            )
        )
    )
    print(
        f"financial_tables={financial_total} with_units={financial_with_units} "
        f"units_rate_with_all={rate:.4f} "
        f"units_rate_without_no_units_tables={rate_without:.4f} "
        f"no_units_tables={len(no_units)} "
        f"sample_misses={len(sample_failures)} all_table_misses={len(all_failures)} "
        f"misaligned_tables={misaligned} fallback_tables={fallback_tables}"
    )
    money_rate = (money_with_units / money_tables) if money_tables else 0.0
    print(
        f"dollar_or_units_phrase_tables={money_tables} "
        f"with_units={money_with_units} units_rate={money_rate:.4f}"
    )
    print("financial_tables_without_units:")
    for line in no_units:
        print(line)
    print("fallback_per_share_or_percentage:")
    if not fallback_special:
        print("(none)")
    for line in fallback_special:
        print(line)
    if args.examples:
        _print_examples(examples)
    if sample_failures or rate < 0.95 or misaligned:
        return 1
    return 0


def _special_kind(rows: list[list[str]]) -> str:
    kinds = []
    if is_per_share_table(rows):
        kinds.append("per-share")
    if is_percentage_table(rows):
        kinds.append("percentage")
    return "+".join(kinds)


def _table_line(filing: dict, element: dict) -> str:
    heading = element["heading_path"][-1] if element["heading_path"] else ""
    preview = element["text"][:160]
    return (
        f"{filing['ticker']} {filing['period_end']} {element['id']} "
        f"item={element['item']} units={element['units']!r} "
        f"source={element['units_source']} heading={heading[:80]!r} text={preview!r}"
    )


def _print_examples(found: list[tuple[dict, dict, str]]) -> None:
    chosen = _choose_examples(found)
    print(f"hard_tables={len(chosen)}")
    for label, filing, element, markup in chosen:
        print("=" * 72)
        print(
            f"{label} | {filing['ticker']} {filing['period_end']} {element['id']} "
            f"item={element['item']} units={element['units']!r} "
            f"source={element['units_source']}"
        )
        print("PARSED GRID:")
        for row in element["grid"]:
            print(row)
        print("RAW HTML:")
        print(_compact_html(markup))


def _choose_examples(
    found: list[tuple[dict, dict, str]],
) -> list[tuple[str, dict, dict, str]]:
    """Pick six tables that show negatives, merged headers, per-share, and segments."""
    pool = [
        (filing, element, markup)
        for filing, element, markup in found
        if len(markup) <= 25000 and 2 <= len(element["grid"]) <= 18
    ]
    specs = [
        (
            "negative amounts and merged header",
            lambda element, markup: has_negative_amount(element["grid"])
            and has_merged_header(markup),
        ),
        (
            "merged header",
            lambda element, markup: has_merged_header(markup)
            and not has_negative_amount(element["grid"]),
        ),
        (
            "per-share",
            lambda element, markup: any(
                re.search(r"(?i)\b(basic|diluted)\b", cell)
                for row in element["grid"]
                for cell in row
            )
            and has_negative_amount(element["grid"]),
        ),
        (
            "segment",
            lambda element, markup: re.search(
                r"(?i)segment",
                " ".join(element["heading_path"]) + " " + element["text"][:400],
            )
            is not None,
        ),
        (
            "negative amounts",
            lambda element, markup: has_negative_amount(element["grid"]),
        ),
        (
            "per-share",
            lambda element, markup: is_per_share_table(element["grid"])
            and "par value" not in element["text"].lower()
            and not any(
                re.search(r"(?i)\b(basic|diluted)\b", cell)
                for row in element["grid"]
                for cell in row
            ),
        ),
    ]
    chosen: list[tuple[str, dict, dict, str]] = []
    used: set[str] = set()
    for label, predicate in specs:
        match = next(
            (
                (label, filing, element, markup)
                for filing, element, markup in pool
                if element["id"] not in used and predicate(element, markup)
            ),
            None,
        )
        if match is not None:
            used.add(match[2]["id"])
            chosen.append(match)
    return chosen


def _compact_html(markup: str) -> str:
    """Drop namespace declarations so the table cells are readable."""
    markup = re.sub(r'\sxmlns(?::\w+)?="[^"]*"', "", markup)
    return re.sub(r'\sstyle="[^"]*"', "", markup)


def _sample(tables: list[dict], count: int, seed: int) -> list[dict]:
    if len(tables) <= count:
        return tables
    picker = random.Random(seed)
    return picker.sample(tables, count)


def _repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


if __name__ == "__main__":
    sys.exit(main())
