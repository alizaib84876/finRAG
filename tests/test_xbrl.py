"""XBRL metrics, the cell check, and the hand-check draw."""

import subprocess
from decimal import Decimal
from pathlib import Path

from finrag.xbrl.check import CAUSE_MISSING, CAUSE_SCALE, CAUSE_SIGN, check_filing
from finrag.xbrl.companyfacts import Fact, entity_fact
from finrag.xbrl.contexts import Context, header_date, parse_contexts
from finrag.xbrl.hand import sample_hand_check
from finrag.xbrl.metrics import build_metrics, load_tag_map, restatements
from finrag.xbrl.numbers import apply_scale, is_scale_factor, parse_display
from finrag.xbrl.periods import fiscal_label, is_full_year

ROOT = Path(__file__).resolve().parents[1]
ACCESSION = "0001045810-26-000021"


def _fact(
    name: str, start: str | None, end: str, value: int, accession: str = ACCESSION
) -> Fact:
    return Fact(name, accession, start, end, value, "10-K", "USD")


def test_full_year_uses_start_and_end_not_a_four_digit_label():
    assert is_full_year("2025-01-27", "2026-01-25")
    assert not is_full_year("2025-10-27", "2026-01-25")
    assert fiscal_label("2026-01-25") == (2026, True)
    assert fiscal_label("2025-11-02") == (2025, False)


def test_parentheses_are_not_the_xbrl_sign():
    amount, parentheses = parse_display("(1,424)")
    assert amount == Decimal(1424)
    assert parentheses is True
    assert apply_scale(amount, 6) == Decimal(1424000000)
    assert is_scale_factor(Decimal(10), Decimal(1))


def test_header_date_reads_the_column_period():
    assert header_date(["Year Ended", "Jan 25, 2026"]).isoformat() == "2026-01-25"
    assert header_date(["December 31,", "2025"]).isoformat() == "2025-12-31"
    assert (
        header_date(["Fiscal Year Ended March 31,", "2026"]).isoformat() == "2026-03-31"
    )
    assert header_date(["Note"]) is None


def test_entity_fact_keeps_full_years_only():
    facts = [
        _fact("us-gaap:Revenues", "2025-01-27", "2026-01-25", 215_938_000_000),
        _fact("us-gaap:Revenues", "2025-10-27", "2026-01-25", 1),
    ]
    chosen = entity_fact(
        facts,
        name="us-gaap:Revenues",
        accession=ACCESSION,
        end="2026-01-25",
        start="2025-01-27",
        full_year=True,
    )
    assert chosen is not None
    assert chosen.value == 215_938_000_000
    assert (
        entity_fact(
            facts,
            name="us-gaap:Revenues",
            accession=ACCESSION,
            end="2026-01-25",
            start="2025-10-27",
            full_year=True,
        )
        is None
    )


def test_metrics_keep_comparatives_and_derive_a_missing_tag():
    specs = load_tag_map(ROOT / "configs" / "xbrl_tags.yaml")
    facts = [
        _fact("us-gaap:Revenues", "2025-01-27", "2026-01-25", 100),
        _fact("us-gaap:Revenues", "2024-01-29", "2025-01-26", 40),
        _fact("us-gaap:CostOfRevenue", "2025-01-27", "2026-01-25", 30),
        _fact("us-gaap:CostOfGoodsAndServicesSold", "2024-01-29", "2025-01-26", 10),
        _fact("us-gaap:Assets", None, "2026-01-25", 200),
        _fact("us-gaap:ProfitLoss", "2025-01-27", "2026-01-25", 70),
    ]
    rows = build_metrics(
        facts,
        specs,
        ticker="NVDA",
        cik="0001045810",
        accession=ACCESSION,
        period_end="2026-01-25",
    )
    by_key = {(row.metric, row.period_end): row for row in rows}
    assert by_key[("revenue", "2026-01-25")].comparative is False
    assert by_key[("revenue", "2026-01-25")].tag_rank == 1
    assert by_key[("revenue", "2026-01-25")].fiscal_year_ambiguous is True
    prior = by_key[("revenue", "2025-01-26")]
    assert prior.comparative is True
    assert prior.accession_number == ACCESSION
    assert prior.fiscal_year == 2025
    assert (
        by_key[("cost_of_revenue", "2025-01-26")].tag
        == "us-gaap:CostOfGoodsAndServicesSold"
    )
    assert by_key[("gross_profit", "2026-01-25")].derived is True
    assert by_key[("gross_profit", "2026-01-25")].value == 70
    assert by_key[("net_income", "2026-01-25")].tag == "us-gaap:ProfitLoss"
    assert by_key[("total_assets", "2026-01-25")].period_start is None


