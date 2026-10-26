"""Per-client rate limiting.

A sliding-window counter keyed by API key when present, otherwise by client IP.
By default each worker keeps its own budget in memory, so the cluster ceiling
is ``rate_limit_requests * worker_count``. With ``SUAS_RATE_LIMIT_SHARED`` the
budget lives in the database every worker already uses, and the ceiling is the
configured number whatever the worker count (#84).
"""

import hashlib
import time
from collections import deque
from collections.abc import Callable
from typing import Final, Protocol

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.config import Settings
from suas.db.models import RateLimitBucketRow

_MAX_TRACKED_CLIENTS: Final[int] = 10_000


class RateLimiter(Protocol):
    """Anything that can admit or refuse one request for a client."""

    async def admit(self, client_key: str) -> int:
        """Record a request; return 0 if admitted, else seconds until it would be."""
        ...


def _retry_after_s(oldest: float, now: float, window_s: float) -> int:
    """Return whole seconds until the oldest hit leaves the window, at least 1."""
    return max(1, int(window_s - (now - oldest)) + 1)


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
        return _retry_after_s(timestamps[0], time.monotonic(), self._window_s)

    async def admit(self, client_key: str) -> int:
        """Record a request; return 0 if admitted, else seconds until it would be."""
        if self.check(client_key):
            return 0
        return self.retry_after_s(client_key)


class DatabaseLimiter:
    """The same sliding window, kept in one row per client that every worker shares.

    Each admission is one transaction: create the client's row if missing, lock
    it (``FOR UPDATE`` on Postgres; SQLite's writer lock is already held), prune,
    decide, write. Concurrent workers on one client therefore serialise, and
    the ceiling holds exactly. Wall-clock time, since workers share no monotonic
    clock.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_requests: int,
        window_s: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._session_factory = session_factory
        self._max_requests = max_requests
        self._window_s = window_s
        self._clock = clock

    async def admit(self, client_key: str) -> int:
        """Record a request; return 0 if admitted, else seconds until it would be."""
        bucket: str = hashlib.sha256(client_key.encode()).hexdigest()
        async with self._session_factory() as session, session.begin():
            dialect = postgresql if session.bind.dialect.name == "postgresql" else sqlite
            await session.execute(
                dialect.insert(RateLimitBucketRow)
                .values(bucket=bucket, hits=[])
                .on_conflict_do_nothing(index_elements=["bucket"])
            )
            locked = select(RateLimitBucketRow).where(RateLimitBucketRow.bucket == bucket)
            row = (await session.execute(locked.with_for_update())).scalar_one()
            now: float = self._clock()
            hits: list[float] = [hit for hit in row.hits if hit > now - self._window_s]
            if len(hits) >= self._max_requests:
                row.hits = hits
                return _retry_after_s(hits[0], now, self._window_s)
            row.hits = [*hits, now]
            return 0


def build_limiter(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> RateLimiter:
    """Return the shared limiter when configured, else the per-process one."""
    if settings.rate_limit_shared:
        return DatabaseLimiter(
            session_factory, settings.rate_limit_requests, settings.rate_limit_window_s
        )
    return SlidingWindowLimiter(settings.rate_limit_requests, settings.rate_limit_window_s)
