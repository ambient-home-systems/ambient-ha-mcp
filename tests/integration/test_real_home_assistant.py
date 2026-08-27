import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from mcp import Client

from ambient_ha.config import Settings
from ambient_ha.ha.client import HomeAssistantClient
from ambient_ha.models.control import ControlAction, ControlDomain, ControlIntent, ControlStatus
from ambient_ha.models.discovery import EntitySearchFilters
from ambient_ha.models.history import RecentChangesFilters
from ambient_ha.models.home import (
    LocationFilters,
    LowBatteryFilters,
    OpeningFilters,
    UnavailableEntityFilters,
)
from ambient_ha.policy import ActionPlanner, PolicyConfig, PolicyEngine
from ambient_ha.policy.execution import ActionExecutor
from ambient_ha.server import build_mcp_server

EXPECTED_TOOLS = {
    "ha_connection_status",
    "ha_server_info",
    "ha_get_entity",
    "ha_search_entities",
    "ha_list_areas",
    "ha_get_area",
    "ha_list_floors",
    "ha_get_floor",
    "ha_domain_summary",
    "ha_get_entity_history",
    "ha_get_logbook",
    "ha_get_recent_changes",
    "ha_get_home_summary",
    "ha_find_unavailable_entities",
    "ha_find_low_batteries",
    "ha_get_openings",
    "ha_get_lights_on",
    "ha_diagnose_home",
    "ha_list_automations",
    "ha_get_automation",
    "ha_find_automations_for_entity",
    "ha_get_automation_traces",
    "ha_get_automation_trace",
    "ha_find_activity_cause",
    "ha_control_light",
    "ha_control_fan",
    "ha_control_media_player",
    "ha_control_climate",
    "ha_control_switch",
    "ha_activate_scene",
    "ha_run_script",
}
SENSITIVE_KEY_MARKERS = {
    "access_token",
    "authorization",
    "camera",
    "credential",
    "entity_picture",
    "gps",
    "latitude",
    "location",
    "longitude",
    "media_content",
    "password",
    "secret",
    "stream",
    "token",
    "url",
    "user_id",
}
USEFUL_ATTRIBUTE_KEYS = {
    "battery_level",
    "current_humidity",
    "current_temperature",
    "humidity",
    "power",
    "temperature",
    "unit_of_measurement",
}


