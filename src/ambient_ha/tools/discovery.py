"""Semantic, read-only discovery tool services with normalized failures."""

from __future__ import annotations

import logging
import re

from ambient_ha.ha.client import HomeAssistantGateway
from ambient_ha.ha.exceptions import HomeAssistantError
from ambient_ha.models.discovery import (
    AreaListResult,
    AreaResult,
    DomainSummaryResult,
    EntityResult,
    EntitySearchFilters,
    EntitySearchResult,
    FloorListResult,
    FloorResult,
)

LOGGER = logging.getLogger(__name__)
MAX_SEARCH_LIMIT = 100
MAX_AREA_ENTITY_LIMIT = 50
_ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_DOMAIN_PATTERN = re.compile(r"^[a-z0-9_]+$")


async def get_entity(client: HomeAssistantGateway, entity_id: str) -> EntityResult:
    """Return one normalized entity, including bounded sanitized attributes."""
    normalized = entity_id.strip().casefold()
    if not _ENTITY_ID_PATTERN.fullmatch(normalized):
        return EntityResult(
            ok=False,
            found=False,
            message="Entity ID must use the form domain.object_id.",
            error_code="invalid_entity_id",
        )
    try:
        entity = await client.get_entity(normalized)
    except HomeAssistantError as exc:
        return EntityResult(ok=False, found=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while retrieving a Home Assistant entity")
        return EntityResult(
            ok=False,
            found=False,
            message="The bridge could not retrieve the Home Assistant entity.",
            error_code="internal_error",
        )
    if entity is None:
        return EntityResult(
            ok=True,
            found=False,
            message=f"Home Assistant entity '{normalized}' was not found.",
            error_code="not_found",
        )
    return EntityResult(
        ok=True,
        found=True,
        entity=entity,
        message="Home Assistant entity state is available.",
    )


async def search_entities(
    client: HomeAssistantGateway,
    *,
    query: str | None = None,
    domain: str | None = None,
    area: str | None = None,
    floor: str | None = None,
    state: str | None = None,
    available: bool | None = None,
    limit: int = 25,
) -> EntitySearchResult:
    """Run bounded deterministic search over a fresh state snapshot."""
    filters = EntitySearchFilters(
        query=_optional_text(query),
        domain=_optional_text(domain),
        area=_optional_text(area),
        floor=_optional_text(floor),
        state=_optional_text(state),
        available=available,
        limit=max(1, min(limit, MAX_SEARCH_LIMIT)),
    )
    try:
        page = await client.search_entities(filters)
    except HomeAssistantError as exc:
        return EntitySearchResult(
            ok=False,
            message=str(exc),
            error_code=exc.code,
            entities=[],
            total_matches=0,
            returned=0,
            limit=filters.limit,
            truncated=False,
        )
    except Exception:
        LOGGER.exception("Unexpected error while searching Home Assistant entities")
        return EntitySearchResult(
            ok=False,
            message="The bridge could not search Home Assistant entities.",
            error_code="internal_error",
            entities=[],
            total_matches=0,
            returned=0,
            limit=filters.limit,
            truncated=False,
        )
    return EntitySearchResult(
        ok=True,
        message=f"Returned {page.returned} of {page.total_matches} matching entities.",
        **page.model_dump(),
    )


async def list_areas(client: HomeAssistantGateway) -> AreaListResult:
    try:
        supported, areas = await client.list_areas()
    except HomeAssistantError as exc:
        return AreaListResult(ok=False, supported=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while listing Home Assistant areas")
        return AreaListResult(
            ok=False,
            supported=False,
            message="The bridge could not list Home Assistant areas.",
            error_code="internal_error",
        )
    if not supported:
        return AreaListResult(
            ok=True,
            supported=False,
            message="This Home Assistant installation does not expose the area registry command.",
        )
    return AreaListResult(
        ok=True,
        supported=True,
        areas=areas,
        message=f"Returned {len(areas)} configured areas.",
    )


async def get_area(
    client: HomeAssistantGateway,
    identifier: str,
    *,
    include_entities: bool = False,
    limit: int = 25,
) -> AreaResult:
    cleaned = identifier.strip()
    if not cleaned:
        return AreaResult(
            ok=False,
            supported=True,
            found=False,
            message="Area ID or name must not be empty.",
            error_code="invalid_area",
        )
    try:
        supported, area = await client.get_area(
            cleaned,
            include_entities=include_entities,
            limit=max(1, min(limit, MAX_AREA_ENTITY_LIMIT)),
        )
    except HomeAssistantError as exc:
        return AreaResult(
            ok=False,
            supported=False,
            found=False,
            message=str(exc),
            error_code=exc.code,
        )
    except Exception:
        LOGGER.exception("Unexpected error while retrieving a Home Assistant area")
        return AreaResult(
            ok=False,
            supported=False,
            found=False,
            message="The bridge could not retrieve the Home Assistant area.",
            error_code="internal_error",
        )
    if not supported:
        return AreaResult(
            ok=True,
            supported=False,
            found=False,
            message="This Home Assistant installation does not expose the area registry command.",
        )
    if area is None:
        return AreaResult(
            ok=True,
            supported=True,
            found=False,
            message=f"Home Assistant area '{cleaned}' was not found.",
            error_code="not_found",
        )
    return AreaResult(
        ok=True,
        supported=True,
        found=True,
        area=area,
        message="Home Assistant area information is available.",
    )


async def list_floors(client: HomeAssistantGateway) -> FloorListResult:
    try:
        supported, floors = await client.list_floors()
    except HomeAssistantError as exc:
        return FloorListResult(ok=False, supported=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while listing Home Assistant floors")
        return FloorListResult(
            ok=False,
            supported=False,
            message="The bridge could not list Home Assistant floors.",
            error_code="internal_error",
        )
    if not supported:
        return FloorListResult(
            ok=True,
            supported=False,
            message="Floors are not supported by this Home Assistant installation.",
        )
    return FloorListResult(
        ok=True,
        supported=True,
        floors=floors,
        message=f"Returned {len(floors)} configured floors.",
    )


async def get_floor(client: HomeAssistantGateway, identifier: str) -> FloorResult:
    cleaned = identifier.strip()
    if not cleaned:
        return FloorResult(
            ok=False,
            supported=True,
            found=False,
            message="Floor ID or name must not be empty.",
            error_code="invalid_floor",
        )
    try:
        supported, floor = await client.get_floor(cleaned)
    except HomeAssistantError as exc:
        return FloorResult(
            ok=False,
            supported=False,
            found=False,
            message=str(exc),
            error_code=exc.code,
        )
    except Exception:
        LOGGER.exception("Unexpected error while retrieving a Home Assistant floor")
        return FloorResult(
            ok=False,
            supported=False,
            found=False,
            message="The bridge could not retrieve the Home Assistant floor.",
            error_code="internal_error",
        )
    if not supported:
        return FloorResult(
            ok=True,
            supported=False,
            found=False,
            message="Floors are not supported by this Home Assistant installation.",
        )
    if floor is None:
        return FloorResult(
            ok=True,
            supported=True,
            found=False,
            message=f"Home Assistant floor '{cleaned}' was not found.",
            error_code="not_found",
        )
    return FloorResult(
        ok=True,
        supported=True,
        found=True,
        floor=floor,
        message="Home Assistant floor information is available.",
    )


async def domain_summary(client: HomeAssistantGateway, domain: str) -> DomainSummaryResult:
    normalized = domain.strip().casefold()
    if not _DOMAIN_PATTERN.fullmatch(normalized):
        return DomainSummaryResult(
            ok=False,
            message="Domain must contain only lowercase letters, digits, and underscores.",
            error_code="invalid_domain",
        )
    try:
        summary = await client.get_domain_summary(normalized)
    except HomeAssistantError as exc:
        return DomainSummaryResult(ok=False, message=str(exc), error_code=exc.code)
    except Exception:
        LOGGER.exception("Unexpected error while summarizing a Home Assistant domain")
        return DomainSummaryResult(
            ok=False,
            message="The bridge could not summarize the Home Assistant domain.",
            error_code="internal_error",
        )
    return DomainSummaryResult(
        ok=True,
        summary=summary,
        message=f"Summarized {summary.total} entities in the '{normalized}' domain.",
    )


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
