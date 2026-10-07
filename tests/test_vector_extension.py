"""Check the pgvector extension when Postgres is reachable."""

import os

import psycopg
import pytest


def test_vector_extension_exists() -> None:
    """Skip when no database is available; otherwise require the vector extension."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not set")

    try:
        connection = psycopg.connect(database_url, connect_timeout=3)
    except psycopg.Error as exc:
        pytest.skip(f"database is not available: {exc}")

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT extname FROM pg_extension WHERE extname = %s",
                ("vector",),
            )
            row = cursor.fetchone()
    finally:
        connection.close()

    assert row == ("vector",)
