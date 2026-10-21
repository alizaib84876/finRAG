# Decisions

## D-005: Definition of a financial table for the units measure (Step 2)

- **Context:** The done-when bar is a measured units rate of at least 95 percent of financial tables. The same filings also contain cover pages, property tables, share-repurchase tables, and $100 stock graphs with comma-grouped numbers.
- **Options:** Count every table that contains a comma-grouped number. Count only tables that also look like a financial statement and record where the units line was found.
- **Decision:** A table is financial for this measure when all of the following hold. It has at least two rows. The joined cell text matches a comma-grouped amount, `\d{1,3}(?:,\d{3})+(?:\.\d+)?`. The joined cell text does not match square feet, `sq. ft.`, trading symbol, title of each class, defined terms, shares of common stock to be sold, shares purchased, or `$100 invested`. It is not a cumulative-return graph, which is text containing both `$100.00` and `S&P`. Units are stored with `units_source` in this order: `caption` (non-table text in the same block), `preceding` (a units statement in the previous eight blocks), `table_text` (the phrase inside the cells), `fallback` (the latest filing-wide scale statement, and only when the table contains `$`).
- **Consequences:** On 2026-10-07, and again on 2026-10-09 after the column grid, `finrag-parse` counted 711 financial tables. 706 have a units line, which is 0.9930. Excluding the 5 financial tables that have no units line, the rate is 706/706 = 1.0000. Those 5 are two AMD Item 9B trading-arrangement tables and three Qualcomm capital-stock rollforwards. An earlier count of 18 included 13 lease, percent, amortization, and assumption tables that matched only because a line break glued a date into a comma-amount such as `28,2024`. Those 13 are no longer in the financial set. A second coverage, measured on 2026-10-09 and not a change to this definition, counts every table that contains a `$` cell or a units phrase (`in thousands`, `in millions`, `in billions`, `per share`, `percent`, or `%`). That set is 1,046 tables, of which 925 have a units line, which is 0.8843. The 121 without a units line are outside this financial-table definition: 92 are percent-only, and the other 29 have a `$` without a scale phrase the resolver stores.

## D-009: Segment and per-cell facts come from inline XBRL (Step 3)

