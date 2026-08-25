from __future__ import annotations

from typing import Any

import httpx
import pytest

from ambient_ha.config import Settings
from ambient_ha.ha.client import HomeAssistantClient
from ambient_ha.ha.websocket import (
    AutomationConfigBatch,
    AutomationTraceContextsPayload,
    AutomationTraceListPayload,
    AutomationTracePayload,
    RegistrySnapshot,
)
from tests.fixtures.automation import (
    AUTOMATION_CONFIGS,
    AUTOMATION_REGISTRY_ENTITIES,
    AUTOMATION_STATES,
    FAILED_TRACE,
    FULL_TRACE,
    TARGET_STATE,
    TRACE_SUMMARY,
)


class FakeRegistryProvider:
    async def get_registries(self) -> RegistrySnapshot:
        return RegistrySnapshot(entities=AUTOMATION_REGISTRY_ENTITIES)


class FakeAutomationProvider:
    def __init__(
        self,
        *,
        configs: dict[str, dict[str, Any]] | None = None,
        traces: list[dict[str, Any]] | None = None,
        full_traces: dict[str, dict[str, Any]] | None = None,
        contexts: dict[str, dict[str, str]] | None = None,
        supported: bool = True,
    ) -> None:
        self.configs = AUTOMATION_CONFIGS if configs is None else configs
        self.traces = [] if traces is None else traces
        self.full_traces = {} if full_traces is None else full_traces
        self.contexts = {} if contexts is None else contexts
        self.supported = supported
        self.config_calls = 0

    async def get_automation_configs(self, entity_ids: list[str]) -> AutomationConfigBatch:
        self.config_calls += 1
        return AutomationConfigBatch(
            supported=self.supported,
            configurations={key: self.configs[key] for key in entity_ids if key in self.configs},
            missing=frozenset(key for key in entity_ids if key not in self.configs),
        )

    async def list_automation_traces(self, item_id: str | None) -> AutomationTraceListPayload:
        traces = self.traces
        if item_id is not None:
            traces = [trace for trace in traces if trace.get("item_id") == item_id]
        return AutomationTraceListPayload(supported=self.supported, traces=tuple(traces))

    async def get_automation_trace(self, item_id: str, run_id: str) -> AutomationTracePayload:
        trace = self.full_traces.get(run_id)
        return AutomationTracePayload(
            supported=self.supported,
            found=trace is not None,
            trace=trace,
        )

    async def get_automation_trace_contexts(self) -> AutomationTraceContextsPayload:
        return AutomationTraceContextsPayload(supported=self.supported, contexts=self.contexts)


def _history(context: dict[str, Any]) -> list[list[dict[str, Any]]]:
    return [
        [
            {
                "entity_id": "light.kitchen",
                "state": "off",
                "last_changed": "2024-08-25T02:10:00+00:00",
                "attributes": {},
                "context": {"id": "ctx-old", "parent_id": None, "user_id": None},
            },
            {
                "entity_id": "light.kitchen",
                "state": "on",
                "last_changed": "2024-08-25T02:14:02+00:00",
                "attributes": {},
                "context": context,
            },
        ]
    ]


