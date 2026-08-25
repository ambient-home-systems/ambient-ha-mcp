"""Deterministic semantic classification over one normalized home snapshot."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal

from ambient_ha.ha.history import parse_timestamp
from ambient_ha.models.discovery import EntityDetail
from ambient_ha.models.home import (
    DiagnosticEntity,
    DiagnosticFinding,
    HomeDiagnosticsReport,
    HomeSummary,
    HomeSummarySection,
    LightOnEntity,
    LightsOnPage,
    LocationFilters,
    LowBatteriesPage,
    LowBatteryEntity,
    LowBatteryFilters,
    OpeningEntity,
    OpeningFilters,
    OpeningsPage,
    OpeningType,
    UnavailableEntitiesPage,
    UnavailableEntity,
    UnavailableEntityFilters,
)

_OPENING_CLASSES: dict[str, OpeningType] = {
    "door": "door",
    "window": "window",
    "garage": "garage_door",
    "garage_door": "garage_door",
    "opening": "opening",
}
_SAFETY_CLASSES = {"moisture", "smoke", "carbon_monoxide", "problem", "connectivity"}
_ENVIRONMENT_CLASSES = {"temperature", "humidity"}
_ENERGY_CLASSES = {"power", "energy"}
_OCCUPANCY_CLASSES = {"motion", "occupancy", "presence"}
_ACTIVE_STATES = {"on", "open", "opening", "closing"}
_INACTIVE_STATES = {"off", "closed"}
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
_NAME_CLASSIFIERS: tuple[tuple[re.Pattern[str], OpeningType], ...] = (
    (re.compile(r"\bgarage[ _-]*door\b", re.IGNORECASE), "garage_door"),
    (re.compile(r"\bwindow\b", re.IGNORECASE), "window"),
    (re.compile(r"\bdoor\b", re.IGNORECASE), "door"),
)


class HomeAnalyzer:
    """Classify current normalized entities without network calls or inference prose."""

    def __init__(
        self,
        entities: list[EntityDetail],
        *,
        battery_warning_threshold: int,
        ignored_entity_ids: frozenset[str] = frozenset(),
        now: datetime | None = None,
    ) -> None:
        self.entities = sorted(
            [
                entity
                for entity in entities
                if entity.entity_id.casefold() not in ignored_entity_ids
            ],
            key=lambda entity: entity.entity_id.casefold(),
        )
        self.battery_warning_threshold = battery_warning_threshold
        self.now = now or datetime.now(UTC)

    def home_summary(self, *, detail_limit: int = 10) -> HomeSummary:
        """Build only sections supported by the current inventory."""
        sections: list[HomeSummarySection] = []
        occupancy = [entity for entity in self.entities if _is_occupancy(entity)]
        if occupancy:
            active = [entity for entity in occupancy if _is_active(entity)]
            sections.append(
                _section(
                    "occupancy",
                    occupancy,
                    facts={
                        "active": len(active),
                        "inactive": sum(_is_inactive(entity) for entity in occupancy),
                        "unknown_or_unavailable": sum(
                            _unresolved_state(entity) for entity in occupancy
                        ),
                    },
                    details=active,
                    limit=detail_limit,
                )
            )

        openings = self._all_openings()
        if openings:
            open_items = [item for item in openings if item.normalized_state == "open"]
            sections.append(
                HomeSummarySection(
                    name="openings",
                    entity_count=len(openings),
                    facts={
                        "open": len(open_items),
                        "closed": sum(item.normalized_state == "closed" for item in openings),
                        "open_by_type": dict(Counter(item.opening_type for item in open_items)),
                    },
                    details=[_compact_from_opening(item) for item in open_items[:detail_limit]],
                    details_truncated=len(open_items) > detail_limit,
                )
            )

        lights = [entity for entity in self.entities if entity.domain == "light"]
        if lights:
            lights_on = [entity for entity in lights if entity.state.casefold() == "on"]
            sections.append(
                _section(
                    "lighting",
                    lights,
                    facts={
                        "on": len(lights_on),
                        "off": sum(entity.state.casefold() == "off" for entity in lights),
                        "unknown_or_unavailable": sum(
                            _unresolved_state(entity) for entity in lights
                        ),
                    },
                    details=lights_on,
                    limit=detail_limit,
                )
            )

        climate = [entity for entity in self.entities if entity.domain == "climate"]
        if climate:
            sections.append(
                _section(
                    "climate",
                    climate,
                    facts={"reported_states": dict(Counter(entity.state for entity in climate))},
                    details=[],
                    limit=detail_limit,
                )
            )

        environment = [
            entity for entity in self.entities if _device_class(entity) in _ENVIRONMENT_CLASSES
        ]
        if environment:
            sections.append(
                _section(
                    "environment",
                    environment,
                    facts={
                        "by_device_class": dict(
                            Counter(_device_class(entity) or "unknown" for entity in environment)
                        )
                    },
                    details=environment,
                    limit=detail_limit,
                )
            )

        findings = self._all_findings()
        health_findings = [
            finding
            for finding in findings
            if finding.category
            in {
                "unavailable_entity",
                "unknown_entity",
                "low_battery",
                "problem_sensor_active",
                "connectivity_problem",
            }
        ]
        health_entities = [
            entity
            for entity in self.entities
            if entity.state.casefold() in {"unavailable", "unknown"}
            or _battery_percentage(entity) is not None
            or _device_class(entity) in {"problem", "connectivity"}
        ]
        if health_entities:
            sections.append(
                HomeSummarySection(
                    name="device_health",
                    entity_count=len(health_entities),
                    facts={
                        "unavailable": sum(
                            entity.state.casefold() == "unavailable" for entity in self.entities
                        ),
                        "unknown": sum(
                            entity.state.casefold() == "unknown" for entity in self.entities
                        ),
                        "low_battery": sum(
                            finding.category == "low_battery" for finding in health_findings
                        ),
                        "connectivity_problems": sum(
                            finding.category == "connectivity_problem"
                            for finding in health_findings
                        ),
                    },
                    details=[finding.entity for finding in health_findings[:detail_limit]],
                    details_truncated=len(health_findings) > detail_limit,
                )
            )

        safety = [entity for entity in self.entities if _device_class(entity) in _SAFETY_CLASSES]
        if safety:
            active_safety = [
                finding
                for finding in findings
                if finding.category
                in {
                    "moisture_detected",
                    "smoke_detected",
                    "carbon_monoxide_detected",
                    "problem_sensor_active",
                    "connectivity_problem",
                }
            ]
            sections.append(
                HomeSummarySection(
                    name="safety",
                    entity_count=len(safety),
                    facts={
                        "reported_findings": len(active_safety),
                        "by_device_class": dict(
                            Counter(_device_class(entity) or "unknown" for entity in safety)
                        ),
                    },
                    details=[finding.entity for finding in active_safety[:detail_limit]],
                    details_truncated=len(active_safety) > detail_limit,
                )
            )

        energy = [entity for entity in self.entities if _device_class(entity) in _ENERGY_CLASSES]
        if energy:
            sections.append(
                _section(
                    "energy",
                    energy,
                    facts={
                        "by_device_class": dict(
                            Counter(_device_class(entity) or "unknown" for entity in energy)
                        )
                    },
                    details=energy,
                    limit=detail_limit,
                )
            )

        return HomeSummary(
            generated_at=self.now.isoformat(),
            total_entities=len(self.entities),
            available_entities=sum(entity.available for entity in self.entities),
            unavailable_entities=sum(not entity.available for entity in self.entities),
            unknown_entities=sum(entity.state.casefold() == "unknown" for entity in self.entities),
            sections=sections,
            attention_items=findings[:detail_limit],
            total_attention_items=len(findings),
            attention_items_truncated=len(findings) > detail_limit,
        )

    def unavailable_entities(self, filters: UnavailableEntityFilters) -> UnavailableEntitiesPage:
        scoped = [entity for entity in self.entities if _matches_scope(entity, filters)]
        unavailable = [entity for entity in scoped if entity.state.casefold() == "unavailable"]
        results: list[UnavailableEntity] = []
        missing_evidence = 0
        minimum_seconds = (
            filters.minimum_duration_minutes * 60
            if filters.minimum_duration_minutes is not None
            else None
        )
        for entity in unavailable:
            duration = _current_state_duration(entity, self.now)
            if minimum_seconds is not None and duration is None:
                missing_evidence += 1
                continue
            if minimum_seconds is not None and duration is not None and duration < minimum_seconds:
                continue
            results.append(
                UnavailableEntity(
                    **_compact(entity).model_dump(),
                    unavailable_duration_seconds=duration,
                    duration_evidence_available=duration is not None,
                )
            )
        return UnavailableEntitiesPage(
            entities=results[: filters.limit],
            total_matches=len(results),
            unknown_in_scope=sum(entity.state.casefold() == "unknown" for entity in scoped),
            returned=min(len(results), filters.limit),
            limit=filters.limit,
            truncated=len(results) > filters.limit,
            duration_filter_complete=missing_evidence == 0,
            entities_without_duration_evidence=missing_evidence,
        )

    def low_batteries(self, filters: LowBatteryFilters) -> LowBatteriesPage:
        results = []
        for entity in self.entities:
            if not _matches_scope(entity, filters):
                continue
            percentage = _battery_percentage(entity)
            if percentage is not None and percentage <= filters.threshold:
                results.append(
                    LowBatteryEntity(**_compact(entity).model_dump(), battery_percent=percentage)
                )
        results.sort(key=lambda item: (item.battery_percent, item.entity_id.casefold()))
        return LowBatteriesPage(
            threshold=filters.threshold,
            entities=results[: filters.limit],
            total_matches=len(results),
            returned=min(len(results), filters.limit),
            limit=filters.limit,
            truncated=len(results) > filters.limit,
        )

    def openings(self, filters: OpeningFilters) -> OpeningsPage:
        results = [item for item in self._all_openings() if _matches_opening_filters(item, filters)]
        counts = Counter(item.opening_type for item in results)
        return OpeningsPage(
            entities=results[: filters.limit],
            counts_by_type=dict(sorted(counts.items())),
            total_matches=len(results),
            returned=min(len(results), filters.limit),
            limit=filters.limit,
            truncated=len(results) > filters.limit,
        )

    def lights_on(self, filters: LocationFilters) -> LightsOnPage:
        results = [
            LightOnEntity(
                **_compact(entity).model_dump(),
                brightness=_integer(entity.attributes.get("brightness")),
            )
            for entity in self.entities
            if entity.domain == "light"
            and entity.state.casefold() == "on"
            and _matches_scope(entity, filters)
        ]
        return LightsOnPage(
            entities=results[: filters.limit],
            total_matches=len(results),
            returned=min(len(results), filters.limit),
            limit=filters.limit,
            truncated=len(results) > filters.limit,
        )

    def diagnose(self, *, limit: int) -> HomeDiagnosticsReport:
        findings = self._all_findings()
        severity_counts: Counter[str] = Counter(finding.severity for finding in findings)
        return HomeDiagnosticsReport(
            generated_at=self.now.isoformat(),
            findings=findings[:limit],
            severity_counts={
                severity: severity_counts[severity]
                for severity in ("critical", "warning", "info")
                if severity_counts[severity]
            },
            total_findings=len(findings),
            returned=min(len(findings), limit),
            limit=limit,
            truncated=len(findings) > limit,
        )

    def _all_openings(self) -> list[OpeningEntity]:
        results = []
        for entity in self.entities:
            opening_type = _opening_type(entity)
            if opening_type is None:
                continue
            results.append(
                OpeningEntity(
                    **_compact(entity).model_dump(),
                    opening_type=opening_type,
                    normalized_state=_opening_state(entity),
                )
            )
        return results

    def _all_findings(self) -> list[DiagnosticFinding]:
        findings: list[DiagnosticFinding] = []
        for entity in self.entities:
            state = entity.state.casefold()
            device_class = _device_class(entity)
            if state == "unavailable":
                findings.append(
                    _finding(
                        "unavailable_entity",
                        "warning",
                        entity,
                        f"Home Assistant reports '{_label(entity)}' as unavailable.",
                    )
                )
            elif state == "unknown":
                findings.append(
                    _finding(
                        "unknown_entity",
                        "info",
                        entity,
                        f"Home Assistant reports an unknown state for '{_label(entity)}'.",
                    )
                )

            percentage = _battery_percentage(entity)
            if percentage is not None and percentage <= self.battery_warning_threshold:
                findings.append(
                    _finding(
                        "low_battery",
                        "warning",
                        entity,
                        f"Home Assistant reports '{_label(entity)}' battery at {percentage:g}%.",
                    )
                )

            opening_type = _opening_type(entity)
            if opening_type is not None and _opening_state(entity) == "open":
                category = {
                    "door": "open_door",
                    "window": "open_window",
                    "garage_door": "open_garage",
                    "opening": "open_door",
                }[opening_type]
                severity = "warning" if opening_type == "garage_door" else "info"
                findings.append(
                    _finding(
                        category,
                        severity,
                        entity,
                        f"Home Assistant reports '{_label(entity)}' as open.",
                    )
                )

            if state not in {"unavailable", "unknown"}:
                safety = _safety_finding(device_class, state)
                if safety is not None:
                    category, severity, noun = safety
                    findings.append(
                        _finding(
                            category,
                            severity,
                            entity,
                            f"Home Assistant reports {noun} '{_label(entity)}' as active.",
                        )
                    )
        return sorted(
            findings,
            key=lambda item: (
                _SEVERITY_ORDER[item.severity],
                item.category,
                item.entity.entity_id.casefold(),
            ),
        )


def _section(
    name: str,
    entities: list[EntityDetail],
    *,
    facts: dict[str, Any],
    details: list[EntityDetail],
    limit: int,
) -> HomeSummarySection:
    return HomeSummarySection(
        name=name,  # type: ignore[arg-type]
        entity_count=len(entities),
        facts=facts,
        details=[_compact(entity) for entity in details[:limit]],
        details_truncated=len(details) > limit,
    )


def _compact(entity: EntityDetail) -> DiagnosticEntity:
    return DiagnosticEntity(
        entity_id=entity.entity_id,
        friendly_name=_bounded_text(entity.friendly_name),
        domain=entity.domain,
        state=entity.state,
        device_class=_device_class(entity),
        unit_of_measurement=_text(entity.attributes.get("unit_of_measurement")),
        area_id=entity.area_id,
        area_name=_bounded_text(entity.area_name),
        floor_id=entity.floor_id,
        floor_name=_bounded_text(entity.floor_name),
        last_changed=entity.last_changed,
    )


def _compact_from_opening(entity: OpeningEntity) -> DiagnosticEntity:
    return DiagnosticEntity(**entity.model_dump(exclude={"opening_type", "normalized_state"}))


def _device_class(entity: EntityDetail) -> str | None:
    value = _text(entity.attributes.get("device_class"))
    return value.casefold() if value else None


def _battery_percentage(entity: EntityDetail) -> float | None:
    if entity.domain != "sensor" or _device_class(entity) != "battery":
        return None
    if _text(entity.attributes.get("unit_of_measurement")) != "%":
        return None
    try:
        value = float(entity.state)
    except ValueError:
        return None
    return value if 0 <= value <= 100 else None


def _opening_type(entity: EntityDetail) -> OpeningType | None:
    device_class = _device_class(entity)
    if device_class in _OPENING_CLASSES and entity.domain in {"binary_sensor", "cover"}:
        return _OPENING_CLASSES[device_class]
    if entity.domain not in {"binary_sensor", "cover"} or device_class is not None:
        return None
    candidate = f"{entity.entity_id.partition('.')[2]} {entity.friendly_name or ''}"
    for pattern, opening_type in _NAME_CLASSIFIERS:
        if pattern.search(candidate.replace("_", " ")):
            return opening_type
    return None


def _opening_state(
    entity: EntityDetail,
) -> Literal["open", "closed", "unavailable", "unknown"]:
    state = entity.state.casefold()
    if state == "unavailable":
        return "unavailable"
    if state == "unknown":
        return "unknown"
    if state in _ACTIVE_STATES:
        return "open"
    return "closed" if state in _INACTIVE_STATES else "unknown"


def _is_occupancy(entity: EntityDetail) -> bool:
    return entity.domain in {"person", "device_tracker"} or (
        entity.domain == "binary_sensor" and _device_class(entity) in _OCCUPANCY_CLASSES
    )


def _is_active(entity: EntityDetail) -> bool:
    state = entity.state.casefold()
    if entity.domain in {"person", "device_tracker"}:
        return state == "home"
    return state == "on"


def _is_inactive(entity: EntityDetail) -> bool:
    state = entity.state.casefold()
    if entity.domain in {"person", "device_tracker"}:
        return state in {"not_home", "away"}
    return state == "off"


def _unresolved_state(entity: EntityDetail) -> bool:
    return entity.state.casefold() in {"unknown", "unavailable"}


def _matches_scope(entity: EntityDetail, filters: Any) -> bool:
    domain = getattr(filters, "domain", None)
    area = getattr(filters, "area", None)
    floor = getattr(filters, "floor", None)
    if domain and entity.domain.casefold() != domain.strip().casefold():
        return False
    if area and not _identifier_matches(area, entity.area_id, entity.area_name):
        return False
    return not (floor and not _identifier_matches(floor, entity.floor_id, entity.floor_name))


def _identifier_matches(value: str, identifier: str | None, name: str | None) -> bool:
    target = value.strip().casefold().replace("_", " ")
    return any(
        candidate is not None and candidate.casefold().replace("_", " ") == target
        for candidate in (identifier, name)
    )


def _matches_opening_filters(entity: OpeningEntity, filters: OpeningFilters) -> bool:
    if filters.opening_type and entity.opening_type != filters.opening_type:
        return False
    if filters.state != "any" and entity.normalized_state != filters.state:
        return False
    if filters.area and not _identifier_matches(filters.area, entity.area_id, entity.area_name):
        return False
    return not (
        filters.floor and not _identifier_matches(filters.floor, entity.floor_id, entity.floor_name)
    )


def _current_state_duration(entity: EntityDetail, now: datetime) -> int | None:
    if entity.last_changed is None:
        return None
    try:
        changed = parse_timestamp(entity.last_changed)
    except Exception:
        return None
    seconds = int((now - changed).total_seconds())
    return seconds if seconds >= 0 else None


def _safety_finding(device_class: str | None, state: str) -> tuple[str, str, str] | None:
    if device_class == "smoke" and state == "on":
        return "smoke_detected", "critical", "smoke sensor"
    if device_class == "carbon_monoxide" and state == "on":
        return "carbon_monoxide_detected", "critical", "carbon monoxide sensor"
    if device_class == "moisture" and state == "on":
        return "moisture_detected", "warning", "moisture sensor"
    if device_class == "problem" and state == "on":
        return "problem_sensor_active", "warning", "problem sensor"
    if device_class == "connectivity" and state == "off":
        return "connectivity_problem", "warning", "connectivity sensor"
    return None


def _finding(
    category: str,
    severity: str,
    entity: EntityDetail,
    message: str,
) -> DiagnosticFinding:
    return DiagnosticFinding(
        category=category,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        message=message,
        evidence=f"state={entity.state!r}; device_class={_device_class(entity)!r}",
        entity=_compact(entity),
    )


def _label(entity: EntityDetail) -> str:
    return _bounded_text(entity.friendly_name) or entity.entity_id


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _bounded_text(value: str | None, *, limit: int = 128) -> str | None:
    return value[:limit] if value else None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
