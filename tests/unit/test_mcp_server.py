from pathlib import Path

import httpx
import pytest
from mcp import Client
from mcp.server.transport_security import TransportSecuritySettings

from ambient_ha.config import Settings
from ambient_ha.ha.automation import (
    AutomationCatalog,
    find_automation_references,
    list_automations,
    normalize_automation_definition,
    normalize_automation_trace,
    normalize_trace_summaries,
)
from ambient_ha.ha.discovery import DiscoveryResolver
from ambient_ha.ha.home import HomeAnalyzer
from ambient_ha.models import ConnectionStatus, HomeAssistantServerInfo
from ambient_ha.models.automation import ActivityCauseReport, CausalityEvidence
from ambient_ha.models.discovery import EntitySearchFilters
from ambient_ha.models.history import (
    EntityHistoryPage,
    LogbookPage,
    RecentChangesFilters,
    RecentChangesPage,
)
from ambient_ha.models.home import (
    LocationFilters,
    LowBatteryFilters,
    OpeningFilters,
    UnavailableEntityFilters,
)
from ambient_ha.server import build_mcp_server
from tests.fixtures.automation import (
    AUTOMATION_CONFIGS,
    AUTOMATION_STATES,
    FULL_TRACE,
    TRACE_SUMMARY,
)
from tests.fixtures.discovery import REGISTRIES, STATES
from tests.fixtures.home import HOME_REGISTRIES, HOME_STATES


def test_invalid_policy_file_fails_server_startup(tmp_path: Path) -> None:
    settings = Settings(
        HOME_ASSISTANT_URL="http://homeassistant.test:8123",
        HOME_ASSISTANT_TOKEN="test-secret-token",
        POLICY_FILE=tmp_path / "missing.toml",
    )

    with pytest.raises(ValueError, match="could not be read"):
        build_mcp_server(settings, client=FakeGateway())


class FakeGateway:
    resolver = DiscoveryResolver(REGISTRIES)
    home_analyzer = HomeAnalyzer(
        DiscoveryResolver(HOME_REGISTRIES).entities(HOME_STATES, include_attributes=True),
        battery_warning_threshold=20,
    )

    async def check_connection(self) -> ConnectionStatus:
        return ConnectionStatus(
            status="connected",
            reachable=True,
            authenticated=True,
            message="Home Assistant is reachable and authenticated.",
        )

    async def get_server_info(self) -> HomeAssistantServerInfo:
        return HomeAssistantServerInfo(version="2026.8.2", time_zone="America/New_York")

    async def get_entity(self, entity_id: str):
        state = next((state for state in STATES if state["entity_id"] == entity_id), None)
        return self.resolver.entity(state) if state else None

    async def search_entities(self, filters: EntitySearchFilters):
        return self.resolver.search(STATES, filters)

    async def list_areas(self):
        return True, self.resolver.list_areas(STATES)

    async def get_area(self, identifier: str, *, include_entities: bool, limit: int):
        return True, self.resolver.get_area(
            STATES, identifier, include_entities=include_entities, limit=limit
        )

    async def list_floors(self):
        return True, self.resolver.list_floors(STATES)

    async def get_floor(self, identifier: str):
        return True, self.resolver.get_floor(STATES, identifier)

    async def get_domain_summary(self, domain: str):
        return self.resolver.domain_summary(STATES, domain)

    async def get_entity_history(self, entity_id: str, **_kwargs: object):
        return True, EntityHistoryPage(
            entity_id=entity_id,
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T12:30:00+00:00",
            total_transitions=0,
            returned=0,
            limit=100,
            truncated=False,
        )

    async def get_logbook(self, **_kwargs: object):
        return LogbookPage(
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T12:30:00+00:00",
            total_entries=0,
            returned=0,
            limit=100,
            truncated=False,
        )

    async def get_recent_changes(self, filters: RecentChangesFilters):
        return RecentChangesPage(
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T12:30:00+00:00",
            candidate_entities=0,
            total_changes=0,
            returned=0,
            limit=filters.limit or 100,
            truncated=False,
        )

    async def get_home_summary(self):
        return self.home_analyzer.home_summary()

    async def find_unavailable_entities(self, filters: UnavailableEntityFilters):
        return self.home_analyzer.unavailable_entities(filters)

    async def find_low_batteries(self, filters: LowBatteryFilters):
        return self.home_analyzer.low_batteries(filters)

    async def get_openings(self, filters: OpeningFilters):
        return self.home_analyzer.openings(filters)

    async def get_lights_on(self, filters: LocationFilters):
        return self.home_analyzer.lights_on(filters)

    async def diagnose_home(self, *, limit: int):
        return self.home_analyzer.diagnose(limit=limit)

    async def list_automations(self, *, query: str | None, enabled: bool | None, limit: int):
        return list_automations(AUTOMATION_STATES, query=query, enabled=enabled, limit=limit)

    async def get_automation(self, entity_id: str):
        state = next((item for item in AUTOMATION_STATES if item["entity_id"] == entity_id), None)
        if state is None:
            return True, False, None
        return (
            True,
            True,
            normalize_automation_definition(
                state, AUTOMATION_CONFIGS.get(entity_id), supported=True
            ),
        )

    async def find_automations_for_entity(self, entity_id: str, *, limit: int):
        page = find_automation_references(
            AutomationCatalog(
                supported=True,
                configurations=AUTOMATION_CONFIGS,
                missing=frozenset(),
                entity_device_ids={"light.kitchen": "device-light"},
            ),
            entity_id,
            limit=limit,
        )
        return True, page

    async def get_automation_traces(self, entity_id: str, *, limit: int):
        return True, normalize_trace_summaries(
            entity_id, [TRACE_SUMMARY], limit=limit, supported=True
        )

    async def get_automation_trace(self, entity_id: str, run_id: str):
        return True, True, normalize_automation_trace(entity_id, run_id, FULL_TRACE)

    async def find_activity_cause(self, entity_id: str, **kwargs: object):
        limit = int(kwargs.get("limit", 10))
        evidence = CausalityEvidence(
            source="automation",
            relationship="confirmed_by_context",
            confidence="confirmed",
            event_timestamp="2024-08-25T02:14:02+00:00",
            automation_id="automation.motion_light",
            run_id="run-1",
            context_relationship="same_context",
            supporting_facts=["Home Assistant directly links the contexts."],
        )
        return True, ActivityCauseReport(
            entity_id=entity_id,
            start="2024-08-25T02:13:02+00:00",
            end="2024-08-25T02:15:02+00:00",
            state_changes_found=1,
            evidence=[evidence],
            total_evidence=1,
            returned=1,
            limit=limit,
            truncated=False,
            complete=True,
        )


