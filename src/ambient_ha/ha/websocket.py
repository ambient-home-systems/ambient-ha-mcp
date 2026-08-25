"""Read-only Home Assistant WebSocket adapter for registry discovery."""

from __future__ import annotations

import asyncio
import json
import ssl
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantInvalidURL,
    HomeAssistantTimeoutError,
    HomeAssistantTLSFailure,
    HomeAssistantUnexpectedResponse,
    HomeAssistantUnreachableError,
)

_UNSUPPORTED_COMMAND_CODES = {"unknown_command"}


@dataclass(frozen=True, slots=True)
class RegistrySnapshot:
    """Bounded raw registry snapshot joined only inside the discovery resolver."""

    entities: tuple[dict[str, Any], ...] = ()
    devices: tuple[dict[str, Any], ...] = ()
    areas: tuple[dict[str, Any], ...] = ()
    floors: tuple[dict[str, Any], ...] = ()
    entity_registry_supported: bool = True
    device_registry_supported: bool = True
    area_registry_supported: bool = True
    floor_registry_supported: bool = True


class RegistryProvider(Protocol):
    """Interface implemented by the WebSocket adapter and test fakes."""

    async def get_registries(self) -> RegistrySnapshot:
        """Fetch entity, device, area, and floor registry metadata."""
        ...


class HomeAssistantWebSocketAPI:
    """Open a short-lived authenticated socket and read registry snapshots."""

    def __init__(self, *, base_url: str, token: str, timeout_seconds: float) -> None:
        self._url = _websocket_url(base_url)
        self._token = token
        self._timeout = timeout_seconds

    async def get_registries(self) -> RegistrySnapshot:
        """Fetch registries, treating individually unknown commands as unsupported."""
        try:
            async with asyncio.timeout(self._timeout):
                async with connect(
                    self._url,
                    open_timeout=self._timeout,
                    close_timeout=min(self._timeout, 5),
                ) as socket:
                    await self._authenticate(socket)
                    entity_supported, entities = await self._list(socket, 1, "entity")
                    device_supported, devices = await self._list(socket, 2, "device")
                    area_supported, areas = await self._list(socket, 3, "area")
                    floor_supported, floors = await self._list(socket, 4, "floor")
        except TimeoutError as exc:
            raise HomeAssistantTimeoutError(
                "Home Assistant WebSocket discovery timed out."
            ) from exc
        except InvalidURI as exc:
            raise HomeAssistantInvalidURL(
                "The configured Home Assistant WebSocket URL is invalid."
            ) from exc
        except ssl.SSLError as exc:
            raise HomeAssistantTLSFailure(
                "A secure WebSocket connection to Home Assistant could not be established."
            ) from exc
        except (ConnectionClosed, InvalidHandshake, OSError) as exc:
            if _contains_ssl_error(exc):
                raise HomeAssistantTLSFailure(
                    "A secure WebSocket connection to Home Assistant could not be established."
                ) from exc
            raise HomeAssistantUnreachableError(
                "Home Assistant WebSocket discovery could not be reached."
            ) from exc

        return RegistrySnapshot(
            entities=tuple(entities),
            devices=tuple(devices),
            areas=tuple(areas),
            floors=tuple(floors),
            entity_registry_supported=entity_supported,
            device_registry_supported=device_supported,
            area_registry_supported=area_supported,
            floor_registry_supported=floor_supported,
        )

    async def _authenticate(self, socket: ClientConnection) -> None:
        opening = await _receive_object(socket)
        if opening.get("type") != "auth_required":
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant WebSocket did not begin the expected authentication flow."
            )
        await socket.send(json.dumps({"type": "auth", "access_token": self._token}))
        result = await _receive_object(socket)
        if result.get("type") == "auth_invalid":
            raise HomeAssistantAuthenticationError(
                "Home Assistant rejected the configured access token."
            )
        if result.get("type") != "auth_ok":
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant WebSocket authentication returned an unexpected response."
            )

    async def _list(
        self, socket: ClientConnection, message_id: int, registry: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        command = f"config/{registry}_registry/list"
        await socket.send(json.dumps({"id": message_id, "type": command}))
        response = await _receive_object(socket)
        if response.get("id") != message_id or response.get("type") != "result":
            raise HomeAssistantUnexpectedResponse(
                f"Home Assistant returned an unexpected {registry} registry response."
            )
        if response.get("success") is not True:
            error = response.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            if code in _UNSUPPORTED_COMMAND_CODES:
                return False, []
            raise HomeAssistantUnexpectedResponse(
                f"Home Assistant rejected the {registry} registry request."
            )
        result = response.get("result")
        if not isinstance(result, list):
            raise HomeAssistantUnexpectedResponse(
                f"Home Assistant returned malformed {registry} registry data."
            )
        return True, [item for item in result if isinstance(item, dict)]


async def _receive_object(socket: ClientConnection) -> dict[str, Any]:
    raw = await socket.recv()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise HomeAssistantUnexpectedResponse(
            "Home Assistant WebSocket returned invalid JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise HomeAssistantUnexpectedResponse(
            "Home Assistant WebSocket returned JSON in an unexpected shape."
        )
    return payload


def _websocket_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws" if parsed.scheme == "http" else ""
    if not scheme or not parsed.netloc:
        raise HomeAssistantInvalidURL("The configured Home Assistant URL is invalid.")
    path = f"{parsed.path.rstrip('/')}/api/websocket"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _contains_ssl_error(exc: BaseException) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ssl.SSLError):
            return True
        current = current.__cause__ or current.__context__
    return False
