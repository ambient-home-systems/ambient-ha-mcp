import httpx
import pytest

from ambient_ha.config import Settings
from ambient_ha.ha.client import HomeAssistantClient


@pytest.mark.anyio
async def test_client_reports_success(settings: Settings) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"message": "API running."})
    )
    result = await HomeAssistantClient(settings, transport=transport).check_connection()

    assert result.status == "connected"
    assert result.reachable is True
    assert result.authenticated is True


@pytest.mark.anyio
async def test_client_distinguishes_authentication_failure(settings: Settings) -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(401, json={}))
    result = await HomeAssistantClient(settings, transport=transport).check_connection()

    assert result.status == "authentication_failed"
    assert result.reachable is True
    assert result.authenticated is False


@pytest.mark.anyio
async def test_server_info_allowlists_safe_fields(settings: Settings) -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "version": "2026.8.2",
                "time_zone": "America/New_York",
                "unit_system": {"temperature": "°F", "length": "mi", "nested": {}},
                "latitude": 39.0,
                "longitude": -77.0,
                "config_dir": "/config",
                "components": ["api", "automation"],
                "location_name": "Private Home",
            },
        )
    )

    result = await HomeAssistantClient(settings, transport=transport).get_server_info()

    assert result.model_dump() == {
        "version": "2026.8.2",
        "time_zone": "America/New_York",
        "unit_system": {"temperature": "°F", "length": "mi"},
    }
