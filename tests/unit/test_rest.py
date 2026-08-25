import ssl

import httpx
import pytest

from ambient_ha.ha.exceptions import (
    HomeAssistantAuthenticationError,
    HomeAssistantLogbookUnavailable,
    HomeAssistantRecorderUnavailable,
    HomeAssistantTimeoutError,
    HomeAssistantTLSFailure,
    HomeAssistantUnexpectedResponse,
    HomeAssistantUnreachableError,
)
from ambient_ha.ha.rest import HomeAssistantRestAPI


def make_api(transport: httpx.AsyncBaseTransport, token: str | None = None) -> HomeAssistantRestAPI:
    return HomeAssistantRestAPI(
        base_url="http://homeassistant.test:8123",
        token=token or "test-secret-token",
        timeout_seconds=1,
        transport=transport,
    )


@pytest.mark.anyio
async def test_successful_connection_uses_authenticated_safe_get() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/"
        assert request.headers["Authorization"] == "Bearer test-secret-token"
        return httpx.Response(200, json={"message": "API running."})

    await make_api(httpx.MockTransport(handler)).check_connection()


@pytest.mark.anyio
async def test_authentication_failure_is_normalized() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(401, json={"message": "no"}))

    with pytest.raises(HomeAssistantAuthenticationError, match="rejected"):
        await make_api(transport).check_connection()


@pytest.mark.anyio
async def test_timeout_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(HomeAssistantTimeoutError, match="timed out"):
        await make_api(httpx.MockTransport(handler)).check_connection()


@pytest.mark.anyio
async def test_unreachable_home_assistant_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(HomeAssistantUnreachableError, match="could not be reached"):
        await make_api(httpx.MockTransport(handler)).check_connection()


@pytest.mark.anyio
async def test_tls_failure_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        try:
            raise ssl.SSLError("certificate details must not leak")
        except ssl.SSLError as exc:
            raise httpx.ConnectError("TLS setup failed", request=request) from exc

    with pytest.raises(HomeAssistantTLSFailure, match="secure connection") as captured:
        await make_api(httpx.MockTransport(handler)).check_connection()

    assert "certificate details" not in str(captured.value)


@pytest.mark.anyio
async def test_unexpected_response_never_echoes_body_or_token() -> None:
    token = "highly-sensitive-token-value"
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(500, text=f"debug body contains {token}")
    )

    with pytest.raises(HomeAssistantUnexpectedResponse) as captured:
        await make_api(transport, token=token).get_config()

    assert token not in str(captured.value)
    assert "debug body" not in str(captured.value)


@pytest.mark.anyio
async def test_get_states_returns_only_object_rows() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=[{"entity_id": "light.kitchen", "state": "on"}, "invalid", 2],
            request=request,
        )
    )

    assert await make_api(transport).get_states() == [{"entity_id": "light.kitchen", "state": "on"}]


@pytest.mark.anyio
async def test_get_state_returns_none_for_normal_not_found() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/states/light.kitchen_ceiling"
        return httpx.Response(404, json={}, request=request)

    assert await make_api(httpx.MockTransport(handler)).get_state("light.kitchen_ceiling") is None


@pytest.mark.anyio
async def test_get_states_rejects_malformed_payload() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}, request=request))

    with pytest.raises(HomeAssistantUnexpectedResponse, match="state data"):
        await make_api(transport).get_states()


@pytest.mark.anyio
async def test_history_request_uses_only_read_only_bounded_query_parameters() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/history/period/2026-08-25T12:00:00+00:00"
        assert request.url.params["filter_entity_id"] == "light.kitchen,cover.garage"
        assert request.url.params["end_time"] == "2026-08-25T13:00:00+00:00"
        assert "minimal_response" in request.url.query.decode()
        return httpx.Response(200, json=[[]], request=request)

    assert await make_api(httpx.MockTransport(handler)).get_history(
        entity_ids=["light.kitchen", "cover.garage"],
        start="2026-08-25T12:00:00+00:00",
        end="2026-08-25T13:00:00+00:00",
        minimal_response=True,
    ) == [[]]


@pytest.mark.anyio
async def test_recorder_and_logbook_absence_are_normalized() -> None:
    recorder = httpx.MockTransport(lambda request: httpx.Response(404, json={}, request=request))
    logbook = httpx.MockTransport(lambda request: httpx.Response(503, json={}, request=request))

    with pytest.raises(HomeAssistantRecorderUnavailable, match="historical data"):
        await make_api(recorder).get_history(
            entity_ids=["light.kitchen"],
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T13:00:00+00:00",
            minimal_response=True,
        )
    with pytest.raises(HomeAssistantLogbookUnavailable, match="historical data"):
        await make_api(logbook).get_logbook(
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T13:00:00+00:00",
            entity_id=None,
        )


@pytest.mark.anyio
async def test_historical_reads_reuse_safe_authentication_and_timeout_handling() -> None:
    unauthorized = httpx.MockTransport(
        lambda request: httpx.Response(401, json={}, request=request)
    )

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(HomeAssistantAuthenticationError):
        await make_api(unauthorized).get_history(
            entity_ids=["light.kitchen"],
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T13:00:00+00:00",
            minimal_response=True,
        )
    with pytest.raises(HomeAssistantTimeoutError):
        await make_api(httpx.MockTransport(timeout)).get_logbook(
            start="2026-08-25T12:00:00+00:00",
            end="2026-08-25T13:00:00+00:00",
            entity_id=None,
        )
