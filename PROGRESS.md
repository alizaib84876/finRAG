# Progress

**Current step:** 0
**Last updated:** 2026-10-07

## Step status

| Step | Title | Status | Done date |
|---|---|---|---|
| 0 | Bootstrap | in progress | |
| 1 | Corpus selection and downloader | not started | |
| 2 | Parse filings into structured elements | not started | |
| 3 | XBRL ground-truth extraction | not started | |
| 4 | Golden set v1 | not started | |
| 5 | Table-aware chunking and indexing | not started | |
| 6 | Baseline pipeline and the eval harness | not started | |
| 7 | LLM judge and judge validation | not started | |
| 8 | Hybrid retrieval, RRF and reranking | not started | |
| 9 | Routing and query transformation | not started | |
| 10 | Reliability and refusal behavior | not started | |
| 11 | CI gate | not started | |
| 12 | Demo PR, API and deployment | not started | |
| 13 | Held-out run, report and README | not started | |

Status values: not started, in progress, blocked, done.

## Current session

- Done: Recorded D-001, D-002, and D-003. Scaffolded the repo, locked uv + Python 3.12, pinned pgvector `0.8.7-pg16`, and added lint, tests, and `ci.yml`.
- In progress: Step 0 stays open until pytest is observed on GitHub Actions. There is no git remote, so that run has not happened. The same CI commands passed locally.
- Next: Do not start Step 1. Push this repo and confirm the `ci` workflow is green, then mark Step 0 done.
- Open questions for Ali: Where should the GitHub remote live so Actions can run?

## Handoff notes

Step 0 "Done when" evidence from 2026-10-07, local only:

- `docker compose up -d --wait` started `finrag-postgres-1`. Status was `healthy`. `psql` returned `vector` version `0.8.7`.
- `uv sync --frozen --all-groups`, `uv run ruff check .`, and `uv run black --check .` passed.
- `uv run pytest` with no `DATABASE_URL`: 1 passed, 1 skipped (`DATABASE_URL is not set`).
- `DATABASE_URL=postgresql://finrag:finrag@localhost:5432/finrag uv run pytest`: 2 passed.
- Ruff reported `linter.line_length = 88`. Black's pyproject config reported `line_length` 88. `uv.lock` has ruff 0.16.10 and black 26.10.0, matching `.pre-commit-config.yaml`.
- The five tracking files exist. `ci.yml` pins `actions/checkout` v7.0.1 and `astral-sh/setup-uv` v10.2.0 by commit SHA, and pins uv 0.12.23.

uv 0.12.23 is installed at `~/.local/bin/uv`. Postgres is still running on port 5432. Step 1 has not been started.
