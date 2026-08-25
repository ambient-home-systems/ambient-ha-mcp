"""Facade that keeps semantic callers independent of raw HA interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta
from typing import Protocol

import httpx

from ambient_ha.config import Settings
from ambient_ha.ha.cache import AsyncTTLCache
from ambient_ha.ha.discovery import DiscoveryResolver
from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantError,
    HomeAssistantQueryError,
)
from ambient_ha.ha.history import (
    QueryWindow,
    build_recent_changes,
    normalize_history_payload,
    normalize_logbook_payload,
    resolve_query_window,
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
from ambient_ha.models.history import (
    EntityHistoryPage,
    LogbookPage,
    RecentChangesFilters,
    RecentChangesPage,
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

    async def get_entity_history(
        self,
        entity_id: str,
        *,
        start: str,
        end: str | None,
        limit: int | None,
        minimal_response: bool,
    ) -> tuple[bool, EntityHistoryPage]:
        """Return one entity's bounded recorder history and current/existing status."""
        ...

    async def get_logbook(
        self,
        *,
        start: str,
        end: str | None,
        entity_id: str | None,
        limit: int | None,
    ) -> LogbookPage:
        """Return bounded normalized logbook facts for one explicit time window."""
        ...

    async def get_recent_changes(self, filters: RecentChangesFilters) -> RecentChangesPage:
        """Return bounded, resolved historical changes for current candidate entities."""
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
        self._settings = settings
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

    async def get_entity_history(
        self,
        entity_id: str,
        *,
        start: str,
        end: str | None,
        limit: int | None,
        minimal_response: bool,
    ) -> tuple[bool, EntityHistoryPage]:
        """Fetch an entity once from recorder and once from current state, both read-only."""
        window = self._history_window(start=start, end=end, duration_minutes=None)
        raw_history, current_state = await asyncio.gather(
            self._rest.get_history(
                entity_ids=[entity_id],
                start=window.start_iso,
                end=window.end_iso,
                minimal_response=minimal_response,
            ),
            self._rest.get_state(entity_id),
        )
        transitions = normalize_history_payload(raw_history, window=window).get(entity_id, [])
        effective_limit = self._history_limit(limit)
        return (
            current_state is not None or bool(transitions),
            EntityHistoryPage(
                entity_id=entity_id,
                start=window.start_iso,
                end=window.end_iso,
                transitions=transitions[:effective_limit],
                total_transitions=len(transitions),
                returned=min(len(transitions), effective_limit),
                limit=effective_limit,
                truncated=len(transitions) > effective_limit,
            ),
        )

    async def get_logbook(
        self,
        *,
        start: str,
        end: str | None,
        entity_id: str | None,
        limit: int | None,
    ) -> LogbookPage:
        """Fetch recorder logbook facts with query-bound protection."""
        window = self._history_window(start=start, end=end, duration_minutes=None)
        entries = normalize_logbook_payload(
            await self._rest.get_logbook(
                start=window.start_iso, end=window.end_iso, entity_id=entity_id
            )
        )
        effective_limit = self._history_limit(limit)
        return LogbookPage(
            start=window.start_iso,
            end=window.end_iso,
            entries=entries[:effective_limit],
            total_entries=len(entries),
            returned=min(len(entries), effective_limit),
            limit=effective_limit,
            truncated=len(entries) > effective_limit,
        )

    async def get_recent_changes(self, filters: RecentChangesFilters) -> RecentChangesPage:
        """Resolve current candidates once, then batch their recorder request once."""
        window = self._history_window(
            start=filters.start,
            end=filters.end,
            duration_minutes=filters.duration_minutes,
        )
        states, resolver = await self._states_and_resolver()
        candidates = [
            entity
            for entity in resolver.entities(states)
            if _matches_recent_change_filters(entity, filters)
        ]
        if len(candidates) > self._settings.history_max_entities:
            raise HomeAssistantQueryError(
                "too_many_candidate_entities",
                "The requested filters match more entities than the historical query limit.",
            )
        effective_limit = self._history_limit(filters.limit)
        if not candidates:
            return RecentChangesPage(
                start=window.start_iso,
                end=window.end_iso,
                candidate_entities=0,
                total_changes=0,
                returned=0,
                limit=effective_limit,
                truncated=False,
            )
        raw_history = await self._rest.get_history(
            entity_ids=[entity.entity_id for entity in candidates],
            start=window.start_iso,
            end=window.end_iso,
            minimal_response=True,
        )
        history = normalize_history_payload(raw_history, window=window)
        changes = build_recent_changes(history, {entity.entity_id: entity for entity in candidates})
        return RecentChangesPage(
            start=window.start_iso,
            end=window.end_iso,
            candidate_entities=len(candidates),
            changes=changes[:effective_limit],
            total_changes=len(changes),
            returned=min(len(changes), effective_limit),
            limit=effective_limit,
            truncated=len(changes) > effective_limit,
        )

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

    def _history_window(
        self, *, start: str | None, end: str | None, duration_minutes: int | None
    ) -> QueryWindow:
        return resolve_query_window(
            start=start,
            end=end,
            duration_minutes=duration_minutes,
            default_lookback=timedelta(hours=self._settings.history_default_lookback_hours),
            maximum_lookback=timedelta(hours=self._settings.history_max_lookback_hours),
        )

    def _history_limit(self, limit: int | None) -> int:
        requested = limit if limit is not None else self._settings.history_default_limit
        return min(max(1, requested), self._settings.history_max_events)


def _matches_recent_change_filters(entity: EntityDetail, filters: RecentChangesFilters) -> bool:
    if filters.entity_id and entity.entity_id.casefold() != filters.entity_id.strip().casefold():
        return False
    if filters.domain and entity.domain.casefold() != filters.domain.strip().casefold():
        return False
    if filters.area and not _matches_identifier(filters.area, entity.area_id, entity.area_name):
        return False
    return not (
        filters.floor and not _matches_identifier(filters.floor, entity.floor_id, entity.floor_name)
    )


def _matches_identifier(value: str, identifier: str | None, name: str | None) -> bool:
    target = value.strip().casefold().replace("_", " ")
    candidates = (identifier, name)
    return any(
        candidate is not None and candidate.casefold().replace("_", " ") == target
        for candidate in candidates
    )
