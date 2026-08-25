"""Safe diagnostic response models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ambient_ha.models.home_assistant import HomeAssistantServerInfo


class ConnectionStatus(BaseModel):
    """Connectivity state without credentials or raw upstream payloads."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["connected", "authentication_failed", "unreachable", "error"]
    reachable: bool
    authenticated: bool
    message: str
    error_code: str | None = None


class ServerInfoResult(BaseModel):
    """Safe server information or a normalized failure."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    server: HomeAssistantServerInfo | None = None
    message: str
    error_code: str | None = None


class HealthStatus(BaseModel):
    """Container-friendly liveness plus upstream readiness details."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    application_running: bool = True
    home_assistant_reachable: bool
    home_assistant_authenticated: bool
