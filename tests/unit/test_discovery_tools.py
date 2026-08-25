from typing import Any

import pytest

from ambient_ha.ha.discovery import DiscoveryResolver
from ambient_ha.ha.exceptions import HomeAssistantAuthenticationError
from ambient_ha.models import ConnectionStatus, HomeAssistantServerInfo
from ambient_ha.models.discovery import EntitySearchFilters
from ambient_ha.tools.discovery import (
    domain_summary,
    get_area,
    get_entity,
    get_floor,
    list_areas,
    list_floors,
    search_entities,
)
from tests.fixtures.discovery import REGISTRIES, STATES


class FakeDiscoveryGateway:
    def __init__(self, *, supported: bool = True, failure: Exception | None = None) -> None:
        self.resolver = DiscoveryResolver(REGISTRIES)
        self.supported = supported
        self.failure = failure
        self.last_filters: EntitySearchFilters | None = None
        self.last_area_limit: int | None = None

    def _raise(self) -> None:
        if self.failure:
            raise self.failure

    async def check_connection(self) -> ConnectionStatus:
        raise NotImplementedError

    async def get_server_info(self) -> HomeAssistantServerInfo:
        raise NotImplementedError

    async def get_entity(self, entity_id: str) -> Any:
        self._raise()
        state = next((state for state in STATES if state["entity_id"] == entity_id), None)
        return self.resolver.entity(state) if state else None

    async def search_entities(self, filters: EntitySearchFilters) -> Any:
        self._raise()
        self.last_filters = filters
        return self.resolver.search(STATES, filters)

    async def list_areas(self) -> Any:
        self._raise()
        return self.supported, self.resolver.list_areas(STATES)

    async def get_area(self, identifier: str, *, include_entities: bool, limit: int) -> Any:
        self._raise()
        self.last_area_limit = limit
        return self.supported, self.resolver.get_area(
            STATES, identifier, include_entities=include_entities, limit=limit
        )

    async def list_floors(self) -> Any:
        self._raise()
        return self.supported, self.resolver.list_floors(STATES)

    async def get_floor(self, identifier: str) -> Any:
        self._raise()
        return self.supported, self.resolver.get_floor(STATES, identifier)

    async def get_domain_summary(self, domain: str) -> Any:
        self._raise()
        return self.resolver.domain_summary(STATES, domain)


@pytest.mark.anyio
async def test_entity_tool_validates_and_returns_normal_not_found() -> None:
    gateway = FakeDiscoveryGateway()

    invalid = await get_entity(gateway, "Kitchen Light")
    missing = await get_entity(gateway, "light.missing")
    found = await get_entity(gateway, " LIGHT.KITCHEN_CEILING ")

    assert (invalid.ok, invalid.error_code) == (False, "invalid_entity_id")
    assert (missing.ok, missing.found, missing.error_code) == (True, False, "not_found")
    assert found.ok is True and found.found is True


@pytest.mark.anyio
async def test_search_and_area_limits_are_clamped() -> None:
    gateway = FakeDiscoveryGateway()

    searched = await search_entities(gateway, query="garage", limit=500)
    area = await get_area(gateway, "garage", include_entities=True, limit=500)

    assert searched.limit == 100
    assert gateway.last_filters is not None and gateway.last_filters.limit == 100
    assert gateway.last_area_limit == 50
    assert area.found is True


@pytest.mark.anyio
async def test_registry_feature_absence_is_a_successful_unsupported_result() -> None:
    gateway = FakeDiscoveryGateway(supported=False)

    areas = await list_areas(gateway)
    area = await get_area(gateway, "garage")
    floors = await list_floors(gateway)
    floor = await get_floor(gateway, "ground floor")

    assert areas.ok is True and areas.supported is False
    assert area.ok is True and area.supported is False and area.found is False
    assert floors.ok is True and floors.supported is False
    assert floor.ok is True and floor.supported is False and floor.found is False


@pytest.mark.anyio
async def test_errors_are_normalized_without_secrets() -> None:
    gateway = FakeDiscoveryGateway(
        failure=HomeAssistantAuthenticationError("Home Assistant rejected the configured token.")
    )

    result = await search_entities(gateway, query="light")

    assert result.ok is False
    assert result.error_code == "authentication_failed"
    assert result.entities == []


@pytest.mark.anyio
async def test_domain_tool_validates_and_preserves_generic_states() -> None:
    gateway = FakeDiscoveryGateway()

    invalid = await domain_summary(gateway, "light.bad")
    result = await domain_summary(gateway, "SENSOR")

    assert invalid.ok is False
    assert result.ok is True
    assert result.summary is not None
    assert result.summary.states == {"51.2": 1, "72.1": 1, "unknown": 1}
