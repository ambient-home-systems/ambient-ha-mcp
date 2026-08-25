"""Diagnostic application services shared by MCP and HTTP health surfaces."""

from __future__ import annotations

import logging

from ambient_ha.ha.client import HomeAssistantGateway
from ambient_ha.ha.exceptions import HomeAssistantError
from ambient_ha.models.diagnostics import ConnectionStatus, HealthStatus, ServerInfoResult

LOGGER = logging.getLogger(__name__)


async def connection_status(client: HomeAssistantGateway) -> ConnectionStatus:
    """Get connectivity state while containing unexpected implementation failures."""
    try:
        return await client.check_connection()
    except Exception:
        LOGGER.exception("Unexpected error while checking Home Assistant connectivity")
        return ConnectionStatus(
            status="error",
            reachable=False,
            authenticated=False,
            message="The bridge could not complete the Home Assistant connection check.",
            error_code="internal_error",
        )


async def server_info(client: HomeAssistantGateway) -> ServerInfoResult:
    """Return normalized server metadata without leaking raw HA configuration."""
    try:
        info = await client.get_server_info()
    except HomeAssistantError as exc:
        return ServerInfoResult(
            available=False,
            message=str(exc),
            error_code=exc.code,
        )
    except Exception:
        LOGGER.exception("Unexpected error while reading Home Assistant server information")
        return ServerInfoResult(
            available=False,
            message="The bridge could not read Home Assistant server information.",
            error_code="internal_error",
        )
    return ServerInfoResult(
        available=True,
        server=info,
        message="Home Assistant server information is available.",
    )


async def health_status(client: HomeAssistantGateway) -> HealthStatus:
    """Keep liveness healthy while reporting upstream readiness separately."""
    connection = await connection_status(client)
    ready = connection.reachable and connection.authenticated
    return HealthStatus(
        status="ok" if ready else "degraded",
        home_assistant_reachable=connection.reachable,
        home_assistant_authenticated=connection.authenticated,
    )
