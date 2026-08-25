import pytest

from ambient_ha.ha.discovery import DiscoveryResolver
from ambient_ha.ha.home import HomeAnalyzer
from ambient_ha.models.home import (
    LocationFilters,
    LowBatteryFilters,
    OpeningFilters,
    UnavailableEntityFilters,
)
from ambient_ha.tools.home import (
    diagnose_home,
    find_low_batteries,
    find_unavailable_entities,
    get_home_summary,
    get_lights_on,
    get_openings,
)
from tests.fixtures.home import HOME_REGISTRIES, HOME_STATES


class FakeHomeGateway:
    def __init__(self) -> None:
        entities = DiscoveryResolver(HOME_REGISTRIES).entities(HOME_STATES, include_attributes=True)
        self.analyzer = HomeAnalyzer(entities, battery_warning_threshold=20)

    async def get_home_summary(self):
        return self.analyzer.home_summary()

    async def find_unavailable_entities(self, filters: UnavailableEntityFilters):
        return self.analyzer.unavailable_entities(filters)

    async def find_low_batteries(self, filters: LowBatteryFilters):
        return self.analyzer.low_batteries(filters)

    async def get_openings(self, filters: OpeningFilters):
        return self.analyzer.openings(filters)

    async def get_lights_on(self, filters: LocationFilters):
        return self.analyzer.lights_on(filters)

    async def diagnose_home(self, *, limit: int):
        return self.analyzer.diagnose(limit=limit)


@pytest.mark.anyio
async def test_home_tools_return_structured_bounded_results() -> None:
    gateway = FakeHomeGateway()

    summary = await get_home_summary(gateway)
    unavailable = await find_unavailable_entities(gateway, area="Basement", limit=999)
    batteries = await find_low_batteries(gateway, default_threshold=20)
    openings = await get_openings(gateway, opening_type="window", state="any")
    lights = await get_lights_on(gateway, floor="Ground Floor")
    diagnostics = await diagnose_home(gateway, limit=2)

    assert summary.ok is True and summary.summary is not None
    assert unavailable.result is not None and unavailable.result.limit == 100
    assert batteries.result is not None and batteries.result.threshold == 20
    assert openings.result is not None and openings.result.total_matches == 1
    assert lights.result is not None and lights.result.total_matches == 1
    assert diagnostics.report is not None and diagnostics.report.returned == 2
    assert diagnostics.report.truncated is True


@pytest.mark.anyio
async def test_home_tools_reject_invalid_semantic_inputs() -> None:
    gateway = FakeHomeGateway()

    domain = await find_unavailable_entities(gateway, domain="bad domain")
    duration = await find_unavailable_entities(gateway, minimum_duration=0)
    battery = await find_low_batteries(gateway, default_threshold=20, threshold=101)
    opening = await get_openings(gateway, state="ajar")

    assert domain.error_code == "invalid_domain"
    assert duration.error_code == "invalid_duration"
    assert battery.error_code == "invalid_threshold"
    assert opening.error_code == "invalid_state"
