"""Semantic read-only MCP tool services."""

from ambient_ha.tools.diagnostics import connection_status, health_status, server_info
from ambient_ha.tools.discovery import (
    domain_summary,
    get_area,
    get_entity,
    get_floor,
    list_areas,
    list_floors,
    search_entities,
)
from ambient_ha.tools.history import get_entity_history, get_logbook, get_recent_changes
from ambient_ha.tools.home import (
    diagnose_home,
    find_low_batteries,
    find_unavailable_entities,
    get_home_summary,
    get_lights_on,
    get_openings,
)

__all__ = [
    "connection_status",
    "diagnose_home",
    "domain_summary",
    "find_low_batteries",
    "find_unavailable_entities",
    "get_area",
    "get_entity",
    "get_entity_history",
    "get_floor",
    "get_home_summary",
    "get_lights_on",
    "get_logbook",
    "get_openings",
    "get_recent_changes",
    "health_status",
    "list_areas",
    "list_floors",
    "search_entities",
    "server_info",
]
