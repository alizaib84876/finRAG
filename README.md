# FinRAG

Eval-gated hybrid RAG over SEC 10-K filings. The evaluation harness is the product.

Step 0 is the bootstrap: tooling, a Postgres 16 + pgvector database, and CI that lints and tests. Measured results are not in this file. Those come from logged runs in later steps.

Copy `.env.example` to `.env` for local database settings. The password there is a local Docker default. Commands for tests, lint, format, and the database are in `CLAUDE.md`.
