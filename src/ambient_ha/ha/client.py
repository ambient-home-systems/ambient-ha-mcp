"""Facade that keeps semantic callers independent of raw HA interfaces."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Literal, Protocol

import httpx

from ambient_ha.config import Settings
from ambient_ha.ha.automation import (
    AutomationCatalog,
    find_automation_references,
    list_automations,
    normalize_automation_definition,
    normalize_automation_trace,
    normalize_trace_summaries,
    trace_target_execution_timestamp,
)
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
    parse_timestamp,
    resolve_query_window,
)
from ambient_ha.ha.home import HomeAnalyzer
from ambient_ha.ha.normalize import normalize_server_info
from ambient_ha.ha.rest import HomeAssistantRestAPI
from ambient_ha.ha.websocket import (
    AutomationProvider,
    HomeAssistantWebSocketAPI,
    RegistryProvider,
    RegistrySnapshot,
)
from ambient_ha.models.automation import (
    ActivityCauseReport,
    AutomationDefinition,
    AutomationListPage,
    AutomationReferencesPage,
    AutomationTrace,
    AutomationTracesPage,
    CausalityEvidence,
)
from ambient_ha.models.control import ControlServiceCall
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
from ambient_ha.models.home import (
    HomeDiagnosticsReport,
    HomeSummary,
    LightsOnPage,
    LocationFilters,
    LowBatteriesPage,
    LowBatteryFilters,
    OpeningFilters,
    OpeningsPage,
    UnavailableEntitiesPage,
    UnavailableEntityFilters,
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

    async def get_home_summary(self) -> HomeSummary:
        """Return one compact whole-home snapshot from a single bulk state read."""
        ...

    async def find_unavailable_entities(
        self, filters: UnavailableEntityFilters
    ) -> UnavailableEntitiesPage:
        """Return unavailable entities with honest current-state duration evidence."""
        ...

    async def find_low_batteries(self, filters: LowBatteryFilters) -> LowBatteriesPage:
        """Return genuine percentage battery sensors at or below a threshold."""
        ...

    async def get_openings(self, filters: OpeningFilters) -> OpeningsPage:
        """Return semantically classified doors, windows, garages, and openings."""
        ...

    async def get_lights_on(self, filters: LocationFilters) -> LightsOnPage:
        """Return a bounded current list of lights reporting on."""
        ...

    async def diagnose_home(self, *, limit: int) -> HomeDiagnosticsReport:
        """Return deterministic evidence-backed findings from one current snapshot."""
        ...

    async def list_automations(
        self, *, query: str | None, enabled: bool | None, limit: int
    ) -> AutomationListPage:
        """Return compact fresh automation entity metadata."""
        ...

    async def get_automation(
        self, entity_id: str
    ) -> tuple[bool, bool, AutomationDefinition | None]:
        """Return supported, found, and a bounded normalized definition."""
        ...

    async def find_automations_for_entity(
        self, entity_id: str, *, limit: int
    ) -> tuple[bool, AutomationReferencesPage]:
        """Return whether the entity exists plus conservative static references."""
        ...

    async def get_automation_traces(
        self, entity_id: str, *, limit: int
    ) -> tuple[bool, AutomationTracesPage]:
        """Return whether the automation exists plus bounded trace metadata."""
        ...

    async def get_automation_trace(
        self, entity_id: str, run_id: str
    ) -> tuple[bool, bool, AutomationTrace | None]:
        """Return supported, found, and one bounded normalized trace."""
        ...

    async def find_activity_cause(
        self,
        entity_id: str,
        *,
        timestamp: str | None,
        start: str | None,
        end: str | None,
        window_seconds: int,
        limit: int,
    ) -> tuple[bool, ActivityCauseReport]:
        """Correlate recorder and trace facts under strict evidence rules."""
        ...

    async def resolve_control_entities(
        self, entity_ids: list[str]
    ) -> tuple[list[EntityDetail], list[str]]:
        """Resolve exact control targets from one fresh state snapshot."""
        ...

    async def execute_control(self, call: ControlServiceCall) -> None:
        """Execute one bounded service call created by the central action executor."""
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
        automation_provider: AutomationProvider | None = None,
    ) -> None:
        self._settings = settings
        self._rest = HomeAssistantRestAPI(
            base_url=settings.home_assistant_url,
            token=settings.home_assistant_token.get_secret_value(),
            timeout_seconds=settings.request_timeout_seconds,
            transport=transport,
        )
        websocket_api = HomeAssistantWebSocketAPI(
            base_url=settings.home_assistant_url,
            websocket_url=settings.home_assistant_websocket_url,
            token=settings.home_assistant_token.get_secret_value(),
            timeout_seconds=settings.request_timeout_seconds,
            use_system_proxy=settings.home_assistant_websocket_use_system_proxy,
        )
        self._registries = registry_provider or websocket_api
        self._automations = automation_provider or websocket_api
        self._registry_cache = AsyncTTLCache[RegistrySnapshot](settings.registry_cache_ttl_seconds)
        self._automation_cache = AsyncTTLCache[AutomationCatalog](
            settings.registry_cache_ttl_seconds
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

    async def get_home_summary(self) -> HomeSummary:
        """Build a compact snapshot from one bulk state read and cached registries."""
        return (await self._home_analyzer()).home_summary()

    async def find_unavailable_entities(
        self, filters: UnavailableEntityFilters
    ) -> UnavailableEntitiesPage:
        return (await self._home_analyzer()).unavailable_entities(filters)

    async def find_low_batteries(self, filters: LowBatteryFilters) -> LowBatteriesPage:
        return (await self._home_analyzer()).low_batteries(filters)

    async def get_openings(self, filters: OpeningFilters) -> OpeningsPage:
        return (await self._home_analyzer()).openings(filters)

    async def get_lights_on(self, filters: LocationFilters) -> LightsOnPage:
        return (await self._home_analyzer()).lights_on(filters)

    async def diagnose_home(self, *, limit: int) -> HomeDiagnosticsReport:
        return (await self._home_analyzer()).diagnose(limit=limit)

    async def list_automations(
        self, *, query: str | None, enabled: bool | None, limit: int
    ) -> AutomationListPage:
        return list_automations(
            await self._rest.get_states(), query=query, enabled=enabled, limit=limit
        )

    async def get_automation(
        self, entity_id: str
    ) -> tuple[bool, bool, AutomationDefinition | None]:
        state = await self._rest.get_state(entity_id)
        if state is None or not entity_id.startswith("automation."):
            return True, False, None
        batch = await self._automations.get_automation_configs([entity_id])
        definition = normalize_automation_definition(
            state,
            batch.configurations.get(entity_id),
            supported=batch.supported,
        )
        return batch.supported, True, definition

    async def find_automations_for_entity(
        self, entity_id: str, *, limit: int
    ) -> tuple[bool, AutomationReferencesPage]:
        current_state, catalog = await asyncio.gather(
            self._rest.get_state(entity_id), self._automation_catalog()
        )
        return current_state is not None, find_automation_references(
            catalog, entity_id, limit=limit
        )

    async def get_automation_traces(
        self, entity_id: str, *, limit: int
    ) -> tuple[bool, AutomationTracesPage]:
        state = await self._rest.get_state(entity_id)
        item_id = entity_id.partition(".")[2]
        if state is None or not item_id:
            return False, normalize_trace_summaries(entity_id, [], limit=limit, supported=True)
        payload = await self._automations.list_automation_traces(item_id)
        return True, normalize_trace_summaries(
            entity_id,
            payload.traces,
            limit=limit,
            supported=payload.supported,
        )

    async def get_automation_trace(
        self, entity_id: str, run_id: str
    ) -> tuple[bool, bool, AutomationTrace | None]:
        state = await self._rest.get_state(entity_id)
        item_id = entity_id.partition(".")[2]
        if state is None or not item_id:
            return True, False, None
        payload = await self._automations.get_automation_trace(item_id, run_id)
        if not payload.supported or not payload.found or payload.trace is None:
            return payload.supported, False, None
        return True, True, normalize_automation_trace(entity_id, run_id, payload.trace)

    async def find_activity_cause(
        self,
        entity_id: str,
        *,
        timestamp: str | None,
        start: str | None,
        end: str | None,
        window_seconds: int,
        limit: int,
    ) -> tuple[bool, ActivityCauseReport]:
        window = self._activity_window(
            timestamp=timestamp,
            start=start,
            end=end,
            window_seconds=window_seconds,
        )
        raw_history, current_state, catalog, raw_traces, contexts = await asyncio.gather(
            self._rest.get_history(
                entity_ids=[entity_id],
                start=window.start_iso,
                end=window.end_iso,
                minimal_response=False,
            ),
            self._rest.get_state(entity_id),
            self._automation_catalog(),
            self._automations.list_automation_traces(None),
            self._automations.get_automation_trace_contexts(),
        )
        transitions = normalize_history_payload(raw_history, window=window).get(entity_id, [])
        changes = [item for item in transitions if item.began_within_range]
        references_page = find_automation_references(catalog, entity_id, limit=100)
        referenced = {item.automation_id for item in references_page.references}
        trace_rows = [row for row in raw_traces.traces if isinstance(row, Mapping)]
        full_trace_cache: dict[tuple[str, str], Mapping[str, object] | None] = {}
        evidence: list[CausalityEvidence] = []

        for change in changes:
            direct_context = None
            relationship: Literal["same_context", "parent_context", "none"] = "none"
            if change.context_id and change.context_id in contexts.contexts:
                direct_context = contexts.contexts[change.context_id]
                relationship = "same_context"
            elif change.context_parent_id and change.context_parent_id in contexts.contexts:
                direct_context = contexts.contexts[change.context_parent_id]
                relationship = "parent_context"
            if direct_context is not None:
                automation_id = f"automation.{direct_context.get('item_id', '')}"
                evidence.append(
                    CausalityEvidence(
                        source="automation",
                        relationship="confirmed_by_context",
                        confidence="confirmed",
                        event_timestamp=change.timestamp,
                        automation_id=automation_id,
                        run_id=direct_context.get("run_id"),
                        context_relationship=relationship,
                        supporting_facts=[
                            "Home Assistant directly links the state-change context to this "
                            "automation trace."
                        ],
                    )
                )
                continue
            if change.origin == "user":
                evidence.append(
                    CausalityEvidence(
                        source="user",
                        relationship="user_origin",
                        confidence="confirmed",
                        event_timestamp=change.timestamp,
                        supporting_facts=[
                            "Home Assistant recorded a user context; the user identifier is "
                            "intentionally omitted."
                        ],
                    )
                )
                continue

            nearby = _nearby_trace_rows(
                trace_rows,
                referenced,
                change_timestamp=change.timestamp,
                window_start=window.start,
                window_end=window.end,
            )
            matched_trace = False
            for automation_id, run_id, _execution_timestamp in nearby[:5]:
                key = (automation_id, run_id)
                if key not in full_trace_cache:
                    payload = await self._automations.get_automation_trace(
                        automation_id.partition(".")[2], run_id
                    )
                    full_trace_cache[key] = payload.trace if payload.found else None
                raw_trace = full_trace_cache[key]
                target_timestamp = (
                    trace_target_execution_timestamp(raw_trace, entity_id)
                    if raw_trace is not None
                    else None
                )
                timing_aligned = False
                if target_timestamp is not None:
                    try:
                        timing_aligned = (
                            abs(
                                (
                                    parse_timestamp(target_timestamp)
                                    - parse_timestamp(change.timestamp)
                                ).total_seconds()
                            )
                            <= 10
                        )
                    except HomeAssistantQueryError:
                        timing_aligned = False
                if timing_aligned:
                    evidence.append(
                        CausalityEvidence(
                            source="automation",
                            relationship="trace_confirmed",
                            confidence="confirmed",
                            event_timestamp=change.timestamp,
                            execution_timestamp=target_timestamp,
                            automation_id=automation_id,
                            run_id=run_id,
                            supporting_facts=[
                                "The stored trace records an executed step explicitly targeting "
                                "the entity.",
                                "The trace execution falls inside the requested event window.",
                            ],
                        )
                    )
                    matched_trace = True
                    break
            if matched_trace:
                continue
            if nearby:
                automation_id, run_id, execution_timestamp = nearby[0]
                evidence.append(
                    CausalityEvidence(
                        source="automation",
                        relationship="strong_temporal_match",
                        confidence="strong",
                        event_timestamp=change.timestamp,
                        execution_timestamp=execution_timestamp,
                        automation_id=automation_id,
                        run_id=run_id,
                        supporting_facts=[
                            "The automation statically references the entity.",
                            "Its trace started inside the requested event window.",
                            "No direct Home Assistant context relationship proves causality.",
                        ],
                    )
                )
                continue
            if references_page.references:
                reference = references_page.references[0]
                evidence.append(
                    CausalityEvidence(
                        source="automation",
                        relationship="possible_reference",
                        confidence="possible",
                        event_timestamp=change.timestamp,
                        automation_id=reference.automation_id,
                        supporting_facts=[
                            f"Static configuration contains a {reference.reference_type}.",
                            "No matching context or trace execution establishes causality.",
                        ],
                    )
                )
                continue
            evidence.append(
                CausalityEvidence(
                    source="unknown",
                    relationship="unrelated_or_unknown",
                    confidence="none",
                    event_timestamp=change.timestamp,
                    supporting_facts=["No supported automation causality evidence was found."],
                )
            )

        limitations = list(references_page.limitations)
        if not raw_traces.supported or not contexts.supported:
            limitations.append("The Home Assistant trace interface is unavailable.")
        complete = references_page.complete and raw_traces.supported and contexts.supported
        report = ActivityCauseReport(
            entity_id=entity_id,
            start=window.start_iso,
            end=window.end_iso,
            state_changes_found=len(changes),
            evidence=evidence[:limit],
            total_evidence=len(evidence),
            returned=min(len(evidence), limit),
            limit=limit,
            truncated=len(evidence) > limit,
            complete=complete,
            limitations=sorted(set(limitations)),
        )
        return current_state is not None or bool(transitions), report

    async def refresh_discovery_cache(self) -> None:
        """Explicitly invalidate registry metadata; states are never cached."""
        await self._registry_cache.clear()

    async def resolve_control_entities(
        self, entity_ids: list[str]
    ) -> tuple[list[EntityDetail], list[str]]:
        """Resolve exact canonical IDs without fuzzy matching or automatic selection."""
        states, resolver = await self._states_and_resolver()
        by_id = {
            entity.entity_id: entity
            for entity in resolver.entities(states, include_attributes=True)
            if entity.entity_id in entity_ids
        }
        return [by_id[item] for item in entity_ids if item in by_id], [
            item for item in entity_ids if item not in by_id
        ]

    async def execute_control(self, call: ControlServiceCall) -> None:
        """Send the executor's fixed semantic mapping to Home Assistant."""
        await self._rest.call_control_service(call)

    async def refresh_automation_cache(self) -> None:
        """Invalidate the bounded automation reference index."""
        await self._automation_cache.clear()

    async def _resolver(self) -> DiscoveryResolver:
        snapshot = await self._registry_cache.get(self._registries.get_registries)
        return DiscoveryResolver(snapshot)

    async def _states_and_resolver(
        self,
    ) -> tuple[list[Mapping[str, object]], DiscoveryResolver]:
        states, resolver = await asyncio.gather(self._rest.get_states(), self._resolver())
        return list(states), resolver

    async def _home_analyzer(self) -> HomeAnalyzer:
        states, resolver = await self._states_and_resolver()
        return HomeAnalyzer(
            resolver.entities(states, include_attributes=True),
            battery_warning_threshold=self._settings.battery_warning_threshold,
            ignored_entity_ids=self._settings.ignored_diagnostic_entity_ids,
        )

    async def _automation_catalog(self) -> AutomationCatalog:
        return await self._automation_cache.get(self._load_automation_catalog)

    async def _load_automation_catalog(self) -> AutomationCatalog:
        states, resolver = await self._states_and_resolver()
        entity_ids = sorted(
            entity_id
            for state in states
            if (entity_id := _mapping_text(state, "entity_id")) is not None
            and entity_id.startswith("automation.")
        )
        maximum = 500
        indexed_ids = entity_ids[:maximum]
        batch = await self._automations.get_automation_configs(indexed_ids)
        entity_device_ids = {
            entity_id: device_id
            for row in resolver.snapshot.entities
            if (entity_id := _mapping_text(row, "entity_id")) is not None
            and (device_id := _mapping_text(row, "device_id")) is not None
        }
        return AutomationCatalog(
            supported=batch.supported,
            configurations=batch.configurations,
            missing=batch.missing,
            entity_device_ids=entity_device_ids,
            truncated=len(entity_ids) > maximum,
        )

    def _activity_window(
        self,
        *,
        timestamp: str | None,
        start: str | None,
        end: str | None,
        window_seconds: int,
    ) -> QueryWindow:
        if timestamp is not None:
            center = parse_timestamp(timestamp)
            delta = timedelta(seconds=window_seconds)
            return self._history_window(
                start=(center - delta).isoformat(),
                end=(center + delta).isoformat(),
                duration_minutes=None,
            )
        return self._history_window(start=start, end=end, duration_minutes=None)

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


def _mapping_text(value: Mapping[str, object], key: str) -> str | None:
    item = value.get(key)
    return item if isinstance(item, str) and item else None


def _nearby_trace_rows(
    rows: list[Mapping[str, object]],
    referenced: set[str],
    *,
    change_timestamp: str,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[str, str, str]]:
    """Select statically relevant traces inside the already validated window."""
    change_time = parse_timestamp(change_timestamp)
    matches: list[tuple[float, str, str, str]] = []
    for row in rows:
        item_id = _mapping_text(row, "item_id")
        run_id = _mapping_text(row, "run_id")
        timestamp = row.get("timestamp")
        start = _mapping_text(timestamp, "start") if isinstance(timestamp, Mapping) else None
        if item_id is None or run_id is None or start is None:
            continue
        automation_id = f"automation.{item_id}"
        if automation_id not in referenced:
            continue
        try:
            trace_time = parse_timestamp(start)
        except HomeAssistantQueryError:
            continue
        if not window_start <= trace_time <= window_end:
            continue
        matches.append(
            (abs((trace_time - change_time).total_seconds()), automation_id, run_id, start)
        )
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(automation_id, run_id, start) for _, automation_id, run_id, start in matches]
