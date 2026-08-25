from collections.abc import Iterator

import pytest

from ambient_ha.config import Settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings() -> Iterator[Settings]:
    yield Settings(
        HOME_ASSISTANT_URL="http://homeassistant.test:8123",
        HOME_ASSISTANT_TOKEN="test-secret-token",
    )
