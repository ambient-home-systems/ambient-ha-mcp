from datetime import UTC, datetime, timedelta

import pytest

from ambient_ha.ha.discovery import DiscoveryResolver
from ambient_ha.ha.exceptions import HomeAssistantQueryError
from ambient_ha.ha.history import (
    QueryWindow,
    build_recent_changes,
    normalize_history_payload,
    normalize_logbook_payload,
    resolve_query_window,
)
from tests.fixtures.discovery import REGISTRIES, STATES
from tests.fixtures.history import HISTORY_PAYLOAD, LOGBOOK_PAYLOAD


def test_history_normalization_deduplicates_and_proves_only_complete_durations() -> None:
    window = QueryWindow(
        start=datetime(2024, 8, 25, 12, 0, tzinfo=UTC),
        end=datetime(2024, 8, 25, 12, 30, tzinfo=UTC),
    )

    normalized = normalize_history_payload(HISTORY_PAYLOAD, window=window)
    door = normalized["cover.garage_door"]

    assert [transition.state for transition in door] == ["closed", "open", "closed"]
    assert door[0].began_within_range is False
    assert door[0].duration_complete is False
    assert door[1].duration_seconds == 300
    assert door[1].duration_complete is True
    assert door[2].duration_seconds is None
    assert door[1].attributes == {"current_position": 100}
    assert door[1].context_id == "ctx-open"
    assert "private" not in door[1].model_dump_json()


def test_logbook_normalization_redacts_url_and_sorts_facts() -> None:
    entries = normalize_logbook_payload([*reversed(LOGBOOK_PAYLOAD), {"when": "invalid"}])

    assert [entry.timestamp for entry in entries] == [
        "2024-08-25T12:10:00+00:00",
        "2024-08-25T12:15:00+00:00",
    ]
    assert entries[1].message == "Redacted Home Assistant logbook message."
    assert "private" not in entries[1].model_dump_json()


def test_recent_changes_keep_metadata_without_inventing_previous_state() -> None:
    window = QueryWindow(
        start=datetime(2024, 8, 25, 12, 0, tzinfo=UTC),
        end=datetime(2024, 8, 25, 12, 30, tzinfo=UTC),
    )
    history = normalize_history_payload(HISTORY_PAYLOAD, window=window)
    entities = {
        entity.entity_id: entity for entity in DiscoveryResolver(REGISTRIES).entities(STATES)
    }

    changes = build_recent_changes(history, entities)

    assert [(change.entity_id, change.previous_state, change.new_state) for change in changes] == [
        ("light.kitchen_ceiling", "off", "on"),
        ("cover.garage_door", "open", "closed"),
        ("cover.garage_door", "closed", "open"),
    ]
    assert changes[0].area_name == "Kitchen"
    assert changes[-1].floor_name == "Ground Floor"


def test_time_windows_require_offsets_reject_invalid_ranges_and_bound_lookback() -> None:
    maximum = timedelta(days=7)
    default = timedelta(hours=24)
    now = datetime(2026, 11, 2, 12, tzinfo=UTC)

    dst_window = resolve_query_window(
        start="2026-11-01T01:30:00-04:00",
        end="2026-11-01T01:30:00-05:00",
        duration_minutes=None,
        default_lookback=default,
        maximum_lookback=maximum,
        now=now,
    )
    assert dst_window.end - dst_window.start == timedelta(hours=1)

    with pytest.raises(HomeAssistantQueryError, match="explicit UTC offset"):
        resolve_query_window(
            start="2026-08-25T12:00:00",
            end="2026-08-25T13:00:00Z",
            duration_minutes=None,
            default_lookback=default,
            maximum_lookback=maximum,
            now=now,
        )
    with pytest.raises(HomeAssistantQueryError, match="before the end"):
        resolve_query_window(
            start="2026-08-25T13:00:00Z",
            end="2026-08-25T12:00:00Z",
            duration_minutes=None,
            default_lookback=default,
            maximum_lookback=maximum,
            now=now,
        )
    with pytest.raises(HomeAssistantQueryError, match="maximum"):
        resolve_query_window(
            start="2026-10-01T00:00:00Z",
            end="2026-11-01T00:00:00Z",
            duration_minutes=None,
            default_lookback=default,
            maximum_lookback=maximum,
            now=now,
        )


def test_default_and_relative_windows_are_timezone_aware() -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)

    default = resolve_query_window(
        start=None,
        end=None,
        duration_minutes=None,
        default_lookback=timedelta(hours=24),
        maximum_lookback=timedelta(days=7),
        now=now,
    )
    relative = resolve_query_window(
        start=None,
        end=None,
        duration_minutes=90,
        default_lookback=timedelta(hours=24),
        maximum_lookback=timedelta(days=7),
        now=now,
    )

    assert default.start == datetime(2026, 8, 24, 12, tzinfo=UTC)
    assert relative.start == datetime(2026, 8, 25, 10, 30, tzinfo=UTC)
