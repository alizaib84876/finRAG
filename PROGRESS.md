# Progress

**Current step:** 4
**Last updated:** 2026-10-21

## Step status

| Step | Title | Status | Done date |
|---|---|---|---|
| 0 | Bootstrap | done | 2026-10-07 |
| 1 | Corpus selection and downloader | done | 2026-10-07 |
| 2 | Parse filings into structured elements | done | 2026-10-11 |
| 3 | XBRL ground-truth extraction | done | 2026-10-21 |
| 4 | Golden set v1 | not started | |

## Done when

- Metrics table covers every company-year for at least eight metrics: met. 18 filings, eight metrics on every own year (`revenue`, `cost_of_revenue`, `gross_profit`, `operating_income`, `net_income`, `research_and_development`, `selling_general_and_administrative`, `total_assets`). 414 metric rows, including comparatives. NVIDIA January period ends stay `fiscal_year_ambiguous`.
- Hand cross-check passes: met on 2026-10-21 for NVIDIA, Broadcom, AMD (both filings), Texas Instruments, and Qualcomm. Every compared value matched the original filing. Microchip was not hand-checked. `data/xbrl/hand_check.json` still has 30 rows, seed 13. Rows 28 to 30 are one NVIDIA segment cell from each of `NVDA-2026-00931`, `NVDA-2025-00916`, and `NVDA-2024-00905`.

## Current session

- Done: Step 3. The hand check matched the original filings for NVIDIA, Broadcom, AMD (both filings), Texas Instruments, and Qualcomm. Microchip was not hand-checked.
- Next: Step 4, golden set v1. Waiting for approval. Do not write code until then.
- Open questions for Ali: NVIDIA fiscal years 2026, 2025, and 2024 end in January and are flagged `fiscal_year_ambiguous`. The label is the calendar year of the period end.

## Handoff notes

Tagged cells on 2026-10-21: financial statements 2,202/2,205, notes 771/771. Untagged cells are MD&A 251 and notes 4, and they are not in those rates. Of 201 sign mismatches, 164 are a natural-positive concept shown in parentheses (D-010). The other 37 keep `sign="-"` and show an unsigned number. 89 matched cells have no date in their own column or on their own row: 75 NVIDIA segment rows under a section date, and 14 AMD goodwill activity cells. The only tagged absolute mismatches are the three Qualcomm cells in P-009. Restated values are AMD selling, general and administrative expense for the periods ending 2023-12-30 and 2024-12-28, listed with both accession numbers in `data/xbrl/restatements.json`. Raw company-facts JSON stays gitignored. Fetch dates and SHA-256 hashes are in `data/xbrl/snapshots.json`.

The 11–12 letters missing from each filing's stored text are the filename in the HTML `head`. The hyphen is not a letter or digit, so the remainder is the ticker plus the period date (`nvda20260125` is 12, `txn20251231` is 11).
