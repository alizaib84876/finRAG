# finRAG

Question answering over SEC 10-K filings. The corpus is about six companies, three fiscal years each, pulled from EDGAR. The manifest records the filing URL and SHA-256 checksum. Raw HTML stays out of git.

Retrieval is hybrid. Chunk embeddings sit in Postgres with pgvector. BM25 covers the same chunks. Reciprocal rank fusion merges the two lists, and a cross-encoder can rerank the fused hits. The generator is one pinned model at temperature 0. Answers cite chunk ids. If the filings do not support an answer, the system refuses.

The question set is about 100 items, written before retrieval is tuned. Dev is the split used while building. The held-out split is scored once. Checks are recall@k and MRR against the gold passages, numeric match with a unit tolerance, and a judge for free-text faithfulness. On a pull request, CI fails if a score drops below the committed baseline by more than the measured run-to-run noise.

## Run

Python 3.12, uv 0.12.23. Ruff 0.16.10 lints, Black 26.10.0 formats, pytest runs the tests. Line length is 88.

```
uv sync --all-groups
uv run ruff check .
uv run black .
uv run pytest
docker compose up -d --wait
```

Postgres 16 and pgvector 0.8.7 come from `pgvector/pgvector:0.8.7-pg16`. `docker/initdb/01-vector.sql` runs `CREATE EXTENSION vector` on first start. User, password, and database default to `finrag` on port 5432. Copy `.env.example` to `.env` to change them. That password is only for the local container.

`tests/test_vector_extension.py` skips when `DATABASE_URL` is unset. CI does the same, so the workflow does not need a database. To run that test against Compose:

```
DATABASE_URL=postgresql://finrag:finrag@localhost:5432/finrag uv run pytest
```

`.github/workflows/ci.yml` checks out the repo, installs uv 0.12.23 and Python 3.12, then runs ruff, `black --check`, and pytest.

Code lives in `src/finrag`: ingest, XBRL, chunking, indexing, retrieval, the router, generation, and the API. `eval/` is the metric code. `data/` holds the manifest. `golden/` holds the questions. `configs/` holds the YAML for a run.
