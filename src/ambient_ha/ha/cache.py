"""Small bounded async TTL cache for slowly changing registry metadata."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic


class AsyncTTLCache[T]:
    """Cache exactly one bounded snapshot and prevent concurrent reload storms."""

    def __init__(self, ttl_seconds: float, *, clock: Callable[[], float] = monotonic) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._value: T | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get(self, loader: Callable[[], Awaitable[T]], *, refresh: bool = False) -> T:
        """Return a fresh-enough value, loading once when missing or expired."""
        if not refresh and self._value is not None and self._clock() < self._expires_at:
            return self._value
        async with self._lock:
            if not refresh and self._value is not None and self._clock() < self._expires_at:
                return self._value
            value = await loader()
            self._value = value
            self._expires_at = self._clock() + self._ttl_seconds
            return value

    async def clear(self) -> None:
        """Invalidate the snapshot so the next request reloads all registries."""
        async with self._lock:
            self._value = None
            self._expires_at = 0.0
