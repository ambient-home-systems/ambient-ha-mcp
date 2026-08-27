"""Read-only Home Assistant WebSocket adapter for registry discovery."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantAuthorizationError,
    HomeAssistantInvalidURL,
    HomeAssistantTimeoutError,
    HomeAssistantTLSFailure,
    HomeAssistantUnexpectedResponse,
    HomeAssistantUnreachableError,
)

_UNSUPPORTED_COMMAND_CODES = {"unknown_command"}
_NOT_FOUND_CODES = {"not_found"}
_AUTHORIZATION_CODES = {"unauthorized"}
T = TypeVar("T")
_TRANSPORT_LOGGER = logging.getLogger("ambient_ha.ha.websocket.transport")
# Home Assistant registry snapshots can exceed websockets' 1 MiB default on real
# installations. Keep the read transport useful for large inventories while retaining
# an explicit ceiling against unexpectedly large upstream messages.
_MAX_MESSAGE_BYTES = 16 * 1024 * 1024
# websockets emits complete frames at DEBUG, including the authentication frame.
# Keep transport diagnostics while preventing payload logging even when Ambient's
# operator-selected application level is DEBUG.
_TRANSPORT_LOGGER.setLevel(logging.INFO)


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


@dataclass(frozen=True, slots=True)
class AutomationConfigBatch:
    """Feature-detected automation configurations keyed by entity ID."""

    supported: bool
    configurations: dict[str, dict[str, Any]]
    missing: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class AutomationTraceListPayload:
    supported: bool
    traces: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class AutomationTracePayload:
    supported: bool
    found: bool
    trace: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AutomationTraceContextsPayload:
    supported: bool
    contexts: dict[str, dict[str, str]]


class AutomationProvider(Protocol):
    """Read-only automation configuration and trace interface."""

    async def get_automation_configs(self, entity_ids: list[str]) -> AutomationConfigBatch: ...

    async def list_automation_traces(self, item_id: str | None) -> AutomationTraceListPayload: ...

    async def get_automation_trace(self, item_id: str, run_id: str) -> AutomationTracePayload: ...

    async def get_automation_trace_contexts(self) -> AutomationTraceContextsPayload: ...


class HomeAssistantWebSocketAPI:
    """Open a short-lived authenticated socket and read registry snapshots."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float,
        websocket_url: str | None = None,
        use_system_proxy: bool = True,
    ) -> None:
        self._url = websocket_url or _websocket_url(base_url)
        self._token = token
        self._timeout = timeout_seconds
        self._proxy: Literal[True] | None = True if use_system_proxy else None

    async def get_registries(self) -> RegistrySnapshot:
        """Fetch registries, treating individually unknown commands as unsupported."""

        async def operation(socket: ClientConnection) -> RegistrySnapshot:
            entity_supported, entities = await self._list(socket, 1, "entity")
            device_supported, devices = await self._list(socket, 2, "device")
            area_supported, areas = await self._list(socket, 3, "area")
            floor_supported, floors = await self._list(socket, 4, "floor")
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

        return await self._run(operation, "discovery")

    async def get_automation_configs(self, entity_ids: list[str]) -> AutomationConfigBatch:
        """Read loaded automation definitions through Home Assistant's WebSocket API."""

        async def operation(socket: ClientConnection) -> AutomationConfigBatch:
            configs: dict[str, dict[str, Any]] = {}
            missing: set[str] = set()
            pending = {
                message_id: entity_id for message_id, entity_id in enumerate(entity_ids, start=1)
            }
            for message_id, entity_id in pending.items():
                await socket.send(
                    json.dumps(
                        {
                            "id": message_id,
                            "type": "automation/config",
                            "entity_id": entity_id,
                        }
                    )
                )
            for _ in pending:
                response = await _receive_object(socket)
                response_id = response.get("id")
                if (
                    not isinstance(response_id, int)
                    or response_id not in pending
                    or response.get("type") != "result"
                ):
                    raise HomeAssistantUnexpectedResponse(
                        "Home Assistant returned an unexpected automation configuration response."
                    )
                entity_id = pending[response_id]
                outcome = _command_outcome(response)
                if outcome == "unsupported":
                    return AutomationConfigBatch(supported=False, configurations={})
                if outcome == "not_found":
                    missing.add(entity_id)
                    continue
                result = response.get("result")
                config = result.get("config") if isinstance(result, Mapping) else None
                if not isinstance(config, dict):
                    raise HomeAssistantUnexpectedResponse(
                        "Home Assistant returned malformed automation configuration data."
                    )
                configs[entity_id] = config
            return AutomationConfigBatch(
                supported=True,
                configurations=configs,
                missing=frozenset(missing),
            )

        return await self._run(operation, "automation configuration")

    async def list_automation_traces(self, item_id: str | None) -> AutomationTraceListPayload:
        """List compact stored trace metadata for one automation."""

        async def operation(socket: ClientConnection) -> AutomationTraceListPayload:
            command: dict[str, Any] = {
                "id": 1,
                "type": "trace/list",
                "domain": "automation",
            }
            if item_id is not None:
                command["item_id"] = item_id
            response = await self._command(
                socket,
                command,
            )
            if _command_outcome(response) == "unsupported":
                return AutomationTraceListPayload(supported=False)
            result = response.get("result")
            if not isinstance(result, list):
                raise HomeAssistantUnexpectedResponse(
                    "Home Assistant returned malformed automation trace metadata."
                )
            return AutomationTraceListPayload(
                supported=True,
                traces=tuple(item for item in result if isinstance(item, dict)),
            )

        return await self._run(operation, "automation trace listing")

    async def get_automation_trace(self, item_id: str, run_id: str) -> AutomationTracePayload:
        """Read one full stored automation trace without executing anything."""

        async def operation(socket: ClientConnection) -> AutomationTracePayload:
            response = await self._command(
                socket,
                {
                    "id": 1,
                    "type": "trace/get",
                    "domain": "automation",
                    "item_id": item_id,
                    "run_id": run_id,
                },
            )
            outcome = _command_outcome(response)
            if outcome == "unsupported":
                return AutomationTracePayload(supported=False, found=False)
            if outcome == "not_found":
                return AutomationTracePayload(supported=True, found=False)
            result = response.get("result")
            if not isinstance(result, dict):
                raise HomeAssistantUnexpectedResponse(
                    "Home Assistant returned malformed automation trace data."
                )
            return AutomationTracePayload(supported=True, found=True, trace=result)

        return await self._run(operation, "automation trace retrieval")

    async def get_automation_trace_contexts(self) -> AutomationTraceContextsPayload:
        """Read the context-to-trace map used for direct causal correlation."""

        async def operation(socket: ClientConnection) -> AutomationTraceContextsPayload:
            response = await self._command(
                socket, {"id": 1, "type": "trace/contexts", "domain": "automation"}
            )
            if _command_outcome(response) == "unsupported":
                return AutomationTraceContextsPayload(supported=False, contexts={})
            result = response.get("result")
            if not isinstance(result, Mapping):
                raise HomeAssistantUnexpectedResponse(
                    "Home Assistant returned malformed automation trace contexts."
                )
            contexts = {
                str(context_id): {str(key): str(value) for key, value in data.items()}
                for context_id, data in result.items()
                if isinstance(context_id, str) and isinstance(data, Mapping)
            }
            if any(
                context.get("domain") != "automation"
                or not context.get("item_id")
                or not context.get("run_id")
                for context in contexts.values()
            ):
                raise HomeAssistantUnexpectedResponse(
                    "Home Assistant returned malformed automation trace context data."
                )
            return AutomationTraceContextsPayload(supported=True, contexts=contexts)

        return await self._run(operation, "automation trace context retrieval")

    async def _run(
        self,
        operation: Callable[[ClientConnection], Awaitable[T]],
        operation_name: str,
    ) -> T:
        """Open one authenticated socket for a bounded read-only operation."""
        try:
            async with asyncio.timeout(self._timeout):
                async with connect(
                    self._url,
                    open_timeout=self._timeout,
                    close_timeout=min(self._timeout, 5),
                    max_size=_MAX_MESSAGE_BYTES,
                    proxy=self._proxy,
                    logger=_TRANSPORT_LOGGER,
                ) as socket:
                    await self._authenticate(socket)
                    return await operation(socket)
        except TimeoutError as exc:
            raise HomeAssistantTimeoutError(
                f"Home Assistant WebSocket {operation_name} timed out."
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
                f"Home Assistant WebSocket {operation_name} could not be reached."
            ) from exc

    async def _command(
        self, socket: ClientConnection, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        await socket.send(json.dumps(payload))
        response = await _receive_object(socket)
        if response.get("id") != payload.get("id") or response.get("type") != "result":
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant returned an unexpected WebSocket command response."
            )
        return response

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


def _command_outcome(response: Mapping[str, Any]) -> str:
    if response.get("success") is True:
        return "success"
    error = response.get("error")
    code = error.get("code") if isinstance(error, Mapping) else None
    if code in _UNSUPPORTED_COMMAND_CODES:
        return "unsupported"
    if code in _NOT_FOUND_CODES:
        return "not_found"
    if code in _AUTHORIZATION_CODES:
        raise HomeAssistantAuthorizationError(
            "Home Assistant requires administrator permission for automation intelligence."
        )
    raise HomeAssistantUnexpectedResponse(
        "Home Assistant rejected a read-only automation intelligence request."
    )
