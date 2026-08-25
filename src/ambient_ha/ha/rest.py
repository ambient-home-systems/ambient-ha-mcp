"""Small async wrapper around the read-only Home Assistant REST endpoints."""

from __future__ import annotations

import ssl
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantError,
    HomeAssistantInvalidURL,
    HomeAssistantLogbookUnavailable,
    HomeAssistantRecorderUnavailable,
    HomeAssistantTimeoutError,
    HomeAssistantTLSFailure,
    HomeAssistantUnexpectedResponse,
    HomeAssistantUnreachableError,
)


class HomeAssistantRestAPI:
    """Read-only REST access used behind :class:`HomeAssistantClient`."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._timeout = timeout_seconds
        self._transport = transport

    async def check_connection(self) -> None:
        """Prove that Home Assistant is reachable and the token is accepted."""
        payload = await self._get_json("/api/")
        if payload.get("message") != "API running.":
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant responded, but the API readiness payload was unexpected."
            )

    async def get_config(self) -> Mapping[str, Any]:
        """Get Home Assistant configuration for immediate normalization."""
        return await self._get_json("/api/config")

    async def get_states(self) -> list[Mapping[str, Any]]:
        """Return a fresh current-state snapshot without caching dynamic data."""
        payload = await self._request_json("/api/states")
        if not isinstance(payload, list):
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant returned state data in an unexpected shape."
            )
        return [item for item in payload if isinstance(item, dict)]

    async def get_state(self, entity_id: str) -> Mapping[str, Any] | None:
        """Return one fresh state, or ``None`` for a normal not-found response."""
        safe_entity_id = quote(entity_id, safe="._")
        payload = await self._request_json(f"/api/states/{safe_entity_id}", allow_not_found=True)
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant returned entity state data in an unexpected shape."
            )
        return payload

    async def get_history(
        self,
        *,
        entity_ids: list[str],
        start: str,
        end: str,
        minimal_response: bool,
    ) -> list[Any]:
        """Read one bounded recorder history window through the official REST API."""
        query = urlencode({"filter_entity_id": ",".join(entity_ids), "end_time": end})
        if minimal_response:
            query = f"{query}&minimal_response"
        payload = await self._request_json(
            f"/api/history/period/{quote(start, safe='')}?{query}",
            unavailable_error=HomeAssistantRecorderUnavailable,
        )
        if not isinstance(payload, list):
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant returned historical state data in an unexpected shape."
            )
        return payload

    async def get_logbook(self, *, start: str, end: str, entity_id: str | None) -> list[Any]:
        """Read one bounded logbook window through the official REST API."""
        query_values = {"end_time": end}
        if entity_id is not None:
            query_values["entity"] = entity_id
        payload = await self._request_json(
            f"/api/logbook/{quote(start, safe='')}?{urlencode(query_values)}",
            unavailable_error=HomeAssistantLogbookUnavailable,
        )
        if not isinstance(payload, list):
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant returned logbook data in an unexpected shape."
            )
        return payload

    async def _get_json(self, path: str) -> Mapping[str, Any]:
        payload = await self._request_json(path)
        if not isinstance(payload, dict):
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant returned JSON in an unexpected shape."
            )
        return payload

    async def _request_json(
        self,
        path: str,
        *,
        allow_not_found: bool = False,
        unavailable_error: type[HomeAssistantError] | None = None,
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(self._timeout),
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.get(path)
        except httpx.InvalidURL as exc:
            raise HomeAssistantInvalidURL("The configured Home Assistant URL is invalid.") from exc
        except httpx.TimeoutException as exc:
            raise HomeAssistantTimeoutError(
                "Home Assistant did not respond before the request timed out."
            ) from exc
        except httpx.ConnectError as exc:
            if _contains_ssl_error(exc):
                raise HomeAssistantTLSFailure(
                    "A secure connection to Home Assistant could not be established."
                ) from exc
            raise HomeAssistantUnreachableError(
                "Home Assistant could not be reached at the configured URL."
            ) from exc
        except httpx.HTTPError as exc:
            raise HomeAssistantUnreachableError(
                "The Home Assistant request failed before a valid response was received."
            ) from exc

        if response.status_code in {401, 403}:
            raise HomeAssistantAuthenticationError(
                "Home Assistant rejected the configured access token."
            )
        if response.status_code == 404 and allow_not_found:
            return None
        if unavailable_error is not None and response.status_code in {404, 500, 503}:
            raise unavailable_error(
                "Home Assistant historical data is not available on this installation."
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise HomeAssistantUnexpectedResponse(
                f"Home Assistant returned unexpected HTTP status {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise HomeAssistantUnexpectedResponse(
                "Home Assistant returned a response that was not valid JSON."
            ) from exc
        return payload


def _contains_ssl_error(exc: BaseException) -> bool:
    """Walk an exception chain without echoing its potentially sensitive text."""
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ssl.SSLError):
            return True
        current = current.__cause__ or current.__context__
    return False