@pytest.mark.anyio
async def test_mcp_diagnostic_tools_are_callable_in_memory(settings: Settings) -> None:
    server = build_mcp_server(settings, client=FakeGateway())

    async with Client(server) as client:
        connection = await client.call_tool("ha_connection_status", {})
        info = await client.call_tool("ha_server_info", {})

    assert connection.structured_content is not None
    assert connection.structured_content["status"] == "connected"
    assert connection.structured_content["authenticated"] is True
    assert info.structured_content is not None
    assert info.structured_content["available"] is True
    assert info.structured_content["server"]["version"] == "2026.8.2"


@pytest.mark.anyio
async def test_health_route_keeps_liveness_separate_from_readiness(settings: Settings) -> None:
    server = build_mcp_server(settings, client=FakeGateway())
    app = server.streamable_http_app(
        transport_security=TransportSecuritySettings(
            allowed_hosts=["localhost", "localhost:*"],
            allowed_origins=[],
        )
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "application_running": True,
        "home_assistant_reachable": True,
        "home_assistant_authenticated": True,
    }


@pytest.mark.anyio
async def test_mcp_discovery_tools_are_registered_and_callable(settings: Settings) -> None:
    server = build_mcp_server(settings, client=FakeGateway())

    async with Client(server) as client:
        listed = await client.list_tools()
        entity = await client.call_tool("ha_get_entity", {"entity_id": "light.kitchen_ceiling"})
        search = await client.call_tool(
            "ha_search_entities", {"query": "garage light", "limit": 10}
        )
        areas = await client.call_tool("ha_list_areas", {})
        area = await client.call_tool("ha_get_area", {"area": "Garage"})
        floors = await client.call_tool("ha_list_floors", {})
        floor = await client.call_tool("ha_get_floor", {"floor": "Ground Floor"})
        summary = await client.call_tool("ha_domain_summary", {"domain": "sensor"})

    names = {tool.name for tool in listed.tools}
    assert {
        "ha_get_entity",
        "ha_search_entities",
        "ha_list_areas",
        "ha_get_area",
        "ha_list_floors",
        "ha_get_floor",
        "ha_domain_summary",
    } <= names
    assert entity.structured_content["found"] is True
    assert search.structured_content["entities"][0]["entity_id"] == ("light.garage_overhead_lights")
    assert areas.structured_content["supported"] is True
    assert area.structured_content["area"]["entity_count"] == 4
    assert floors.structured_content["floors"][0]["floor_id"] == "lower_level"
    assert floor.structured_content["floor"]["entity_count"] == 6
    assert summary.structured_content["summary"]["unknown"] == 1


