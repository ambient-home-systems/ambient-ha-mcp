import httpx
import pytest

from ambient_ha.config import Settings
from ambient_ha.ha.client import HomeAssistantClient
from ambient_ha.ha.websocket import RegistrySnapshot
from ambient_ha.models.discovery import EntitySearchFilters
from tests.fixtures.discovery import REGISTRIES, STATES


class FakeRegistryProvider:
    def __init__(self, snapshot: RegistrySnapshot = REGISTRIES) -> None:
        self.snapshot = snapshot
        self.calls = 0

    async def get_registries(self) -> RegistrySnapshot:
        self.calls += 1
        return self.snapshot


@pytest.mark.anyio
async def test_client_reports_success(settings: Settings) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"message": "API running."})
    )
    result = await HomeAssistantClient(settings, transport=transport).check_connection()

    assert result.status == "connected"
    assert result.reachable is True
    assert result.authenticated is True


@pytest.mark.anyio
async def test_client_distinguishes_authentication_failure(settings: Settings) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(401, json={}))
    result = await HomeAssistantClient(settings, transport=transport).check_connection()

    assert result.status == "authentication_failed"
    assert result.reachable is True
    assert result.authenticated is False


@pytest.mark.anyio
async def test_server_info_allowlists_safe_fields(settings: Settings) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "version": "2026.8.2",
                "time_zone": "America/New_York",
                "unit_system": {"temperature": "°F", "length": "mi", "nested": {}},
                "latitude": 39.0,
                "longitude": -77.0,
                "config_dir": "/config",
                "components": ["api", "automation"],
                "location_name": "Private Home",
            },
        )
    )

    result = await HomeAssistantClient(settings, transport=transport).get_server_info()

    assert result.model_dump() == {
        "version": "2026.8.2",
        "time_zone": "America/New_York",
        "unit_system": {"temperature": "°F", "length": "mi"},
    }


@pytest.mark.anyio
async def test_discovery_uses_fresh_states_and_cached_registries(settings: Settings) -> None:
    state_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal state_reads
        if request.url.path == "/api/states":
            state_reads += 1
            payload = [dict(state) for state in STATES]
            payload[1] = {**payload[1], "state": "on" if state_reads == 2 else "off"}
            return httpx.Response(200, json=payload, request=request)
        raise AssertionError(f"unexpected path: {request.url.path}")

    provider = FakeRegistryProvider()
    client = HomeAssistantClient(
        settings,
        transport=httpx.MockTransport(handler),
        registry_provider=provider,
    )

    first = await client.search_entities(EntitySearchFilters(domain="light"))
    second = await client.search_entities(EntitySearchFilters(domain="light"))

    assert first.entities[0].state == "off"
    assert second.entities[0].state == "on"
    assert state_reads == 2
    assert provider.calls == 1

    await client.refresh_discovery_cache()
    await client.list_areas()
    assert provider.calls == 2


@pytest.mark.anyio
async def test_get_entity_reads_exact_state_and_enriches_it(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/states/light.kitchen_ceiling"
        return httpx.Response(200, json=STATES[0], request=request)

    result = await HomeAssistantClient(
        settings,
        transport=httpx.MockTransport(handler),
        registry_provider=FakeRegistryProvider(),
    ).get_entity("light.kitchen_ceiling")

    assert result is not None
    assert result.area_name == "Kitchen"
    assert result.attributes == {"brightness": 180}
