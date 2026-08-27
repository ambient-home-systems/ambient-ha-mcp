"""Pure capability, service-mapping, and verification logic for semantic controls."""

from __future__ import annotations

from collections.abc import Sequence

from ambient_ha.models.control import (
    ControlAction,
    ControlDomain,
    ControlIntent,
    ControlServiceCall,
)
from ambient_ha.models.discovery import EntityDetail
from ambient_ha.policy.models import OperationClass, ResolvedTarget

_FAN_SET_SPEED = 1
_MEDIA_PAUSE = 1
_MEDIA_VOLUME_SET = 4
_MEDIA_VOLUME_MUTE = 8
_MEDIA_STOP = 4096
_MEDIA_PLAY = 16384
_CLIMATE_TARGET_TEMPERATURE = 1


def operation_class_for(intent: ControlIntent) -> OperationClass:
    if intent.domain is ControlDomain.CLIMATE:
        return OperationClass.CLIMATE_CONTROL
    if intent.domain is ControlDomain.SWITCH:
        return OperationClass.SENSITIVE_CONTROL
    if intent.domain is ControlDomain.SCENE:
        return OperationClass.SCENE_EXECUTION
    if intent.domain is ControlDomain.SCRIPT:
        return OperationClass.SCRIPT_EXECUTION
    return OperationClass.NORMAL_CONTROL


def resolved_target_for(entity: EntityDetail, intent: ControlIntent) -> ResolvedTarget:
    known, supported, reason = _capability(entity, intent)
    return ResolvedTarget(
        entity_id=entity.entity_id,
        domain=entity.domain,
        area_id=entity.area_id,
        floor_id=entity.floor_id,
        capability_known=known,
        capability_supported=supported,
        capability_reason=reason,
    )


def service_call_for(intent: ControlIntent) -> ControlServiceCall:
    """Map only validated semantic operations to a fixed Home Assistant service."""
    service = service_name_for(intent)
    value = intent.value
    data: dict[str, object] = {}
    if intent.domain is ControlDomain.LIGHT:
        if value is not None:
            if value.brightness_percent is not None:
                data["brightness_pct"] = value.brightness_percent
            if value.color_temperature_kelvin is not None:
                data["color_temp_kelvin"] = value.color_temperature_kelvin
            if value.rgb_color is not None:
                data["rgb_color"] = list(value.rgb_color)
    elif intent.domain is ControlDomain.FAN:
        if value is not None and value.fan_percentage is not None:
            data["percentage"] = value.fan_percentage
    elif intent.domain is ControlDomain.MEDIA_PLAYER:
        if intent.action is ControlAction.SET_VOLUME and value is not None:
            data["volume_level"] = value.volume_level
        elif intent.action in {ControlAction.MUTE, ControlAction.UNMUTE}:
            data["is_volume_muted"] = intent.action is ControlAction.MUTE
    elif intent.domain is ControlDomain.CLIMATE:
        if value is not None:
            if value.temperature is not None:
                data["temperature"] = value.temperature
            if value.hvac_mode is not None:
                data["hvac_mode"] = value.hvac_mode
    return ControlServiceCall(
        domain=intent.domain,
        service=service,
        entity_ids=intent.entity_ids,
        data=data,
    )


def service_name_for(intent: ControlIntent) -> str:
    """Return the fixed service name without constructing a size-bounded call."""
    if intent.domain in {ControlDomain.LIGHT, ControlDomain.FAN, ControlDomain.SWITCH}:
        return "turn_on" if intent.action is ControlAction.ON else "turn_off"
    if intent.domain is ControlDomain.MEDIA_PLAYER:
        return {
            ControlAction.PLAY: "media_play",
            ControlAction.PAUSE: "media_pause",
            ControlAction.STOP: "media_stop",
            ControlAction.SET_VOLUME: "volume_set",
            ControlAction.MUTE: "volume_mute",
            ControlAction.UNMUTE: "volume_mute",
        }[intent.action]
    if intent.domain is ControlDomain.CLIMATE:
        return (
            "set_temperature"
            if intent.value is not None and intent.value.temperature is not None
            else "set_hvac_mode"
        )
    return "turn_on"


