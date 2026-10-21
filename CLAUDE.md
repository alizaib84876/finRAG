# FinRAG: assistant guide

## Project

Hybrid RAG over SEC 10-K filings with an eval-gated CI pipeline.
The evaluation harness is the product.

## Rules

1. Work only on the current step in PROGRESS.md. One step at a time.
2. At the start of a step: restate the goal, list files to touch, wait for approval if architecture changes.
3. Every module ships with tests. A step is done only when its "Done when" checklist passes.
4. Update PROGRESS.md at the end of every session.
5. Log every problem in PROBLEMS.md immediately, with cause and fix.
6. Log every metric run in EXPERIMENTS.md with config and commit hash.
7. Record non-trivial choices in DECISIONS.md before implementing.
8. Never read, tune on, or report the held-out split before Step 13.
9. Never invent numbers. Verify library behavior in current docs.
10. Temperature 0, pinned model versions, fixed random seeds.
11. No secrets in the repo. Use environment variables.
12. Respect SEC rules: descriptive User-Agent with contact email, stay well under 10 requests per second.

## Conventions

- Type hints and docstrings on public functions.
- Formatting: ruff + black. Tests: pytest.
- Config in YAML files, not hardcoded.
- Commit messages start with the step id, for example `step-05`.

## Commands

- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Format: `uv run black .`
- Database: `docker compose up -d --wait`
