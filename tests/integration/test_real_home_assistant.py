import os

import pytest

from ambient_ha.config import Settings
from ambient_ha.ha.client import HomeAssistantClient


@pytest.mark.integration
@pytest.mark.anyio
async def test_real_home_assistant_connection() -> None:
    if os.environ.get("RUN_HA_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_HA_INTEGRATION_TESTS=1 to use a real Home Assistant instance")

    settings = Settings()  # type: ignore[call-arg]
    result = await HomeAssistantClient(settings).check_connection()

    assert result.status == "connected", result.message
