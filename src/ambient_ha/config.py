"""Typed application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
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
    read_only: bool = Field(default=True, alias="READ_ONLY")

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

    @property
    def allowed_hosts(self) -> list[str]:
        """Return the explicit MCP Host-header allowlist."""
        return [item.strip() for item in self.mcp_allowed_hosts.split(",") if item.strip()]

    @property
    def allowed_origins(self) -> list[str]:
        """Return the explicit MCP browser-origin allowlist."""
        return [item.strip() for item in self.mcp_allowed_origins.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache validated process configuration."""
    return Settings()  # type: ignore[call-arg]
