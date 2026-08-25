"""Normalize raw Home Assistant payloads into intentionally safe models."""

from collections.abc import Mapping
from typing import Any

from ambient_ha.models.home_assistant import HomeAssistantServerInfo


def normalize_server_info(payload: Mapping[str, Any]) -> HomeAssistantServerInfo:
    """Keep only non-sensitive fields needed for Phase 1 diagnostics."""
    unit_system = payload.get("unit_system")
    safe_units: dict[str, str] | None = None
    if isinstance(unit_system, dict):
        safe_units = {
            str(key): str(value)
            for key, value in unit_system.items()
            if isinstance(key, str) and isinstance(value, str)
        }
    version = payload.get("version")
    time_zone = payload.get("time_zone")
    return HomeAssistantServerInfo(
        version=version if isinstance(version, str) else None,
        time_zone=time_zone if isinstance(time_zone, str) else None,
        unit_system=safe_units,
    )