def test_restatement_is_a_changed_value_for_the_same_period():
    specs = load_tag_map(ROOT / "configs" / "xbrl_tags.yaml")
    later = "0001045810-26-000021"
    earlier = "0001045810-25-000023"
    facts = [
        _fact("us-gaap:Revenues", "2024-01-29", "2025-01-26", 40, later),
        _fact("us-gaap:Revenues", "2024-01-29", "2025-01-26", 39, earlier),
    ]
    rows = []
    for accession, end in ((later, "2026-01-25"), (earlier, "2025-01-26")):
        rows.extend(
            build_metrics(
                facts,
                specs,
                ticker="NVDA",
                cik="0001045810",
                accession=accession,
                period_end=end,
            )
        )
    changed = restatements(rows)
    assert changed
    assert {item["value"] for item in changed[0]["reports"]} == {40, 39}


def test_cell_check_splits_sign_from_the_absolute_value():
    contexts = {
        "c-1": Context("c-1", "2025-01-27", "2026-01-25", None, ()),
        "c-seg": Context(
            "c-seg",
            "2025-01-27",
            "2026-01-25",
            None,
            (("us-gaap:StatementBusinessSegmentsAxis", "nvda:ComputeMember"),),
        ),
    }
    facts = [
        _fact("us-gaap:Revenues", "2025-01-27", "2026-01-25", 215_938_000_000),
        _fact(
            "us-gaap:IncomeTaxExpenseBenefit", "2025-01-27", "2026-01-25", -10_000_000
        ),
        _fact("us-gaap:OtherExpense", "2025-01-27", "2026-01-25", 215_940_000_000),
    ]
    element = {
        "element_type": "table",
        "id": "EX-1",
        "heading_path": ["Consolidated Statements of Income"],
        "text": "Consolidated Statements of Income",
        "section_role": "financial_statements",
        "units_source": "caption",
        "grid": [
            ["", "Jan 25, 2026", "Note"],
            ["Revenue", "215,938", ""],
            ["Tax", "10", ""],
            ["Untagged", "(259)", ""],
            ["Scaled", "21,594", ""],
            ["Segment", "5,000", ""],
            ["No date", "", "1,000"],
        ],
        "facts": [
            [[], [], []],
            [[], [_ix("us-gaap:Revenues", "c-1", "215,938")], []],
            [[], [_ix("us-gaap:IncomeTaxExpenseBenefit", "c-1", "10", sign="-")], []],
            [[], [], []],
            [[], [_ix("us-gaap:OtherExpense", "c-1", "215,940")], []],
            [[], [_ix("us-gaap:Revenues", "c-seg", "5,000")], []],
            [[], [], [_ix("us-gaap:Revenues", "c-1", "1,000")]],
        ],
    }
    checks, mismatches = check_filing(
        [element], contexts, facts, ticker="NVDA", accession=ACCESSION
    )
    by_cell = {}
    for item in mismatches:
        by_cell.setdefault(item.cell, []).append(item)
    assert checks[0].matched is True
    assert [item.cause for item in by_cell["r2c1"]] == [CAUSE_SIGN]
    assert by_cell["r2c1"][0].expected == "negative"
    assert by_cell["r3c1"][0].cause == CAUSE_MISSING
    assert by_cell["r4c1"][0].cause == CAUSE_SCALE
    assert by_cell["r6c2"][0].cause == "header-period parse failure"
    assert "r5c1" not in by_cell


