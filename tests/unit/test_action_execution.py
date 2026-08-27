from __future__ import annotations

from copy import deepcopy

import pytest

from ambient_ha.ha.exceptions import HomeAssistantTimeoutError
from ambient_ha.models.control import (
    ControlAction,
    ControlDomain,
    ControlIntent,
    ControlServiceCall,
    ControlStatus,
)
from ambient_ha.models.discovery import EntityDetail
from ambient_ha.models.home_assistant import HomeAssistantServerInfo
from ambient_ha.policy import ActionPlanner, PolicyConfig, PolicyEngine
from ambient_ha.policy.audit import AuditEvent
from ambient_ha.policy.execution import ActionExecutor
from ambient_ha.policy.models import ControlValue


def entity(
    entity_id: str,
    state: str,
    *,
    attributes: dict[str, object] | None = None,
    available: bool = True,
) -> EntityDetail:
    return EntityDetail(
        entity_id=entity_id,
        domain=entity_id.partition(".")[0],
        state=state,
        available=available,
        attributes=attributes or {},
    )


class CapturingAuditSink:
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[AuditEvent] = []
        self.fail = fail

    def emit(self, event: AuditEvent) -> None:
        if self.fail:
            raise RuntimeError("audit unavailable")
        self.events.append(event)


class FakeControlGateway:
    def __init__(self) -> None:
        self.entities = {
            "light.kitchen": entity(
                "light.kitchen",
                "off",
                attributes={
                    "brightness": 0,
                    "supported_color_modes": ["brightness", "color_temp", "rgb"],
                },
            ),
            "light.onoff_only": entity(
                "light.onoff_only",
                "off",
                attributes={"supported_color_modes": ["onoff"]},
            ),
            "fan.bedroom": entity(
                "fan.bedroom",
                "off",
                attributes={"supported_features": 1, "percentage": 0},
            ),
            "media_player.den": entity(
                "media_player.den",
                "paused",
                attributes={"supported_features": 1 | 4 | 8 | 4096 | 16384},
            ),
            "climate.house": entity(
                "climate.house",
                "heat",
                attributes={
                    "supported_features": 1,
                    "min_temp": 45,
                    "max_temp": 86,
                    "temperature": 68,
                    "hvac_modes": ["off", "heat", "cool"],
                },
            ),
            "switch.safe_lamp": entity("switch.safe_lamp", "off"),
            "scene.reading": entity("scene.reading", "unknown"),
            "script.safe_chime": entity("script.safe_chime", "off"),
        }
        self.calls: list[ControlServiceCall] = []
        self.mutate_after_call = True
        self.fail_verification = False

    async def get_server_info(self) -> HomeAssistantServerInfo:
        return HomeAssistantServerInfo(unit_system={"temperature": "°F"})

    async def resolve_control_entities(
        self, entity_ids: list[str]
    ) -> tuple[list[EntityDetail], list[str]]:
        if self.calls and self.fail_verification:
            raise HomeAssistantTimeoutError("Home Assistant verification timed out.")
        return (
            [deepcopy(self.entities[item]) for item in entity_ids if item in self.entities],
            [item for item in entity_ids if item not in self.entities],
        )

    async def execute_control(self, call: ControlServiceCall) -> None:
        self.calls.append(call)
        if not self.mutate_after_call:
            return
        for entity_id in call.entity_ids:
            current = self.entities[entity_id]
            attributes = dict(current.attributes)
            state = current.state
            if call.domain in {ControlDomain.LIGHT, ControlDomain.FAN, ControlDomain.SWITCH}:
                state = "on" if call.service == "turn_on" else "off"
            if call.domain is ControlDomain.LIGHT:
                if "brightness_pct" in call.data:
                    attributes["brightness"] = round(float(call.data["brightness_pct"]) * 255 / 100)
                if "color_temp_kelvin" in call.data:
                    attributes["color_temp_kelvin"] = call.data["color_temp_kelvin"]
                if "rgb_color" in call.data:
                    attributes["rgb_color"] = call.data["rgb_color"]
            elif call.domain is ControlDomain.FAN and "percentage" in call.data:
                attributes["percentage"] = call.data["percentage"]
            elif call.domain is ControlDomain.MEDIA_PLAYER:
                state = {
                    "media_play": "playing",
                    "media_pause": "paused",
                    "media_stop": "idle",
                }.get(call.service, state)
                if "volume_level" in call.data:
                    attributes["volume_level"] = call.data["volume_level"]
                if "is_volume_muted" in call.data:
                    attributes["is_volume_muted"] = call.data["is_volume_muted"]
            elif call.domain is ControlDomain.CLIMATE:
                if "temperature" in call.data:
                    attributes["temperature"] = call.data["temperature"]
                if "hvac_mode" in call.data:
                    state = str(call.data["hvac_mode"])
            self.entities[entity_id] = current.model_copy(
                update={"state": state, "attributes": attributes}
            )


