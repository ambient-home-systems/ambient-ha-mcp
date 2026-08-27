"""Typed authorization, planning, and confirmation models.

Home Assistant labels and other natural-language content are deliberately absent
from these models.  Policy consumes canonical identifiers and typed values only.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ENTITY_ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
_CANONICAL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SERVICE_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def normalize_entity_id(value: str) -> str:
    """Normalize and strictly validate a canonical Home Assistant entity ID."""
    normalized = value.strip().casefold()
    if not _ENTITY_ID_PATTERN.fullmatch(normalized):
        raise ValueError("entity IDs must use canonical domain.object_id syntax")
    return normalized


def normalize_domain(value: str) -> str:
    """Normalize and validate a Home Assistant domain."""
    normalized = value.strip().casefold()
    if not _CANONICAL_ID_PATTERN.fullmatch(normalized):
        raise ValueError("domains must be canonical lowercase identifiers")
    return normalized


def normalize_registry_id(value: str) -> str:
    """Normalize a canonical area/floor registry ID without trusting a label."""
    normalized = value.strip().casefold()
    if not _CANONICAL_ID_PATTERN.fullmatch(normalized):
        raise ValueError("registry IDs must be canonical identifiers, not display names")
    return normalized


class PolicyAction(StrEnum):
    """Server-authoritative authorization outcomes."""

    ALLOW = "allow"
    DENY = "deny"
    CONFIRM_REQUIRED = "confirm_required"


class OperationClass(StrEnum):
    """Write sensitivity classes independent of Home Assistant privileges."""

    READ = "read"
    NORMAL_CONTROL = "normal_control"
    CLIMATE_CONTROL = "climate_control"
    SENSITIVE_CONTROL = "sensitive_control"
    SCENE_EXECUTION = "scene_execution"
    SCRIPT_EXECUTION = "script_execution"
    ADMINISTRATIVE = "administrative"


class ResolvedTarget(BaseModel):
    """A canonical target resolved before policy evaluation.

    Display names are intentionally not accepted.  The domain must agree with the
    canonical entity ID so a caller cannot authorize one domain and execute another.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    domain: str
    area_id: str | None = None
    floor_id: str | None = None
    capability_known: bool = True
    capability_supported: bool = True
    capability_reason: str | None = None

    @field_validator("entity_id")
    @classmethod
    def validate_entity_id(cls, value: str) -> str:
        return normalize_entity_id(value)

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        return normalize_domain(value)

    @field_validator("area_id", "floor_id")
    @classmethod
    def validate_registry_id(cls, value: str | None) -> str | None:
        return normalize_registry_id(value) if value is not None else None

    @model_validator(mode="after")
    def validate_domain_matches_entity(self) -> Self:
        entity_domain = self.entity_id.partition(".")[0]
        if entity_domain != self.domain:
            raise ValueError("target domain must match the canonical entity ID")
        return self


class ControlValue(BaseModel):
    """Typed semantic control values; invalid forms are rejected, never clamped."""

    model_config = ConfigDict(extra="forbid")

    temperature: float | None = None
    temperature_unit: str | None = None
    hvac_mode: str | None = None
    brightness_percent: float | None = Field(default=None, ge=0, le=100)
    color_temperature_kelvin: int | None = Field(default=None, gt=0)
    rgb_color: tuple[int, int, int] | None = None
    volume_level: float | None = Field(default=None, ge=0, le=1)
    fan_percentage: float | None = Field(default=None, ge=0, le=100)

    @field_validator("rgb_color")
    @classmethod
    def validate_rgb_color(cls, value: tuple[int, int, int] | None) -> tuple[int, int, int] | None:
        if value is not None and any(channel < 0 or channel > 255 for channel in value):
            raise ValueError("RGB channels must be integers from 0 through 255")
        return value

    @field_validator("temperature_unit")
    @classmethod
    def validate_temperature_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper().replace("°", "")
        if normalized not in {"C", "F"}:
            raise ValueError("temperature_unit must be C or F")
        return normalized

    @field_validator("hvac_mode")
    @classmethod
    def normalize_hvac_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if not _CANONICAL_ID_PATTERN.fullmatch(normalized):
            raise ValueError("hvac_mode must be a canonical identifier")
        return normalized

    @model_validator(mode="after")
    def require_temperature_unit(self) -> Self:
        if (self.temperature is None) != (self.temperature_unit is None):
            raise ValueError("temperature and temperature_unit must be supplied together")
        return self


class PolicyDecision(BaseModel):
    """A deterministic authorization result suitable for an audit record."""

    model_config = ConfigDict(extra="forbid")

    decision: PolicyAction
    operation_class: OperationClass
    reason: str
    matched_rule: str
    target: str | None = None
    confirmation_required: bool = False
    policy_metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """Compatibility/helper flag; confirmation is not authorization to execute."""
        return self.decision is PolicyAction.ALLOW


class ConfirmationRequirement(BaseModel):
    """Future server-verifiable confirmation state.

    Phase 6 intentionally accepts no caller-supplied ``confirmed`` boolean.  A
    later executor must validate a server-issued challenge before execution.
    """

    model_config = ConfigDict(extra="forbid")

    required: bool = True
    status: str = "required_unverified"
    verification_method: str = "server_verifiable_challenge"
    correlation_id: str
    scope: list[str] = Field(default_factory=list)
    expires_at: str | None = None


class ActionRequest(BaseModel):
    """Internal input produced only after semantic target resolution."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    mcp_tool: str = Field(min_length=1, max_length=128)
    operation_class: OperationClass
    action: str = Field(min_length=1, max_length=128)
    targets: list[ResolvedTarget] = Field(default_factory=list, max_length=1000)
    ambiguous_candidate_ids: list[str] = Field(default_factory=list, max_length=100)
    value: ControlValue | None = None
    operation_count: int = Field(default=1, ge=1, le=1000)
    predicted_service: str | None = None
    predicted_payload: dict[str, object] | None = None

    @field_validator("ambiguous_candidate_ids")
    @classmethod
    def normalize_candidates(cls, values: list[str]) -> list[str]:
        return [normalize_entity_id(value) for value in values]

    @field_validator("predicted_service")
    @classmethod
    def validate_predicted_service(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        if not _SERVICE_PATTERN.fullmatch(normalized):
            raise ValueError("predicted_service must use canonical domain.service syntax")
        return normalized


class MassActionResult(BaseModel):
    """Independent hard-limit result for a future multi-target action."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    target_count: int
    operation_count: int
    max_targets: int
    max_operations: int
    reason: str | None = None


class ActionPlan(BaseModel):
    """Bounded policy plan that only the central executor may consume."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    correlation_id: str
    mcp_tool: str
    operation_class: OperationClass
    action: str
    overall_decision: PolicyAction
    decisions: list[PolicyDecision] = Field(default_factory=list)
    allowed_targets: list[str] = Field(default_factory=list)
    denied_targets: list[str] = Field(default_factory=list)
    confirmation_targets: list[str] = Field(default_factory=list)
    clarification_required: bool = False
    ambiguous_candidate_ids: list[str] = Field(default_factory=list)
    mass_action: MassActionResult
    confirmation: ConfirmationRequirement | None = None
    predicted_service: str | None = None
    predicted_payload: dict[str, object] | None = None
    executable: bool = False
    execution_available: bool = False
    reason: str
