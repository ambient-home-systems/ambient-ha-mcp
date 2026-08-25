import pytest

from ambient_ha.ha.cache import AsyncTTLCache


@pytest.mark.anyio
async def test_cache_reuses_value_until_expired_and_can_be_cleared() -> None:
    now = 10.0
    calls = 0

    def clock() -> float:
        return now

    async def loader() -> str:
        nonlocal calls
        calls += 1
        return f"snapshot-{calls}"

    cache = AsyncTTLCache[str](5, clock=clock)
    assert await cache.get(loader) == "snapshot-1"
    assert await cache.get(loader) == "snapshot-1"

    now = 15.0
    assert await cache.get(loader) == "snapshot-2"

    await cache.clear()
    assert await cache.get(loader) == "snapshot-3"
    assert calls == 3


@pytest.mark.anyio
async def test_refresh_forces_reload() -> None:
    calls = 0

    async def loader() -> int:
        nonlocal calls
        calls += 1
        return calls

    cache = AsyncTTLCache[int](60)
    assert await cache.get(loader) == 1
    assert await cache.get(loader, refresh=True) == 2
