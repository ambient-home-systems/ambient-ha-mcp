"""Read-only automation discovery, trace, reference, and evidence tools."""

from __future__ import annotations

import logging
import re

from ambient_ha.ha.client import HomeAssistantGateway
from ambient_ha.ha.exceptions import HomeAssistantError
from ambient_ha.models.automation import (
    ActivityCauseResult,
    AutomationListResult,
    AutomationReferencesResult,
    AutomationResult,
    AutomationTraceResult,
    AutomationTracesResult,
)

LOGGER = logging.getLogger(__name__)
MAX_AUTOMATION_RESULTS = 100
MAX_TRACE_RUNS = 50
MAX_CAUSALITY_RESULTS = 50
MAX_CAUSALITY_WINDOW_SECONDS = 600
_ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


async def list_automations(
    client: HomeAssistantGateway,
    *,
    query: str | None = None,
    enabled: bool | None = None,
    limit: int = 25,
) -> AutomationListResult:
    """Return compact current automation entity metadata."""
    try:
        page = await client.list_automations(
            query=_optional_text(query), enabled=enabled, limit=_limit(limit)
        )
    except HomeAssistantError as exc:
        return AutomationListResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while listing Home Assistant automations")
        return AutomationListResult(
            ok=False,
            message="The bridge could not list Home Assistant automations.",
            error_code="internal_error",
        )
    return AutomationListResult(
        ok=True,
        message=f"Returned {page.returned} of {page.total_matches} matching automations.",
        result=page,
    )


async def get_automation(client: HomeAssistantGateway, automation: str) -> AutomationResult:
    """Return one bounded normalized automation definition when supported."""
    entity_id = _automation_id(automation)
    if entity_id is None:
        return AutomationResult(
            ok=False,
            found=False,
            supported=True,
            message="Automation must be an automation entity ID or object ID.",
            error_code="invalid_automation_id",
        )
    try:
        supported, found, definition = await client.get_automation(entity_id)
    except HomeAssistantError as exc:
        return AutomationResult(
            ok=False,
            found=False,
            supported=True,
            message=str(exc),
            error_code=exc.code,
        )
    except Exception:
        LOGGER.exception("Unexpected error while retrieving a Home Assistant automation")
        return AutomationResult(
            ok=False,
            found=False,
            supported=True,
            message="The bridge could not retrieve the Home Assistant automation.",
            error_code="internal_error",
        )
    if not found:
        return AutomationResult(
            ok=True,
            found=False,
            supported=supported,
            message=f"Home Assistant automation '{entity_id}' was not found.",
            error_code="not_found",
        )
    return AutomationResult(
        ok=True,
        found=True,
        supported=supported,
        automation=definition,
        message=(
            "Automation metadata is available, but configuration is unsupported."
            if not supported
            else "Automation configuration is available."
        ),
    )


async def find_automations_for_entity(
    client: HomeAssistantGateway, entity_id: str, *, limit: int = 25
) -> AutomationReferencesResult:
    """Return conservative static references without evaluating templates."""
    normalized = _entity_id(entity_id)
    if normalized is None:
        return AutomationReferencesResult(
            ok=False,
            message="Entity ID must use the form domain.object_id.",
            error_code="invalid_entity_id",
        )
    try:
        found, page = await client.find_automations_for_entity(normalized, limit=_limit(limit))
    except HomeAssistantError as exc:
        return AutomationReferencesResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while indexing Home Assistant automation references")
        return AutomationReferencesResult(
            ok=False,
            message="The bridge could not inspect automation references.",
            error_code="internal_error",
        )
    if not found:
        return AutomationReferencesResult(
            ok=True,
            message=f"Home Assistant entity '{normalized}' was not found.",
            result=page,
            error_code="not_found",
        )
    return AutomationReferencesResult(
        ok=True,
        message=f"Returned {page.returned} of {page.total_matches} static references.",
        result=page,
    )


async def get_automation_traces(
    client: HomeAssistantGateway, automation: str, *, limit: int = 10
) -> AutomationTracesResult:
    """Return compact recent trace metadata; no full trace bodies."""
    entity_id = _automation_id(automation)
    if entity_id is None:
        return AutomationTracesResult(
            ok=False,
            found=False,
            supported=True,
            message="Automation must be an automation entity ID or object ID.",
            error_code="invalid_automation_id",
        )
    try:
        found, page = await client.get_automation_traces(
            entity_id, limit=max(1, min(limit, MAX_TRACE_RUNS))
        )
    except HomeAssistantError as exc:
        return AutomationTracesResult(
            ok=False,
            found=False,
            supported=True,
            message=str(exc),
            error_code=exc.code,
        )
    except Exception:
        LOGGER.exception("Unexpected error while listing Home Assistant automation traces")
        return AutomationTracesResult(
            ok=False,
            found=False,
            supported=True,
            message="The bridge could not list automation traces.",
            error_code="internal_error",
        )
    if not found:
        return AutomationTracesResult(
            ok=True,
            found=False,
            supported=page.supported,
            result=page,
            message=f"Home Assistant automation '{entity_id}' was not found.",
            error_code="not_found",
        )
    if not page.supported:
        return AutomationTracesResult(
            ok=True,
            found=True,
            supported=False,
            result=page,
            message="This Home Assistant installation does not expose stored traces.",
        )
    return AutomationTracesResult(
        ok=True,
        found=True,
        supported=True,
        result=page,
        message=(
            "No stored traces exist for this automation."
            if page.total_traces == 0
            else f"Returned {page.returned} of {page.total_traces} stored traces."
        ),
    )