def intent(
    domain: ControlDomain,
    action: ControlAction,
    *entity_ids: str,
    value: ControlValue | None = None,
) -> ControlIntent:
    return ControlIntent(
        mcp_tool=f"ha_control_{domain.value}",
        domain=domain,
        action=action,
        entity_ids=list(entity_ids),
        value=value,
    )


def executor(
    gateway: FakeControlGateway,
    *,
    read_only: bool = False,
    control_enabled: bool = True,
    entity_rules: dict[str, str] | None = None,
    sink: CapturingAuditSink | None = None,
) -> tuple[ActionExecutor, CapturingAuditSink]:
    audit = sink or CapturingAuditSink()
    policy = PolicyEngine(
        PolicyConfig(read_only=read_only, entity_rules=entity_rules or {}),
        control_enabled=control_enabled,
    )
    return (
        ActionExecutor(
            gateway,
            ActionPlanner(policy, execution_available=True),
            audit_sink=audit,
            verification_timeout_seconds=0,
        ),
        audit,
    )


@pytest.mark.anyio
async def test_light_action_uses_fixed_service_mapping_verifies_and_audits() -> None:
    gateway = FakeControlGateway()
    runner, audit = executor(gateway)

    result = await runner.execute(
        intent(
            ControlDomain.LIGHT,
            ControlAction.ON,
            "light.kitchen",
            value=ControlValue(brightness_percent=50, rgb_color=(1, 2, 3)),
        )
    )

    assert result.status is ControlStatus.VERIFIED
    assert gateway.calls == [
        ControlServiceCall(
            domain="light",
            service="turn_on",
            entity_ids=["light.kitchen"],
            data={"brightness_pct": 50.0, "rgb_color": [1, 2, 3]},
        )
    ]
    assert [event.execution_result for event in audit.events] == [
        "authorized_pending_execution",
        "verified",
    ]
    assert result.request_id != result.correlation_id


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("read_only", "control_enabled", "expected"),
    [
        (True, True, ControlStatus.READ_ONLY),
        (False, False, ControlStatus.CONTROLS_DISABLED),
    ],
)
async def test_both_global_gates_are_required(
    read_only: bool,
    control_enabled: bool,
    expected: ControlStatus,
) -> None:
    gateway = FakeControlGateway()
    runner, audit = executor(
        gateway,
        read_only=read_only,
        control_enabled=control_enabled,
    )

    result = await runner.execute(intent(ControlDomain.LIGHT, ControlAction.ON, "light.kitchen"))

    assert result.status is expected
    assert gateway.calls == []
    assert len(audit.events) == 1


@pytest.mark.anyio
async def test_unknown_or_unsupported_capability_fails_before_write() -> None:
    gateway = FakeControlGateway()
    runner, _audit = executor(gateway)

    result = await runner.execute(
        intent(
            ControlDomain.LIGHT,
            ControlAction.ON,
            "light.onoff_only",
            value=ControlValue(brightness_percent=50),
        )
    )

    assert result.status is ControlStatus.UNSUPPORTED
    assert gateway.calls == []
    assert result.matched_rules == ["capability.unsupported"]


@pytest.mark.anyio
async def test_missing_and_mass_targets_never_partially_execute() -> None:
    gateway = FakeControlGateway()
    runner, _audit = executor(gateway)
    missing = await runner.execute(
        intent(
            ControlDomain.LIGHT,
            ControlAction.ON,
            "light.kitchen",
            "light.not_found",
        )
    )
    too_many_ids = [f"light.room_{index}" for index in range(21)]
    for entity_id in too_many_ids:
        gateway.entities[entity_id] = entity(entity_id, "off")
    mass = await runner.execute(intent(ControlDomain.LIGHT, ControlAction.ON, *too_many_ids))

    assert missing.status is ControlStatus.CLARIFICATION_REQUIRED
    assert mass.status is ControlStatus.DENIED
    assert gateway.calls == []


