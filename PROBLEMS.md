# Problems

## P-001: Filing index JSON type is an icon name (Step 1)

- **Date:** 2026-10-07
- **Symptom:** The dry-run rejected `nvda-20260125.htm` because its index type was `text.gif`.
- **Root cause:** `index.json` uses `type` for a file icon (`text.gif`, `image2.gif`), not the EDGAR form type. The form type is the Type column in the filing index HTML.
- **Fix:** Confirm the primary document from that HTML Type column. It must be exactly `10-K`.
- **Verification:** The saved index-table test passes. The live dry-run then selected 18 documents whose index Type column is 10-K.
- **Prevention:** The confirmation test includes both a 10-K row and an exhibit row.
- **Status:** resolved

## P-002: Table cells were checked against the parser, and line breaks were glued together (Step 2)

- **Date:** 2026-10-07
- **Symptom:** The first spot check reported zero misses, and a date such as January 28, 2024 could satisfy the comma-amount test.
- **Root cause:** The check searched each cell inside `_visible_text`, which is the same walker that builds the cell. A `<br/>` contributed no space, so `$<br/>Change` became `$Change` and `28<br/>2024` became `28,2024` when a comma sat on the other side of the break.
- **Fix:** A line break is a space. The spot check now searches tag-stripped HTML from `raw_html_text`, which does not call the cell walker. `finrag-parse` draws 10 tables per filing with seed 13 and also checks every table.
- **Verification:** After the change, sample misses are 0 and all-table misses are 0. Financial tables are 711, of which 706 have units (0.9930).
- **Prevention:** `tests/test_parse.py` checks `$<br/>Change` against the tag-stripped HTML, and it rejects a bare age or an EIN as a negative amount.
- **Status:** resolved

## P-003: Item 8 is a cross-reference in some filings (Step 2)

- **Date:** 2026-10-07
- **Symptom:** NVIDIA and Qualcomm have 2 elements labeled item 8. Microchip has 55 elements labeled item 8, of which 2 are tables. AMD, Texas Instruments, and Broadcom have the statements under item 8.
- **Root cause:** NVIDIA Item 8 and Qualcomm Item 8 point at the statements, which are printed later under Item 15 and Item 16. Microchip Item 8 points at Item 15, and the statement section then starts again at `Item 1. Financial Statements`, so those statements are labeled item 1.
- **Fix:** The `item` field still follows the heading in the file. A separate `section_role` is set from that heading and is the same label for every company: `business`, `risk_factors`, `mdna`, `financial_statements`, `notes`, or `other`. Item 1A is `risk_factors`, Item 7 is `mdna`, Item 8 is `financial_statements`, and Item 1 is `business` unless the heading says financial statements. A later statement title such as `Consolidated Statements of Income` sets `financial_statements` again, which is how Item 15 and Item 16 statements are labeled. `Notes to ... Financial Statements` sets `notes` only from the statements or from `other`, so an MD&A mention does not take the rest of that section.
- **Verification:** `finrag-parse` on 2026-10-09. NVIDIA `Consolidated Statements of Income` is `NVDA-2026-00746`, item 15, `financial_statements`, and the income-statement table `NVDA-2026-00748` has the same item and role. Qualcomm `CONSOLIDATED STATEMENTS OF OPERATIONS` is `QCOM-2025-00658`, item 16, `financial_statements`, and table `QCOM-2025-00660` matches. Microchip `CONSOLIDATED STATEMENTS OF OPERATIONS` is `MCHP-2026-01061`, item 1, `financial_statements`. Role counts for each filing are in the 2026-10-09 parse report.
- **Prevention:** Use `section_role` when a question needs the statements. Do not require item 8.
- **Status:** resolved

## P-004: Empty cells were dropped, so table rows did not share a column count (Step 2)

- **Date:** 2026-10-09
- **Symptom:** The NVIDIA repurchase Total row parsed as `Total`, `19.5`, `19.5`. The price and remaining-authorization cells are empty, so the row was shorter than the header.
- **Root cause:** `table_rows` ignored `colspan` and `rowspan` and skipped empty cells. Spacer columns and the empty Total cells both disappeared, and a merged header was not repeated across the columns it covers.
- **Fix:** Each cell is placed at the column where it starts, after colspan and rowspan. A logical column is a column where some non-empty cell starts. Spacer columns that never start a cell are removed. A merged header is copied onto each logical column it covers. An empty data cell stays, so every row has the header's width. Markdown joins `$` or `%` into the adjacent amount. Parentheses stay as written.
- **Verification:** `finrag-parse` on 2026-10-09 reports `misaligned_tables=0` across 1,320 tables. `tests/test_parse.py` parses the NVDA-2026-00491 table and expects the Total row `['Total', '19.5', '', '', '19.5', '', '']`.
- **Prevention:** `rows_are_aligned` is checked for every table. `finrag-parse` exits non-zero if any table fails it.
- **Status:** resolved

