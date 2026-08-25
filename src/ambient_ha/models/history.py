"""Bounded, normalized read-only historical Home Assistant models."""

from __future__ import annotations

from pydantic import Field, JsonValue

from ambient_ha.models.discovery import StrictModel


class StateTransition(StrictModel):
    """One normalized recorder state boundary, never a raw state payload."""

    entity_id: str
    state: str
    timestamp: str
    attributes: dict[str, JsonValue] = Field(default_factory=dict)
    context_id: str | None = None
    context_parent_id: str | None = None
    origin: str = "unknown"
    began_within_range: bool
    duration_seconds: int | None = None
    duration_complete: bool = False


class EntityHistoryPage(StrictModel):
    """Bounded state-transition history for one entity and explicit query window."""

    entity_id: str
    start: str
    end: str
    transitions: list[StateTransition] = Field(default_factory=list)
    total_transitions: int
    returned: int
    limit: int
    truncated: bool


class LogbookEntry(StrictModel):
    """A compact, privacy-filtered logbook fact."""

    timestamp: str
    entity_id: str | None = None
    name: str | None = None
    message: str | None = None
    domain: str | None = None
    context_id: str | None = None
    context_parent_id: str | None = None


class LogbookPage(StrictModel):
    """Bounded normalized logbook facts for one explicit time window."""

    start: str
    end: str
    entries: list[LogbookEntry] = Field(default_factory=list)
    total_entries: int
    returned: int
    limit: int
    truncated: bool


class RecentChange(StrictModel):
    """A resolved historical state change without causal interpretation."""

    entity_id: str
    friendly_name: str | None = None
    previous_state: str | None = None
    new_state: str
    timestamp: str
    area_id: str | None = None
    area_name: str | None = None
    floor_id: str | None = None
    floor_name: str | None = None
    context_id: str | None = None
    context_parent_id: str | None = None
    origin: str = "unknown"


class RecentChangesFilters(StrictModel):
    """Composable, bounded filters for the recent-change semantic view."""

    start: str | None = None
    end: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=10080)
    area: str | None = None
    floor: str | None = None
    domain: str | None = None
    entity_id: str | None = None
    limit: int | None = Field(default=None, ge=1, le=500)


class RecentChangesPage(StrictModel):
    """A deterministic, bounded chronology of resolved state changes."""

    start: str
    end: str
    candidate_entities: int
    changes: list[RecentChange] = Field(default_factory=list)
    total_changes: int
    returned: int
    limit: int
    truncated: bool


class EntityHistoryResult(StrictModel):
    ok: bool
    message: str
    found: bool
    history: EntityHistoryPage | None = None
    error_code: str | None = None


class LogbookResult(StrictModel):
    ok: bool
    message: str
    logbook: LogbookPage | None = None
    error_code: str | None = None


class RecentChangesResult(StrictModel):
    ok: bool
    message: str
    changes: RecentChangesPage | None = None
    error_code: str | None = None
