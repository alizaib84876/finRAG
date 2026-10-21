"""Tests for 10-K selection, fiscal year labels, and resumable downloads."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from finrag.ingest.corpus import download_filings, rebuild_from_manifest
from finrag.ingest.filings import (
    PrimaryDocumentError,
    confirm_primary_document,
    document_url,
    label_fiscal_year,
    rows_from_page,
    select_10k,
)
from finrag.ingest.manifest import filing_record
from finrag.ingest.sec import SecClient

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_select_10k_excludes_amendments_and_keeps_latest_original() -> None:
    """10-K/A is ignored, and the later original 10-K wins for a repeated period end."""
    rows = rows_from_page(_load("submissions_sample.json"))
    chosen = select_10k(rows, limit=3)
    assert [row.report_date for row in chosen] == [
        "2025-01-26",
        "2024-01-28",
        "2023-01-29",
    ]
    assert chosen[0].primary_document == "fy2025.htm"
    assert all(row.form == "10-K" for row in chosen)


def test_january_period_end_is_flagged() -> None:
    """A January period end uses that calendar year and is marked ambiguous."""
    year, ambiguous = label_fiscal_year("2025-01-26")
    assert year == 2025
    assert ambiguous is True
    december_year, december_flag = label_fiscal_year("2024-12-28")
    assert december_year == 2024
    assert december_flag is False


def test_primary_document_must_be_the_10k() -> None:
    """The filing index must type the primary document as 10-K, not an exhibit."""
    confirm_primary_document(_read("index_10k.html"), "fy2025.htm")
    with pytest.raises(PrimaryDocumentError):
        confirm_primary_document(_read("index_exhibit.html"), "ex21.htm")


def test_document_url_uses_accession_without_dashes() -> None:
    """The archive URL is built from the CIK, accession, and primary document name."""
    url = document_url("0000000001", "0000000001-25-000010", "fy2025.htm")
    assert (
        url == "https://www.sec.gov/Archives/edgar/data/1/000000000125000010/fy2025.htm"
    )


def test_download_skips_file_with_matching_checksum(tmp_path: Path) -> None:
    """A file that already matches the manifest checksum is not requested again."""
    body = b"<html>10-K</html>"
    digest = hashlib.sha256(body).hexdigest()
    raw = tmp_path / "data" / "raw"
    destination = raw / "NVDA" / "000000000125000010" / "fy2025.htm"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(body)
    filing = _selected()
    client = _RejectingClient()
    records = download_filings(
        client,
        [filing],
        raw_root=raw,
        repo_root=tmp_path,
        known_checksums={filing.accession_number: digest},
    )
    assert client.urls == []
    assert records[0]["sha256"] == digest
    assert records[0]["file_size"] == len(body)


def test_rebuild_verifies_checksum_and_skips_match(tmp_path: Path) -> None:
    """Rebuild downloads a missing file and skips it once the checksum matches."""
    body = b"<html>10-K</html>"
    digest = hashlib.sha256(body).hexdigest()
    filing = filing_record(
        _selected(),
        path="data/raw/NVDA/000000000125000010/fy2025.htm",
        file_size=len(body),
        sha256=digest,
    )
    client = _BodyClient(body)
    downloaded, skipped = rebuild_from_manifest(client, [filing], repo_root=tmp_path)
    assert downloaded == 1
    assert skipped == 0
    downloaded, skipped = rebuild_from_manifest(client, [filing], repo_root=tmp_path)
    assert downloaded == 0
    assert skipped == 1
    assert client.calls == 1


def test_rate_limit_spaces_requests() -> None:
    """Two requests are at least the configured interval apart."""
    import time

    stamps: list[float] = []

    def getter(url: str, user_agent: str) -> bytes:
        stamps.append(time.monotonic())
        assert user_agent == "test-agent"
        assert url
        return b"{}"

    client = SecClient("test-agent", getter=getter, min_interval=0.05)
    client.get("https://data.sec.gov/example-a")
    client.get("https://data.sec.gov/example-b")
    assert stamps[1] - stamps[0] >= 0.05


def _selected():
    from finrag.ingest.filings import SelectedFiling

    return SelectedFiling(
        company="EXAMPLE CORP",
        ticker="NVDA",
        cik="0000000001",
        form="10-K",
        period_end="2025-01-26",
        fiscal_year=2025,
        fiscal_year_end="2025-01-26",
        fiscal_year_ambiguous=True,
        filing_date="2025-02-20",
        accession_number="0000000001-25-000010",
        primary_document="fy2025.htm",
        url="https://www.sec.gov/Archives/edgar/data/1/000000000125000010/fy2025.htm",
    )


class _RejectingClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str) -> bytes:
        self.urls.append(url)
        raise AssertionError(url)


class _BodyClient:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    def get(self, url: str) -> bytes:
        self.calls += 1
        assert url
        return self.body