- **Context:** The parser check needs one XBRL fact per table cell, including segment breakdowns. SEC company-facts is the bulk source for entity-wide metrics.
- **Options:** Read every fact from company-facts. Or use company-facts for entity-wide metrics and the filing's inline tags for the cell check.
- **Decision:** Company-facts stays the source for the metrics table. The SEC EDGAR API page, last reviewed April 8, 2025, says the XBRL APIs keep facts that use a standard taxonomy and apply to the entire filing entity. A downloaded company-facts record has `start`, `end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, and `frame`, and no dimension members. Segment facts and the per-cell check use `ix:nonFraction` in the filing: `contextRef`, `scale`, `sign`, and `decimals` are stored on the cell. `fy` is the filing's fiscal-year focus, so a period is identified by `start` and `end`, or by `end` alone for an instant.
- **Consequences:** The sign of a fact is the `sign` attribute. Parentheses in the displayed cell are not the XBRL sign. Absolute value and sign are checked separately.

## D-007: Filter and chunk on section_role, not item (Step 2)

- **Context:** The `item` field copies the Item heading as printed. That heading is not the statements section for every company. Microchip prints `Item 8` as a pointer and then restarts the statements at `Item 1. Financial Statements`, so those tables have `item` 1. NVIDIA's statements are under Item 15 and Qualcomm's under Item 16.
- **Options:** Filter and store chunk metadata from `item`. Or filter and store chunk metadata from `section_role`, which uses the same labels for every company.
- **Decision:** `item` stays the heading as printed and is unreliable for Microchip. `section_role` is the field used for all filtering and chunk metadata from now on.
- **Consequences:** Later steps select financial statements, notes, MD&A, risk factors, and business with `section_role`. `item` remains on the element for debugging the printed heading.

## D-008: Collapsed grid is the table used for numbers (Step 2)

- **Context:** The logical grid repeats a colspan across every column it covers and leaves `$` and `%` in their own columns. Numeric checks and markdown need one value under each period header.
- **Options:** Use the logical grid everywhere. Or keep it for debugging and store a collapsed grid for markdown, units, and numeric checks.
- **Decision:** `rows` is the logical grid and is for debugging and the raw-HTML spot check. `grid` is one column per header period: `$` and `%` are joined into the amount, and a repeated span is stored once. Markdown, `text`, `column_units`, and the financial-table checks read `grid`.
- **Consequences:** `NVDA-2026-00748` is four columns: the line label and one column for each of Jan 25, 2026, Jan 26, 2025, and Jan 28, 2024. Revenue is `$215,938`, `$130,497`, and `$60,922`.

## D-006: Logical columns and a section role (Step 2)

- **Context:** Filing tables use colspan for year headers and for spacer columns. Dropping empty cells made the NVIDIA share-repurchase Total row shorter than its header. The item number in the file is not the same home for the statements at every company: NVIDIA prints them under Item 15, Qualcomm under Item 16, and Microchip restarts them at Item 1.
- **Options:** Keep one cell per visible `<td>` and leave the item number as the only section label. Or build a column from each place a non-empty cell starts, and store a separate role that uses the same names for every company.
- **Decision:** A logical column is a column index where a non-empty cell starts, after colspan and rowspan. Spacer columns that never start a cell are removed. Header text is repeated across the logical columns that cell covers. Empty data cells stay, so each row has the header width. Markdown joins a `$` or `%` column into the adjacent amount and leaves parentheses as written. `column_units` keeps `in millions`, `in billions`, `in thousands`, `per share`, and `percent` from the header text of that column. `units` and `units_source` stay on the table. `section_role` is `business`, `risk_factors`, `mdna`, `financial_statements`, `notes`, or `other`. The `item` field is unchanged.
- **Consequences:** On 2026-10-09 every one of the 1,320 tables has one logical width (`misaligned_tables=0`). 549 tables have a unit phrase on at least one column header. Financial-table `units_source` counts are unchanged, including 195 fallback tables. Across every table, not only the financial set, 313 use `units_source=fallback`.

## D-004: Parse 10-K HTML with lxml (Step 2)

- **Context:** Step 2 turns each 10-K into headings, paragraphs, and tables. The plan allows lxml or BeautifulSoup and forbids a PDF conversion. The eighteen filings are XML documents with inline XBRL.
- **Options:** lxml, treating the file as XML. BeautifulSoup on the same markup.
- **Decision:** Use lxml 6.1.3, the version `uv add lxml` installed, and `XMLParser`. Read the XHTML directly. Do not convert to PDF.
- **Consequences:** Namespaces stay intact, so inline XBRL tags can be skipped. A filing that is not well-formed XML will fail the parse instead of being guessed through HTML recovery.

## D-003: Fiscal year label from the SEC period end (Step 1)

- **Context:** Each 10-K has a period of report in SEC submissions data. NVIDIA's fiscal year ends in January, so most of that year falls in the prior calendar year. The label has to be derived, not guessed.
- **Options:** Label the fiscal year as the calendar year of the period end. Label it as the prior calendar year when the period ends in January.
- **Decision:** `period_end` is the SEC `reportDate` and is authoritative. The fiscal year label is the calendar year of that date. A January period end is stored with `fiscal_year_ambiguous: true` and called out before download. `fiscal_year_end` for that filing is the same period-end date.
- **Consequences:** A year ended 26 January 2025 is labeled 2025 and flagged. December, March, September, and November year ends are not flagged. The label can be changed if the flag is rejected.

## D-002: Semiconductor corpus, 10-K only (Step 1)

- **Context:** The corpus is one sector and three direct-competitor pairs, about six companies, three fiscal years each. Questions later have to survive different fiscal year ends. Amended filings would duplicate or replace the original annual report.
- **Options:** Semiconductors or cloud software. Within semiconductors, the approved pairs are NVIDIA/AMD, Texas Instruments/Microchip, and Qualcomm/Broadcom. Filing form 10-K only, or 10-K plus 10-K/A.
- **Decision:** Semiconductors. Pairs are NVIDIA/AMD, Texas Instruments/Microchip, and Qualcomm/Broadcom. Keep form type 10-K only. Exclude 10-K/A.
- **Consequences:** Eighteen primary 10-K documents if every company has three. CIKs, accession numbers, and URLs come from SEC submissions data, not from memory. A company with fewer than three 10-K filings is replaced before download. Fiscal year ends are taken from those filings.
