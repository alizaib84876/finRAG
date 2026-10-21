# Decisions

Record a decision here before changing the stack, schema, or eval design. Newest first.

## D-003: ruff for lint and black for format (Step 0)

- **Context:** CLAUDE.md requires ruff and black. Ruff can also format, which would leave two formatters.
- **Options:** ruff check plus black; ruff check plus ruff format.
- **Decision:** Ruff lints and Black formats. Both use line length 88, set in `pyproject.toml`. Package versions are pinned to the current releases checked on 2026-10-07: ruff 0.16.10 (GitHub release `0.16.10`, pre-commit rev `v0.16.10` on `astral-sh/ruff-pre-commit`) and black 26.10.0 (tag `26.10.0` on `psf/black`). `uv.lock` and `.pre-commit-config.yaml` must carry those same versions. The pre-commit config enables `ruff-check` and `black` only.
- **Consequences:** A formatter or linter bump updates the lockfile and the pre-commit rev together. Formatting stays on black.

## D-002: Postgres 16 with pinned pgvector image (Step 0)

- **Context:** The local database is Postgres with pgvector. Postgres 16 was approved. Docker Hub's floating tag `pg16` moves when a new pgvector release is published.
- **Options:** `pgvector/pgvector:pg16` (floating); `pgvector/pgvector:0.8.7-pg16` (versioned).
- **Decision:** Pin `pgvector/pgvector:0.8.7-pg16`. Checked on Docker Hub on 2026-10-07: that tag was updated 2026-10-01 and its manifest digest is `sha256:7b822b0aac60967beb1ea5e576b8602c94c300a157d187f385ae3e0da199b90a`, the same digest as the floating `pg16` tag. Compose uses that tag plus the digest. `docker/initdb/01-vector.sql` runs `CREATE EXTENSION IF NOT EXISTS vector`. The service healthcheck is `pg_isready`.
- **Consequences:** Local Postgres stays on 16 and pgvector 0.8.7 until a later decision changes the tag. The extension test skips when no database is reachable, and fails if a reachable database has no `vector` extension.

## D-001: uv and Python 3.12 (Step 0)

- **Context:** The plan allows uv or pip, and Python 3.11+. This machine's `python3` is 3.10. The Step 0 proposal to use uv and Python 3.12 was approved.
- **Options:** uv with Python 3.12; pip with a requirements file and some other 3.11+ interpreter.
- **Decision:** Use uv. `requires-python` is `>=3.11`. The project interpreter is Python 3.12 (`.python-version`). Commit `uv.lock`. The official installer on 2026-10-07 installed uv 0.12.23; CI pins that uv version. The build backend is `uv_build`, which `uv init --package` generated on that uv version (`uv_build>=0.12.23,<0.13.0`).
- **Consequences:** Local runs and CI install from the lockfile. System Python 3.10 is not the project interpreter.

## Entry format

## D-NNN: short title (Step N)

- **Context:**
- **Options:**
- **Decision:**
- **Consequences:**
