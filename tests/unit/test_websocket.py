import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

import ambient_ha.ha.websocket as websocket_module
from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantAuthorizationError,
)
from ambient_ha.ha.websocket import (
    _MAX_MESSAGE_BYTES,
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


class FakeConnectionContext:
    def __init__(self, socket: FakeSocket) -> None:
        self.socket = socket

    async def __aenter__(self) -> FakeSocket:
        return self.socket

    async def __aexit__(self, *_args: object) -> None:
        return None


def test_websocket_url_preserves_base_path_and_selects_secure_scheme() -> None:
    assert _websocket_url("https://ha.example/base/") == "wss://ha.example/base/api/websocket"
    assert (
        _websocket_url("http://homeassistant.local:8123")
        == "ws://homeassistant.local:8123/api/websocket"
    )
    assert _websocket_url("https://ha.example.com") == "wss://ha.example.com/api/websocket"


def test_explicit_supervisor_websocket_url_bypasses_standalone_derivation() -> None:
    api = HomeAssistantWebSocketAPI(
        base_url="http://supervisor/core",
        websocket_url="ws://supervisor/core/websocket",
        token="secret",
        timeout_seconds=1,
    )

    assert api._url == "ws://supervisor/core/websocket"
    assert api._url != "ws://supervisor/core/api/websocket"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("use_system_proxy", "expected_proxy"),
    [(True, True), (False, None)],
)
async def test_websocket_connection_uses_explicit_proxy_policy(
    monkeypatch: pytest.MonkeyPatch,
    use_system_proxy: bool,
    expected_proxy: bool | None,
) -> None:
    captured: dict[str, object] = {}
    socket = FakeSocket([{"type": "auth_required"}, {"type": "auth_ok"}])
    monkeypatch.setenv("ALL_PROXY", "socks5://proxy.invalid:1080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")

    def fake_connect(url: str, **kwargs: object) -> FakeConnectionContext:
        captured["url"] = url
        captured.update(kwargs)
        return FakeConnectionContext(socket)

    monkeypatch.setattr(websocket_module, "connect", fake_connect)
    api = HomeAssistantWebSocketAPI(
        base_url="http://supervisor/core",
        websocket_url="ws://supervisor/core/websocket",
        token="secret",
        timeout_seconds=1,
        use_system_proxy=use_system_proxy,
    )

    async def operation(_socket: object) -> str:
        return "ok"

    assert await api._run(operation, "test") == "ok"  # type: ignore[arg-type]
    assert captured["url"] == "ws://supervisor/core/websocket"
    assert captured["proxy"] is expected_proxy
    assert captured["max_size"] == _MAX_MESSAGE_BYTES
    assert captured["logger"] is websocket_module._TRANSPORT_LOGGER
    assert websocket_module._TRANSPORT_LOGGER.getEffectiveLevel() >= logging.INFO


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
async def test_registry_response_larger_than_websockets_default_is_supported() -> None:
    rows = [
        {"entity_id": f"sensor.large_registry_{index}", "name": "x" * 220} for index in range(5_000)
    ]
    large_response = json.dumps({"id": 1, "type": "result", "success": True, "result": rows})
    assert len(large_response.encode()) > 1_048_576
    assert len(large_response.encode()) < _MAX_MESSAGE_BYTES

    async def handler(socket: ServerConnection) -> None:
        await socket.send(json.dumps({"type": "auth_required"}))
        assert json.loads(await socket.recv())["type"] == "auth"
        await socket.send(json.dumps({"type": "auth_ok"}))
        for message_id, registry in enumerate(("entity", "device", "area", "floor"), start=1):
            request = json.loads(await socket.recv())
            assert request == {"id": message_id, "type": f"config/{registry}_registry/list"}
            if registry == "entity":
                await socket.send(large_response)
            else:
                await socket.send(
                    json.dumps({"id": message_id, "type": "result", "success": True, "result": []})
                )

    async with serve(handler, "127.0.0.1", 0) as server:
        assert server.sockets
        port = server.sockets[0].getsockname()[1]
        api = HomeAssistantWebSocketAPI(
            base_url="http://127.0.0.1",
            websocket_url=f"ws://127.0.0.1:{port}",
            token="test-only",
            timeout_seconds=5,
            use_system_proxy=False,
        )

        snapshot = await api.get_registries()

    assert len(snapshot.entities) == len(rows)
    assert snapshot.entities[0]["entity_id"] == "sensor.large_registry_0"
    assert snapshot.devices == ()
    assert snapshot.areas == ()
    assert snapshot.floors == ()


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
