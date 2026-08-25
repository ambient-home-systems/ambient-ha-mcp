import os
from datetime import UTC, datetime, timedelta

import pytest

from ambient_ha.config import Settings
from ambient_ha.ha.client import HomeAssistantClient
from ambient_ha.models.discovery import EntitySearchFilters
from ambient_ha.models.history import RecentChangesFilters
from ambient_ha.models.home import (
    LocationFilters,
    LowBatteryFilters,
    OpeningFilters,
    UnavailableEntityFilters,
)


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

    summary = await client.get_home_summary()
    unavailable = await client.find_unavailable_entities(UnavailableEntityFilters(limit=5))
    batteries = await client.find_low_batteries(
        LowBatteryFilters(threshold=settings.battery_warning_threshold, limit=5)
    )
    openings = await client.get_openings(OpeningFilters(limit=5))
    lights = await client.get_lights_on(LocationFilters(limit=5))
    diagnostics = await client.diagnose_home(limit=5)

    assert summary.total_entities >= summary.unavailable_entities
    assert unavailable.returned <= 5
    assert batteries.returned <= 5
    assert openings.returned <= 5
    assert lights.returned <= 5
    assert diagnostics.returned <= 5

    if entities.entities:
        entity_id = entities.entities[0].entity_id
        start = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        found, history = await client.get_entity_history(
            entity_id, start=start, end=None, limit=5, minimal_response=True
        )
        logbook = await client.get_logbook(start=start, end=None, entity_id=entity_id, limit=5)
        changes = await client.get_recent_changes(
            RecentChangesFilters(entity_id=entity_id, duration_minutes=60, limit=5)
        )

        assert found is True
        assert history.returned <= 5
        assert logbook.returned <= 5
        assert changes.returned <= 5
