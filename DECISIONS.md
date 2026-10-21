# Decisions

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