def _transport(history: list[list[dict[str, Any]]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/states":
            return httpx.Response(200, json=[*AUTOMATION_STATES, TARGET_STATE], request=request)
        if request.url.path in {
            "/api/states/light.kitchen",
            "/api/states/automation.motion_light",
        }:
            payload = (
                TARGET_STATE if request.url.path.endswith("light.kitchen") else AUTOMATION_STATES[0]
            )
            return httpx.Response(200, json=payload, request=request)
        if request.url.path.startswith("/api/history/period/"):
            return httpx.Response(200, json=history, request=request)
        raise AssertionError(f"unexpected path: {request.url.path}")

    return httpx.MockTransport(handler)


def _client(
    settings: Settings,
    provider: FakeAutomationProvider,
    *,
    context: dict[str, Any] | None = None,
) -> HomeAssistantClient:
    return HomeAssistantClient(
        settings,
        transport=_transport(
            _history(context or {"id": "ctx-state", "parent_id": None, "user_id": None})
        ),
        registry_provider=FakeRegistryProvider(),
        automation_provider=provider,
    )


@pytest.mark.anyio
async def test_reference_index_is_cached_and_manually_refreshable(settings: Settings) -> None:
    provider = FakeAutomationProvider()
    client = _client(settings, provider)

    first_found, first = await client.find_automations_for_entity("light.kitchen", limit=10)
    second_found, second = await client.find_automations_for_entity("light.kitchen", limit=10)
    await client.refresh_automation_cache()
    await client.find_automations_for_entity("light.kitchen", limit=10)

    assert first_found is second_found is True
    assert first.total_matches == second.total_matches
    assert provider.config_calls == 2


@pytest.mark.anyio
async def test_client_gets_configuration_and_trace_without_writes(settings: Settings) -> None:
    provider = FakeAutomationProvider(traces=[TRACE_SUMMARY], full_traces={"run-1": FULL_TRACE})
    client = _client(settings, provider)

    supported, found, automation = await client.get_automation("automation.motion_light")
    trace_found, traces = await client.get_automation_traces("automation.motion_light", limit=5)
    trace_supported, run_found, trace = await client.get_automation_trace(
        "automation.motion_light", "run-1"
    )

    assert supported is found is True
    assert automation is not None and automation.mode == "restart"
    assert trace_found is True and traces.total_traces == 1
    assert trace_supported is run_found is True
    assert trace is not None and trace.steps[-1].kind == "parallel"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("context", "provider", "expected"),
    [
        (
            {"id": "ctx-automation", "parent_id": None, "user_id": None},
            FakeAutomationProvider(
                contexts={
                    "ctx-automation": {
                        "domain": "automation",
                        "item_id": "motion_light",
                        "run_id": "run-1",
                    }
                }
            ),
            "confirmed_by_context",
        ),
        (
            {"id": "ctx-child", "parent_id": "ctx-automation", "user_id": None},
            FakeAutomationProvider(
                contexts={
                    "ctx-automation": {
                        "domain": "automation",
                        "item_id": "motion_light",
                        "run_id": "run-1",
                    }
                }
            ),
            "confirmed_by_context",
        ),
        (
            {"id": "ctx-state", "parent_id": None, "user_id": None},
            FakeAutomationProvider(traces=[TRACE_SUMMARY], full_traces={"run-1": FULL_TRACE}),
            "trace_confirmed",
        ),
        (
            {"id": "ctx-state", "parent_id": None, "user_id": None},
            FakeAutomationProvider(
                traces=[{**TRACE_SUMMARY, "run_id": "run-failed"}],
                full_traces={"run-failed": FAILED_TRACE},
            ),
            "strong_temporal_match",
        ),
        (
            {"id": "ctx-state", "parent_id": None, "user_id": None},
            FakeAutomationProvider(),
            "possible_reference",
        ),
        (
            {"id": "ctx-user", "parent_id": None, "user_id": "private-user-id"},
            FakeAutomationProvider(),
            "user_origin",
        ),
        (
            {"id": "ctx-state", "parent_id": None, "user_id": None},
            FakeAutomationProvider(configs={}),
            "unrelated_or_unknown",
        ),
    ],
)
async def test_causality_evidence_categories_do_not_overclaim(
    settings: Settings,
    context: dict[str, Any],
    provider: FakeAutomationProvider,
    expected: str,
) -> None:
    found, report = await _client(settings, provider, context=context).find_activity_cause(
        "light.kitchen",
        timestamp="2024-08-25T02:14:02Z",
        start=None,
        end=None,
        window_seconds=60,
        limit=10,
    )

    assert found is True
    assert report.state_changes_found == 1
    assert report.evidence[0].relationship == expected
    serialized = report.model_dump_json()
    assert "private-user-id" not in serialized
    if expected == "strong_temporal_match":
        assert report.evidence[0].confidence == "strong"
        assert "No direct" in report.evidence[0].supporting_facts[-1]
    if expected == "possible_reference":
        assert report.evidence[0].confidence == "possible"


@pytest.mark.anyio
async def test_unsupported_trace_api_degrades_feature_locally(settings: Settings) -> None:
    provider = FakeAutomationProvider(supported=False)
    client = _client(settings, provider)

    found, traces = await client.get_automation_traces("automation.motion_light", limit=5)
    cause_found, cause = await client.find_activity_cause(
        "light.kitchen",
        timestamp="2024-08-25T02:14:02Z",
        start=None,
        end=None,
        window_seconds=30,
        limit=5,
    )

    assert found is True and traces.supported is False
    assert cause_found is True
    assert cause.complete is False
    assert "trace interface is unavailable" in " ".join(cause.limitations)
