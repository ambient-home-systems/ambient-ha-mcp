"""Time-safe normalization and aggregation for read-only Home Assistant history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ambient_ha.ha.discovery import sanitize_attributes
from ambient_ha.ha.exceptions import HomeAssistantQueryError
from ambient_ha.models.discovery import EntityDetail, EntitySummary
from ambient_ha.models.history import LogbookEntry, RecentChange, StateTransition

_SENSITIVE_TEXT_MARKERS = (
    "access_token",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "rtsp://",
    "http://",
    "https://",
)


@dataclass(frozen=True, slots=True)
class QueryWindow:
    """An explicit timezone-aware historical query interval."""

    start: datetime
    end: datetime

    @property
    def start_iso(self) -> str:
        return _iso(self.start)

    @property
    def end_iso(self) -> str:
        return _iso(self.end)


def resolve_query_window(
    *,
    start: str | None,
    end: str | None,
    duration_minutes: int | None,
    default_lookback: timedelta,
    maximum_lookback: timedelta,
    now: datetime | None = None,
) -> QueryWindow:
    """Validate an explicit ISO-8601 interval without accepting naive timestamps."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise RuntimeError("The historical clock must be timezone-aware.")
    if duration_minutes is not None and (start is not None or end is not None):
        raise HomeAssistantQueryError(
            "invalid_range",
            "Use either duration_minutes or explicit start/end timestamps, not both.",
        )
    if duration_minutes is not None:
        if duration_minutes <= 0:
            raise HomeAssistantQueryError("invalid_range", "Duration must be greater than zero.")
        query_end = current
        query_start = query_end - timedelta(minutes=duration_minutes)
    else:
        query_end = parse_timestamp(end) if end else current
        query_start = parse_timestamp(start) if start else query_end - default_lookback
    if query_start >= query_end:
        raise HomeAssistantQueryError(
            "invalid_range", "The historical start timestamp must be before the end timestamp."
        )
    if query_start > current or query_end > current:
        raise HomeAssistantQueryError(
            "future_range", "Historical queries cannot request a future timestamp."
        )
    if query_end - query_start > maximum_lookback:
        raise HomeAssistantQueryError(
            "range_too_large", "The requested historical range exceeds the configured maximum."
        )
    return QueryWindow(start=query_start, end=query_end)


def parse_timestamp(value: str) -> datetime:
    """Require an ISO-8601 timestamp with an explicit UTC offset or ``Z``."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise HomeAssistantQueryError(
            "invalid_timestamp", "Timestamps must use valid ISO-8601 syntax."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HomeAssistantQueryError(
            "invalid_timestamp", "Timestamps must include an explicit UTC offset or Z."
        )
    return parsed


def normalize_history_payload(
    payload: Iterable[Any], *, window: QueryWindow
) -> dict[str, list[StateTransition]]:
    """Normalize recorder rows, collapsing repeated states and proving durations conservatively."""
    normalized: dict[str, list[StateTransition]] = {}
    for sequence in payload:
        if not isinstance(sequence, list):
            continue
        transitions = _normalize_entity_history(sequence, window=window)
        if transitions:
            normalized[transitions[0].entity_id] = transitions
    return normalized


def normalize_logbook_payload(payload: Iterable[Any]) -> list[LogbookEntry]:
    """Reduce logbook rows to bounded facts and exclude private message content."""
    entries: list[LogbookEntry] = []
    for raw in payload:
        if not isinstance(raw, Mapping):
            continue
        timestamp = _raw_timestamp(raw.get("when"))
        if timestamp is None:
            continue
        context = raw.get("context")
        context_values = context if isinstance(context, Mapping) else {}
        entries.append(
            LogbookEntry(
                timestamp=_iso(timestamp),
                entity_id=_text(raw.get("entity_id")),
                name=_safe_text(raw.get("name")),
                message=_safe_text(raw.get("message")),
                domain=_text(raw.get("domain")),
                context_id=_text(raw.get("context_id")) or _text(context_values.get("id")),
                context_parent_id=_text(raw.get("context_parent_id"))
                or _text(context_values.get("parent_id")),
            )
        )
    return sorted(entries, key=lambda item: parse_timestamp(item.timestamp))


def build_recent_changes(
    history: Mapping[str, list[StateTransition]],
    entities: Mapping[str, EntitySummary | EntityDetail],
) -> list[RecentChange]:
    """Turn recorded transitions into resolved facts without causal inference."""
    changes: list[RecentChange] = []
    for entity_id, transitions in history.items():
        entity = entities.get(entity_id)
        for index, transition in enumerate(transitions):
            if not transition.began_within_range:
                continue
            previous = transitions[index - 1].state if index else None
            changes.append(
                RecentChange(
                    entity_id=entity_id,
                    friendly_name=entity.friendly_name if entity else None,
                    previous_state=previous,
                    new_state=transition.state,
                    timestamp=transition.timestamp,
                    area_id=entity.area_id if entity else None,
                    area_name=entity.area_name if entity else None,
                    floor_id=entity.floor_id if entity else None,
                    floor_name=entity.floor_name if entity else None,
                    context_id=transition.context_id,
                    context_parent_id=transition.context_parent_id,
                )
            )
    return sorted(
        changes,
        key=lambda item: (parse_timestamp(item.timestamp), item.entity_id, item.new_state),
        reverse=True,
    )


def _normalize_entity_history(rows: Iterable[Any], *, window: QueryWindow) -> list[StateTransition]:
    entity_id: str | None = None
    raw_transitions: list[tuple[str, str, datetime, Mapping[str, Any], Mapping[str, Any]]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        entity_id = _text(raw.get("entity_id")) or entity_id
        state = _text(raw.get("state"))
        timestamp = _raw_timestamp(raw.get("last_changed"))
        if entity_id is None or state is None or timestamp is None:
            continue
        if raw_transitions and raw_transitions[-1][1] == state:
            continue
        attributes = raw.get("attributes")
        context = raw.get("context")
        raw_transitions.append(
            (
                entity_id,
                state,
                timestamp,
                attributes if isinstance(attributes, Mapping) else {},
                context if isinstance(context, Mapping) else {},
            )
        )

    transitions: list[StateTransition] = []
    for index, (row_entity_id, state, timestamp, attributes, context) in enumerate(raw_transitions):
        next_timestamp = raw_transitions[index + 1][2] if index + 1 < len(raw_transitions) else None
        began_within_range = timestamp >= window.start
        duration = (
            int((next_timestamp - timestamp).total_seconds())
            if began_within_range and next_timestamp is not None and next_timestamp <= window.end
            else None
        )
        transitions.append(
            StateTransition(
                entity_id=row_entity_id,
                state=state,
                timestamp=_iso(timestamp),
                attributes=sanitize_attributes(attributes),
                context_id=_text(context.get("id")),
                context_parent_id=_text(context.get("parent_id")),
                began_within_range=began_within_range,
                duration_seconds=duration,
                duration_complete=duration is not None,
            )
        )
    return transitions


def _raw_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_timestamp(value)
    except HomeAssistantQueryError:
        return None


def _iso(value: datetime) -> str:
    return value.isoformat()


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_text(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    if any(marker in text.casefold() for marker in _SENSITIVE_TEXT_MARKERS):
        return "Redacted Home Assistant logbook message."
    return text[:256]
