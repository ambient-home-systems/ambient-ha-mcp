"""Normalized read-only discovery and entity-state models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictModel(BaseModel):
    """Reject accidental schema expansion at every MCP boundary."""

    model_config = ConfigDict(extra="forbid")


class EntitySummary(StrictModel):
    """Compact entity representation suitable for lists and search results."""

    entity_id: str
    domain: str
    state: str
    friendly_name: str | None = None
    area_id: str | None = None
    area_name: str | None = None
    floor_id: str | None = None
    floor_name: str | None = None
    device_id: str | None = None
    device_name: str | None = None
    available: bool


class EntityDetail(EntitySummary):
    """Expanded single-entity result with bounded, sanitized attributes."""

    last_changed: str | None = None
    last_updated: str | None = None
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class EntitySearchFilters(StrictModel):
    """Composable deterministic entity search filters."""

    query: str | None = None
    domain: str | None = None
    area: str | None = None
    floor: str | None = None
    state: str | None = None
    available: bool | None = None
    limit: int = Field(default=25, ge=1, le=100)


class EntitySearchPage(StrictModel):
    """Bounded search results with truncation metadata."""

    entities: list[EntitySummary]
    total_matches: int
    returned: int
    limit: int
    truncated: bool


class AreaSummary(StrictModel):
    """Compact area metadata without an embedded entity dump."""

    area_id: str
    name: str
    floor_id: str | None = None
    floor_name: str | None = None
    entity_count: int


class AreaDetail(AreaSummary):
    """Area aggregates with optional, explicitly requested entities."""

    entity_counts_by_domain: dict[str, int]
    entities: list[EntitySummary] = Field(default_factory=list)
    entities_included: bool = False
    entities_truncated: bool = False


class FloorSummary(StrictModel):
    """Compact floor metadata and aggregate counts."""

    floor_id: str
    name: str
    level: int | None = None
    area_count: int
    entity_count: int


class FloorDetail(FloorSummary):
    """Floor metadata with bounded area summaries and domain counts."""

    areas: list[AreaSummary]
    entity_counts_by_domain: dict[str, int]


class DomainSummary(StrictModel):
    """Generic domain aggregates that do not assume on/off semantics."""

    domain: str
    total: int
    available: int
    unavailable: int
    unknown: int
    states: dict[str, int]


class EntityResult(StrictModel):
    ok: bool
    message: str
    found: bool
    entity: EntityDetail | None = None
    error_code: str | None = None


class EntitySearchResult(EntitySearchPage):
    ok: bool
    message: str
    error_code: str | None = None


class AreaListResult(StrictModel):
    ok: bool
    message: str
    supported: bool
    areas: list[AreaSummary] = Field(default_factory=list)
    error_code: str | None = None


class AreaResult(StrictModel):
    ok: bool
    message: str
    supported: bool
    found: bool
    area: AreaDetail | None = None
    error_code: str | None = None


class FloorListResult(StrictModel):
    ok: bool
    message: str
    supported: bool
    floors: list[FloorSummary] = Field(default_factory=list)
    error_code: str | None = None


class FloorResult(StrictModel):
    ok: bool
    message: str
    supported: bool
    found: bool
    floor: FloorDetail | None = None
    error_code: str | None = None


class DomainSummaryResult(StrictModel):
    ok: bool
    message: str
    summary: DomainSummary | None = None
    error_code: str | None = None
