"""Pure joining, normalization, search, and privacy logic for HA discovery."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import JsonValue

from ambient_ha.ha.websocket import RegistrySnapshot
from ambient_ha.models.discovery import (
    AreaDetail,
    AreaSummary,
    DomainSummary,
    EntityDetail,
    EntitySearchFilters,
    EntitySearchPage,
    EntitySummary,
    FloorDetail,
    FloorSummary,
)

_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")
_SAFE_ATTRIBUTE_KEYS = {
    "battery_level",
    "brightness",
    "color_mode",
    "color_temp_kelvin",
    "current_humidity",
    "current_position",
    "current_temperature",
    "device_class",
    "energy",
    "fan_mode",
    "fan_modes",
    "hs_color",
    "humidity",
    "hvac_action",
    "hvac_mode",
    "hvac_modes",
    "illuminance",
    "is_volume_muted",
    "max_temp",
    "min_temp",
    "mode",
    "percentage",
    "position",
    "power",
    "preset_mode",
    "preset_modes",
    "pressure",
    "rgb_color",
    "state_class",
    "supported_color_modes",
    "supported_features",
    "swing_mode",
    "target_humidity",
    "target_temp_high",
    "target_temp_low",
    "target_temperature",
    "temperature",
    "tilt_position",
    "unit_of_measurement",
    "voltage",
    "volume_level",
    "xy_color",
}
_SAFE_MEASUREMENT_SUFFIXES = (
    "_battery",
    "_current",
    "_energy",
    "_humidity",
    "_illuminance",
    "_power",
    "_pressure",
    "_temperature",
    "_voltage",
)
_SENSITIVE_KEY_MARKERS = (
    "access_token",
    "authorization",
    "camera",
    "credential",
    "entity_picture",
    "gps",
    "latitude",
    "location",
    "longitude",
    "media_content",
    "password",
    "secret",
    "stream",
    "token",
    "url",
)


class DiscoveryResolver:
    """Join REST states with registry metadata using Home Assistant precedence."""

    def __init__(self, snapshot: RegistrySnapshot) -> None:
        self.snapshot = snapshot
        self._entities = _index(snapshot.entities, "entity_id")
        self._devices = _index(snapshot.devices, "id")
        self._areas = _index(snapshot.areas, "area_id")
        self._floors = _index(snapshot.floors, "floor_id")

    def entity(self, state: Mapping[str, Any], *, include_attributes: bool = True) -> EntityDetail:
        """Normalize one state and resolve device-inherited area plus floor."""
        entity_id = _text(state.get("entity_id")) or ""
        domain = entity_id.partition(".")[0]
        state_value = _text(state.get("state")) or "unknown"
        attributes = state.get("attributes")
        state_attributes = attributes if isinstance(attributes, Mapping) else {}
        registry = self._entities.get(entity_id, {})

        device_id = _text(registry.get("device_id"))
        device = self._devices.get(device_id or "", {})
        entity_area_id = _text(registry.get("area_id"))
        device_area_id = _text(device.get("area_id"))
        area_id = entity_area_id or device_area_id
        area = self._areas.get(area_id or "", {})
        floor_id = _text(area.get("floor_id"))
        floor = self._floors.get(floor_id or "", {})

        friendly_name = _text(state_attributes.get("friendly_name"))
        if friendly_name is None:
            friendly_name = _text(registry.get("name")) or _text(registry.get("original_name"))

        return EntityDetail(
            entity_id=entity_id,
            domain=domain,
            state=state_value,
            friendly_name=friendly_name,
            area_id=area_id,
            area_name=_text(area.get("name")),
            floor_id=floor_id,
            floor_name=_text(floor.get("name")),
            device_id=device_id,
            device_name=_text(device.get("name_by_user")) or _text(device.get("name")),
            available=state_value.casefold() != "unavailable",
            last_changed=_text(state.get("last_changed")),
            last_updated=_text(state.get("last_updated")),
            attributes=sanitize_attributes(state_attributes) if include_attributes else {},
        )

    def entities(
        self, states: Iterable[Mapping[str, Any]], *, include_attributes: bool = False
    ) -> list[EntityDetail]:
        """Normalize all well-formed states in deterministic entity-ID order."""
        normalized = [
            self.entity(state, include_attributes=include_attributes)
            for state in states
            if _valid_entity_id(_text(state.get("entity_id")))
        ]
        return sorted(normalized, key=lambda item: item.entity_id.casefold())

    def search(
        self, states: Iterable[Mapping[str, Any]], filters: EntitySearchFilters
    ) -> EntitySearchPage:
        """Apply composable filters and conservative deterministic text ranking."""
        query = _normalize(filters.query) if filters.query else ""
        ranked: list[tuple[int, EntitySummary]] = []
        for entity in self.entities(states):
            if not _matches_filters(entity, filters):
                continue
            score = _entity_match_score(entity, query) if query else 0
            if query and score == 0:
                continue
            ranked.append((score, _summary(entity)))

        ranked.sort(
            key=lambda item: (
                -item[0],
                (item[1].friendly_name or item[1].entity_id).casefold(),
                item[1].entity_id.casefold(),
            )
        )
        total = len(ranked)
        returned = [entity for _, entity in ranked[: filters.limit]]
        return EntitySearchPage(
            entities=returned,
            total_matches=total,
            returned=len(returned),
            limit=filters.limit,
            truncated=total > len(returned),
        )

    def list_areas(self, states: Iterable[Mapping[str, Any]]) -> list[AreaSummary]:
        entities = self.entities(states)
        counts = Counter(entity.area_id for entity in entities if entity.area_id)
        areas = [
            AreaSummary(
                area_id=area_id,
                name=_text(area.get("name")) or area_id,
                floor_id=(floor_id := _text(area.get("floor_id"))),
                floor_name=_text(self._floors.get(floor_id or "", {}).get("name")),
                entity_count=counts[area_id],
            )
            for area_id, area in self._areas.items()
        ]
        return sorted(areas, key=lambda item: (item.name.casefold(), item.area_id))

    def get_area(
        self,
        states: Iterable[Mapping[str, Any]],
        identifier: str,
        *,
        include_entities: bool,
        limit: int,
    ) -> AreaDetail | None:
        area_id = _resolve_identifier(self._areas, identifier)
        if area_id is None:
            return None
        area = self._areas[area_id]
        floor_id = _text(area.get("floor_id"))
        all_entities = [entity for entity in self.entities(states) if entity.area_id == area_id]
        summaries = [_summary(entity) for entity in all_entities]
        counts = Counter(entity.domain for entity in all_entities)
        included = summaries[:limit] if include_entities else []
        return AreaDetail(
            area_id=area_id,
            name=_text(area.get("name")) or area_id,
            floor_id=floor_id,
            floor_name=_text(self._floors.get(floor_id or "", {}).get("name")),
            entity_count=len(all_entities),
            entity_counts_by_domain=dict(sorted(counts.items())),
            entities=included,
            entities_included=include_entities,
            entities_truncated=include_entities and len(summaries) > len(included),
        )

    def list_floors(self, states: Iterable[Mapping[str, Any]]) -> list[FloorSummary]:
        entities = self.entities(states)
        area_counts = Counter(_text(area.get("floor_id")) for area in self._areas.values())
        entity_counts = Counter(entity.floor_id for entity in entities if entity.floor_id)
        floors = [
            FloorSummary(
                floor_id=floor_id,
                name=_text(floor.get("name")) or floor_id,
                level=_integer(floor.get("level")),
                area_count=area_counts[floor_id],
                entity_count=entity_counts[floor_id],
            )
            for floor_id, floor in self._floors.items()
        ]
        return sorted(
            floors,
            key=lambda item: (
                item.level is None,
                item.level if item.level is not None else 0,
                item.name.casefold(),
            ),
        )

    def get_floor(self, states: Iterable[Mapping[str, Any]], identifier: str) -> FloorDetail | None:
        floor_id = _resolve_identifier(self._floors, identifier)
        if floor_id is None:
            return None
        floor = self._floors[floor_id]
        areas = [area for area in self.list_areas(states) if area.floor_id == floor_id]
        entities = [entity for entity in self.entities(states) if entity.floor_id == floor_id]
        counts = Counter(entity.domain for entity in entities)
        return FloorDetail(
            floor_id=floor_id,
            name=_text(floor.get("name")) or floor_id,
            level=_integer(floor.get("level")),
            area_count=len(areas),
            entity_count=len(entities),
            areas=areas,
            entity_counts_by_domain=dict(sorted(counts.items())),
        )

    def domain_summary(self, states: Iterable[Mapping[str, Any]], domain: str) -> DomainSummary:
        entities = [
            entity
            for entity in self.entities(states)
            if entity.domain.casefold() == domain.casefold()
        ]
        states_counter = Counter(entity.state for entity in entities)
        return DomainSummary(
            domain=domain.casefold(),
            total=len(entities),
            available=sum(entity.available for entity in entities),
            unavailable=sum(not entity.available for entity in entities),
            unknown=sum(entity.state.casefold() == "unknown" for entity in entities),
            states=dict(sorted(states_counter.items(), key=lambda item: item[0].casefold())),
        )


def sanitize_attributes(attributes: Mapping[str, Any]) -> dict[str, JsonValue]:
    """Allowlist useful device measurements while excluding private metadata."""
    sanitized: dict[str, JsonValue] = {}
    for key in sorted(attributes):
        normalized_key = key.casefold()
        if any(marker in normalized_key for marker in _SENSITIVE_KEY_MARKERS):
            continue
        if normalized_key not in _SAFE_ATTRIBUTE_KEYS and not normalized_key.endswith(
            _SAFE_MEASUREMENT_SUFFIXES
        ):
            continue
        accepted, value = _sanitize_value(attributes[key], depth=0)
        if accepted:
            sanitized[key] = value
        if len(sanitized) >= 40:
            break
    return sanitized


def _sanitize_value(value: Any, *, depth: int) -> tuple[bool, JsonValue]:
    if value is None or isinstance(value, (bool, int, float)):
        return True, value
    if isinstance(value, str):
        if value.casefold().startswith(("http://", "https://", "rtsp://")):
            return False, None
        return True, value[:256]
    if depth >= 2:
        return False, None
    if isinstance(value, (list, tuple)):
        values: list[JsonValue] = []
        for item in value[:20]:
            accepted, sanitized = _sanitize_value(item, depth=depth + 1)
            if accepted:
                values.append(sanitized)
        return True, values
    if isinstance(value, Mapping):
        values_dict: dict[str, JsonValue] = {}
        for raw_key, raw_value in list(value.items())[:20]:
            if not isinstance(raw_key, str):
                continue
            if any(marker in raw_key.casefold() for marker in _SENSITIVE_KEY_MARKERS):
                continue
            accepted, sanitized = _sanitize_value(raw_value, depth=depth + 1)
            if accepted:
                values_dict[raw_key[:64]] = sanitized
        return True, values_dict
    return False, None


def _index(items: Iterable[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    return {identifier: item for item in items if (identifier := _text(item.get(key))) is not None}


def _matches_filters(entity: EntitySummary, filters: EntitySearchFilters) -> bool:
    if filters.domain and entity.domain.casefold() != filters.domain.strip().casefold():
        return False
    if filters.state and entity.state.casefold() != filters.state.strip().casefold():
        return False
    if filters.available is not None and entity.available is not filters.available:
        return False
    if filters.area and not _identifier_or_name_matches(
        filters.area, entity.area_id, entity.area_name
    ):
        return False
    return not (
        filters.floor
        and not _identifier_or_name_matches(filters.floor, entity.floor_id, entity.floor_name)
    )


def _identifier_or_name_matches(value: str, identifier: str | None, name: str | None) -> bool:
    target = _normalize(value)
    return target in {_normalize(identifier), _normalize(name)}


def _entity_match_score(entity: EntitySummary, query: str) -> int:
    object_id = entity.entity_id.partition(".")[2]
    candidates = (
        (entity.entity_id, 10),
        (object_id, 10),
        (entity.friendly_name, 8),
        (entity.device_name, 6),
        (entity.area_name, 4),
        (entity.floor_name, 2),
    )
    return max((_text_match_score(value, query, bonus) for value, bonus in candidates), default=0)


def _text_match_score(value: str | None, query: str, bonus: int) -> int:
    candidate = _normalize(value)
    if not candidate:
        return 0
    if candidate == query:
        return bonus * 100 + 40
    if candidate.startswith(query):
        return bonus * 100 + 30
    if query in candidate:
        return bonus * 100 + 20
    query_tokens = query.split()
    candidate_tokens = candidate.split()
    if query_tokens and all(
        any(
            token == word or word.startswith(token) or token.startswith(word)
            for word in candidate_tokens
        )
        for token in query_tokens
    ):
        return bonus * 100 + 10
    return 0


def _resolve_identifier(items: Mapping[str, Mapping[str, Any]], identifier: str) -> str | None:
    normalized = _normalize(identifier)
    for item_id, item in items.items():
        if normalized in {_normalize(item_id), _normalize(_text(item.get("name")))}:
            return item_id
    return None


def _summary(entity: EntityDetail) -> EntitySummary:
    return EntitySummary(
        **entity.model_dump(exclude={"last_changed", "last_updated", "attributes"})
    )


def _normalize(value: str | None) -> str:
    return _SEPARATOR_PATTERN.sub(" ", (value or "").casefold()).strip()


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _valid_entity_id(value: str | None) -> bool:
    if value is None or value.count(".") != 1:
        return False
    domain, object_id = value.split(".", 1)
    return bool(domain and object_id)
