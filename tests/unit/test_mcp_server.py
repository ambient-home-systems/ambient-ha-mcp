import httpx
import pytest
from mcp import Client
from mcp.server.transport_security import TransportSecuritySettings

from ambient_ha.config import Settings
from ambient_ha.models import ConnectionStatus, HomeAssistantServerInfo
from ambient_ha.server import build_mcp_server


class FakeGateway:
    async def check_connection(self) -> ConnectionStatus:
        return ConnectionStatus(
            status="connected",
            reachable=True,
            authenticated=True,
            message="Home Assistant is reachable and authenticated.",
        )

    async def get_server_info(self) -> HomeAssistantServerInfo:
        return HomeAssistantServerInfo(version="2026.8.2", time_zone="America/New_York")


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
