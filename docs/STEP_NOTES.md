# Step notes

Each step ends with one entry here: what it built, why, what could go wrong, and how to explain it.

## Step 0 — Bootstrap

The repo is a Python project managed by uv, on Python 3.12. Postgres 16 with pgvector 0.8.7 starts from Docker Compose, and the first boot creates the `vector` extension. Ruff, Black, and pytest run locally and in GitHub Actions. Config lives in YAML. The CI job does not need a database: the pgvector test skips when `DATABASE_URL` is unset.

This exists so later steps have one way to install, lint, test, and store embeddings. Without it, every later change would invent its own setup.

What could go wrong is a silent skip. The vector test passes in CI because it never connects. A real embedding bug shows up only when Compose is running. The other trap is treating the local database password as a secret worth publishing. It is only for the container on this machine.

In an interview I would say: I stood up the project so the evaluation harness, not a demo chat box, is what we can run and gate on. The database is there for vectors, and the test suite still runs without it.

## Step 1 — Corpus

The downloader pulls the latest three 10-Ks for NVIDIA, AMD, Texas Instruments, Microchip, Qualcomm, and Broadcom. That is 18 filings. The manifest stores the filing URL, the period end, the fiscal-year label, and a SHA-256 of the file. A download that is already on disk with the same hash is left alone. The primary document has to be the 10-K itself, not an exhibit. Requests use a contact User-Agent from the environment and stay near five per second.

The fiscal year label is the calendar year of the period end. NVIDIA's year ends in January, so those filings are flagged ambiguous instead of being renamed to the prior calendar year.

This exists so every later number can be tied to a file we can re-fetch and checksum.

What could go wrong is grabbing an exhibit that looks like the annual report, or trusting the filing index's icon name as the form type. The index says `text.gif` for the HTML file. The form type is a different column, and it has to be exactly `10-K`. Another miss is calling NVIDIA's January 2026 year "fiscal 2025" because the year started in 2025. We label it 2026 and flag it.

In an interview I would say: the corpus is small on purpose, six chip companies and three years, and the manifest is the contract. I can rebuild it, I can prove a file did not change, and I did not quietly relabel NVIDIA's fiscal year.

## Step 2 — Parser

Each 10-K is HTML with inline XBRL, so the parser is lxml, not a PDF conversion. It writes headings, paragraphs, and tables in document order. `section_role` is the label used everywhere after this: business, risk factors, MD&A, financial statements, notes, or other. The printed item number is kept and is not trusted. Microchip restarts the statements at Item 1, NVIDIA prints them under Item 15, and Qualcomm under Item 16.

Tables have two grids. `rows` is the logical grid, including empty cells, so a total row stays aligned. `grid` collapses `$` and `%` into the amount and keeps one column per period. Markdown and numeric work use `grid`. A spot check compares cell text with the tags stripped out of the raw HTML, not with the parser's own text walker. On the run that accepted this step, all 1,320 tables were aligned, sample misses were zero, and 706 of 711 financial tables had a units line.

This exists so retrieval and the XBRL check share one structure, and so a formatting choice cannot mark its own homework.

What could go wrong is treating the item number as the section, dropping empty cells and shifting the columns, or counting a colspan once per year and calling the extra letters a parsing bug. The stored text is a bit longer than the source because a spanned header is repeated. Counting each source cell once, the gap is the filename in the HTML head.

In an interview I would say: I parse the filing the company filed, I keep the section label separate from the printed item number, and I check the cells against the raw HTML. The collapsed grid is for numbers. The logical grid is for debugging.

## Step 3 — XBRL ground truth

Company-facts supplies the entity-wide metrics. It has no segment dimensions, so the per-cell check uses `ix:nonFraction` in the filing: the tag, the context, the scale, and the sign attribute. Periods are the fact's start and end. `fy` is the filing's fiscal-year focus, which is why a comparative year in NVIDIA's 2026 10-K still says `fy` 2026.

The metrics table covers all 18 company-years for eight metrics. Revenue, cost, profit, R&D, SG&A, and assets come from a tag list in config. The first tag wins. A later tag is marked `alternate-tag`. NVIDIA, Qualcomm, AMD, and Texas Instruments use that alternate tag for every year. Broadcom uses `ProfitLoss` for every year on the FY2023 and FY2025 filings. Qualcomm has no gross-profit tag, so that row is `derived` from revenue minus cost. If two filings report different values for the same period, every one of those rows is `restated`. The only restatements in this corpus are AMD's selling, general and administrative expense. For the year ending 2023-12-30, accession `0000002488-26-000018` reports 2,318,000,000 and accessions `0000002488-25-000012` and `0000002488-24-000012` report 2,352,000,000. For the year ending 2024-12-28, `0000002488-26-000018` reports 2,735,000,000 and `0000002488-25-000012` reports 2,783,000,000.

The cell check compares absolute value and sign separately. Parentheses are not the XBRL sign. D-010 says a numeric answer for a natural-positive concept, one whose company-facts value is zero or positive, matches on absolute value. A negative company-facts value keeps its sign. D-011 covers the 37 reconciling cells where the fact is negative and the page prints an unsigned number: the filing's presentation sets the direction, and a golden question names expense, reduction, or add-back, or it avoids a sign-dependent answer.

