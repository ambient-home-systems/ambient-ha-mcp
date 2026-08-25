"""Read-only whole-home summaries and deterministic diagnostic tool services."""

from __future__ import annotations

import logging
import re

from ambient_ha.ha.client import HomeAssistantGateway
from ambient_ha.ha.exceptions import HomeAssistantError
from ambient_ha.models.home import (
    HomeDiagnosticsResult,
    HomeSummaryResult,
    LightsOnResult,
    LocationFilters,
    LowBatteriesResult,
    LowBatteryFilters,
    OpeningFilters,
    OpeningsResult,
    OpeningType,
    UnavailableEntitiesResult,
    UnavailableEntityFilters,
)

LOGGER = logging.getLogger(__name__)
MAX_DIAGNOSTIC_LIMIT = 100
MAX_MINIMUM_DURATION_MINUTES = 10080
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9_]+$")


async def get_home_summary(client: HomeAssistantGateway) -> HomeSummaryResult:
    """Return a compact supported-section summary from one current snapshot."""
    try:
        summary = await client.get_home_summary()
    except HomeAssistantError as exc:
        return HomeSummaryResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while summarizing Home Assistant")
        return HomeSummaryResult(
            ok=False,
            message="The bridge could not summarize the current Home Assistant state.",
            error_code="internal_error",
        )
    return HomeSummaryResult(
        ok=True,
        summary=summary,
        message=(
            f"Summarized {summary.total_entities} current entities across "
            f"{len(summary.sections)} supported sections."
        ),
    )


async def find_unavailable_entities(
    client: HomeAssistantGateway,
    *,
    domain: str | None = None,
    area: str | None = None,
    floor: str | None = None,
    minimum_duration: int | None = None,
    limit: int = 25,
) -> UnavailableEntitiesResult:
    """Return bounded unavailable entities without inventing duration evidence."""
    normalized_domain = _optional_text(domain)
    if normalized_domain and not _DOMAIN_PATTERN.fullmatch(normalized_domain.casefold()):
        return UnavailableEntitiesResult(
            ok=False, message="Domain is invalid.", error_code="invalid_domain"
        )
    if minimum_duration is not None and not 1 <= minimum_duration <= MAX_MINIMUM_DURATION_MINUTES:
        return UnavailableEntitiesResult(
            ok=False,
            message="Minimum duration must be between 1 minute and 7 days.",
            error_code="invalid_duration",
        )
    filters = UnavailableEntityFilters(
        domain=normalized_domain.casefold() if normalized_domain else None,
        area=_optional_text(area),
        floor=_optional_text(floor),
        minimum_duration_minutes=minimum_duration,
        limit=_limit(limit),
    )
    try:
        page = await client.find_unavailable_entities(filters)
    except HomeAssistantError as exc:
        return UnavailableEntitiesResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while finding unavailable Home Assistant entities")
        return UnavailableEntitiesResult(
            ok=False,
            message="The bridge could not inspect unavailable Home Assistant entities.",
            error_code="internal_error",
        )
    return UnavailableEntitiesResult(
        ok=True,
        result=page,
        message=f"Returned {page.returned} of {page.total_matches} unavailable entities.",
    )


async def find_low_batteries(
    client: HomeAssistantGateway,
    *,
    default_threshold: int,
    threshold: int | None = None,
    area: str | None = None,
    floor: str | None = None,
    limit: int = 25,
) -> LowBatteriesResult:
    """Return only numeric percentage sensors with the battery device class."""
    effective_threshold = threshold if threshold is not None else default_threshold
    if not 1 <= effective_threshold <= 100:
        return LowBatteriesResult(
            ok=False,
            message="Battery threshold must be between 1 and 100 percent.",
            error_code="invalid_threshold",
        )
    filters = LowBatteryFilters(
        threshold=effective_threshold,
        area=_optional_text(area),
        floor=_optional_text(floor),
        limit=_limit(limit),
    )
    try:
        page = await client.find_low_batteries(filters)
    except HomeAssistantError as exc:
        return LowBatteriesResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while finding low Home Assistant batteries")
        return LowBatteriesResult(
            ok=False,
            message="The bridge could not inspect Home Assistant battery sensors.",
            error_code="internal_error",
        )
    return LowBatteriesResult(
        ok=True,
        result=page,
        message=(
            f"Returned {page.returned} of {page.total_matches} battery sensors at or below "
            f"{page.threshold} percent."
        ),
    )


async def get_openings(
    client: HomeAssistantGateway,
    *,
    area: str | None = None,
    floor: str | None = None,
    opening_type: OpeningType | None = None,
    state: str = "open",
    limit: int = 25,
) -> OpeningsResult:
    """Return semantic doors, windows, garage doors, and other openings."""
    normalized_state = state.strip().casefold()
    if normalized_state not in {"open", "closed", "unavailable", "unknown", "any"}:
        return OpeningsResult(
            ok=False,
            message="Opening state must be open, closed, unavailable, unknown, or any.",
            error_code="invalid_state",
        )
    filters = OpeningFilters(
        area=_optional_text(area),
        floor=_optional_text(floor),
        opening_type=opening_type,
        state=normalized_state,  # type: ignore[arg-type]
        limit=_limit(limit),
    )
    try:
        page = await client.get_openings(filters)
    except HomeAssistantError as exc:
        return OpeningsResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while inspecting Home Assistant openings")
        return OpeningsResult(
            ok=False,
            message="The bridge could not inspect Home Assistant openings.",
            error_code="internal_error",
        )
    return OpeningsResult(
        ok=True,
        result=page,
        message=f"Returned {page.returned} of {page.total_matches} matching openings.",
    )


async def get_lights_on(
    client: HomeAssistantGateway,
    *,
    area: str | None = None,
    floor: str | None = None,
    limit: int = 25,
) -> LightsOnResult:
    """Return current lights reporting state ``on`` without any control surface."""
    filters = LocationFilters(
        area=_optional_text(area), floor=_optional_text(floor), limit=_limit(limit)
    )
    try:
        page = await client.get_lights_on(filters)
    except HomeAssistantError as exc:
        return LightsOnResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while inspecting Home Assistant lights")
        return LightsOnResult(
            ok=False,
            message="The bridge could not inspect current Home Assistant lights.",
            error_code="internal_error",
        )
    return LightsOnResult(
        ok=True,
        result=page,
        message=f"Returned {page.returned} of {page.total_matches} lights reporting on.",
    )


async def diagnose_home(client: HomeAssistantGateway, *, limit: int = 25) -> HomeDiagnosticsResult:
    """Return deterministic findings with factual Home Assistant evidence."""
    effective_limit = _limit(limit)
    try:
        report = await client.diagnose_home(limit=effective_limit)
    except HomeAssistantError as exc:
        return HomeDiagnosticsResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while diagnosing Home Assistant")
        return HomeDiagnosticsResult(
            ok=False,
            message="The bridge could not diagnose the current Home Assistant state.",
            error_code="internal_error",
        )
    return HomeDiagnosticsResult(
        ok=True,
        report=report,
        message=f"Returned {report.returned} of {report.total_findings} deterministic findings.",
    )


def _limit(value: int) -> int:
    return max(1, min(value, MAX_DIAGNOSTIC_LIMIT))


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
