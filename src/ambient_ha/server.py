"""MCP server and lightweight health endpoint."""

from __future__ import annotations

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ambient_ha.config import Settings, get_settings
from ambient_ha.ha.client import HomeAssistantClient, HomeAssistantGateway
from ambient_ha.logging import configure_logging
from ambient_ha.models.diagnostics import ConnectionStatus, ServerInfoResult
from ambient_ha.models.discovery import (
    AreaListResult,
    AreaResult,
    DomainSummaryResult,
    EntityResult,
    EntitySearchResult,
    FloorListResult,
    FloorResult,
)
from ambient_ha.models.history import EntityHistoryResult, LogbookResult, RecentChangesResult
from ambient_ha.tools.diagnostics import connection_status, health_status, server_info
from ambient_ha.tools.discovery import (
    domain_summary as domain_summary_tool,
)
from ambient_ha.tools.discovery import (
    get_area as get_area_tool,
)
from ambient_ha.tools.discovery import (
    get_entity as get_entity_tool,
)
from ambient_ha.tools.discovery import (
    get_floor as get_floor_tool,
)
from ambient_ha.tools.discovery import (
    list_areas as list_areas_tool,
)
from ambient_ha.tools.discovery import (
    list_floors as list_floors_tool,
)
from ambient_ha.tools.discovery import (
    search_entities as search_entities_tool,
)
from ambient_ha.tools.history import (
    get_entity_history as get_entity_history_tool,
)
from ambient_ha.tools.history import (
    get_logbook as get_logbook_tool,
)
from ambient_ha.tools.history import (
    get_recent_changes as get_recent_changes_tool,
)


