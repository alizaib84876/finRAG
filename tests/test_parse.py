"""Tests for 10-K HTML parsing."""

from pathlib import Path

import pytest

from finrag.ingest.manifest import read_manifest
from finrag.ingest.parse import (
    FilingMeta,
    cells_follow_source,
    expand_grid,
    has_negative_amount,
    is_financial_table,
    parse_filing,
    raw_html_text,
    rows_are_aligned,
)

FIXTURE = Path(__file__).parent / "fixtures" / "parse_sample.xhtml"
META = FilingMeta(
    ticker="NVDA",
    cik="0001045810",
    accession_number="0001045810-26-000021",
    fiscal_year=2026,
    period_end="2026-01-25",
)


def test_parse_items_tables_and_units() -> None:
    """Items, a units line, and table cells come from the HTML, not from PDF."""
    html = FIXTURE.read_text()
    elements = parse_filing(html, META)
    kinds = [element["element_type"] for element in elements]
    assert "do not show" not in " ".join(element["text"] for element in elements)
    assert "hidden fact" not in " ".join(element["text"] for element in elements)

    risk = elements[0]
    assert risk["element_type"] == "heading"
    assert risk["item"] == "1A"
    assert risk["section_role"] == "risk_factors"
    assert risk["heading_path"] == ["ITEM 1A. Risk factors"]

    demand = next(
        element for element in elements if element["text"] == "Demand may fall."
    )
    assert demand["item"] == "1A"
    assert demand["element_type"] == "paragraph"

    table = next(element for element in elements if element["element_type"] == "table")
    assert table["item"] == "8"
    assert table["section_role"] == "financial_statements"
    assert rows_are_aligned(table["rows"])
    assert table["rows"] == [
        ["Year Ended", "Year Ended", "Year Ended", ""],
        ["Revenue", "$", "215,938", "130,497"],
        ["Cost of revenue", "62,475", "", ""],
    ]
    assert table["units"] == "(In millions, except per share data)"
    assert table["units_source"] == "preceding"
    assert "Revenue" in table["markdown"]
    assert is_financial_table(table["rows"])
    raw = raw_html_text(html)
    assert "<table>" not in raw
    assert "hidden fact" not in raw
    assert cells_follow_source(table["rows"], raw)
    assert not cells_follow_source([["not-in-the-filing"]], raw)

    market = next(
        element for element in elements if element["text"].startswith("ITEM 7A.")
    )
    assert market["item"] == "7A"
    rates = next(
        element
        for element in elements
        if element["text"] == "Interest rates may change."
    )
    assert rates["item"] == "7A"
    assert kinds.count("table") == 1


def test_heading_path_keeps_item_and_subsection() -> None:
    """A bold subsection sits under the current Item heading."""
    elements = parse_filing(FIXTURE.read_text(), META)
    statement = next(
        element
        for element in elements
        if element["text"] == "Consolidated Statements of Income"
    )
    assert statement["element_type"] == "heading"
    assert statement["heading_path"] == [
        "ITEM 8. Financial statements and supplementary data",
        "Consolidated Statements of Income",
    ]
    assert statement["item"] == "8"


def test_dollars_in_millions_and_running_units() -> None:
    """A caption and a later all-tables statement both count as units."""
    html = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<div>Net sales were as follows (dollars in millions):</div>
<table><tr><td>Product</td><td>2026</td></tr>
<tr><td>Analog</td><td>$</td><td>1,329.0</td></tr></table>
<div>All dollar amounts in the tables are stated in millions of U.S. dollars.</div>
<table><tr><td></td><td>2025</td></tr>
<tr><td>Cash</td><td>$</td><td>4,880</td></tr></table>
</body></html>"""
    elements = parse_filing(html, META)
    tables = [element for element in elements if element["element_type"] == "table"]
    assert tables[0]["units"] == "(dollars in millions)"
    assert tables[0]["units_source"] == "preceding"
    assert tables[1]["units_source"] == "preceding"
    assert "millions of" in tables[1]["units"]
    assert is_financial_table(tables[0]["rows"])

    same_div = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<div>(In millions, except per share data)
<table><tr><td>Year Ended</td></tr>
<tr><td>Revenue</td><td>$</td><td>60,922</td></tr></table>
</div></body></html>"""
    same = parse_filing(same_div, META)
    table = next(element for element in same if element["element_type"] == "table")
    assert table["units"] == "(In millions, except per share data)"
    assert table["units_source"] == "caption"


def test_line_break_inside_a_cell_stays_in_the_raw_html() -> None:
    """A br inside a cell is a space, and that cell is in the tag-stripped HTML."""
    html = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<table><tr><td>$<br/>Change</td><td>Expected<br/>Remaining Term</td></tr>
