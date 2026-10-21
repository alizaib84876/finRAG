# Progress

**Current step:** 1
**Last updated:** 2026-10-07

## Step status

| Step | Title | Status | Done date |
|---|---|---|---|
| 0 | Bootstrap | done | 2026-10-07 |
| 1 | Corpus selection and downloader | done | 2026-10-07 |
| 2 | Parse filings into structured elements | not started | |

## Current session

- Done: Selected 18 form 10-K filings for the six semiconductor companies, wrote `data/manifest.json`, and checked that a rebuild from the manifest matches every SHA-256.
- In progress: Nothing.
- Next: Do not start Step 2 until asked.
- Open questions for Ali: NVIDIA fiscal years 2026, 2025, and 2024 end in January and are flagged `fiscal_year_ambiguous`. The label is the calendar year of the period end.

## Handoff notes

Dry-run printed 18 filings and downloaded none. `finrag-corpus fetch` wrote the manifest. With `data/raw` removed, `finrag-corpus rebuild` reported `downloaded=18 skipped=0 verified=18`, and a second run reported `downloaded=0 skipped=18 verified=18`. Checksum mismatches after that rebuild: 0. `SEC_USER_AGENT` is in `.env` only.