def state_matches_intent(entity: EntityDetail, intent: ControlIntent) -> bool | None:
    """Return True/False for verifiable actions and None for accepted-only actions."""
    action = intent.action
    attributes = entity.attributes
    if intent.domain in {ControlDomain.SCENE, ControlDomain.SCRIPT}:
        return None
    if intent.domain in {ControlDomain.LIGHT, ControlDomain.FAN, ControlDomain.SWITCH}:
        expected = "on" if action is ControlAction.ON else "off"
        if entity.state.casefold() != expected:
            return False
        value = intent.value
        if intent.domain is ControlDomain.LIGHT and value is not None:
            if value.brightness_percent is not None:
                brightness = _number(attributes.get("brightness"))
                expected_brightness = round(value.brightness_percent * 255 / 100)
                if brightness is None or abs(brightness - expected_brightness) > 2:
                    return False
            if value.color_temperature_kelvin is not None:
                color_temp = _number(attributes.get("color_temp_kelvin"))
                if color_temp is None or abs(color_temp - value.color_temperature_kelvin) > 25:
                    return False
            if (
                value.rgb_color is not None
                and _integer_triplet(attributes.get("rgb_color")) != value.rgb_color
            ):
                return False
        if intent.domain is ControlDomain.FAN and value and value.fan_percentage is not None:
            percentage = _number(attributes.get("percentage"))
            if percentage is None or abs(percentage - value.fan_percentage) > 1:
                return False
        return True
    if intent.domain is ControlDomain.MEDIA_PLAYER:
        if action is ControlAction.PLAY:
            return entity.state.casefold() == "playing"
        if action is ControlAction.PAUSE:
            return entity.state.casefold() == "paused"
        if action is ControlAction.STOP:
            return entity.state.casefold() in {"idle", "off", "standby"}
        if action is ControlAction.SET_VOLUME and intent.value is not None:
            volume = _number(attributes.get("volume_level"))
            return volume is not None and abs(volume - (intent.value.volume_level or 0)) <= 0.01
        muted = attributes.get("is_volume_muted")
        return isinstance(muted, bool) and muted is (action is ControlAction.MUTE)
    if intent.domain is ControlDomain.CLIMATE:
        value = intent.value
        if value is None:
            return False
        if value.temperature is not None:
            temperature = _number(attributes.get("temperature"))
            if temperature is None or abs(temperature - value.temperature) > 0.1:
                return False
        if value.hvac_mode is not None and entity.state.casefold() != value.hvac_mode:
            return False
        return True
    return False


def _capability(entity: EntityDetail, intent: ControlIntent) -> tuple[bool, bool, str | None]:
    if not entity.available:
        return True, False, "Home Assistant reports the target unavailable."
    attributes = entity.attributes
    value = intent.value
    simple_domains = {
        ControlDomain.LIGHT,
        ControlDomain.SWITCH,
        ControlDomain.SCENE,
        ControlDomain.SCRIPT,
    }
    if intent.domain in simple_domains:
        if intent.domain is ControlDomain.LIGHT and value is not None:
            modes = _string_set(attributes.get("supported_color_modes"))
            if value.brightness_percent is not None:
                if modes is None:
                    return False, False, "Light brightness capability is unknown."
                if modes <= {"onoff"}:
                    return True, False, "The light does not support brightness control."
            if value.color_temperature_kelvin is not None:
                if modes is None:
                    return False, False, "Light color-temperature capability is unknown."
                if "color_temp" not in modes:
                    return True, False, "The light does not support color temperature."
            if value.rgb_color is not None:
                if modes is None:
                    return False, False, "Light color capability is unknown."
                if not modes.intersection({"hs", "xy", "rgb", "rgbw", "rgbww"}):
                    return True, False, "The light does not support color control."
        return True, True, None
    features = _integer(attributes.get("supported_features"))
    if intent.domain is ControlDomain.FAN:
        if value is not None and value.fan_percentage is not None:
            if features is None:
                return False, False, "Fan percentage capability is unknown."
            if features & _FAN_SET_SPEED == 0:
                return True, False, "The fan does not support percentage control."
        return True, True, None
    if intent.domain is ControlDomain.MEDIA_PLAYER:
        if features is None:
            return False, False, "Media-player capability is unknown."
        required = {
            ControlAction.PLAY: _MEDIA_PLAY,
            ControlAction.PAUSE: _MEDIA_PAUSE,
            ControlAction.STOP: _MEDIA_STOP,
            ControlAction.SET_VOLUME: _MEDIA_VOLUME_SET,
            ControlAction.MUTE: _MEDIA_VOLUME_MUTE,
            ControlAction.UNMUTE: _MEDIA_VOLUME_MUTE,
        }[intent.action]
        if features & required == 0:
            return True, False, "The media player does not support the requested action."
        return True, True, None
    if intent.domain is ControlDomain.CLIMATE:
        if value is None:
            return True, False, "Climate values are missing."
        if value.temperature is not None:
            if features is None:
                return False, False, "Climate temperature capability is unknown."
            if features & _CLIMATE_TARGET_TEMPERATURE == 0:
                return True, False, "The climate entity does not support a target temperature."
            minimum = _number(attributes.get("min_temp"))
            maximum = _number(attributes.get("max_temp"))
            if minimum is None or maximum is None:
                return False, False, "Climate device temperature bounds are unknown."
            if not minimum <= value.temperature <= maximum:
                return (
                    True,
                    False,
                    "The target temperature is outside the device's supported range.",
                )
        if value.hvac_mode is not None:
            modes = _string_set(attributes.get("hvac_modes"))
            if modes is None:
                return False, False, "Supported HVAC modes are unknown."
            if value.hvac_mode not in modes:
                return True, False, "The climate entity does not support the requested HVAC mode."
        return True, True, None
    return True, False, "The control domain is unsupported."


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _string_set(value: object) -> set[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return {item.casefold() for item in value}


def _integer_triplet(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    if len(value) != 3 or not all(isinstance(item, int) for item in value):
        return None
    return int(value[0]), int(value[1]), int(value[2])
