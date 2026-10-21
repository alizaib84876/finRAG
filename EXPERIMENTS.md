# Experiments

## 2026-10-11 company-facts cell check

- **Commit:** 72545e072eb64be609cdefbac87ff5e72b056757
- **Config:** `configs/xbrl_tags.yaml`. Full-year durations are 350 to 380 days. Instants have no start. Periods are `start` and `end`, not `fy`. The hand-check seed is 13. Company-facts snapshots were fetched 2026-10-11. Hashes are in `data/xbrl/snapshots.json`.
- **Command:** `uv run finrag-xbrl`
- **Results:** 18 filings, 3,231 numeric statement cells, 414 metric rows.

Absolute match rate by `units_source`:

| units_source | checked | matched | match rate |
|---|---:|---:|---:|
| caption | 153 | 109 | 0.7124 |
| fallback | 155 | 155 | 1.0000 |
| preceding | 979 | 976 | 0.9969 |
| table_text | 1,944 | 1,719 | 0.8843 |

Absolute match rate by `section_role`:

| section_role | checked | matched | match rate |
|---|---:|---:|---:|
| financial_statements | 2,205 | 2,202 | 0.9986 |
| mdna | 251 | 0 | 0.0000 |
| notes | 775 | 757 | 0.9768 |

Mismatch causes, each row in `data/xbrl/mismatches.jsonl`: missing tag 255, sign 201, header-period parse failure 17. Scale 0. Rounding 0. Sign rows are not in the match rates.

Tag changes (`tag_rank` > 0): 42 rows. NVIDIA and Qualcomm revenue use `us-gaap:Revenues`. AMD and Texas Instruments cost of revenue use `us-gaap:CostOfGoodsAndServicesSold`. Broadcom net income uses `us-gaap:ProfitLoss` on the filings that do not have `us-gaap:NetIncomeLoss`. Derived gross profit: 9 Qualcomm rows, five distinct period values. Restatements: AMD selling, general and administrative expense for period ends 2023-12-30 and 2024-12-28. The later filing reports 2,318,000,000 and 2,735,000,000. The prior filings report 2,352,000,000 and 2,783,000,000.
