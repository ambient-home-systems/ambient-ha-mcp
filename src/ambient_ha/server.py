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
from ambient_ha.tools.diagnostics import connection_status, health_status, server_info


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
            "Use these read-only diagnostic tools to verify the bridge and inspect safe "
            "Home Assistant installation metadata. No device-control tools are available."
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
