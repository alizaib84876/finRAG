"""Fetch company-facts snapshots and write the metrics table and the cell check."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from finrag.ingest.cli import _repo_root, _user_agent
from finrag.ingest.manifest import read_manifest, sha256_file
from finrag.ingest.parse import FilingMeta, parse_filing
from finrag.ingest.sec import SecClient
from finrag.xbrl.check import check_filing, match_rates
from finrag.xbrl.companyfacts import companyfacts_url, load_companyfacts
from finrag.xbrl.contexts import parse_contexts
from finrag.xbrl.hand import fallback_rows, locate_rows, sample_hand_check
from finrag.xbrl.metrics import (
    MetricRow,
    build_metrics,
    label_metrics,
    load_tag_map,
    restatements,
)

HAND_SEED = 13


def main(argv: list[str] | None = None) -> int:
    """Fetch snapshots if needed, then write metrics, mismatches, and the hand check."""
    parser = argparse.ArgumentParser(
        description="Build the XBRL metrics table and check parsed cells."
    )
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = _repo_root(args.root)
    filings = read_manifest(root / "data" / "manifest.json")
    specs = load_tag_map(root / "configs" / "xbrl_tags.yaml")
    snapshots = _snapshots(root, filings)
    _write_json(root / "data" / "xbrl" / "snapshots.json", {"snapshots": snapshots})

    by_cik = {item["cik"]: load_companyfacts(root / item["path"]) for item in snapshots}
    metric_rows: list[MetricRow] = []
    checks = []
    mismatches = []
    pool = []
    for filing in filings:
        html = (root / filing["path"]).read_text()
        elements = parse_filing(
            html,
            FilingMeta(
                ticker=filing["ticker"],
                cik=filing["cik"],
                accession_number=filing["accession_number"],
                fiscal_year=int(filing["fiscal_year"]),
                period_end=filing["period_end"],
            ),
        )
        contexts = parse_contexts(html)
        facts = by_cik[filing["cik"]]
        filing_metrics = build_metrics(
            facts,
            specs,
            ticker=filing["ticker"],
            cik=filing["cik"],
            accession=filing["accession_number"],
            period_end=filing["period_end"],
        )
        metric_rows.extend(filing_metrics)
        filing_checks, filing_mismatches = check_filing(
            elements,
            contexts,
            facts,
            ticker=filing["ticker"],
            accession=filing["accession_number"],
        )
        checks.extend(filing_checks)
        mismatches.extend(filing_mismatches)
        roles = {element["id"]: element.get("section_role") for element in elements}
        sources = {element["id"]: element.get("units_source") for element in elements}
        located = locate_rows(
            filing_metrics,
            filing_checks,
            filing_url=filing["url"],
            section_roles=roles,
            units_sources=sources,
            restated=set(),
        )
        pool.extend(located)
        occupied = {(row["element_id"], row["cell"]) for row in located}
        for row in fallback_rows(
            filing_checks,
            ticker=filing["ticker"],
            filing_url=filing["url"],
            accession=filing["accession_number"],
        ):
            if (row["element_id"], row["cell"]) not in occupied:
                pool.append(row)

    metric_rows = label_metrics(metric_rows)
    changed = restatements(metric_rows)
    restated_keys = {
        (item["ticker"], item["metric"], item["period_end"]) for item in changed
    }
    for row in pool:
        row["restated"] = (
            row["ticker"],
            row["metric"],
            row["period_end"],
        ) in restated_keys

    out = root / "data" / "xbrl"
    _write_jsonl(out / "metrics.jsonl", [_metric_dict(row) for row in metric_rows])
    _write_jsonl(out / "mismatches.jsonl", [item.__dict__ for item in mismatches])
    _write_json(out / "restatements.json", {"restatements": changed})
    sample = sample_hand_check(pool, seed=HAND_SEED)
    _write_json(
        out / "hand_check.json",
        {"seed": HAND_SEED, "status": "open", "rows": sample},
    )
    rates = match_rates(checks)
    summary = {
        "filings": len(filings),
        "metrics": len(metric_rows),
        "checked_cells": len(checks),
        "mismatches": len(mismatches),
        "mismatch_causes": dict(Counter(item.cause for item in mismatches)),
        "match_rates": rates,
        "alternate_tags": [
            _metric_dict(row)
            for row in metric_rows
            if row.tag_rank is not None and row.tag_rank > 0
        ],
        "derived": [_metric_dict(row) for row in metric_rows if row.derived],
        "restatements": len(changed),
        "hand_check_rows": len(sample),
    }
    _write_json(out / "summary.json", summary)
    print(
        json.dumps(
            {
                "checked_cells": len(checks),
                "mismatch_causes": summary["mismatch_causes"],
            },
            indent=2,
        )
    )
    return 0


def _snapshots(root: Path, filings: list[dict]) -> list[dict]:
    raw = root / "data" / "xbrl" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    sidecar = root / "data" / "xbrl" / "snapshots.json"
    previous = {}
    if sidecar.is_file():
        previous = {
            item["cik"]: item for item in json.loads(sidecar.read_text())["snapshots"]
        }
    companies: dict[str, str] = {}
    for filing in filings:
        companies.setdefault(filing["cik"], filing["ticker"])
    missing = [cik for cik in companies if not (raw / f"{cik}.json").is_file()]
    if missing:
        client = SecClient(_user_agent(root))
        for cik in missing:
            payload = client.get_json(companyfacts_url(cik))
            (raw / f"{cik}.json").write_text(json.dumps(payload))
    records = []
    for cik, ticker in sorted(companies.items(), key=lambda item: item[1]):
        path = raw / f"{cik}.json"
        digest = sha256_file(path)
        prior = previous.get(cik)
        fetched_at = (
            prior["fetched_at"]
            if prior and prior.get("sha256") == digest
            else datetime.now(UTC).date().isoformat()
        )
        records.append(
            {
                "ticker": ticker,
                "cik": cik,
                "path": f"data/xbrl/raw/{cik}.json",
                "url": companyfacts_url(cik),
                "fetched_at": fetched_at,
                "sha256": digest,
                "bytes": path.stat().st_size,
            }
        )
    return records


def _metric_dict(row: MetricRow) -> dict:
    return {
        "ticker": row.ticker,
        "cik": row.cik,
        "fiscal_year": row.fiscal_year,
        "fiscal_year_ambiguous": row.fiscal_year_ambiguous,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "accession_number": row.accession_number,
        "metric": row.metric,
        "tag": row.tag,
        "tag_rank": row.tag_rank,
        "value": row.value,
        "unit": row.unit,
        "derived": row.derived,
        "fact_status": row.fact_status,
        "comparative": row.comparative,
        "reported_in_fiscal_year": row.reported_in_fiscal_year,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
