"""Compact whole-home summaries and deterministic diagnostic models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from ambient_ha.models.discovery import StrictModel

DiagnosticSeverity = Literal["critical", "warning", "info"]
FindingCategory = Literal[
    "unavailable_entity",
    "unknown_entity",
    "low_battery",
    "open_door",
    "open_window",
    "open_garage",
    "moisture_detected",
    "smoke_detected",
    "carbon_monoxide_detected",
    "problem_sensor_active",
    "connectivity_problem",
]
OpeningType = Literal["door", "window", "garage_door", "opening"]


class DiagnosticEntity(StrictModel):
    """Privacy-minimized current entity evidence suitable for bounded lists."""

    entity_id: str
    friendly_name: str | None = None
    domain: str
    state: str
    device_class: str | None = None
    unit_of_measurement: str | None = None
    area_id: str | None = None
    area_name: str | None = None
    floor_id: str | None = None
    floor_name: str | None = None
    last_changed: str | None = None


class UnavailableEntity(DiagnosticEntity):
    """Unavailable entity with duration only when current-state evidence proves it."""

    unavailable_duration_seconds: int | None = None
    duration_evidence_available: bool


class LowBatteryEntity(DiagnosticEntity):
    battery_percent: float


class OpeningEntity(DiagnosticEntity):
    opening_type: OpeningType
    normalized_state: Literal["open", "closed", "unavailable", "unknown"]


class LightOnEntity(DiagnosticEntity):
    brightness: int | None = None


class DiagnosticFinding(StrictModel):
    """Deterministic finding containing a cautious statement and factual evidence."""

    category: FindingCategory
    severity: DiagnosticSeverity
    message: str
    evidence: str
    entity: DiagnosticEntity


class HomeSummarySection(StrictModel):
    """One supported whole-home section with compact facts and bounded evidence."""

    name: Literal[
        "occupancy",
        "openings",
        "lighting",
        "climate",
        "environment",
        "device_health",
        "safety",
        "energy",
    ]
    entity_count: int
    facts: dict[str, JsonValue] = Field(default_factory=dict)
    details: list[DiagnosticEntity] = Field(default_factory=list)
    details_truncated: bool = False


class HomeSummary(StrictModel):
    generated_at: str
    total_entities: int
    available_entities: int
    unavailable_entities: int
    unknown_entities: int
    sections: list[HomeSummarySection] = Field(default_factory=list)
    attention_items: list[DiagnosticFinding] = Field(default_factory=list)
    total_attention_items: int
    attention_items_truncated: bool


class UnavailableEntityFilters(StrictModel):
    domain: str | None = None
    area: str | None = None
    floor: str | None = None
    minimum_duration_minutes: int | None = Field(default=None, ge=1, le=10080)
    limit: int = Field(default=25, ge=1, le=100)


class LowBatteryFilters(StrictModel):
    threshold: int = Field(ge=1, le=100)
    area: str | None = None
    floor: str | None = None
    limit: int = Field(default=25, ge=1, le=100)


class OpeningFilters(StrictModel):
    area: str | None = None
    floor: str | None = None
    opening_type: OpeningType | None = None
    state: Literal["open", "closed", "unavailable", "unknown", "any"] = "open"
    limit: int = Field(default=25, ge=1, le=100)


class LocationFilters(StrictModel):
    area: str | None = None
    floor: str | None = None
    limit: int = Field(default=25, ge=1, le=100)


class UnavailableEntitiesPage(StrictModel):
    entities: list[UnavailableEntity] = Field(default_factory=list)
    total_matches: int
    unknown_in_scope: int
    returned: int
    limit: int
    truncated: bool
    duration_filter_complete: bool
    entities_without_duration_evidence: int


class LowBatteriesPage(StrictModel):
    threshold: int
    entities: list[LowBatteryEntity] = Field(default_factory=list)
    total_matches: int
    returned: int
    limit: int
    truncated: bool


class OpeningsPage(StrictModel):
    entities: list[OpeningEntity] = Field(default_factory=list)
    counts_by_type: dict[str, int] = Field(default_factory=dict)
    total_matches: int
    returned: int
    limit: int
    truncated: bool


class LightsOnPage(StrictModel):
    entities: list[LightOnEntity] = Field(default_factory=list)
    total_matches: int
    returned: int
    limit: int
    truncated: bool


class HomeDiagnosticsReport(StrictModel):
    generated_at: str
    findings: list[DiagnosticFinding] = Field(default_factory=list)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    total_findings: int
    returned: int
    limit: int
    truncated: bool


class HomeSummaryResult(StrictModel):
    ok: bool
    message: str
    summary: HomeSummary | None = None
    error_code: str | None = None


class UnavailableEntitiesResult(StrictModel):
    ok: bool
    message: str
    result: UnavailableEntitiesPage | None = None
    error_code: str | None = None


class LowBatteriesResult(StrictModel):
    ok: bool
    message: str
    result: LowBatteriesPage | None = None
    error_code: str | None = None


class OpeningsResult(StrictModel):
    ok: bool
    message: str
    result: OpeningsPage | None = None
    error_code: str | None = None


class LightsOnResult(StrictModel):
    ok: bool
    message: str
    result: LightsOnPage | None = None
    error_code: str | None = None


class HomeDiagnosticsResult(StrictModel):
    ok: bool
    message: str
    report: HomeDiagnosticsReport | None = None
    error_code: str | None = None
