"""Smoke test for the installed package."""

from finrag import __version__


def test_version() -> None:
    """The package version matches the Step 0 release marker."""
    assert __version__ == "0.1.0"
