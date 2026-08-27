"""Strict, conservative policy configuration and optional TOML loading."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ambient_ha.policy.models import (
    OperationClass,
    PolicyAction,
    normalize_domain,
    normalize_entity_id,
)


def _default_operation_rules() -> dict[OperationClass, PolicyAction]:
    return {
        OperationClass.READ: PolicyAction.ALLOW,
        OperationClass.NORMAL_CONTROL: PolicyAction.DENY,
        OperationClass.CLIMATE_CONTROL: PolicyAction.DENY,
        OperationClass.SENSITIVE_CONTROL: PolicyAction.DENY,
        OperationClass.SCENE_EXECUTION: PolicyAction.CONFIRM_REQUIRED,
        OperationClass.SCRIPT_EXECUTION: PolicyAction.DENY,
        OperationClass.ADMINISTRATIVE: PolicyAction.DENY,
    }


def _default_domain_rules() -> dict[str, PolicyAction]:
    return {
        "light": PolicyAction.ALLOW,
        "fan": PolicyAction.ALLOW,
        "media_player": PolicyAction.ALLOW,
        "climate": PolicyAction.ALLOW,
        "switch": PolicyAction.DENY,
        "cover": PolicyAction.CONFIRM_REQUIRED,
        "lock": PolicyAction.DENY,
        "alarm_control_panel": PolicyAction.DENY,
        "valve": PolicyAction.DENY,
        "scene": PolicyAction.CONFIRM_REQUIRED,
        "script": PolicyAction.DENY,
        "automation": PolicyAction.DENY,
    }


class PolicyLimits(BaseModel):
    """Hard request-size limits enforced before per-target authorization."""

    model_config = ConfigDict(extra="forbid")

    max_entities_per_action: int = Field(default=20, ge=1, le=100)
    max_operations_per_request: int = Field(default=10, ge=1, le=100)


class ValueLimits(BaseModel):
    """Semantic-control bounds; out-of-range values are rejected."""

    model_config = ConfigDict(extra="forbid")

    climate_min_celsius: float = 7.0
    climate_max_celsius: float = 30.0
    climate_min_fahrenheit: float = 45.0
    climate_max_fahrenheit: float = 86.0
    allowed_hvac_modes: frozenset[str] = Field(
        default_factory=lambda: frozenset({"off", "heat", "cool", "auto", "dry", "fan_only"})
    )
    max_media_volume: float = Field(default=0.75, ge=0, le=1)
    min_brightness_percent: float = Field(default=0, ge=0, le=100)
    max_brightness_percent: float = Field(default=100, ge=0, le=100)
    min_color_temperature_kelvin: int = Field(default=1500, gt=0)
    max_color_temperature_kelvin: int = Field(default=10000, gt=0)
    min_fan_percentage: float = Field(default=0, ge=0, le=100)
    max_fan_percentage: float = Field(default=100, ge=0, le=100)

    @field_validator("allowed_hvac_modes", mode="before")
    @classmethod
    def normalize_modes(cls, value: object) -> frozenset[str]:
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("allowed_hvac_modes must be an array of canonical mode names")
        modes = frozenset(normalize_domain(str(item)) for item in value)
        if not modes:
            raise ValueError("allowed_hvac_modes must not be empty")
        return modes

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        pairs = (
            (self.climate_min_celsius, self.climate_max_celsius, "Celsius"),
            (self.climate_min_fahrenheit, self.climate_max_fahrenheit, "Fahrenheit"),
            (self.min_brightness_percent, self.max_brightness_percent, "brightness"),
            (
                self.min_color_temperature_kelvin,
                self.max_color_temperature_kelvin,
                "color temperature",
            ),
            (self.min_fan_percentage, self.max_fan_percentage, "fan percentage"),
        )
        for lower, upper, label in pairs:
            if lower > upper:
                raise ValueError(f"minimum {label} must not exceed maximum")
        return self


class PolicyConfig(BaseModel):
    """Validated server-side policy configuration.

    Area and floor policy are deliberately deferred.  Canonical location IDs are
    carried by planning models, but authorization is not based on display names.
    """

    model_config = ConfigDict(extra="forbid")

    read_only: bool = True
    global_default: PolicyAction = PolicyAction.DENY
    operation_rules: dict[OperationClass, PolicyAction] = Field(
        default_factory=_default_operation_rules
    )
    domain_rules: dict[str, PolicyAction] = Field(default_factory=_default_domain_rules)
    entity_rules: dict[str, PolicyAction] = Field(default_factory=dict)
    protected_entities: dict[str, PolicyAction] = Field(default_factory=dict)
    limits: PolicyLimits = Field(default_factory=PolicyLimits)
    values: ValueLimits = Field(default_factory=ValueLimits)

    @field_validator("domain_rules", mode="before")
    @classmethod
    def normalize_domain_rules(cls, value: object) -> dict[str, object]:
        return _normalize_rule_mapping(value, normalize_domain, "domain")

    @field_validator("entity_rules", "protected_entities", mode="before")
    @classmethod
    def normalize_entity_rules(cls, value: object) -> dict[str, object]:
        return _normalize_rule_mapping(value, normalize_entity_id, "entity")

    @model_validator(mode="after")
    def validate_protected_decisions(self) -> Self:
        invalid = {
            entity_id: decision
            for entity_id, decision in self.protected_entities.items()
            if decision not in {PolicyAction.DENY, PolicyAction.CONFIRM_REQUIRED}
        }
        if invalid:
            raise ValueError("protected entities may only deny or require confirmation")
        if self.operation_rules.get(OperationClass.READ) is not PolicyAction.ALLOW:
            raise ValueError("the READ operation rule must remain allow")
        return self


def load_policy_file(path: Path) -> PolicyConfig:
    """Load a strict TOML policy file; malformed or unknown configuration fails."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("policy configuration could not be read") from exc
    try:
        parsed = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("policy configuration is not valid TOML") from exc
    return PolicyConfig.model_validate(parsed)


def effective_policy_config(*, environment_read_only: bool, path: Path | None) -> PolicyConfig:
    """Combine environment and file boundaries using fail-safe read-only precedence.

    A policy file adds a second read-only boundary when present. Without one, the
    environment boundary is authoritative; the separate CONTROL_ENABLED gate is
    still required by the policy engine before any Phase 7 execution.
    """
    config = (
        load_policy_file(path)
        if path is not None
        else PolicyConfig(read_only=environment_read_only)
    )
    return config.model_copy(update={"read_only": environment_read_only or config.read_only})


def _normalize_rule_mapping(
    value: object,
    normalizer: Any,
    label: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} rules must be a mapping")
    normalized: dict[str, object] = {}
    for raw_key, decision in value.items():
        if not isinstance(raw_key, str):
            raise ValueError(f"{label} rule keys must be strings")
        key = normalizer(raw_key)
        if key in normalized:
            raise ValueError(f"duplicate normalized {label} rule: {key}")
        normalized[key] = decision
    return normalized
