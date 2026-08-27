"""Domain-specific Phase 7 control services with strict input validation."""

from __future__ import annotations

from typing import Literal

from pydantic import ValidationError

from ambient_ha.models.control import (
    ControlAction,
    ControlDomain,
    ControlIntent,
    ControlResult,
)
from ambient_ha.policy.execution import ActionExecutor
from ambient_ha.policy.models import ControlValue


async def control_light(
    executor: ActionExecutor,
    *,
    entity_ids: list[str],
    action: Literal["on", "off"],
    brightness_percent: float | None = None,
    color_temperature_kelvin: int | None = None,
    rgb_color: list[int] | None = None,
) -> ControlResult:
    return await _execute(
        executor,
        mcp_tool="ha_control_light",
        domain=ControlDomain.LIGHT,
        action=ControlAction(action),
        entity_ids=entity_ids,
        value_data={
            "brightness_percent": brightness_percent,
            "color_temperature_kelvin": color_temperature_kelvin,
            "rgb_color": tuple(rgb_color) if rgb_color is not None else None,
        },
    )


async def control_fan(
    executor: ActionExecutor,
    *,
    entity_ids: list[str],
    action: Literal["on", "off"],
    percentage: float | None = None,
) -> ControlResult:
    return await _execute(
        executor,
        mcp_tool="ha_control_fan",
        domain=ControlDomain.FAN,
        action=ControlAction(action),
        entity_ids=entity_ids,
        value_data={"fan_percentage": percentage},
    )


async def control_media_player(
    executor: ActionExecutor,
    *,
    entity_ids: list[str],
    action: Literal["play", "pause", "stop", "volume", "mute", "unmute"],
    volume_level: float | None = None,
) -> ControlResult:
    internal_action = ControlAction.SET_VOLUME if action == "volume" else ControlAction(action)
    return await _execute(
        executor,
        mcp_tool="ha_control_media_player",
        domain=ControlDomain.MEDIA_PLAYER,
        action=internal_action,
        entity_ids=entity_ids,
        value_data={"volume_level": volume_level},
    )


async def control_climate(
    executor: ActionExecutor,
    *,
    entity_ids: list[str],
    target_temperature: float | None = None,
    temperature_unit: Literal["C", "F"] | None = None,
    hvac_mode: str | None = None,
) -> ControlResult:
    return await _execute(
        executor,
        mcp_tool="ha_control_climate",
        domain=ControlDomain.CLIMATE,
        action=ControlAction.SET_CLIMATE,
        entity_ids=entity_ids,
        value_data={
            "temperature": target_temperature,
            "temperature_unit": temperature_unit,
            "hvac_mode": hvac_mode,
        },
    )


async def control_switch(
    executor: ActionExecutor,
    *,
    entity_ids: list[str],
    action: Literal["on", "off"],
) -> ControlResult:
    return await _execute(
        executor,
        mcp_tool="ha_control_switch",
        domain=ControlDomain.SWITCH,
        action=ControlAction(action),
        entity_ids=entity_ids,
    )


async def activate_scene(executor: ActionExecutor, *, entity_ids: list[str]) -> ControlResult:
    return await _execute(
        executor,
        mcp_tool="ha_activate_scene",
        domain=ControlDomain.SCENE,
        action=ControlAction.ACTIVATE,
        entity_ids=entity_ids,
    )


async def run_script(executor: ActionExecutor, *, entity_ids: list[str]) -> ControlResult:
    return await _execute(
        executor,
        mcp_tool="ha_run_script",
        domain=ControlDomain.SCRIPT,
        action=ControlAction.RUN,
        entity_ids=entity_ids,
    )


async def _execute(
    executor: ActionExecutor,
    *,
    mcp_tool: str,
    domain: ControlDomain,
    action: ControlAction,
    entity_ids: list[str],
    value_data: dict[str, object] | None = None,
) -> ControlResult:
    try:
        supplied = {key: item for key, item in (value_data or {}).items() if item is not None}
        intent = ControlIntent(
            mcp_tool=mcp_tool,
            domain=domain,
            action=action,
            entity_ids=entity_ids,
            value=ControlValue.model_validate(supplied) if supplied else None,
        )
    except ValidationError:
        return executor.reject_invalid(
            mcp_tool=mcp_tool,
            domain=domain,
            action=action.value,
            entity_ids=entity_ids,
        )
    return await executor.execute(intent)