@pytest.mark.anyio
async def test_switch_scene_and_script_require_exact_policy_authorization() -> None:
    gateway = FakeControlGateway()
    default_runner, _audit = executor(gateway)

    switch_denied = await default_runner.execute(
        intent(ControlDomain.SWITCH, ControlAction.ON, "switch.safe_lamp")
    )
    scene_confirm = await default_runner.execute(
        intent(ControlDomain.SCENE, ControlAction.ACTIVATE, "scene.reading")
    )
    script_denied = await default_runner.execute(
        intent(ControlDomain.SCRIPT, ControlAction.RUN, "script.safe_chime")
    )

    assert switch_denied.status is ControlStatus.DENIED
    assert scene_confirm.status is ControlStatus.CONFIRMATION_REQUIRED
    assert scene_confirm.confirmation_status == "required_unverified"
    assert script_denied.status is ControlStatus.DENIED
    assert gateway.calls == []

    allowed_runner, _audit = executor(
        gateway,
        entity_rules={
            "switch.safe_lamp": "allow",
            "scene.reading": "allow",
            "script.safe_chime": "allow",
        },
    )
    assert (
        await allowed_runner.execute(
            intent(ControlDomain.SWITCH, ControlAction.ON, "switch.safe_lamp")
        )
    ).status is ControlStatus.VERIFIED
    assert (
        await allowed_runner.execute(
            intent(ControlDomain.SCENE, ControlAction.ACTIVATE, "scene.reading")
        )
    ).status is ControlStatus.CONFIRMATION_REQUIRED
    assert (
        await allowed_runner.execute(
            intent(ControlDomain.SCRIPT, ControlAction.RUN, "script.safe_chime")
        )
    ).status is ControlStatus.ACCEPTED


@pytest.mark.anyio
async def test_climate_temperature_is_converted_to_home_assistant_unit() -> None:
    gateway = FakeControlGateway()
    runner, _audit = executor(gateway)

    result = await runner.execute(
        intent(
            ControlDomain.CLIMATE,
            ControlAction.SET_CLIMATE,
            "climate.house",
            value=ControlValue(temperature=20, temperature_unit="C", hvac_mode="heat"),
        )
    )

    assert result.status is ControlStatus.VERIFIED
    assert gateway.calls[0].data == {"temperature": 68.0, "hvac_mode": "heat"}


@pytest.mark.anyio
async def test_service_acceptance_is_not_mislabeled_as_state_verification() -> None:
    gateway = FakeControlGateway()
    gateway.mutate_after_call = False
    runner, _audit = executor(gateway)

    result = await runner.execute(intent(ControlDomain.FAN, ControlAction.ON, "fan.bedroom"))

    assert result.status is ControlStatus.ACCEPTED
    assert result.targets[0].status is ControlStatus.ACCEPTED
    assert result.targets[0].after_state == "off"


@pytest.mark.anyio
async def test_verification_failure_preserves_service_acceptance() -> None:
    gateway = FakeControlGateway()
    gateway.fail_verification = True
    runner, audit = executor(gateway)

    result = await runner.execute(intent(ControlDomain.FAN, ControlAction.ON, "fan.bedroom"))

    assert result.ok is True
    assert result.status is ControlStatus.ACCEPTED
    assert result.error_code == "verification_timeout"
    assert len(gateway.calls) == 1
    assert audit.events[-1].execution_result == "accepted"
    assert audit.events[-1].metadata["verification_error_code"] == "timeout"


@pytest.mark.anyio
async def test_pre_execution_audit_failure_blocks_the_write() -> None:
    gateway = FakeControlGateway()
    runner, _audit = executor(gateway, sink=CapturingAuditSink(fail=True))

    result = await runner.execute(intent(ControlDomain.LIGHT, ControlAction.ON, "light.kitchen"))

    assert result.status is ControlStatus.FAILED
    assert gateway.calls == []
