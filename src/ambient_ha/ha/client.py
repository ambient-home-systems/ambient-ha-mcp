"""Facade that keeps semantic callers independent of raw HA interfaces."""

from __future__ import annotations

from typing import Protocol

import httpx

from ambient_ha.config import Settings
from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantError,
)
from ambient_ha.ha.normalize import normalize_server_info
from ambient_ha.ha.rest import HomeAssistantRestAPI
from ambient_ha.models.diagnostics import ConnectionStatus
from ambient_ha.models.home_assistant import HomeAssistantServerInfo


class HomeAssistantGateway(Protocol):
    """Semantic interface consumed by tools and future application services."""

    async def check_connection(self) -> ConnectionStatus:
        """Return normalized connectivity and authentication state."""
        ...

    async def get_server_info(self) -> HomeAssistantServerInfo:
        """Return a safe subset of Home Assistant installation information."""
        ...


class HomeAssistantClient:
    """Coordinate Home Assistant interfaces without leaking them to MCP tools.

    Phase 1 uses REST for two harmless reads. WebSocket and Home Assistant MCP
    adapters can be added behind this facade without changing tool contracts.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._rest = HomeAssistantRestAPI(
            base_url=settings.home_assistant_url,
            token=settings.home_assistant_token.get_secret_value(),
            timeout_seconds=settings.request_timeout_seconds,
            transport=transport,
        )

    async def check_connection(self) -> ConnectionStatus:
        """Return a stable, secret-free connection result."""
        try:
            await self._rest.check_connection()
        except HomeAssistantAuthenticationError as exc:
            return ConnectionStatus(
                status="authentication_failed",
                reachable=True,
                authenticated=False,
                message=str(exc),
                error_code=exc.code,
            )
        except HomeAssistantError as exc:
            return ConnectionStatus(
                status="unreachable" if not exc.reachable else "error",
                reachable=exc.reachable,
                authenticated=exc.authenticated,
                message=str(exc),
                error_code=exc.code,
            )
        return ConnectionStatus(
            status="connected",
            reachable=True,
            authenticated=True,
            message="Home Assistant is reachable and authenticated.",
        )

    async def get_server_info(self) -> HomeAssistantServerInfo:
        """Fetch and immediately reduce the HA config response to safe fields."""
        return normalize_server_info(await self._rest.get_config())
