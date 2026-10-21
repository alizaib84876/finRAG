"""Build the 10-K corpus from SEC submissions data and a local manifest."""

from __future__ import annotations

from pathlib import Path

import yaml

from finrag.ingest.filings import (
    CorpusShortfall,
    FilingRow,
    SelectedFiling,
    cik_for_ticker,
    confirm_primary_document,
    document_url,
    extra_submission_names,
    extra_submissions_url,
    index_html_url,
    label_fiscal_year,
    local_filing_path,
    rows_from_page,
    select_10k,
    submissions_url,
)
from finrag.ingest.manifest import checksum_matches, filing_record, sha256_file
from finrag.ingest.sec import SecClient

TICKER_URL = "https://www.sec.gov/files/company_tickers.json"


def load_corpus_config(path: Path) -> tuple[str, int, list[str]]:
    """Read the form, filing count, and tickers from the corpus config."""
    payload = yaml.safe_load(path.read_text())
    form = str(payload["form"])
    limit = int(payload["filings_per_company"])
    tickers = [str(item["ticker"]).upper() for item in payload["companies"]]
    return form, limit, tickers


def collect_filings(
    client: SecClient, tickers: list[str], *, limit: int = 3
) -> list[SelectedFiling]:
    """Select the latest 10-K filings and confirm each primary document."""
    ticker_payload = client.get_json(TICKER_URL)
    selected: list[SelectedFiling] = []
    shortfalls: list[tuple[str, int]] = []
    for ticker in tickers:
        filings = _filings_for_ticker(client, ticker_payload, ticker, limit)
        if len(filings) < limit:
            shortfalls.append((ticker, len(filings)))
            continue
        selected.extend(filings)
    if shortfalls:
        raise CorpusShortfall(shortfalls)
    return selected


def download_filings(
    client: SecClient,
    filings: list[SelectedFiling],
    *,
    raw_root: Path,
    repo_root: Path,
    known_checksums: dict[str, str],
) -> list[dict]:
    """Download primary documents, skipping a file whose checksum already matches."""
    records: list[dict] = []
    for filing in filings:
        destination = local_filing_path(
            raw_root, filing.ticker, filing.accession_number, filing.primary_document
        )
        expected = known_checksums.get(filing.accession_number)
        if checksum_matches(destination, expected):
            size = destination.stat().st_size
            digest = expected or sha256_file(destination)
        else:
            body = client.get(filing.url)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
            size = len(body)
            digest = sha256_file(destination)
        relative = destination.relative_to(repo_root).as_posix()
        records.append(
            filing_record(filing, path=relative, file_size=size, sha256=digest)
        )
    return records


def rebuild_from_manifest(
    client: SecClient, filings: list[dict], *, repo_root: Path
) -> tuple[int, int]:
    """Download manifest URLs that are missing or whose checksum does not match.

    Returns ``(downloaded, skipped)``.
    """
    downloaded = 0
    skipped = 0
    for filing in filings:
        destination = repo_root / filing["path"]
        expected = filing["sha256"]
        if checksum_matches(destination, expected):
            skipped += 1
            continue
        body = client.get(filing["url"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        actual = sha256_file(destination)
        if actual != expected:
            raise ValueError(f"checksum mismatch for {filing['accession_number']}")
        downloaded += 1
    return downloaded, skipped


def _filings_for_ticker(
    client: SecClient, ticker_payload: dict, ticker: str, limit: int
) -> list[SelectedFiling]:
    cik, fallback_name = cik_for_ticker(ticker_payload, ticker)
    payload = client.get_json(submissions_url(cik))
    company = str(payload.get("name") or fallback_name)
    rows = rows_from_page(payload)
    chosen = select_10k(rows, limit=limit)
    for name in extra_submission_names(payload):
        if len(chosen) >= limit:
            break
        extra = client.get_json(extra_submissions_url(name))
        rows.extend(rows_from_page(extra))
        chosen = select_10k(rows, limit=limit)
    filings: list[SelectedFiling] = []
    for row in chosen:
        filings.append(_confirm_row(client, company, ticker, cik, row))
    return filings


def _confirm_row(
    client: SecClient, company: str, ticker: str, cik: str, row: FilingRow
) -> SelectedFiling:
    index_html = client.get(index_html_url(cik, row.accession_number)).decode(
        "utf-8", errors="replace"
    )
    confirm_primary_document(index_html, row.primary_document)
    fiscal_year, ambiguous = label_fiscal_year(row.report_date)
    return SelectedFiling(
        company=company,
        ticker=ticker,
        cik=cik,
        form=row.form,
        period_end=row.report_date,
        fiscal_year=fiscal_year,
        fiscal_year_end=row.report_date,
        fiscal_year_ambiguous=ambiguous,
        filing_date=row.filing_date,
        accession_number=row.accession_number,
        primary_document=row.primary_document,
        url=document_url(cik, row.accession_number, row.primary_document),
    )