@pytest.mark.anyio
async def test_mcp_history_tools_are_registered_and_callable(settings: Settings) -> None:
    server = build_mcp_server(settings, client=FakeGateway())

    async with Client(server) as client:
        listed = await client.list_tools()
        history = await client.call_tool(
            "ha_get_entity_history",
            {"entity_id": "light.kitchen_ceiling", "start": "2026-08-25T12:00:00Z"},
        )
        logbook = await client.call_tool("ha_get_logbook", {"start": "2026-08-25T12:00:00Z"})
        changes = await client.call_tool("ha_get_recent_changes", {"duration_minutes": 30})

    names = {tool.name for tool in listed.tools}
    assert {"ha_get_entity_history", "ha_get_logbook", "ha_get_recent_changes"} <= names
    assert history.structured_content["found"] is True
    assert logbook.structured_content["logbook"]["returned"] == 0
    assert changes.structured_content["changes"]["candidate_entities"] == 0


@pytest.mark.anyio
async def test_mcp_home_diagnostic_tools_are_registered_and_callable(settings: Settings) -> None:
    server = build_mcp_server(settings, client=FakeGateway())

    async with Client(server) as client:
        listed = await client.list_tools()
        summary = await client.call_tool("ha_get_home_summary", {})
        unavailable = await client.call_tool("ha_find_unavailable_entities", {"limit": 2})
        batteries = await client.call_tool("ha_find_low_batteries", {})
        openings = await client.call_tool("ha_get_openings", {"state": "open"})
        lights = await client.call_tool("ha_get_lights_on", {})
        diagnostics = await client.call_tool("ha_diagnose_home", {"limit": 3})

    names = {tool.name for tool in listed.tools}
    assert {
        "ha_get_home_summary",
        "ha_find_unavailable_entities",
        "ha_find_low_batteries",
        "ha_get_openings",
        "ha_get_lights_on",
        "ha_diagnose_home",
    } <= names
    assert len(names) == 24
    assert summary.structured_content["summary"]["total_entities"] == len(HOME_STATES)
    assert unavailable.structured_content["result"]["total_matches"] == 1
    assert batteries.structured_content["result"]["total_matches"] == 1
    assert openings.structured_content["result"]["total_matches"] == 4
    assert lights.structured_content["result"]["total_matches"] == 1
    assert diagnostics.structured_content["report"]["returned"] == 3


@pytest.mark.anyio
async def test_mcp_automation_tools_are_registered_and_callable(settings: Settings) -> None:
    server = build_mcp_server(settings, client=FakeGateway())

    async with Client(server) as client:
        listed = await client.list_tools()
        automations = await client.call_tool("ha_list_automations", {"query": "Kitchen Motion"})
        automation = await client.call_tool("ha_get_automation", {"automation": "motion_light"})
        references = await client.call_tool(
            "ha_find_automations_for_entity", {"entity_id": "light.kitchen"}
        )
        traces = await client.call_tool(
            "ha_get_automation_traces", {"automation": "automation.motion_light"}
        )
        trace = await client.call_tool(
            "ha_get_automation_trace",
            {"automation": "motion_light", "run_id": "run-1"},
        )
        cause = await client.call_tool(
            "ha_find_activity_cause",
            {"entity_id": "light.kitchen", "timestamp": "2024-08-25T02:14:02Z"},
        )

    names = {tool.name for tool in listed.tools}
    assert {
        "ha_list_automations",
        "ha_get_automation",
        "ha_find_automations_for_entity",
        "ha_get_automation_traces",
        "ha_get_automation_trace",
        "ha_find_activity_cause",
    } <= names
    assert automations.structured_content["result"]["returned"] == 1
    assert automation.structured_content["automation"]["configuration_available"] is True
    assert references.structured_content["result"]["total_matches"] >= 1
    assert traces.structured_content["result"]["total_traces"] == 1
    assert trace.structured_content["trace"]["run_id"] == "run-1"
    assert cause.structured_content["result"]["evidence"][0]["confidence"] == "confirmed"
