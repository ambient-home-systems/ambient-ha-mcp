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


@pytest.mark.parametrize("ttl", [4, 3601])
def test_registry_cache_ttl_is_bounded(ttl: int) -> None:
    with pytest.raises(ValidationError):
        Settings(
            HOME_ASSISTANT_URL="http://homeassistant.local:8123",
            HOME_ASSISTANT_TOKEN="secret",
            REGISTRY_CACHE_TTL_SECONDS=ttl,
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
