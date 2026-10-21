"""Command line for selecting, downloading, and rebuilding the 10-K corpus."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from finrag.ingest.corpus import (
    collect_filings,
    download_filings,
    load_corpus_config,
    rebuild_from_manifest,
)
from finrag.ingest.filings import CorpusShortfall, PrimaryDocumentError
from finrag.ingest.manifest import read_manifest, write_manifest
from finrag.ingest.sec import SecClient, SecRequestError


def main(argv: list[str] | None = None) -> int:
    """Run ``fetch`` or ``rebuild``."""
    parser = argparse.ArgumentParser(
        description="Download SEC 10-K filings listed for this corpus."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root. Defaults to the current checkout.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="Select 10-K filings from EDGAR.")
    fetch.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selected filings and do not download.",
    )

    subparsers.add_parser(
        "rebuild", help="Rebuild data/raw from data/manifest.json and verify checksums."
    )
    args = parser.parse_args(argv)
    root = _repo_root(args.root)

    try:
        client = SecClient(_user_agent(root))
        if args.command == "fetch":
            return _fetch(client, root, dry_run=args.dry_run)
        return _rebuild(client, root)
    except (CorpusShortfall, PrimaryDocumentError, SecRequestError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1


def _fetch(client: SecClient, root: Path, *, dry_run: bool) -> int:
    _form, limit, tickers = load_corpus_config(root / "configs" / "corpus.yaml")
    filings = collect_filings(client, tickers, limit=limit)
    if dry_run:
        print(f"dry-run: {len(filings)} filings, no downloads")
        for filing in filings:
            print(filing.dry_run_line())
        ambiguous = [filing for filing in filings if filing.fiscal_year_ambiguous]
        if ambiguous:
            print(f"ambiguous fiscal year labels: {len(ambiguous)}")
        return 0

    manifest_path = root / "data" / "manifest.json"
    known = _known_checksums(manifest_path)
    records = download_filings(
        client,
        filings,
        raw_root=root / "data" / "raw",
        repo_root=root,
        known_checksums=known,
    )
    write_manifest(manifest_path, records)
    print(f"wrote {manifest_path} ({len(records)} filings)")
    return 0


def _rebuild(client: SecClient, root: Path) -> int:
    manifest_path = root / "data" / "manifest.json"
    filings = read_manifest(manifest_path)
    downloaded, skipped = rebuild_from_manifest(client, filings, repo_root=root)
    print(f"rebuild downloaded={downloaded} skipped={skipped} verified={len(filings)}")
    return 0


def _known_checksums(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return {item["accession_number"]: item["sha256"] for item in read_manifest(path)}


def _user_agent(root: Path) -> str:
    _load_dotenv(root / ".env")
    value = os.environ.get("SEC_USER_AGENT", "").strip()
    if not value or "example.com" in value:
        raise ValueError("Set SEC_USER_AGENT in .env")
    return value


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _repo_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


if __name__ == "__main__":
    raise SystemExit(main())
