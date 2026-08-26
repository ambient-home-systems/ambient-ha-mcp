"""Runtime launcher for standalone and Home Assistant App installations."""

from __future__ import annotations

import json
import os
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Final

from ambient_ha.server import main as server_main

APP_RUNTIME_MODE: Final = "home_assistant_app"
APP_OPTIONS_PATH: Final = Path("/data/options.json")
SUPERVISOR_CORE_URL: Final = "http://supervisor/core"
MAX_OPTIONS_FILE_BYTES: Final = 64 * 1024

_OPTION_ENVIRONMENT_KEYS: Final = {
    "log_level": "LOG_LEVEL",
    "request_timeout_seconds": "REQUEST_TIMEOUT_SECONDS",
    "registry_cache_ttl_seconds": "REGISTRY_CACHE_TTL_SECONDS",
    "history_default_lookback_hours": "HISTORY_DEFAULT_LOOKBACK_HOURS",
    "history_max_lookback_hours": "HISTORY_MAX_LOOKBACK_HOURS",
    "history_default_limit": "HISTORY_DEFAULT_LIMIT",
    "history_max_events": "HISTORY_MAX_EVENTS",
    "history_max_entities": "HISTORY_MAX_ENTITIES",
    "battery_warning_threshold": "BATTERY_WARNING_THRESHOLD",
    "ignored_diagnostic_entities": "IGNORED_DIAGNOSTIC_ENTITIES",
    "mcp_allowed_hosts": "MCP_ALLOWED_HOSTS",
}
_LIST_OPTIONS: Final = {"ignored_diagnostic_entities", "mcp_allowed_hosts"}


class RuntimeConfigurationError(RuntimeError):
    """Raised when a runtime environment is incomplete or unsafe."""


def _read_app_options(path: Path) -> dict[str, Any]:
    """Read the bounded, Supervisor-managed App options document."""
    try:
        if path.stat().st_size > MAX_OPTIONS_FILE_BYTES:
            raise RuntimeConfigurationError("Home Assistant App options exceed the size limit")
        raw_options = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeConfigurationError("Home Assistant App options are unavailable") from exc

    if len(raw_options.encode("utf-8")) > MAX_OPTIONS_FILE_BYTES:
        raise RuntimeConfigurationError("Home Assistant App options exceed the size limit")
    try:
        options = json.loads(raw_options)
    except json.JSONDecodeError as exc:
        raise RuntimeConfigurationError("Home Assistant App options are invalid JSON") from exc
    if not isinstance(options, dict) or not all(isinstance(key, str) for key in options):
        raise RuntimeConfigurationError("Home Assistant App options must be an object")

    if set(options) - _OPTION_ENVIRONMENT_KEYS.keys():
        raise RuntimeConfigurationError("Unsupported Home Assistant App option present")
    return options


def _option_value(value: Any, *, option_name: str) -> str:
    """Convert a validated App option to its environment representation."""
    if option_name in _LIST_OPTIONS and not isinstance(value, list):
        raise RuntimeConfigurationError(
            f"Invalid list value for Home Assistant App option: {option_name}"
        )
    if isinstance(value, bool) or value is None or isinstance(value, (dict, float)):
        raise RuntimeConfigurationError(
            f"Invalid value for Home Assistant App option: {option_name}"
        )
    if isinstance(value, list):
        if option_name not in _LIST_OPTIONS:
            raise RuntimeConfigurationError(
                f"Invalid list value for Home Assistant App option: {option_name}"
            )
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise RuntimeConfigurationError(
                f"Invalid list value for Home Assistant App option: {option_name}"
            )
        normalized = [item.strip() for item in value]
        if option_name == "mcp_allowed_hosts" and any(
            item == "*" or "://" in item or "/" in item or any(char.isspace() for char in item)
            for item in normalized
        ):
            raise RuntimeConfigurationError("Unsafe Home Assistant App MCP Host allowlist")
        return ",".join(normalized)
    if isinstance(value, (str, int)):
        return str(value)
    raise RuntimeConfigurationError(f"Invalid value for Home Assistant App option: {option_name}")


def configure_home_assistant_app_environment(
    *,
    options_path: Path = APP_OPTIONS_PATH,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Configure the server from Supervisor auth and allowlisted App options.

    The Supervisor token is copied only in process memory. It is never persisted or
    included in an error. Phase 6.5 hard-forces read-only operation.
    """
    target = os.environ if environ is None else environ
    supervisor_token = target.get("SUPERVISOR_TOKEN", "")
    if not supervisor_token:
        raise RuntimeConfigurationError("Supervisor authentication is unavailable")

    options = _read_app_options(options_path)
    for option_name, value in options.items():
        target[_OPTION_ENVIRONMENT_KEYS[option_name]] = _option_value(
            value, option_name=option_name
        )

    target["HOME_ASSISTANT_URL"] = SUPERVISOR_CORE_URL
    target["HOME_ASSISTANT_TOKEN"] = supervisor_token
    target["READ_ONLY"] = "true"
    # The App network namespace is isolated; its host port remains disabled by default.
    target["MCP_HOST"] = "0.0.0.0"  # noqa: S104
    target["MCP_PORT"] = "8000"
    target["MCP_ALLOWED_ORIGINS"] = ""
    target.pop("POLICY_FILE", None)


def main() -> None:
    """Select the runtime adapter, then start the shared MCP server."""
    runtime_mode = os.environ.get("AMBIENT_RUNTIME_MODE", "standalone").strip().casefold()
    if runtime_mode == APP_RUNTIME_MODE:
        try:
            configure_home_assistant_app_environment()
        except RuntimeConfigurationError as exc:
            raise SystemExit(f"Ambient MCP startup failed: {exc}") from exc
    elif runtime_mode != "standalone":
        raise SystemExit("Ambient MCP startup failed: unsupported runtime mode")
    server_main()


if __name__ == "__main__":
    main()
