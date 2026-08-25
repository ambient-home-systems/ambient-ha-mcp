import pytest
from pydantic import ValidationError

from ambient_ha.config import Settings


def test_required_configuration_and_defaults() -> None:
    settings = Settings(
        HOME_ASSISTANT_URL="http://homeassistant.local:8123/",
        HOME_ASSISTANT_TOKEN="secret",
    )

    assert settings.home_assistant_url == "http://homeassistant.local:8123"
    assert settings.home_assistant_token.get_secret_value() == "secret"
    assert settings.log_level == "INFO"
    assert settings.read_only is True
    assert settings.registry_cache_ttl_seconds == 60
    assert settings.history_default_lookback_hours == 24
    assert settings.history_max_lookback_hours == 168
    assert settings.history_default_limit == 100
    assert settings.history_max_events == 500
    assert settings.history_max_entities == 50
    assert settings.battery_warning_threshold == 20
    assert settings.ignored_diagnostic_entity_ids == frozenset()


@pytest.mark.parametrize("ttl", [4, 3601])
def test_registry_cache_ttl_is_bounded(ttl: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            HOME_ASSISTANT_URL="http://homeassistant.local:8123",
            HOME_ASSISTANT_TOKEN="secret",
            REGISTRY_CACHE_TTL_SECONDS=ttl,
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("HISTORY_DEFAULT_LOOKBACK_HOURS", 0),
        ("HISTORY_MAX_LOOKBACK_HOURS", 721),
        ("HISTORY_MAX_EVENTS", 0),
        ("HISTORY_MAX_ENTITIES", 101),
    ],
)
def test_history_bounds_are_validated(name: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            HOME_ASSISTANT_URL="http://homeassistant.local:8123",
            HOME_ASSISTANT_TOKEN="secret",
            **{name: value},
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"HISTORY_DEFAULT_LOOKBACK_HOURS": 25, "HISTORY_MAX_LOOKBACK_HOURS": 24},
        {"HISTORY_DEFAULT_LIMIT": 101, "HISTORY_MAX_EVENTS": 100},
    ],
)
def test_history_defaults_cannot_exceed_hard_bounds(overrides: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Settings(
            HOME_ASSISTANT_URL="http://homeassistant.local:8123",
            HOME_ASSISTANT_TOKEN="secret",
            **overrides,
        )


@pytest.mark.parametrize(
    "url",
    [
        "homeassistant.local:8123",
        "ftp://homeassistant.local",
        "http://user:password@homeassistant.local:8123",
        "http://homeassistant.local:8123?token=secret",
    ],
)
def test_invalid_or_credentialed_url_is_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(HOME_ASSISTANT_URL=url, HOME_ASSISTANT_TOKEN="secret")


def test_missing_token_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(HOME_ASSISTANT_URL="http://homeassistant.local:8123")  # type: ignore[call-arg]


def test_allowlists_are_parsed_without_empty_entries() -> None:
    settings = Settings(
        HOME_ASSISTANT_URL="http://homeassistant.local:8123",
        HOME_ASSISTANT_TOKEN="secret",
        MCP_ALLOWED_HOSTS="localhost, mcp.example.test,",
        MCP_ALLOWED_ORIGINS="https://chat.example.test,",
    )

    assert settings.allowed_hosts == ["localhost", "mcp.example.test"]
    assert settings.allowed_origins == ["https://chat.example.test"]


def test_diagnostic_configuration_is_bounded_and_normalized() -> None:
    settings = Settings(
        HOME_ASSISTANT_URL="http://homeassistant.local:8123",
        HOME_ASSISTANT_TOKEN="secret",
        BATTERY_WARNING_THRESHOLD=15,
        IGNORED_DIAGNOSTIC_ENTITIES="sensor.One, binary_sensor.Two,",
    )

    assert settings.battery_warning_threshold == 15
    assert settings.ignored_diagnostic_entity_ids == frozenset({"sensor.one", "binary_sensor.two"})

    with pytest.raises(ValidationError):
        Settings(
            HOME_ASSISTANT_URL="http://homeassistant.local:8123",
            HOME_ASSISTANT_TOKEN="secret",
            BATTERY_WARNING_THRESHOLD=0,
        )
