"""Manifest read, write, and checksum checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from finrag.ingest.filings import SelectedFiling


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_matches(path: Path, expected: str | None) -> bool:
    """True when the file exists and its SHA-256 equals ``expected``."""
    if not expected or not path.is_file():
        return False
    return sha256_file(path) == expected


def write_manifest(path: Path, filings: list[dict]) -> None:
    """Write the corpus manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fiscal_year_rule": (
            "fiscal_year is the calendar year of period_end; "
            "January period ends are flagged fiscal_year_ambiguous"
        ),
        "filings": filings,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def read_manifest(path: Path) -> list[dict]:
    """Load filing records from the manifest."""
    payload = json.loads(path.read_text())
    return list(payload["filings"])


def filing_record(
    filing: SelectedFiling,
    *,
    path: str,
    file_size: int,
    sha256: str,
) -> dict:
    """Build one manifest object."""
    return {
        "company": filing.company,
        "ticker": filing.ticker,
        "cik": filing.cik,
        "form": filing.form,
        "fiscal_year": filing.fiscal_year,
        "fiscal_year_end": filing.fiscal_year_end,
        "period_end": filing.period_end,
        "fiscal_year_ambiguous": filing.fiscal_year_ambiguous,
        "filing_date": filing.filing_date,
        "accession_number": filing.accession_number,
        "url": filing.url,
        "path": path,
        "file_size": file_size,
        "sha256": sha256,
    }
