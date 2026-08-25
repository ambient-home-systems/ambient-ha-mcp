"""Facade that keeps semantic callers independent of raw HA interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Protocol

import httpx

from ambient_ha.config import Settings
from ambient_ha.ha.cache import AsyncTTLCache
from ambient_ha.ha.discovery import DiscoveryResolver
from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantError,
)
from ambient_ha.ha.normalize import normalize_server_info
from ambient_ha.ha.rest import HomeAssistantRestAPI
from ambient_ha.ha.websocket import (
    HomeAssistantWebSocketAPI,
    RegistryProvider,
    RegistrySnapshot,
)
from ambient_ha.models.diagnostics import ConnectionStatus
from ambient_ha.models.discovery import (
    AreaDetail,
    AreaSummary,
    DomainSummary,
    EntityDetail,
    EntitySearchFilters,
    EntitySearchPage,
    FloorDetail,
    FloorSummary,
)
from ambient_ha.models.home_assistant import HomeAssistantServerInfo


class HomeAssistantGateway(Protocol):
    """Semantic interface consumed by tools and future application services."""

    async def check_connection(self) -> ConnectionStatus:
        """Return normalized connectivity and authentication state."""
        ...

    async def get_server_info(self) -> HomeAssistantServerInfo:
        """Return a safe subset of Home Assistant installation information."""
        ...

    async def get_entity(self, entity_id: str) -> EntityDetail | None:
        """Return one current normalized entity or ``None`` when it does not exist."""
        ...

    async def search_entities(self, filters: EntitySearchFilters) -> EntitySearchPage:
        """Search fresh states using cached registry metadata."""
        ...

    async def list_areas(self) -> tuple[bool, list[AreaSummary]]:
        """Return whether area registry is supported and its compact areas."""
        ...

    async def get_area(
        self, identifier: str, *, include_entities: bool, limit: int
    ) -> tuple[bool, AreaDetail | None]:
        """Resolve an area by ID or name."""
        ...

    async def list_floors(self) -> tuple[bool, list[FloorSummary]]:
        """Return whether floors are supported and configured floor summaries."""
        ...

    async def get_floor(self, identifier: str) -> tuple[bool, FloorDetail | None]:
        """Resolve a floor by ID or name when supported."""
        ...

    async def get_domain_summary(self, domain: str) -> DomainSummary:
        """Aggregate current states for one domain."""
        ...


class HomeAssistantClient:
    """Coordinate Home Assistant interfaces without leaking them to MCP tools.

    REST supplies fresh states and safe metadata. WebSocket supplies slowly
    changing registries without exposing transport details to tool contracts.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        registry_provider: RegistryProvider | None = None,
    ) -> None:
        self._rest = HomeAssistantRestAPI(
            base_url=settings.home_assistant_url,
            token=settings.home_assistant_token.get_secret_value(),
            timeout_seconds=settings.request_timeout_seconds,
            transport=transport,
        )
        self._registries = registry_provider or HomeAssistantWebSocketAPI(
            base_url=settings.home_assistant_url,
            token=settings.home_assistant_token.get_secret_value(),
            timeout_seconds=settings.request_timeout_seconds,
        )
        self._registry_cache = AsyncTTLCache[RegistrySnapshot](settings.registry_cache_ttl_seconds)

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

    async def get_entity(self, entity_id: str) -> EntityDetail | None:
        """Read one state fresh and enrich it with cached registry metadata."""
        state = await self._rest.get_state(entity_id)
        if state is None:
            return None
        resolver = await self._resolver()
        return resolver.entity(state)

    async def search_entities(self, filters: EntitySearchFilters) -> EntitySearchPage:
        states, resolver = await self._states_and_resolver()
        return resolver.search(states, filters)

    async def list_areas(self) -> tuple[bool, list[AreaSummary]]:
        states, resolver = await self._states_and_resolver()
        return resolver.snapshot.area_registry_supported, resolver.list_areas(states)

    async def get_area(
        self, identifier: str, *, include_entities: bool, limit: int
    ) -> tuple[bool, AreaDetail | None]:
        states, resolver = await self._states_and_resolver()
        return (
            resolver.snapshot.area_registry_supported,
            resolver.get_area(
                states,
                identifier,
                include_entities=include_entities,
                limit=limit,
            ),
        )

    async def list_floors(self) -> tuple[bool, list[FloorSummary]]:
        states, resolver = await self._states_and_resolver()
        return resolver.snapshot.floor_registry_supported, resolver.list_floors(states)

    async def get_floor(self, identifier: str) -> tuple[bool, FloorDetail | None]:
        states, resolver = await self._states_and_resolver()
        return resolver.snapshot.floor_registry_supported, resolver.get_floor(states, identifier)

    async def get_domain_summary(self, domain: str) -> DomainSummary:
        states, resolver = await self._states_and_resolver()
        return resolver.domain_summary(states, domain)

    async def refresh_discovery_cache(self) -> None:
        """Explicitly invalidate registry metadata; states are never cached."""
        await self._registry_cache.clear()

    async def _resolver(self) -> DiscoveryResolver:
        snapshot = await self._registry_cache.get(self._registries.get_registries)
        return DiscoveryResolver(snapshot)

    async def _states_and_resolver(
        self,
    ) -> tuple[list[Mapping[str, object]], DiscoveryResolver]:
        states, resolver = await asyncio.gather(self._rest.get_states(), self._resolver())
        return list(states), resolver
