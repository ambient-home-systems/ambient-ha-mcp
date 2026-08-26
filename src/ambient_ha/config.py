"""Typed application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values are read from the process environment and, for local development only,
    an uncommitted ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    home_assistant_url: str = Field(alias="HOME_ASSISTANT_URL")
    home_assistant_websocket_url: str | None = Field(
        default=None, alias="HOME_ASSISTANT_WEBSOCKET_URL"
    )
    home_assistant_token: SecretStr = Field(min_length=1, alias="HOME_ASSISTANT_TOKEN")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )
    mcp_host: str = Field(default="127.0.0.1", alias="MCP_HOST")
    mcp_port: int = Field(default=8000, ge=1, le=65535, alias="MCP_PORT")
    mcp_allowed_hosts: str = Field(
        default="localhost,localhost:*,127.0.0.1,127.0.0.1:*,[::1],[::1]:*",
        alias="MCP_ALLOWED_HOSTS",
    )
    mcp_allowed_origins: str = Field(default="", alias="MCP_ALLOWED_ORIGINS")
    request_timeout_seconds: float = Field(
        default=10.0, gt=0, le=120, alias="REQUEST_TIMEOUT_SECONDS"
    )
    registry_cache_ttl_seconds: float = Field(
        default=60.0, ge=5, le=3600, alias="REGISTRY_CACHE_TTL_SECONDS"
    )
    history_default_lookback_hours: int = Field(
        default=24, ge=1, le=168, alias="HISTORY_DEFAULT_LOOKBACK_HOURS"
    )
    history_max_lookback_hours: int = Field(
        default=168, ge=1, le=720, alias="HISTORY_MAX_LOOKBACK_HOURS"
    )
    history_default_limit: int = Field(default=100, ge=1, le=500, alias="HISTORY_DEFAULT_LIMIT")
    history_max_events: int = Field(default=500, ge=1, le=1000, alias="HISTORY_MAX_EVENTS")
    history_max_entities: int = Field(default=50, ge=1, le=100, alias="HISTORY_MAX_ENTITIES")
    battery_warning_threshold: int = Field(
        default=20, ge=1, le=100, alias="BATTERY_WARNING_THRESHOLD"
    )
    ignored_diagnostic_entities: str = Field(default="", alias="IGNORED_DIAGNOSTIC_ENTITIES")
    read_only: bool = Field(default=True, alias="READ_ONLY")
    policy_file: Path | None = Field(default=None, alias="POLICY_FILE")

    @field_validator("home_assistant_url")
    @classmethod
    def validate_home_assistant_url(cls, value: str) -> str:
        """Accept only credential-free HTTP(S) base URLs."""
        cleaned = value.strip().rstrip("/")
        parsed = urlsplit(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("HOME_ASSISTANT_URL must be an absolute http(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("HOME_ASSISTANT_URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("HOME_ASSISTANT_URL must not contain a query or fragment")
        return cleaned

    @field_validator("home_assistant_websocket_url")
    @classmethod
    def validate_home_assistant_websocket_url(cls, value: str | None) -> str | None:
        """Validate an optional explicit Home Assistant WebSocket endpoint."""
        if value is None:
            return None
        cleaned = value.strip().rstrip("/")
        parsed = urlsplit(cleaned)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
            raise ValueError("HOME_ASSISTANT_WEBSOCKET_URL must be an absolute ws(s) URL")
        if parsed.username or parsed.password:
            raise ValueError("HOME_ASSISTANT_WEBSOCKET_URL must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("HOME_ASSISTANT_WEBSOCKET_URL must not contain a query or fragment")
        return cleaned

    @model_validator(mode="after")
    def validate_history_query_bounds(self) -> Self:
        """Keep default historical queries within their configured hard bounds."""
        if self.history_default_lookback_hours > self.history_max_lookback_hours:
            raise ValueError(
                "HISTORY_DEFAULT_LOOKBACK_HOURS must not exceed HISTORY_MAX_LOOKBACK_HOURS"
            )
        if self.history_default_limit > self.history_max_events:
            raise ValueError("HISTORY_DEFAULT_LIMIT must not exceed HISTORY_MAX_EVENTS")
        return self

    @property
    def allowed_hosts(self) -> list[str]:
        """Return the explicit MCP Host-header allowlist."""
        return [item.strip() for item in self.mcp_allowed_hosts.split(",") if item.strip()]

    @property
    def allowed_origins(self) -> list[str]:
        """Return the explicit MCP browser-origin allowlist."""
        return [item.strip() for item in self.mcp_allowed_origins.split(",") if item.strip()]

    @property
    def ignored_diagnostic_entity_ids(self) -> frozenset[str]:
        """Return normalized entity IDs excluded from aggregate diagnostic views."""
        return frozenset(
            item.strip().casefold()
            for item in self.ignored_diagnostic_entities.split(",")
            if item.strip()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache validated process configuration."""
    return Settings()  # type: ignore[call-arg]