## P-005: Parentheses and the sign attribute disagree (Step 3)

- **Date:** 2026-10-11
- **Symptom:** 201 cells match on absolute value and are reported as sign mismatches. 164 show parentheses while the `sign` attribute is absent. 37 have `sign="-"` while the cell shows an unsigned number.
- **Root cause:** The parentheses are drawn outside `ix:nonFraction`. NVIDIA interest expense on `NVDA-2026-00748` is the cell `(259)` and the tag text `259` with no `sign` attribute. Company-facts for that accession, start `2025-01-27` and end `2026-01-25`, is `259000000`, which is positive. The other 37 cells, such as AMD `AMD-2025-00707` cell `r4c1` (`$2,254`), carry `sign="-"` and do not put parentheses in the cell text.
- **Fix:** The check compares the absolute displayed amount with the absolute XBRL amount, and it reports the sign disagreement on its own. It does not treat parentheses as the XBRL sign.
- **Verification:** `finrag-xbrl` on 2026-10-11. Financial-statement absolute match rate is 2202/2205. The 201 sign rows are in `data/xbrl/mismatches.jsonl` with cause `sign`.
- **Prevention:** A sign mismatch is not counted in the absolute match rate.
- **Status:** recorded

## P-006: MD&A reprints and a few note amounts have no inline tag (Step 3)

- **Date:** 2026-10-11
- **Symptom:** 255 numeric cells have no `ix:nonFraction`. 251 of them are in `mdna`. The MD&A absolute match rate is 0/251. Four note cells are also untagged.
- **Root cause:** The MD&A tables repeat statement numbers without inline tags. NVIDIA `NVDA-2026-00574` (`Revenue by Reportable Segments`) is one of them. The same amounts are tagged on the financial statements. The four note cells are AMD goodwill reassignment `(126)` and `(238)` on `AMD-2025-00729`, and two geographic amounts `$1,143` and `$1,589` on `AMD-2023-00731` (`NOTE 4 – Segment Reporting`).
- **Fix:** Those cells are reported as `missing tag`. The checker does not copy a tag from another table.
- **Verification:** `data/xbrl/mismatches.jsonl` has 251 `mdna` rows and 4 `notes` rows with cause `missing tag`.
- **Prevention:** Question generation can use the tagged statement cell for these amounts.
- **Follow-up:** On 2026-10-21 these 255 cells are reported as untagged counts, not as failures in the match rate. MD&A has 251. Notes have 4.
- **Status:** recorded

## P-007: Some note columns do not print the fact's period end (Step 3)

- **Date:** 2026-10-11
- **Symptom:** 17 cells are `header-period parse failure` after the header reader accepts a split date, a later date in the same column, and a year-only header.
- **Root cause:** Fourteen are AMD goodwill rollforwards. `AMD-2023-00762` has 12 and `AMD-2025-00729` has 2. An activity column is labeled `Acquisitions`, or the amount sits between two balance dates, and the fact's end is the closing date rather than a date printed in that column. The other three are Qualcomm `IncomeLossFromContinuingOperations` in the oldest income-statement column: `QCOM-2025-00660` `r17c3` context end `2023-06-25` under header `2023-09-24`, and the same column in `QCOM-2024-00699` (`2022-06-26` vs `2022-09-25`) and `QCOM-2023-00690` (`2021-06-27` vs `2021-09-26`).
- **Fix:** The fourteen AMD cells were a checker bug and are fixed in P-008. The three Qualcomm cells stay in the mismatch file. The June context is the one on the tag, and the checker does not replace it with the September header.
- **Verification:** After the header changes, header failures fell from 1,160 to 17. Notes absolute match rate is 757/775.
- **Prevention:** Tests cover a split `December 31,` / `2025` header, a second date lower in the column, and a year-only header.
- **Follow-up:** Fourteen of these seventeen were a rollforward bug, fixed in P-008. The three Qualcomm cells are the filing's own context, not a parser bug.
- **Status:** recorded

## P-008: Rollforward activity cells were tied to the opening date (Step 3)

- **Date:** 2026-10-21
- **Symptom:** Fourteen note cells were `header-period parse failure`. The fact's end date was the closing balance, and the checker compared it with the opening date or with no date at all.
- **Root cause:** In a goodwill rollforward, an activity row sits between two stub dates, and an activity column sits to the left of the closing-date header. The checker used only a date above the cell or in the same column. `Acquisitions` has no date of its own.
- **Fix:** When the cell's own column has no date, the context end may match the next stub date below or the next dated header to the right. A date printed in the column still has to match exactly, so a disagreeing column header is unchanged.
- **Verification:** After the fix, header-period failures are the three Qualcomm cells below. Tagged note cells match 771/771. `tests/test_xbrl.py` covers an activity row, an activity column, and a column date that still disagrees.
- **The fourteen cells that were the bug:**

