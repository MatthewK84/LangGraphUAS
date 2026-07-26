"""Per-client rate limiting.

A sliding-window counter keyed by API key when present, otherwise by client IP.
This is an in-process limiter: each worker enforces its own budget, so the
effective cluster limit is ``rate_limit_requests * worker_count``. That is
acceptable as a spend guard against runaway model calls. Put a shared limiter
(Redis or the ingress) in front when you need an exact global ceiling.
"""

import time
from collections import deque
from typing import Final

_MAX_TRACKED_CLIENTS: Final[int] = 10_000


class SlidingWindowLimiter:
    """Allows a fixed number of requests per client within a rolling window."""

    def __init__(self, max_requests: int, window_s: float) -> None:
        self._max_requests = max_requests
        self._window_s = window_s
        self._hits: dict[str, deque[float]] = {}

    def _prune(self, timestamps: deque[float], now: float) -> None:
        """Drop timestamps that have fallen outside the window."""
        cutoff: float = now - self._window_s
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

    def _evict_if_needed(self) -> None:
        """Bound memory by clearing tracking once too many clients accumulate."""
        if len(self._hits) > _MAX_TRACKED_CLIENTS:
            self._hits.clear()

    def check(self, client_key: str) -> bool:
        """Record a request and return whether it is within the allowance.

        Args:
            client_key: Stable identifier for the caller.
        """
        now: float = time.monotonic()
        timestamps: deque[float] = self._hits.setdefault(client_key, deque())
        self._prune(timestamps, now)
        if len(timestamps) >= self._max_requests:
            return False
        timestamps.append(now)
        self._evict_if_needed()
        return True

    def retry_after_s(self, client_key: str) -> int:
        """Return seconds until the client's oldest hit leaves the window."""
        timestamps: deque[float] = self._hits.get(client_key, deque())
        if not timestamps:
            return 0
        remaining: float = self._window_s - (time.monotonic() - timestamps[0])
        return max(1, int(remaining) + 1)