def test_segment_period_comes_from_the_row_stub():
    contexts = {"c-seg": Context("c-seg", "2025-01-27", "2026-01-25", None, ())}
    element = {
        "element_type": "table",
        "id": "SEG-1",
        "heading_path": ["Segment information"],
        "text": "Revenue by segment",
        "section_role": "notes",
        "units_source": "table_text",
        "grid": [
            ["", "Compute", "Graphics"],
            ["Year Ended Jan 25, 2026", "", ""],
            ["Revenue", "193,479", "22,459"],
        ],
        "facts": [
            [[], [], []],
            [[], [], []],
            [
                [],
                [_ix("us-gaap:Revenues", "c-seg", "193,479")],
                [_ix("us-gaap:Revenues", "c-seg", "22,459")],
            ],
        ],
    }
    checks, mismatches = check_filing(
        [element], contexts, [], ticker="NVDA", accession=ACCESSION
    )
    assert mismatches == []
    assert all(item.matched for item in checks)


def test_a_later_date_in_the_column_replaces_the_first_header():
    contexts = {
        "c-new": Context("c-new", None, None, "2026-03-31", ()),
        "c-old": Context("c-old", None, None, "2025-03-31", ()),
    }
    element = {
        "element_type": "table",
        "id": "MCHP-1",
        "heading_path": ["Segment Information"],
        "text": "Net sales by segment",
        "section_role": "notes",
        "units_source": "preceding",
        "grid": [
            [
                "",
                "Fiscal Year Ended March 31, 2026",
                "Fiscal Year Ended March 31, 2026",
            ],
            ["Net sales", "4,549.3", "4,713.1"],
            [
                "",
                "Fiscal Year Ended March 31, 2025",
                "Fiscal Year Ended March 31, 2025",
            ],
            ["Net sales", "4,401.6", "4,401.6"],
        ],
        "facts": [
            [[], [], []],
            [
                [],
                [_ix("us-gaap:Revenues", "c-new", "4,549.3")],
                [_ix("us-gaap:Revenues", "c-new", "4,713.1")],
            ],
            [[], [], []],
            [
                [],
                [_ix("us-gaap:Revenues", "c-old", "4,401.6")],
                [_ix("us-gaap:Revenues", "c-old", "4,401.6")],
            ],
        ],
    }
    _checks, mismatches = check_filing(
        [element], contexts, [], ticker="MCHP", accession=ACCESSION
    )
    assert mismatches == []


def test_a_year_only_header_matches_that_calendar_year():
    contexts = {"c-1": Context("c-1", "2024-11-04", "2025-11-02", None, ())}
    element = {
        "element_type": "table",
        "id": "AVGO-1",
        "heading_path": ["Segment Information"],
        "text": "Net revenue",
        "section_role": "notes",
        "units_source": "table_text",
        "grid": [
            ["", "2025"],
            ["Net revenue", "36,858"],
        ],
        "facts": [
            [[], []],
            [[], [_ix("us-gaap:Revenues", "c-1", "36,858")]],
        ],
    }
    _checks, mismatches = check_filing(
        [element], contexts, [], ticker="AVGO", accession=ACCESSION
    )
    assert mismatches == []


def test_a_dash_is_not_a_missing_tag():
    element = {
        "element_type": "table",
        "id": "DASH-1",
        "heading_path": ["Consolidated Balance Sheets"],
        "text": "Consolidated Balance Sheets",
        "section_role": "financial_statements",
        "units_source": "caption",
        "grid": [["", "December 31, 2025"], ["Licensing", "—"]],
        "facts": [
            [[], []],
            [[], [_ix("us-gaap:Revenues", "c-1", "—")]],
        ],
    }
    checks, mismatches = check_filing(
        [element], {}, [], ticker="TXN", accession=ACCESSION
    )
    assert checks == []
    assert mismatches == []


