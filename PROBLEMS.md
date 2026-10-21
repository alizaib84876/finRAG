# Problems

## P-001: Filing index JSON type is an icon name (Step 1)

- **Date:** 2026-10-07
- **Symptom:** The dry-run rejected `nvda-20260125.htm` because its index type was `text.gif`.
- **Root cause:** `index.json` uses `type` for a file icon (`text.gif`, `image2.gif`), not the EDGAR form type. The form type is the Type column in the filing index HTML.
- **Fix:** Confirm the primary document from that HTML Type column. It must be exactly `10-K`.
- **Verification:** The saved index-table test passes. The live dry-run then selected 18 documents whose index Type column is 10-K.
- **Prevention:** The confirmation test includes both a 10-K row and an exhibit row.
- **Status:** resolved
