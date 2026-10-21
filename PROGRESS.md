# Progress

**Current step:** 3
**Last updated:** 2026-10-11

## Step status

| Step | Title | Status | Done date |
|---|---|---|---|
| 0 | Bootstrap | done | 2026-10-07 |
| 1 | Corpus selection and downloader | done | 2026-10-07 |
| 2 | Parse filings into structured elements | done | 2026-10-11 |
| 3 | XBRL ground-truth extraction | in progress | |

## Done when

- Metrics table covers every company-year for at least eight metrics: met. 18 filings, eight metrics on every own year (`revenue`, `cost_of_revenue`, `gross_profit`, `operating_income`, `net_income`, `research_and_development`, `selling_general_and_administrative`, `total_assets`). 414 metric rows, including comparatives. NVIDIA January period ends stay `fiscal_year_ambiguous`.
- Hand cross-check passes: not met. `data/xbrl/hand_check.json` has 27 rows, seed 13, status `open`. The draw is larger than 25 because the distinct derived and restated values do not fit in 25 once each company has both FY2024 and FY2025, three rows, and five fallback rows.

## Current session

- Done: Company-facts snapshots for the six companies, the tag map, the metrics table, and the cell check. Absolute match rates are in EXPERIMENTS.md. Every mismatch is in `data/xbrl/mismatches.jsonl`. Systematic groups are P-005, P-006, and P-007.
- In progress: The hand check is written and not marked done.
- Next: A person checks the 27 rows. Do not start Step 4.
- Open questions for Ali: NVIDIA fiscal years 2026, 2025, and 2024 end in January and are flagged `fiscal_year_ambiguous`. The label is the calendar year of the period end.

## Handoff notes

`finrag-xbrl` on 2026-10-11 checked 3,231 statement cells. Financial statements matched 2,202/2,205 on absolute value. Notes matched 757/775. MD&A matched 0/251, all missing tags. Sign mismatches are 201 and are not in those rates. Header-period failures left after the header reader are 17. No scale or rounding mismatches. Raw company-facts JSON is gitignored under `data/xbrl/raw/`. Fetch dates and SHA-256 hashes are in `data/xbrl/snapshots.json`.

The 11–12 letters missing from each filing's stored text are the filename in the HTML `head`. The hyphen is not a letter or digit, so the remainder is the ticker plus the period date (`nvda20260125` is 12, `txn20251231` is 11).