Tagged-cell match rates, from the 2026-10-21 run: financial statements 2,202 of 2,205, notes 771 of 771. Untagged cells are reported separately: 251 in MD&A and 4 in the notes. Those MD&A tables repeat numbers that are tagged on the statements. Fourteen earlier header failures were a rollforward bug: activity columns and rows belong to the closing date. That is fixed. After that fix, 89 matched cells still have no date in their own column and none on their own row. Seventy-five are NVIDIA segment rows sitting under a "Year Ended" stub. Fourteen are the AMD goodwill activity cells. Another 198 matched cells have only a four-digit year in the header. The 89 are the ones verified without a date of their own.

The three remaining financial-statement misses are a Qualcomm tagging choice, not a parse error. The row is `Income from continuing operations` and the concept is `us-gaap:IncomeLossFromContinuingOperations`. In `QCOM-2025-00660` r17c3 the column says September 24, 2023 and the tag is `<ix:nonFraction unitRef="usd" contextRef="c-11" decimals="-6" name="us-gaap:IncomeLossFromContinuingOperations" format="ixt:num-dot-decimal" scale="6" id="f-173">7,339</ix:nonFraction>`, context `c-11` from 2022-09-26 to 2023-06-25. `QCOM-2024-00699` r17c3 is `12,986` on `c-13`, 2021-09-27 to 2022-06-26, under September 25, 2022. `QCOM-2023-00690` r17c3 is `9,043` on `c-9`, 2020-09-28 to 2021-06-27, under September 26, 2021. The parser stored the context that is on the tag. P-009 records that.

Of the 201 sign mismatches, 164 are the D-010 case: a natural-positive concept, no `sign` attribute, printed in parentheses. The other 37 are not that case. Thirty-one are AMD segment reconciliation lines (`AMD-2025-00707`, `AMD-2024-00718`, `AMD-2023-00724`) for amortization, stock-based compensation, acquisition costs, restructuring, inventory write-down, and other expense. The tag has `sign="-"` and the cell shows an unsigned number such as `$2,254`. They are dimensional, so company-facts has no value. Six are Qualcomm `Other (Note 2)`, `us-gaap:OtherOperatingIncomeExpenseNet`, on `QCOM-2025-00660` r10c1 through r10c3, `QCOM-2024-00699` r10c1 and r10c2, and `QCOM-2023-00690` r10c1. The company-facts values are negative (`-39000000`, `-179000000`, `-862000000`), the tag has `sign="-"`, and the cell shows `39`, `179`, or `862` with no parentheses.

The 42 `alternate-tag` rows are nine company-years each, except Broadcom:

- NVIDIA revenue, `us-gaap:Revenues`, fiscal years 2022, 2023, 2024, 2025, and 2026, each reported in the filings that include that year.
- AMD cost of revenue, `us-gaap:CostOfGoodsAndServicesSold`, fiscal years 2021 through 2025.
- Texas Instruments cost of revenue, the same tag, fiscal years 2021 through 2025.
- Qualcomm revenue, `us-gaap:Revenues`, fiscal years 2021 through 2025.
- Broadcom net income, `us-gaap:ProfitLoss`, six rows: fiscal 2021, 2022, and 2023 in the FY2023 filing, and fiscal 2023, 2024, and 2025 in the FY2025 filing.

Broadcom's `ProfitLoss` amount is the net income line. In the FY2025 statement `AVGO-2025-00679` the line is `$23,126`, `$5,895`, `$14,082`, which is 23,126,000,000, 5,895,000,000, and 14,082,000,000. In the FY2023 statement `AVGO-2023-00755` the line is `$14,082`, `$11,495`, `$6,736`, which is 14,082,000,000, 11,495,000,000, and 6,736,000,000. Each of those equals the `ProfitLoss` row for that year. The FY2024 statement's current-year net income is also `ProfitLoss` of `$5,895`, the same amount.

The hand check, seed 13, has 30 rows, including three NVIDIA segment cells, rows 28 to 30: `NVDA-2026-00931` r3c1 `$193,479` (tag value 193,479,000,000), `NVDA-2025-00916` r3c1 `$116,193` (116,193,000,000), and `NVDA-2024-00905` r3c1 `$47,405` (47,405,000,000). On 2026-10-21 the values were compared with the original filings for NVIDIA, Broadcom, AMD (both filings), Texas Instruments, and Qualcomm, and all matched. Microchip was not hand-checked.

This exists so question answers can be checked against the company's own numbers, and so the parser is checked by something that is not the parser.

What could go wrong is grading an expense wrong because the page shows parentheses and the fact is positive. Or calling a restatement a parser bug. Or treating MD&A reprints with no tags as failed parses. Or using `fy` to name a comparative year.

In an interview I would say: I built a small audited numbers table from SEC company-facts, I checked the parser against the inline tags, and I separated "the page has no tag" from "the tag and the cell disagree." The match rate on tagged statement cells is 2,202 out of 2,205. I can name the three that miss and why. I compared the hand-check values with the original filings for NVIDIA, Broadcom, AMD, Texas Instruments, and Qualcomm, and they matched. Microchip was not hand-checked.
