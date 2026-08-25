import httpx
import pytest
from mcp import Client
from mcp.server.transport_security import TransportSecuritySettings

from ambient_ha.config import Settings
from ambient_ha.ha.discovery import DiscoveryResolver
from ambient_ha.models import ConnectionStatus, HomeAssistantServerInfo
from ambient_ha.models.discovery import EntitySearchFilters
from ambient_ha.models.history import (
    EntityHistoryPage,
    LogbookPage,
    RecentChangesFilters,
    RecentChangesPage,
)
from ambient_ha.server import build_mcp_server
from tests.fixtures.discovery import REGISTRIES, STATES


class FakeGateway:
    resolver = DiscoveryResolver(REGISTRIES)

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