| table id | cell | expected | parsed before the fix | cause |
|---|---|---|---|---|
| AMD-2025-00729 | r4c1 | 2025-12-27 | 2024-12-28 | header-period parse failure |
| AMD-2025-00729 | r4c6 | 2025-12-27 | 2024-12-28 | header-period parse failure |
| AMD-2023-00762 | r3c3 | 2022-12-31 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r4c2 | 2022-12-31 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r4c3 | 2022-12-31 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r6c2 | 2022-12-31 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r6c3 | 2022-12-31 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r6c5 | 2023-12-30 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r7c5 | 2023-12-30 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r8c3 | 2022-12-31 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r9c3 | 2022-12-31 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r9c5 | 2023-12-30 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r10c2 | 2022-12-31 | unparsed header | header-period parse failure |
| AMD-2023-00762 | r10c5 | 2023-12-30 | unparsed header | header-period parse failure |

- **The three financial-statement mismatches are a filer tagging quirk, recorded in P-009.** The parser copied the `contextRef` that is on the tag.

- **The eighteen note mismatches before the fix** were the fourteen rows above plus these four. The four have no `ix:nonFraction` in the HTML. `(126)` and `(238)` are `ix:nonNumeric` text facts named `GoodwillChangeInGoodwillAllocationDescription`. `$1,143` and `$1,589` are plain text. They stay untagged and are not in the tagged match rate.

| table id | cell | expected | parsed | cause |
|---|---|---|---|---|
| AMD-2025-00729 | r3c3 |  | (126) | missing tag |
| AMD-2025-00729 | r3c4 |  | (238) | missing tag |
| AMD-2023-00731 | r2c1 |  | $1,143 | missing tag |
| AMD-2023-00731 | r9c1 |  | $1,589 | missing tag |

- **Prevention:** A column that already prints a date cannot be rescued by a neighboring date.
- **Status:** resolved

## P-009: Qualcomm continuing-operations tag uses a June context (Step 3)

- **Date:** 2026-10-21
- **Symptom:** Three income-statement cells fail the header-period check. The column is a September year end. The fact's context ends in June of that same fiscal year. These are the only tagged absolute mismatches in the financial statements.
- **Root cause:** The filer put a June `contextRef` on `us-gaap:IncomeLossFromContinuingOperations` in the oldest column. Neighboring rows in that column use the September context. The parser stored the tag that is inside the cell. The row label on all three is `Income from continuing operations`.
- **QCOM-2025-00660 r17c3**, column header `September 24, 2023`, cell text `7,339`. Context `c-11` is 2022-09-26 to 2023-06-25. Tag: `<ix:nonFraction unitRef="usd" contextRef="c-11" decimals="-6" name="us-gaap:IncomeLossFromContinuingOperations" format="ixt:num-dot-decimal" scale="6" id="f-173">7,339</ix:nonFraction>`.
- **QCOM-2024-00699 r17c3**, column header `September 25, 2022`, cell text `12,986`. Context `c-13` is 2021-09-27 to 2022-06-26. Tag: `<ix:nonFraction unitRef="usd" contextRef="c-13" decimals="-6" name="us-gaap:IncomeLossFromContinuingOperations" format="ixt:num-dot-decimal" scale="6" id="f-167">12,986</ix:nonFraction>`.
- **QCOM-2023-00690 r17c3**, column header `September 26, 2021`, cell text `9,043`. Context `c-9` is 2020-09-28 to 2021-06-27. Tag: `<ix:nonFraction unitRef="usd" contextRef="c-9" decimals="-6" name="us-gaap:IncomeLossFromContinuingOperations" format="ixt:num-dot-decimal" scale="6" id="f-161">9,043</ix:nonFraction>`.
- **Fix:** Leave the three mismatches. Do not rewrite the context to the column header. Company-facts stores the same concept with that June-ending context: 272 days, for example 2022-09-26 to 2023-06-25 with value `7339000000`, and again for 2021-09-27 to 2022-06-26 (`12986000000`) and 2020-09-28 to 2021-06-27 (`9043000000`). A full-year fact with the same value is also present. `us-gaap:IncomeLossFromContinuingOperations` must not be used as a metric without a period check.
- **Verification:** The raw tag, the context dates, and the parsed cell agree with each other on all three filings.
- **Prevention:** A printed column date that disagrees with `contextRef` stays a header-period failure. `test_a_printed_column_date_that_disagrees_stays_a_mismatch` locks that.
- **Status:** recorded
