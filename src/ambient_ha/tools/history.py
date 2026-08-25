"""Read-only semantic services for recorded Home Assistant facts."""

from __future__ import annotations

import logging
import re

from ambient_ha.ha.client import HomeAssistantGateway
from ambient_ha.ha.exceptions import HomeAssistantError
from ambient_ha.models.history import (
    EntityHistoryResult,
    LogbookResult,
    RecentChangesFilters,
    RecentChangesResult,
)

LOGGER = logging.getLogger(__name__)
MAX_HISTORY_LIMIT = 500
MAX_DURATION_MINUTES = 10080
_ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9_]+$")


async def get_entity_history(
    client: HomeAssistantGateway,
    entity_id: str,
    *,
    start: str,
    end: str | None = None,
    limit: int | None = None,
    minimal_response: bool = True,
) -> EntityHistoryResult:
    """Return bounded recorder transitions for one exact entity ID."""
    normalized = entity_id.strip().casefold()
    if not _ENTITY_ID_PATTERN.fullmatch(normalized):
        return EntityHistoryResult(
            ok=False,
            found=False,
            message="Entity ID must use the form domain.object_id.",
            error_code="invalid_entity_id",
        )
    if not start.strip():
        return EntityHistoryResult(
            ok=False,
            found=False,
            message="A historical start timestamp is required.",
            error_code="invalid_timestamp",
        )
    try:
        found, history = await client.get_entity_history(
            normalized,
            start=start.strip(),
            end=_optional_text(end),
            limit=_bounded_limit(limit),
            minimal_response=minimal_response,
        )
    except HomeAssistantError as exc:
        return EntityHistoryResult(ok=False, found=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while reading Home Assistant entity history")
        return EntityHistoryResult(
            ok=False,
            found=False,
            message="The bridge could not read Home Assistant entity history.",
            error_code="internal_error",
        )
    if not found:
        return EntityHistoryResult(
            ok=True,
            found=False,
            message=(
                f"Home Assistant entity '{normalized}' was not found and has no recorded history."
            ),
            history=history,
            error_code="not_found",
        )
    return EntityHistoryResult(
        ok=True,
        found=True,
        history=history,
        message=(
            "No recorded state transitions were returned for this interval."
            if history.total_transitions == 0
            else f"Returned {history.returned} of {history.total_transitions} recorded transitions."
        ),
    )


async def get_logbook(
    client: HomeAssistantGateway,
    *,
    start: str,
    end: str | None = None,
    entity_id: str | None = None,
    limit: int | None = None,
) -> LogbookResult:
    """Return bounded, privacy-filtered recorded logbook facts."""
    normalized_entity = _optional_text(entity_id)
    if normalized_entity and not _ENTITY_ID_PATTERN.fullmatch(normalized_entity.casefold()):
        return LogbookResult(
            ok=False,
            message="Entity ID must use the form domain.object_id.",
            error_code="invalid_entity_id",
        )
    if not start.strip():
        return LogbookResult(
            ok=False,
            message="A logbook start timestamp is required.",
            error_code="invalid_timestamp",
        )
    try:
        logbook = await client.get_logbook(
            start=start.strip(),
            end=_optional_text(end),
            entity_id=normalized_entity.casefold() if normalized_entity else None,
            limit=_bounded_limit(limit),
        )
    except HomeAssistantError as exc:
        return LogbookResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while reading Home Assistant logbook")
        return LogbookResult(
            ok=False,
            message="The bridge could not read the Home Assistant logbook.",
            error_code="internal_error",
        )
    return LogbookResult(
        ok=True,
        logbook=logbook,
        message=(
            "No recorded logbook entries were returned for this interval."
            if logbook.total_entries == 0
            else f"Returned {logbook.returned} of {logbook.total_entries} recorded logbook entries."
        ),
    )


async def get_recent_changes(
    client: HomeAssistantGateway,
    *,
    start: str | None = None,
    end: str | None = None,
    duration_minutes: int | None = None,
    area: str | None = None,
    floor: str | None = None,
    domain: str | None = None,
    entity_id: str | None = None,
    limit: int | None = None,
) -> RecentChangesResult:
    """Return bounded historical facts for resolver-filtered current entities."""
    normalized_domain = _optional_text(domain)
    normalized_entity = _optional_text(entity_id)
    if normalized_domain and not _DOMAIN_PATTERN.fullmatch(normalized_domain.casefold()):
        return RecentChangesResult(
            ok=False,
            message="Domain must contain only lowercase letters, digits, and underscores.",
            error_code="invalid_domain",
        )
    if normalized_entity and not _ENTITY_ID_PATTERN.fullmatch(normalized_entity.casefold()):
        return RecentChangesResult(
            ok=False,
            message="Entity ID must use the form domain.object_id.",
            error_code="invalid_entity_id",
        )
    if duration_minutes is not None and not 1 <= duration_minutes <= MAX_DURATION_MINUTES:
        return RecentChangesResult(
            ok=False,
            message="Duration must be between 1 minute and 7 days.",
            error_code="range_too_large",
        )
    filters = RecentChangesFilters(
        start=_optional_text(start),
        end=_optional_text(end),
        duration_minutes=duration_minutes,
        area=_optional_text(area),
        floor=_optional_text(floor),
        domain=normalized_domain,
        entity_id=normalized_entity,
        limit=_bounded_limit(limit),
    )
    try:
        changes = await client.get_recent_changes(filters)
    except HomeAssistantError as exc:
        return RecentChangesResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while reading recent Home Assistant changes")
        return RecentChangesResult(
            ok=False,
            message="The bridge could not read recent Home Assistant changes.",
            error_code="internal_error",
        )
    return RecentChangesResult(
        ok=True,
        changes=changes,
        message=(
            "No recorded changes matched this interval and filter set."
            if changes.total_changes == 0
            else f"Returned {changes.returned} of {changes.total_changes} recorded changes."
        ),
    )


def _bounded_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    return max(1, min(limit, MAX_HISTORY_LIMIT))


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
