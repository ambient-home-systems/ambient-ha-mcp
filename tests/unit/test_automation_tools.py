import pytest

from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantTimeoutError,
)
from ambient_ha.tools.automation import (
    find_activity_cause,
    get_automation,
    get_automation_trace,
    list_automations,
)


class ErrorGateway:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def list_automations(self, **_kwargs: object):
        raise self.error

    async def get_automation(self, _entity_id: str):
        raise self.error


@pytest.mark.anyio
async def test_automation_tools_normalize_timeout_and_authentication_failures() -> None:
    timeout = await list_automations(
        ErrorGateway(HomeAssistantTimeoutError("Home Assistant request timed out.")),  # type: ignore[arg-type]
        limit=5,
    )
    authentication = await get_automation(
        ErrorGateway(HomeAssistantAuthenticationError("Home Assistant rejected access.")),  # type: ignore[arg-type]
        "automation.example",
    )

    assert timeout.ok is False and timeout.error_code == "timeout"
    assert authentication.ok is False
    assert authentication.error_code == "authentication_failed"


@pytest.mark.anyio
async def test_automation_tools_reject_invalid_ids_and_time_ranges_without_io() -> None:
    client = ErrorGateway(AssertionError("must not be called"))

    automation = await get_automation(client, "light.not_an_automation")  # type: ignore[arg-type]
    trace = await get_automation_trace(client, "automation.example", "bad run id")  # type: ignore[arg-type]
    cause = await find_activity_cause(
        client,  # type: ignore[arg-type]
        "light.kitchen",
        timestamp="2024-08-25T02:14:02Z",
        start="2024-08-25T02:13:00Z",
    )

    assert automation.error_code == "invalid_automation_id"
    assert trace.error_code == "invalid_trace_id"
    assert cause.error_code == "invalid_range"