<tr><td>Revenue</td><td>1,329</td></tr></table>
</body></html>"""
    elements = parse_filing(html, META)
    table = next(element for element in elements if element["element_type"] == "table")
    assert table["rows"][0] == ["$ Change", "Expected Remaining Term"]
    assert cells_follow_source(table["rows"], raw_html_text(html))
    assert has_negative_amount([["(3,549)"]])
    assert not has_negative_amount([["63"], ["94-3177549"]])


def test_filing_wide_fallback_is_labeled() -> None:
    """A dollar table far below the scale statement uses the fallback source."""
    gap = "\n".join(f"<div>Note {index}.</div>" for index in range(9))
    html = f"""<html xmlns="http://www.w3.org/1999/xhtml"><body>
<div>All dollar amounts in the tables are stated in millions of U.S. dollars.</div>
{gap}
<table><tr><td>Cash</td></tr><tr><td>$</td><td>4,880</td></tr></table>
</body></html>"""
    elements = parse_filing(html, META)
    table = next(element for element in elements if element["element_type"] == "table")
    assert "millions of" in table["units"]
    assert table["units_source"] == "fallback"


REPURCHASE = Path(__file__).parent / "fixtures" / "nvda_2026_00491.xhtml"


def test_repurchase_total_row_keeps_empty_price_cells() -> None:
    """The NVDA-2026-00491 Total row lines up with the merged header."""
    elements = parse_filing(REPURCHASE.read_text(), META)
    table = next(element for element in elements if element["element_type"] == "table")
    assert rows_are_aligned(table["rows"])
    width = len(table["rows"][0])
    assert all(len(row) == width for row in table["rows"])
    assert table["rows"][0] == [
        "Period",
        "Total Number of Shares Purchased (In millions)",
        "Average Price Paid per Share (1)",
        "Average Price Paid per Share (1)",
        "Total Number of Shares Purchased as Part of Publicly Announced Program (In millions)",
        "Approximate Dollar Value of Shares that May Yet Be Purchased Under the Program (In billions)",
        "Approximate Dollar Value of Shares that May Yet Be Purchased Under the Program (In billions)",
    ]
    assert table["rows"][-1] == ["Total", "19.5", "", "", "19.5", "", ""]
    assert table["column_units"] == [
        None,
        "in millions",
        "per share",
        "in millions",
        "in billions",
    ]
    assert table["grid"][-1] == ["Total", "19.5", "", "19.5", ""]
    assert "(In millions)" in table["rows"][0][1]
    assert "(In billions)" in table["rows"][0][5]
    assert table["units_source"] == "table_text"
    assert "$198.89" in table["markdown"]
    assert "| Total | 19.5 |  | 19.5 |  |" in table["markdown"]
    assert cells_follow_source(table["rows"], raw_html_text(REPURCHASE.read_text()))


def test_markdown_joins_dollars_and_keeps_parentheses() -> None:
    """$ and % join the adjacent number. A parenthesized amount stays parenthesized."""
    html = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<table>
<tr><td></td><td colspan="2">Year Ended</td><td colspan="2">Year Ended</td></tr>
<tr><td></td><td colspan="2">Jan 25, 2026</td><td colspan="2">Jan 26, 2025</td></tr>
<tr><td>Revenue</td><td>$</td><td>215,938</td><td>$</td><td>130,497</td></tr>
<tr><td>Interest expense</td><td>$</td><td>(259)</td><td>$</td><td>(272)</td></tr>
<tr><td>Margin</td><td>12.5</td><td>%</td><td>11.0</td><td>%</td></tr>
</table>
</body></html>"""
    elements = parse_filing(html, META)
    table = next(element for element in elements if element["element_type"] == "table")
    assert rows_are_aligned(table["rows"])
    assert "(259)" in table["markdown"]
    assert "-259" not in table["markdown"]
    assert "$215,938" in table["markdown"]
    assert "$(259)" in table["markdown"]
    assert "12.5%" in table["markdown"]
    assert table["grid"][2] == ["Revenue", "$215,938", "$130,497"]
    assert table["grid"][3] == ["Interest expense", "$(259)", "$(272)"]
    assert has_negative_amount([table["grid"][3]])


