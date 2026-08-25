"""Normalized, deliberately limited Home Assistant models."""

from pydantic import BaseModel, ConfigDict


class HomeAssistantServerInfo(BaseModel):
    """Non-sensitive Home Assistant installation metadata."""

    model_config = ConfigDict(extra="forbid")

    version: str | None = None
    time_zone: str | None = None
    unit_system: dict[str, str] | None = None
