import os

import pytest

from ambient_ha.config import Settings
from ambient_ha.ha.client import HomeAssistantClient
from ambient_ha.models.discovery import EntitySearchFilters


@pytest.mark.integration
@pytest.mark.anyio
async def test_real_home_assistant_connection() -> None:
    if os.environ.get("RUN_HA_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_HA_INTEGRATION_TESTS=1 to use a real Home Assistant instance")

    settings = Settings()  # type: ignore[call-arg]
    client = HomeAssistantClient(settings)
    result = await client.check_connection()

    assert result.status == "connected", result.message

    entities = await client.search_entities(EntitySearchFilters(limit=1))
    areas_supported, _areas = await client.list_areas()
    floors_supported, _floors = await client.list_floors()

    assert entities.returned <= 1
    assert isinstance(areas_supported, bool)
    assert isinstance(floors_supported, bool)
