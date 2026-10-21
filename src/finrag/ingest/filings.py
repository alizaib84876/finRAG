"""Select 10-K filings from SEC submissions data."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


class PrimaryDocumentError(Exception):
    """The submissions primary document is missing or is not the 10-K itself."""


class CorpusShortfall(Exception):
    """A company does not have enough 10-K filings."""

    def __init__(self, shortfalls: list[tuple[str, int]]) -> None:
        self.shortfalls = shortfalls
        detail = ", ".join(f"{ticker} has {count}" for ticker, count in shortfalls)
        super().__init__(f"Need 3 form 10-K filings; {detail}")


@dataclass(frozen=True)
class FilingRow:
    """One row from a SEC submissions filing list."""

    form: str
    accession_number: str
    filing_date: str
    report_date: str
    primary_document: str
    primary_doc_description: str


@dataclass(frozen=True)
class SelectedFiling:
    """A 10-K chosen for the corpus."""

    company: str
    ticker: str
    cik: str
    form: str
    period_end: str
    fiscal_year: int
    fiscal_year_end: str
    fiscal_year_ambiguous: bool
    filing_date: str
    accession_number: str
    primary_document: str
    url: str

    def dry_run_line(self) -> str:
        """One line for dry-run output. No document body."""
        line = (
            f"{self.company} | {self.form} | period_end={self.period_end} | "
            f"filed={self.filing_date} | fy={self.fiscal_year} | {self.url}"
        )
        if self.fiscal_year_ambiguous:
            line += (
                " | ambiguous: period ends in January; "
                "fiscal year label is the year of the period end"
            )
        return line


def rows_from_page(payload: dict) -> list[FilingRow]:
    """Read a submissions document or an older page that is only the recent table."""
    if "form" in payload and "accessionNumber" in payload:
        return rows_from_submissions({"filings": {"recent": payload}})
    return rows_from_submissions(payload)


def rows_from_submissions(payload: dict) -> list[FilingRow]:
    """Read the columnar ``filings.recent`` block into rows."""
    recent = payload["filings"]["recent"]
    count = len(recent["form"])
    descriptions = recent.get("primaryDocDescription", [""] * count)
    rows: list[FilingRow] = []
    for index in range(count):
        rows.append(
            FilingRow(
                form=recent["form"][index],
                accession_number=recent["accessionNumber"][index],
                filing_date=recent["filingDate"][index],
                report_date=recent["reportDate"][index],
                primary_document=recent["primaryDocument"][index],
                primary_doc_description=(
                    descriptions[index] if index < len(descriptions) else ""
                ),
            )
        )
    return rows


def extra_submission_names(payload: dict) -> list[str]:
    """Names of older submission pages linked from the main submissions file."""
    files = payload.get("filings", {}).get("files", [])
    return [item["name"] for item in files if item.get("name")]


def select_10k(rows: list[FilingRow], *, limit: int = 3) -> list[FilingRow]:
    """Keep form 10-K only, one filing per period end, and return the latest periods."""
    chosen: dict[str, FilingRow] = {}
    for row in rows:
        if row.form != "10-K":
            continue
        current = chosen.get(row.report_date)
        if current is None or row.filing_date > current.filing_date:
            chosen[row.report_date] = row
    ordered = sorted(
        chosen.values(),
        key=lambda row: (row.report_date, row.filing_date),
        reverse=True,
    )
    return ordered[:limit]


def label_fiscal_year(period_end: str) -> tuple[int, bool]:
    """Return the calendar year of the period end, and whether a January end is ambiguous."""
    year_text, month_text, _day_text = period_end.split("-")
    return int(year_text), int(month_text) == 1


def cik_for_ticker(ticker_payload: dict, ticker: str) -> tuple[str, str]:
    """Look up a zero-padded CIK and company title from SEC's company ticker file."""
    wanted = ticker.upper()
    entries = (
        ticker_payload.values() if isinstance(ticker_payload, dict) else ticker_payload
    )
    for entry in entries:
        if str(entry.get("ticker", "")).upper() != wanted:
            continue
        cik = f"{int(entry['cik_str']):010d}"
        title = str(entry.get("title") or ticker)
        return cik, title
    raise KeyError(ticker)


def submissions_url(cik: str) -> str:
    """URL of the primary submissions JSON for a CIK."""
    return f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"


def extra_submissions_url(name: str) -> str:
    """URL of an older submissions page named by the primary file."""
    return f"https://data.sec.gov/submissions/{name}"


def index_html_url(cik: str, accession_number: str) -> str:
    """URL of the human filing index, whose Type column is the EDGAR form type."""
    accession_path = accession_number.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession_path}/{accession_number}-index.html"
    )


def document_url(cik: str, accession_number: str, primary_document: str) -> str:
    """URL of the primary document named in the submissions file."""
    accession_path = accession_number.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{accession_path}/{primary_document}"
    )


def confirm_primary_document(index_html: str, primary_document: str) -> None:
    """Require the index HTML Type column for this document to be exactly 10-K."""
    matches = [
        row
        for row in _index_rows(index_html)
        if _row_names_document(row, primary_document)
    ]
    if not matches:
        raise PrimaryDocumentError(
            f"{primary_document} is not listed in the filing index"
        )
    document_type = matches[0][3] if len(matches[0]) > 3 else ""
    if document_type != "10-K":
        shown = document_type or "unknown"
        raise PrimaryDocumentError(
            f"{primary_document} has index type {shown}, not 10-K"
        )


def local_filing_path(
    raw_root: Path, ticker: str, accession_number: str, primary_document: str
) -> Path:
    """Path under ``data/raw`` for one primary document."""
    relative = Path(primary_document)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe primary document name: {primary_document}")
    accession_path = accession_number.replace("-", "")
    return raw_root / ticker.upper() / accession_path / relative


def _index_rows(index_html: str) -> list[list[str]]:
    parser = _IndexTableParser()
    parser.feed(index_html)
    return parser.rows


def _row_names_document(row: list[str], primary_document: str) -> bool:
    document_cell = row[2] if len(row) > 2 else ""
    return primary_document in document_cell


class _IndexTableParser(HTMLParser):
    """Collect text from each table row in the filing index."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_cell = False
        self._cell: list[str] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag == "td":
            self._in_cell = True
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_cell:
            self._row.append("".join(self._cell).strip())
            self._in_cell = False
        elif tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell.append(data)