def _assert_private_data_absent(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert not any(marker in str(key).casefold() for marker in SENSITIVE_KEY_MARKERS)
            _assert_private_data_absent(item)
    elif isinstance(value, list):
        for item in value:
            _assert_private_data_absent(item)
    elif isinstance(value, str):
        assert not value.casefold().startswith(("http://", "https://", "rtsp://"))


@pytest.mark.integration
@pytest.mark.anyio
async def test_real_home_assistant_connection() -> None:
    if os.environ.get("RUN_HA_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_HA_INTEGRATION_TESTS=1 to use a real Home Assistant instance")
    if not os.environ.get("HOME_ASSISTANT_URL") or not os.environ.get("HOME_ASSISTANT_TOKEN"):
        pytest.skip("Secure Home Assistant integration credentials are unavailable")

    settings = Settings().model_copy(  # type: ignore[call-arg]
        update={"read_only": True, "control_enabled": False}
    )
    client = HomeAssistantClient(settings)
    result = await client.check_connection()

    assert result.status == "connected", result.message

    assert client._registry_cache._value is None
    entities = await client.search_entities(EntitySearchFilters(limit=1))
    first_registry_snapshot = client._registry_cache._value
    assert first_registry_snapshot is not None
    areas_supported, areas = await client.list_areas()
    assert client._registry_cache._value is first_registry_snapshot
    floors_supported, floors = await client.list_floors()
    assert client._registry_cache._value is first_registry_snapshot
    await client.refresh_discovery_cache()
    assert client._registry_cache._value is None
    await client.search_entities(EntitySearchFilters(limit=1))
    assert client._registry_cache._value is not None
    assert client._registry_cache._value is not first_registry_snapshot

    assert entities.returned <= 1
    assert isinstance(areas_supported, bool)
    assert isinstance(floors_supported, bool)

    summary = await client.get_home_summary()
    unavailable = await client.find_unavailable_entities(UnavailableEntityFilters(limit=5))
    batteries = await client.find_low_batteries(
        LowBatteryFilters(threshold=settings.battery_warning_threshold, limit=5)
    )
    openings = await client.get_openings(OpeningFilters(limit=5))
    lights = await client.get_lights_on(LocationFilters(limit=5))
    diagnostics = await client.diagnose_home(limit=5)
    automations = await client.list_automations(query=None, enabled=None, limit=5)

    assert summary.total_entities >= summary.unavailable_entities
    assert unavailable.returned <= 5
    assert batteries.returned <= 5
    assert openings.returned <= 5
    assert lights.returned <= 5
    assert diagnostics.returned <= 5
    assert automations.returned <= 5

    raw_states = await client._rest.get_states()
    assert raw_states
    rich_state = max(
        raw_states,
        key=lambda state: (
            len(state.get("attributes", {})) if isinstance(state.get("attributes"), dict) else 0
        ),
    )
    rich_entity_id = rich_state.get("entity_id")
    assert isinstance(rich_entity_id, str)
    rich_entity = await client.get_entity(rich_entity_id)
    assert rich_entity is not None
    _assert_private_data_absent(rich_entity.model_dump(mode="json"))

    useful_state = next(
        (
            state
            for state in raw_states
            if isinstance(state.get("attributes"), dict)
            and USEFUL_ATTRIBUTE_KEYS.intersection(state["attributes"])
        ),
        None,
    )
    if useful_state is not None:
        useful_entity_id = useful_state.get("entity_id")
        assert isinstance(useful_entity_id, str)
        useful_entity = await client.get_entity(useful_entity_id)
        assert useful_entity is not None
        raw_attributes = useful_state["attributes"]
        expected_useful = USEFUL_ATTRIBUTE_KEYS.intersection(raw_attributes)
        assert expected_useful <= useful_entity.attributes.keys()

    if entities.entities:
        entity_id = entities.entities[0].entity_id
        start = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        found, history = await client.get_entity_history(
            entity_id, start=start, end=None, limit=5, minimal_response=True
        )
        logbook = await client.get_logbook(start=start, end=None, entity_id=entity_id, limit=5)
        changes = await client.get_recent_changes(
            RecentChangesFilters(entity_id=entity_id, duration_minutes=60, limit=5)
        )

        assert found is True
        assert history.returned <= 5
        assert logbook.returned <= 5
        assert changes.returned <= 5

        entity_found, references = await client.find_automations_for_entity(entity_id, limit=5)
        cause_found, causes = await client.find_activity_cause(
            entity_id,
            timestamp=None,
            start=start,
            end=None,
            window_seconds=60,
            limit=5,
        )

        assert entity_found is True
        assert references.returned <= 5
        assert cause_found is True
        assert causes.returned <= 5

    if automations.automations:
        automation_id = automations.automations[0].entity_id
        _supported, found, definition = await client.get_automation(automation_id)
        trace_entity_found, traces = await client.get_automation_traces(automation_id, limit=5)

        assert found is True
        assert definition is not None
        assert trace_entity_found is True
        assert traces.returned <= 5

        if traces.traces:
            supported, trace_found, trace = await client.get_automation_trace(
                automation_id, traces.traces[0].run_id
            )
            assert isinstance(supported, bool)
            if supported:
                assert trace_found is True
                assert trace is not None

    assert entities.entities
    entity_id = entities.entities[0].entity_id
    domain = entities.entities[0].domain
    start = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    automation_id = (
        automations.automations[0].entity_id
        if automations.automations
        else "automation.ambient_validation_missing"
    )
    trace_run_id = "ambient-validation-missing"
    if automations.automations:
        _trace_found, trace_page = await client.get_automation_traces(automation_id, limit=1)
        if trace_page.traces:
            trace_run_id = trace_page.traces[0].run_id

    server = build_mcp_server(settings, client=client)
    async with Client(server) as mcp_client:
        listed = await mcp_client.list_tools()
        assert {tool.name for tool in listed.tools} == EXPECTED_TOOLS

        tool_calls: list[tuple[str, dict[str, object]]] = [
            ("ha_connection_status", {}),
            ("ha_server_info", {}),
            ("ha_get_entity", {"entity_id": entity_id}),
            ("ha_search_entities", {"query": entity_id, "limit": 5}),
            ("ha_list_areas", {}),
            (
                "ha_get_area",
                {"area": areas[0].area_id if areas else "ambient_validation_missing"},
            ),
            ("ha_list_floors", {}),
            (
                "ha_get_floor",
                {"floor": floors[0].floor_id if floors else "ambient_validation_missing"},
            ),
            ("ha_domain_summary", {"domain": domain}),
            ("ha_get_entity_history", {"entity_id": entity_id, "start": start, "limit": 5}),
            ("ha_get_logbook", {"entity_id": entity_id, "start": start, "limit": 5}),
            ("ha_get_recent_changes", {"entity_id": entity_id, "duration_minutes": 60}),
            ("ha_get_home_summary", {}),
            ("ha_find_unavailable_entities", {"limit": 5}),
            ("ha_find_low_batteries", {"limit": 5}),
            ("ha_get_openings", {"state": "any", "limit": 5}),
            ("ha_get_lights_on", {"limit": 5}),
            ("ha_diagnose_home", {"limit": 5}),
            ("ha_list_automations", {"limit": 5}),
            ("ha_get_automation", {"automation": automation_id}),
            ("ha_find_automations_for_entity", {"entity_id": entity_id, "limit": 5}),
            ("ha_get_automation_traces", {"automation": automation_id, "limit": 5}),
            (
                "ha_get_automation_trace",
                {"automation": automation_id, "run_id": trace_run_id},
            ),
            (
                "ha_find_activity_cause",
                {"entity_id": entity_id, "start": start, "limit": 5},
            ),
            (
                "ha_control_light",
                {"entity_ids": ["light.ambient_validation_missing"], "action": "off"},
            ),
            (
                "ha_control_fan",
                {"entity_ids": ["fan.ambient_validation_missing"], "action": "off"},
            ),
            (
                "ha_control_media_player",
                {"entity_ids": ["media_player.ambient_validation_missing"], "action": "pause"},
            ),
            (
                "ha_control_climate",
                {"entity_ids": ["climate.ambient_validation_missing"], "hvac_mode": "off"},
            ),
            (
                "ha_control_switch",
                {"entity_ids": ["switch.ambient_validation_missing"], "action": "off"},
            ),
            ("ha_activate_scene", {"entity_ids": ["scene.ambient_validation_missing"]}),
            ("ha_run_script", {"entity_ids": ["script.ambient_validation_missing"]}),
        ]
        for tool_name, arguments in tool_calls:
            tool_result = await mcp_client.call_tool(tool_name, arguments)
            assert not tool_result.is_error, tool_name
            _assert_private_data_absent(tool_result.structured_content)


@pytest.mark.integration
@pytest.mark.anyio
async def test_explicit_safe_light_write_and_restore() -> None:
    """Opt-in only: toggle one operator-designated light and restore its state."""
    if os.environ.get("RUN_HA_WRITE_TESTS") != "1":
        pytest.skip("Set RUN_HA_WRITE_TESTS=1 for the explicit safe-light write test")
    entity_id = os.environ.get("AMBIENT_HA_TEST_LIGHT_ENTITY", "").strip().casefold()
    if not entity_id.startswith("light.") or len(entity_id.partition(".")[2]) == 0:
        pytest.skip("Set AMBIENT_HA_TEST_LIGHT_ENTITY to one explicit harmless light ID")
    if not os.environ.get("HOME_ASSISTANT_URL") or not os.environ.get("HOME_ASSISTANT_TOKEN"):
        pytest.skip("Secure Home Assistant integration credentials are unavailable")

    settings = Settings().model_copy(  # type: ignore[call-arg]
        update={"read_only": False, "control_enabled": True}
    )
    client = HomeAssistantClient(settings)
    original = await client.get_entity(entity_id)
    assert original is not None, "The explicitly designated light does not exist"
    assert original.domain == "light"
    assert original.available is True
    assert original.state in {"on", "off"}, "The designated light must have a stable on/off state"

    runner = ActionExecutor(
        client,
        ActionPlanner(
            PolicyEngine(PolicyConfig(read_only=False), control_enabled=True),
            execution_available=True,
        ),
    )
    test_action = ControlAction.OFF if original.state == "on" else ControlAction.ON
    restore_action = ControlAction.ON if original.state == "on" else ControlAction.OFF

    try:
        changed = await runner.execute(
            ControlIntent(
                mcp_tool="integration_explicit_safe_light",
                domain=ControlDomain.LIGHT,
                action=test_action,
                entity_ids=[entity_id],
            )
        )
        assert changed.status is ControlStatus.VERIFIED
    finally:
        restored = await runner.execute(
            ControlIntent(
                mcp_tool="integration_explicit_safe_light_restore",
                domain=ControlDomain.LIGHT,
                action=restore_action,
                entity_ids=[entity_id],
            )
        )
        assert restored.status is ControlStatus.VERIFIED
        final = await client.get_entity(entity_id)
        assert final is not None
        assert final.state == original.state
