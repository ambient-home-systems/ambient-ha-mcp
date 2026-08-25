import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantAuthorizationError,
)
from ambient_ha.ha.websocket import (
    HomeAssistantWebSocketAPI,
    _command_outcome,
    _websocket_url,
)


class FakeSocket:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = iter(responses)
        self.sent: list[dict[str, Any]] = []

    async def recv(self) -> str:
        return json.dumps(next(self.responses))

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def __aiter__(self) -> AsyncIterator[str]:
        raise NotImplementedError


def test_websocket_url_preserves_base_path_and_selects_secure_scheme() -> None:
    assert _websocket_url("https://ha.example/base/") == "wss://ha.example/base/api/websocket"
    assert _websocket_url("http://ha.local:8123") == "ws://ha.local:8123/api/websocket"


@pytest.mark.anyio
async def test_unknown_registry_command_is_reported_as_unsupported() -> None:
    api = HomeAssistantWebSocketAPI(base_url="http://ha.test", token="secret", timeout_seconds=1)
    socket = FakeSocket(
        [{"id": 4, "type": "result", "success": False, "error": {"code": "unknown_command"}}]
    )

    supported, rows = await api._list(socket, 4, "floor")  # type: ignore[arg-type]

    assert supported is False
    assert rows == []
    assert socket.sent == [{"id": 4, "type": "config/floor_registry/list"}]


@pytest.mark.anyio
async def test_auth_failure_never_echoes_token() -> None:
    api = HomeAssistantWebSocketAPI(
        base_url="http://ha.test", token="do-not-print-this", timeout_seconds=1
    )
    socket = FakeSocket([{"type": "auth_required"}, {"type": "auth_invalid"}])

    with pytest.raises(HomeAssistantAuthenticationError) as captured:
        await api._authenticate(socket)  # type: ignore[arg-type]

    assert "do-not-print-this" not in str(captured.value)


def test_admin_only_automation_command_reports_permission_denied() -> None:
    with pytest.raises(HomeAssistantAuthorizationError) as captured:
        _command_outcome(
            {
                "success": False,
                "error": {"code": "unauthorized", "message": "private upstream detail"},
            }
        )

    assert captured.value.code == "permission_denied"
    assert "private upstream detail" not in str(captured.value)