async def get_automation_trace(
    client: HomeAssistantGateway, automation: str, run_id: str
) -> AutomationTraceResult:
    """Return one normalized stored execution trace."""
    entity_id = _automation_id(automation)
    if entity_id is None:
        return AutomationTraceResult(
            ok=False,
            found=False,
            supported=True,
            message="Automation must be an automation entity ID or object ID.",
            error_code="invalid_automation_id",
        )
    cleaned_run_id = run_id.strip()
    if not _RUN_ID_PATTERN.fullmatch(cleaned_run_id):
        return AutomationTraceResult(
            ok=False,
            found=False,
            supported=True,
            message="Trace run identifier is invalid.",
            error_code="invalid_trace_id",
        )
    try:
        supported, found, trace = await client.get_automation_trace(entity_id, cleaned_run_id)
    except HomeAssistantError as exc:
        return AutomationTraceResult(
            ok=False,
            found=False,
            supported=True,
            message=str(exc),
            error_code=exc.code,
        )
    except Exception:
        LOGGER.exception("Unexpected error while retrieving a Home Assistant automation trace")
        return AutomationTraceResult(
            ok=False,
            found=False,
            supported=True,
            message="The bridge could not retrieve the automation trace.",
            error_code="internal_error",
        )
    if not supported:
        return AutomationTraceResult(
            ok=True,
            found=False,
            supported=False,
            message="This Home Assistant installation does not expose stored traces.",
        )
    if not found:
        return AutomationTraceResult(
            ok=True,
            found=False,
            supported=True,
            message="The requested automation or stored trace was not found.",
            error_code="not_found",
        )
    return AutomationTraceResult(
        ok=True,
        found=True,
        supported=True,
        trace=trace,
        message="Normalized automation trace is available.",
    )


async def find_activity_cause(
    client: HomeAssistantGateway,
    entity_id: str,
    *,
    timestamp: str | None = None,
    start: str | None = None,
    end: str | None = None,
    window_seconds: int = 60,
    limit: int = 10,
) -> ActivityCauseResult:
    """Gather deterministic context, trace, timing, and reference evidence."""
    normalized = _entity_id(entity_id)
    if normalized is None:
        return ActivityCauseResult(
            ok=False,
            found=False,
            message="Entity ID must use the form domain.object_id.",
            error_code="invalid_entity_id",
        )
    cleaned_timestamp = _optional_text(timestamp)
    cleaned_start = _optional_text(start)
    cleaned_end = _optional_text(end)
    if cleaned_timestamp is not None and (cleaned_start is not None or cleaned_end is not None):
        return ActivityCauseResult(
            ok=False,
            found=False,
            message="Use either timestamp or start/end, not both.",
            error_code="invalid_range",
        )
    if cleaned_timestamp is None and cleaned_start is None:
        return ActivityCauseResult(
            ok=False,
            found=False,
            message="Provide a timestamp or an explicit start timestamp.",
            error_code="invalid_range",
        )
    bounded_window = max(1, min(window_seconds, MAX_CAUSALITY_WINDOW_SECONDS))
    try:
        found, report = await client.find_activity_cause(
            normalized,
            timestamp=cleaned_timestamp,
            start=cleaned_start,
            end=cleaned_end,
            window_seconds=bounded_window,
            limit=max(1, min(limit, MAX_CAUSALITY_RESULTS)),
        )
    except HomeAssistantError as exc:
        return ActivityCauseResult(
            ok=False,
            found=False,
            message=str(exc),
            error_code=exc.code,
        )
    except Exception:
        LOGGER.exception("Unexpected error while correlating Home Assistant activity evidence")
        return ActivityCauseResult(
            ok=False,
            found=False,
            message="The bridge could not correlate Home Assistant activity evidence.",
            error_code="internal_error",
        )
    return ActivityCauseResult(
        ok=True,
        found=found,
        result=report,
        message=(
            "No recorded state change was found in the requested interval."
            if report.state_changes_found == 0
            else f"Returned {report.returned} of {report.total_evidence} evidence records."
        ),
        error_code=None if found else "not_found",
    )


def _automation_id(value: str) -> str | None:
    cleaned = value.strip().casefold()
    entity_id = cleaned if "." in cleaned else f"automation.{cleaned}"
    if not _ENTITY_ID_PATTERN.fullmatch(entity_id) or not entity_id.startswith("automation."):
        return None
    return entity_id


def _entity_id(value: str) -> str | None:
    cleaned = value.strip().casefold()
    return cleaned if _ENTITY_ID_PATTERN.fullmatch(cleaned) else None


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _limit(value: int) -> int:
    return max(1, min(value, MAX_AUTOMATION_RESULTS))
