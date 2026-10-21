"""HTTP client for SEC EDGAR with a fixed request rate and retries."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

Getter = Callable[[str, str], bytes]

_RETRY_STATUSES = {429, 500, 502, 503, 504}


class SecRequestError(Exception):
    """A SEC request failed after retries."""


class SecClient:
    """Fetch SEC URLs using the contact string from ``SEC_USER_AGENT``."""

    def __init__(
        self,
        user_agent: str,
        *,
        getter: Getter | None = None,
        min_interval: float = 0.2,
        max_attempts: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a client. ``min_interval`` of 0.2 keeps the rate at about 5 requests per second."""
        if not user_agent.strip():
            raise ValueError("SEC_USER_AGENT is empty")
        self._user_agent = user_agent
        self._getter = getter or _urllib_get
        self._min_interval = min_interval
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._clock = clock
        self._last_request = 0.0

    def get_json(self, url: str) -> Any:
        """GET a URL and parse the body as JSON."""
        import json

        return json.loads(self.get(url).decode("utf-8"))

    def get(self, url: str) -> bytes:
        """GET a URL, waiting between calls and backing off on retryable failures."""
        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            self._wait_turn()
            try:
                return self._getter(url, self._user_agent)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in _RETRY_STATUSES or attempt == self._max_attempts:
                    raise SecRequestError(
                        f"SEC request failed with status {exc.code}: {url}"
                    ) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                self._sleep(_retry_delay(retry_after, delay))
                delay *= 2
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise SecRequestError(f"SEC request failed: {url}") from exc
                self._sleep(delay)
                delay *= 2
        raise SecRequestError(f"SEC request failed: {url}") from last_error

    def _wait_turn(self) -> None:
        elapsed = self._clock() - self._last_request
        if self._last_request and elapsed < self._min_interval:
            self._sleep(self._min_interval - elapsed)
        self._last_request = self._clock()


def _retry_delay(retry_after: str | None, fallback: float) -> float:
    if retry_after is None:
        return fallback
    try:
        return max(float(retry_after), fallback)
    except ValueError:
        return fallback


def _urllib_get(url: str, user_agent: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json,text/html,*/*",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()
