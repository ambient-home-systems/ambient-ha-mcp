from dataclasses import dataclass

import pytest

from ambient_ha.models import ConnectionStatus, HomeAssistantServerInfo
from ambient_ha.tools import connection_status, health_status, server_info


@dataclass
class FakeGateway:
    connection: ConnectionStatus

    async def check_connection(self) -> ConnectionStatus:
        return self.connection

    async def get_server_info(self) -> HomeAssistantServerInfo:
        return HomeAssistantServerInfo(version="2026.8.2", time_zone="America/New_York")


@pytest.mark.anyio
async def test_diagnostic_tool_services_return_structured_results() -> None:
    gateway = FakeGateway(
        ConnectionStatus(
            status="connected",
            reachable=True,
            authenticated=True,
            message="connected",
        )
    )

    connection = await connection_status(gateway)
    info = await server_info(gateway)
    health = await health_status(gateway)

    assert connection.authenticated is True
    assert info.available is True
    assert info.server is not None
    assert info.server.version == "2026.8.2"
    assert health.status == "ok"


@pytest.mark.anyio
async def test_health_is_degraded_when_home_assistant_is_unavailable() -> None:
    gateway = FakeGateway(
        ConnectionStatus(
            status="unreachable",
            reachable=False,
            authenticated=False,
            message="unreachable",
            error_code="unreachable",
        )
    )

    health = await health_status(gateway)

    assert health.application_running is True
    assert health.status == "degraded"
    assert health.home_assistant_reachable is False