def test_nvda_income_statement_collapses_to_one_column_per_year() -> None:
    """NVDA-2026-00748 keeps one value per period, with $ joined to the amount."""
    root = Path(__file__).resolve().parents[1]
    filing = next(
        item
        for item in read_manifest(root / "data" / "manifest.json")
        if item["ticker"] == "NVDA" and item["period_end"] == "2026-01-25"
    )
    path = root / filing["path"]
    if not path.is_file():
        pytest.skip("NVDA 2026 filing is not in data/raw")
    elements = parse_filing(path.read_text(encoding="utf-8", errors="replace"), META)
    table = next(element for element in elements if element["id"] == "NVDA-2026-00748")
    assert table["section_role"] == "financial_statements"
    assert table["rows"][2] == [
        "Revenue",
        "$",
        "215,938",
        "$",
        "130,497",
        "$",
        "60,922",
    ]
    assert all(len(row) == 4 for row in table["grid"])
    assert table["grid"][0] == ["", "Year Ended", "Year Ended", "Year Ended"]
    assert table["grid"][1] == ["", "Jan 25, 2026", "Jan 26, 2025", "Jan 28, 2024"]
    assert table["grid"][2] == ["Revenue", "$215,938", "$130,497", "$60,922"]
    assert table["grid"][3] == ["Cost of revenue", "62,475", "32,639", "16,621"]
    assert "$215,938" in table["markdown"]
    assert is_financial_table(table["grid"])
    assert expand_grid(table["grid"], table["rows"]) == table["rows"]


def test_inline_fact_attributes_stay_on_the_amount_cell() -> None:
    """scale, sign, and contextRef ride with the number, not the dollar sign."""
    html = """<html xmlns="http://www.w3.org/1999/xhtml"
        xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">
<body>
<table>
<tr><td></td><td colspan="2">Jan 25, 2026</td></tr>
<tr><td>Revenue</td><td>$</td><td>
  <ix:nonFraction name="us-gaap:Revenues" contextRef="c-1" scale="6"
    decimals="-6" unitRef="usd" id="f-72">215,938</ix:nonFraction>
</td></tr>
<tr><td>Tax</td><td>$</td><td>
  <ix:nonFraction name="us-gaap:DeferredIncomeTaxExpenseBenefit" contextRef="c-1"
    scale="6" sign="-" decimals="-6">(1,424)</ix:nonFraction>
</td></tr>
</table>
</body></html>"""
    elements = parse_filing(html, META)
    table = next(element for element in elements if element["element_type"] == "table")
    revenue = table["facts"][1][1]
    assert len(revenue) == 1
    assert revenue[0]["name"] == "us-gaap:Revenues"
    assert revenue[0]["context_ref"] == "c-1"
    assert revenue[0]["scale"] == 6
    assert revenue[0]["sign"] is None
    assert revenue[0]["decimals"] == "-6"
    assert revenue[0]["text"] == "215,938"
    assert table["facts"][1][0] == []
    tax = table["facts"][2][1][0]
    assert tax["sign"] == "-"
    assert tax["text"] == "(1,424)"


def test_grid_expands_back_to_the_logical_rows() -> None:
    """Collapsed cells, read in order, are the same values as the logical grid."""
    repurchase = parse_filing(REPURCHASE.read_text(), META)
    table = next(
        element for element in repurchase if element["element_type"] == "table"
    )
    assert expand_grid(table["grid"], table["rows"]) == table["rows"]

    html = """<html xmlns="http://www.w3.org/1999/xhtml"><body>
<table>
<tr><td></td><td colspan="2">Year Ended</td><td colspan="2">Year Ended</td></tr>
<tr><td></td><td colspan="2">Jan 25, 2026</td><td colspan="2">Jan 26, 2025</td></tr>
<tr><td>Revenue</td><td>$</td><td>215,938</td><td>$</td><td>130,497</td></tr>
<tr><td>Interest expense</td><td>$</td><td>(259)</td><td>$</td><td>(272)</td></tr>
<tr><td>Margin</td><td>12.5</td><td>%</td><td>11.0</td><td>%</td></tr>
</table>
</body></html>"""
    sample = parse_filing(html, META)
    sample_table = next(
        element for element in sample if element["element_type"] == "table"
    )
    assert (
        expand_grid(sample_table["grid"], sample_table["rows"]) == sample_table["rows"]
    )

    root = Path(__file__).resolve().parents[1]
    filing = next(
        item
        for item in read_manifest(root / "data" / "manifest.json")
        if item["ticker"] == "NVDA" and item["period_end"] == "2026-01-25"
    )
    path = root / filing["path"]
    if not path.is_file():
        return
    elements = parse_filing(path.read_text(encoding="utf-8", errors="replace"), META)
    tables = [element for element in elements if element["element_type"] == "table"]
    assert tables
    for element in tables:
        assert expand_grid(element["grid"], element["rows"]) == element["rows"]
