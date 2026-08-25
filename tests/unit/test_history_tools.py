import pytest

from ambient_ha.ha.exceptions import (
    HomeAssistantQueryError,
    HomeAssistantRecorderUnavailable,
)
from ambient_ha.models.history import (
    EntityHistoryPage,
    LogbookPage,
    RecentChangesFilters,
    RecentChangesPage,
)
from ambient_ha.tools.history import get_entity_history, get_logbook, get_recent_changes


class FakeHistoryGateway:
    def __init__(self, *, found: bool = True, failure: Exception | None = None) -> None:
        self.found = found
        self.failure = failure
        self.last_filters: RecentChangesFilters | None = None

    def _raise(self) -> None:
        if self.failure:
            raise self.failure

    async def get_entity_history(self, entity_id: str, **_kwargs: object):
        self._raise()
        return self.found, EntityHistoryPage(
            entity_id=entity_id,
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T12:30:00+00:00",
            total_transitions=0,
            returned=0,
            limit=100,
            truncated=False,
        )

    async def get_logbook(self, **_kwargs: object):
        self._raise()
        return LogbookPage(
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T12:30:00+00:00",
            total_entries=0,
            returned=0,
            limit=100,
            truncated=False,
        )

    async def get_recent_changes(self, filters: RecentChangesFilters):
        self._raise()
        self.last_filters = filters
        return RecentChangesPage(
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T12:30:00+00:00",
            candidate_entities=0,
            total_changes=0,
            returned=0,
            limit=filters.limit or 100,
            truncated=False,
        )


@pytest.mark.anyio
async def test_entity_history_normalizes_not_found_and_recorder_failure() -> None:
    missing = await get_entity_history(
        FakeHistoryGateway(found=False), "light.missing", start="2026-08-25T12:00:00Z"
    )
    unavailable = await get_entity_history(
        FakeHistoryGateway(failure=HomeAssistantRecorderUnavailable("Recorder unavailable.")),
        "light.kitchen",
        start="2026-08-25T12:00:00Z",
    )

    assert (missing.ok, missing.found, missing.error_code) == (True, False, "not_found")
    assert (unavailable.ok, unavailable.error_code) == (False, "recorder_unavailable")


@pytest.mark.anyio
async def test_history_tools_validate_inputs_and_bound_limits() -> None:
    gateway = FakeHistoryGateway()

    invalid_entity = await get_entity_history(
        gateway, "Kitchen Light", start="2026-08-25T12:00:00Z"
    )
    invalid_logbook = await get_logbook(gateway, start="", entity_id="sensor.bad id")
    changes = await get_recent_changes(gateway, duration_minutes=30, limit=9999)
    invalid_duration = await get_recent_changes(gateway, duration_minutes=10081)

    assert invalid_entity.error_code == "invalid_entity_id"
    assert invalid_logbook.error_code == "invalid_entity_id"
    assert gateway.last_filters is not None and gateway.last_filters.limit == 500
    assert changes.ok is True
    assert invalid_duration.error_code == "range_too_large"


@pytest.mark.anyio
async def test_recent_changes_propagate_safe_range_errors() -> None:
    result = await get_recent_changes(
        FakeHistoryGateway(
            failure=HomeAssistantQueryError("invalid_range", "The range is not valid.")
        ),
        start="2026-08-25T12:00:00Z",
    )

    assert result.ok is False
    assert result.error_code == "invalid_range"