def test_contexts_keep_period_and_dimensions():
    html = """<?xml version="1.0"?>
    <html xmlns="http://www.w3.org/1999/xhtml"><body>
      <xbrli:context xmlns:xbrli="http://www.xbrl.org/2003/instance" id="c-1">
        <xbrli:period><xbrli:startDate>2025-01-27</xbrli:startDate><xbrli:endDate>2026-01-25</xbrli:endDate></xbrli:period>
      </xbrli:context>
    </body></html>"""
    found = parse_contexts(html)
    assert found["c-1"].start == "2025-01-27"
    assert found["c-1"].end == "2026-01-25"
    assert found["c-1"].has_dimensions is False


def test_hand_check_covers_companies_years_and_fallback():
    rows = []
    for ticker in ("NVDA", "AMD", "TXN"):
        for year, source in (
            (2024, "caption"),
            (2025, "fallback"),
            (2026, "table_text"),
        ):
            rows.append(_hand_row(ticker, year, "revenue", source, False, False, False))
        rows.append(
            _hand_row(ticker, 2025, "gross_profit", "caption", False, True, False)
        )
    rows.append(_hand_row("NVDA", 2024, "net_income", "fallback", True, False, False))
    rows.append(
        _hand_row("AMD", 2024, "cost_of_revenue", "fallback", False, False, True)
    )
    rows.append(_hand_row("TXN", 2026, "total_assets", "fallback", False, False, False))
    drawn = sample_hand_check(rows, seed=13, size=25)
    for ticker in ("NVDA", "AMD", "TXN"):
        years = {row["fiscal_year"] for row in drawn if row["ticker"] == ticker}
        assert years >= {2024, 2025}
        assert sum(1 for row in drawn if row["ticker"] == ticker) >= 3
    assert sum(1 for row in drawn if row["units_source"] == "fallback") >= 5
    assert any(row["tag_changed"] for row in drawn)
    assert any(row["derived"] for row in drawn)
    assert any(row["restated"] for row in drawn)
    assert all(row["status"] == "open" for row in drawn)


def test_company_facts_raw_json_is_gitignored():
    probe = ROOT / "data" / "xbrl" / "raw" / "gitignore-probe.json"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("{}\n")
    result = subprocess.run(
        ["git", "check-ignore", "-q", "data/xbrl/raw/gitignore-probe.json"],
        cwd=ROOT,
        check=False,
    )
    probe.unlink()
    assert result.returncode == 0


def _ix(name: str, context: str, text: str, sign: str | None = None) -> dict:
    return {
        "name": name,
        "context_ref": context,
        "scale": 6,
        "sign": sign,
        "decimals": "-6",
        "unit_ref": "usd",
        "fact_id": "f-1",
        "text": text,
    }


def _hand_row(ticker, year, metric, source, changed, derived, restated) -> dict:
    return {
        "ticker": ticker,
        "fiscal_year": year,
        "metric": metric,
        "accession_number": f"{ticker}-{year}",
        "element_id": f"{ticker}-{year}-{metric}",
        "cell": "r1c1",
        "units_source": source,
        "tag_changed": changed,
        "derived": derived,
        "restated": restated,
        "status": "open",
        "value": 1,
        "section_role": "financial_statements",
        "filing_url": "https://www.sec.gov/example",
    }


def test_snapshot_sidecar_records_hash_and_date(tmp_path: Path):
    from finrag.xbrl.cli import _snapshots

    cik = "0000000001"
    raw = tmp_path / "data" / "xbrl" / "raw"
    raw.mkdir(parents=True)
    (raw / f"{cik}.json").write_text("{}\n")
    records = _snapshots(tmp_path, [{"cik": cik, "ticker": "EX"}])
    assert records[0]["path"] == f"data/xbrl/raw/{cik}.json"
    assert records[0]["fetched_at"]
    assert len(records[0]["sha256"]) == 64
