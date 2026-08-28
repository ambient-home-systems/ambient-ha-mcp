"""Strict semantic-control models exposed by the Phase 7 tool surface."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ambient_ha.policy.models import ControlValue, normalize_entity_id


class ControlDomain(StrEnum):
    LIGHT = "light"
    FAN = "fan"
    MEDIA_PLAYER = "media_player"
    CLIMATE = "climate"
    SWITCH = "switch"
    SCENE = "scene"
    SCRIPT = "script"


class ControlAction(StrEnum):
    ON = "on"
    OFF = "off"
    PLAY = "play"
    PAUSE = "pause"
    STOP = "stop"
    SET_VOLUME = "set_volume"
    MUTE = "mute"
    UNMUTE = "unmute"
    SET_CLIMATE = "set_climate"
    ACTIVATE = "activate"
    RUN = "run"


class ControlStatus(StrEnum):
    VERIFIED = "verified"
    ACCEPTED = "accepted"
    PARTIALLY_VERIFIED = "partially_verified"
    FAILED = "failed"
    DENIED = "denied"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CLARIFICATION_REQUIRED = "clarification_required"
    READ_ONLY = "read_only"
    CONTROLS_DISABLED = "controls_disabled"
    UNSUPPORTED = "unsupported"


class ControlIntent(BaseModel):
    """Server-internal semantic intent built from one domain-specific MCP tool."""

    model_config = ConfigDict(extra="forbid")

    mcp_tool: str = Field(min_length=1, max_length=128)
    domain: ControlDomain
    action: ControlAction
    entity_ids: list[str] = Field(min_length=1, max_length=1000)
    value: ControlValue | None = None

    @field_validator("entity_ids")
    @classmethod
    def normalize_targets(cls, values: list[str]) -> list[str]:
        normalized = [normalize_entity_id(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("entity IDs must not be duplicated")
        return normalized

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        if any(entity_id.partition(".")[0] != self.domain.value for entity_id in self.entity_ids):
            raise ValueError("every target must belong to the semantic tool's domain")

        allowed_actions = {
            ControlDomain.LIGHT: {ControlAction.ON, ControlAction.OFF},
            ControlDomain.FAN: {ControlAction.ON, ControlAction.OFF},
            ControlDomain.MEDIA_PLAYER: {
                ControlAction.PLAY,
                ControlAction.PAUSE,
                ControlAction.STOP,
                ControlAction.SET_VOLUME,
                ControlAction.MUTE,
                ControlAction.UNMUTE,
            },
            ControlDomain.CLIMATE: {ControlAction.SET_CLIMATE},
            ControlDomain.SWITCH: {ControlAction.ON, ControlAction.OFF},
            ControlDomain.SCENE: {ControlAction.ACTIVATE},
            ControlDomain.SCRIPT: {ControlAction.RUN},
        }
        if self.action not in allowed_actions[self.domain]:
            raise ValueError("the requested action is not valid for this semantic tool")

        value = self.value or ControlValue()
        supplied = value.model_dump(exclude_none=True)
        if self.domain is ControlDomain.LIGHT:
            allowed = {"brightness_percent", "color_temperature_kelvin", "rgb_color"}
            if set(supplied) - allowed:
                raise ValueError("light controls contain values for another domain")
            if self.action is ControlAction.OFF and supplied:
                raise ValueError("light off does not accept brightness or color values")
        elif self.domain is ControlDomain.FAN:
            if set(supplied) - {"fan_percentage"}:
                raise ValueError("fan controls contain values for another domain")
            if self.action is ControlAction.OFF and supplied:
                raise ValueError("fan off does not accept a percentage")
        elif self.domain is ControlDomain.MEDIA_PLAYER:
            if set(supplied) - {"volume_level"}:
                raise ValueError("media-player controls contain values for another domain")
            if self.action is ControlAction.SET_VOLUME and value.volume_level is None:
                raise ValueError("set_volume requires volume_level")
            if self.action is not ControlAction.SET_VOLUME and supplied:
                raise ValueError("only set_volume accepts volume_level")
        elif self.domain is ControlDomain.CLIMATE:
            if set(supplied) - {"temperature", "temperature_unit", "hvac_mode"}:
                raise ValueError("climate controls contain values for another domain")
            if value.temperature is None and value.hvac_mode is None:
                raise ValueError("climate control requires a target temperature or HVAC mode")
        elif supplied:
            raise ValueError("this action does not accept control values")
        return self


class ControlServiceCall(BaseModel):
    """Bounded internal call generated from a validated semantic intent."""

    model_config = ConfigDict(extra="forbid")

    domain: ControlDomain
    service: str
    entity_ids: list[str] = Field(min_length=1, max_length=20)
    data: dict[str, object] = Field(default_factory=dict)

    @field_validator("entity_ids")
    @classmethod
    def validate_service_targets(cls, values: list[str]) -> list[str]:
        normalized = [normalize_entity_id(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("service targets must not be duplicated")
        return normalized

    @model_validator(mode="after")
    def enforce_fixed_service_surface(self) -> Self:
        allowed_services = {
            ControlDomain.LIGHT: {"turn_on", "turn_off"},
            ControlDomain.FAN: {"turn_on", "turn_off"},
            ControlDomain.MEDIA_PLAYER: {
                "media_play",
                "media_pause",
                "media_stop",
                "volume_set",
                "volume_mute",
            },
            ControlDomain.CLIMATE: {"set_temperature", "set_hvac_mode"},
            ControlDomain.SWITCH: {"turn_on", "turn_off"},
            ControlDomain.SCENE: {"turn_on"},
            ControlDomain.SCRIPT: {"turn_on"},
        }
        allowed_data = {
            ControlDomain.LIGHT: {
                "brightness_pct",
                "color_temp_kelvin",
                "rgb_color",
            },
            ControlDomain.FAN: {"percentage"},
            ControlDomain.MEDIA_PLAYER: {"volume_level", "is_volume_muted"},
            ControlDomain.CLIMATE: {"temperature", "hvac_mode"},
            ControlDomain.SWITCH: set(),
            ControlDomain.SCENE: set(),
            ControlDomain.SCRIPT: set(),
        }
        if self.service not in allowed_services[self.domain]:
            raise ValueError("service is outside the fixed semantic control surface")
        if set(self.data) - allowed_data[self.domain]:
            raise ValueError("service data is outside the fixed semantic control surface")
        if any(item.partition(".")[0] != self.domain.value for item in self.entity_ids):
            raise ValueError("service targets must match the fixed service domain")
        required_data = {
            (ControlDomain.MEDIA_PLAYER, "volume_set"): {"volume_level"},
            (ControlDomain.MEDIA_PLAYER, "volume_mute"): {"is_volume_muted"},
            (ControlDomain.CLIMATE, "set_hvac_mode"): {"hvac_mode"},
        }
        exact_keys = required_data.get((self.domain, self.service))
        if exact_keys is not None and set(self.data) != exact_keys:
            raise ValueError("service data does not match the fixed semantic service")
        if self.domain is ControlDomain.CLIMATE and self.service == "set_temperature":
            if "temperature" not in self.data:
                raise ValueError("set_temperature requires a target temperature")
        services_without_data = {
            (ControlDomain.LIGHT, "turn_off"),
            (ControlDomain.FAN, "turn_off"),
            (ControlDomain.MEDIA_PLAYER, "media_play"),
            (ControlDomain.MEDIA_PLAYER, "media_pause"),
            (ControlDomain.MEDIA_PLAYER, "media_stop"),
            (ControlDomain.SWITCH, "turn_on"),
            (ControlDomain.SWITCH, "turn_off"),
            (ControlDomain.SCENE, "turn_on"),
            (ControlDomain.SCRIPT, "turn_on"),
        }
        if (self.domain, self.service) in services_without_data and self.data:
            raise ValueError("this fixed semantic service does not accept data")
        return self


class ControlTargetResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    status: ControlStatus
    before_state: str | None = None
    after_state: str | None = None
    message: str


class ControlResult(BaseModel):
    """Stable, secret-free result returned by every semantic control tool."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    status: ControlStatus
    message: str
    request_id: str
    correlation_id: str
    action: str
    targets: list[ControlTargetResult] = Field(default_factory=list)
    policy_decision: str
    matched_rules: list[str] = Field(default_factory=list)
    confirmation_status: str | None = None
    error_code: str | None = None