def build_mcp_server(
    settings: Settings,
    *,
    client: HomeAssistantGateway | None = None,
) -> MCPServer:
    """Build a testable MCP server with its semantic dependencies injected."""
    ha_client = client or HomeAssistantClient(settings)
    server = MCPServer(
        "Ambient Home Assistant MCP",
        instructions=(
            "Use these read-only tools to inspect Home Assistant connectivity, entities, "
            "areas, floors, current state, and recorded historical facts. Prefer search when a "
            "user gives a human name instead of an entity ID. Historical tools report recorded "
            "facts, not why an event happened. No tool changes Home Assistant."
        ),
    )

    @server.tool(
        description=(
            "Check whether the Ambient bridge can reach Home Assistant and whether its "
            "configured access token is accepted. Use this first when another Home Assistant "
            "request fails. The result never includes credentials."
        )
    )
    async def ha_connection_status() -> ConnectionStatus:
        return await connection_status(ha_client)

    @server.tool(
        description=(
            "Return a deliberately limited set of non-sensitive Home Assistant installation "
            "metadata, such as version, time zone, and unit system. This does not return raw "
            "Home Assistant configuration, entity data, paths, coordinates, or credentials."
        )
    )
    async def ha_server_info() -> ServerInfoResult:
        return await server_info(ha_client)

    @server.tool(
        description=(
            "Get one Home Assistant entity by its exact entity ID, including current state, "
            "resolved area/floor/device metadata, and a bounded allowlist of safe attributes. "
            "Use this when the entity ID is known. Do not use it for a human-readable name; "
            "use ha_search_entities instead. This operation is read-only."
        )
    )
    async def ha_get_entity(entity_id: str) -> EntityResult:
        return await get_entity_tool(ha_client, entity_id)

    @server.tool(
        description=(
            "Search Home Assistant entities by human-readable query, domain, area, floor, "
            "state, or availability. Filters compose and matching is case-insensitive. Use "
            "this when the exact entity ID is unknown or when the user asks for a set such as "
            "lights that are on. Results are compact, deterministically ranked, and capped at "
            "100. This operation is read-only and does not return detailed attributes."
        )
    )
    async def ha_search_entities(
        query: str | None = None,
        domain: str | None = None,
        area: str | None = None,
        floor: str | None = None,
        state: str | None = None,
        available: bool | None = None,
        limit: int = 25,
    ) -> EntitySearchResult:
        return await search_entities_tool(
            ha_client,
            query=query,
            domain=domain,
            area=area,
            floor=floor,
            state=state,
            available=available,
            limit=limit,
        )

    @server.tool(
        description=(
            "List configured Home Assistant areas with floor and entity counts. Use this to "
            "discover available area names or summarize the home's organization. Do not use "
            "it to retrieve every entity in an area; use ha_get_area when details are needed. "
            "This operation is read-only and never embeds giant entity arrays."
        )
    )
    async def ha_list_areas() -> AreaListResult:
        return await list_areas_tool(ha_client)

    @server.tool(
        description=(
            "Get one Home Assistant area by area ID or human-readable name. Returns floor "
            "metadata and domain/entity counts. Set include_entities only when a bounded entity "
            "list is genuinely needed; that list is capped at 50. This operation is read-only."
        )
    )
    async def ha_get_area(area: str, include_entities: bool = False, limit: int = 25) -> AreaResult:
        return await get_area_tool(
            ha_client,
            area,
            include_entities=include_entities,
            limit=limit,
        )

    @server.tool(
        description=(
            "List configured Home Assistant floors with level, area count, and entity count. "
            "Use this to discover floor names or see the home's high-level organization. "
            "Returns a useful unsupported result on older Home Assistant versions. This is "
            "read-only and does not return entity arrays."
        )
    )
    async def ha_list_floors() -> FloorListResult:
        return await list_floors_tool(ha_client)

    @server.tool(
        description=(
            "Get one Home Assistant floor by floor ID or human-readable name, including its "
            "areas and aggregate entity counts by domain. Use this for floor-level questions, "
            "not for one known entity. Returns unsupported rather than failing on installations "
            "without floors. This operation is read-only."
        )
    )
    async def ha_get_floor(floor: str) -> FloorResult:
        return await get_floor_tool(ha_client, floor)

    @server.tool(
        description=(
            "Summarize current Home Assistant entities in one domain, such as light, sensor, "
            "or binary_sensor. Returns total, availability, unknown count, and generic counts "
            "for every observed state without assuming all domains use on/off. Use search when "
            "individual entities are needed. This operation is read-only."
        )
    )
    async def ha_domain_summary(domain: str) -> DomainSummaryResult:
        return await domain_summary_tool(ha_client, domain)

    @server.tool(
        description=(
            "Get recorded Home Assistant state transitions for one exact entity ID over an "
            "explicit ISO-8601 time window. Use this for questions such as when an entity "
            "changed state or how long a recorded state lasted. Timestamps must include an "
            "offset or Z; results are bounded and mark incomplete durations honestly. This is "
            "read-only and reports recorded facts, not why they happened."
        )
    )
    async def ha_get_entity_history(
        entity_id: str,
        start: str,
        end: str | None = None,
        limit: int | None = None,
        minimal_response: bool = True,
    ) -> EntityHistoryResult:
        return await get_entity_history_tool(
            ha_client,
            entity_id,
            start=start,
            end=end,
            limit=limit,
            minimal_response=minimal_response,
        )

    @server.tool(
        description=(
            "Get recorded Home Assistant logbook facts for an explicit ISO-8601 time window, "
            "optionally filtered to one entity. Use this for concise activity records when the "
            "entity ID is known. Results are bounded and privacy-filtered. This is read-only; "
            "Recorder retention, exclusions, or unavailable logbook data can yield no results."
        )
    )
    async def ha_get_logbook(
        start: str,
        end: str | None = None,
        entity_id: str | None = None,
        limit: int | None = None,
    ) -> LogbookResult:
        return await get_logbook_tool(
            ha_client, start=start, end=end, entity_id=entity_id, limit=limit
        )

    @server.tool(
        description=(
            "Find recorded Home Assistant state changes across current entities during a "
            "bounded time window. Filter by area, floor, domain, or exact entity ID. Use this "
            "for questions such as what changed in a room recently. It returns chronological "
            "facts only, never causal explanations, and is completely read-only."
        )
    )
    async def ha_get_recent_changes(
        start: str | None = None,
        end: str | None = None,
        duration_minutes: int | None = None,
        area: str | None = None,
        floor: str | None = None,
        domain: str | None = None,
        entity_id: str | None = None,
        limit: int | None = None,
    ) -> RecentChangesResult:
        return await get_recent_changes_tool(
            ha_client,
            start=start,
            end=end,
            duration_minutes=duration_minutes,
            area=area,
            floor=floor,
            domain=domain,
            entity_id=entity_id,
            limit=limit,
        )

    @server.custom_route("/health", methods=["GET"])  # type: ignore[untyped-decorator]
    async def health(_request: Request) -> Response:
        result = await health_status(ha_client)
        # Liveness stays HTTP 200 while an upstream HA outage is represented as degraded.
        return JSONResponse(result.model_dump(mode="json"), status_code=200)

    return server


def create_app(settings: Settings | None = None) -> Starlette:
    """Create the Streamable HTTP ASGI application."""
    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)
    server = build_mcp_server(runtime_settings)
    security = TransportSecuritySettings(
        allowed_hosts=runtime_settings.allowed_hosts,
        allowed_origins=runtime_settings.allowed_origins,
    )
    return server.streamable_http_app(transport_security=security)


def main() -> None:
    """Run the local/container server with graceful ASGI signal handling."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
