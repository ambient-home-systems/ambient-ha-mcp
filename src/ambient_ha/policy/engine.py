"""Fail-closed, server-side authorization policy engine."""

from __future__ import annotations

from ambient_ha.policy.config import PolicyConfig
from ambient_ha.policy.models import (
    ControlValue,
    OperationClass,
    PolicyAction,
    PolicyDecision,
    ResolvedTarget,
)


class PolicyEngine:
    """Evaluate canonical targets independently of the MCP client and HA token."""

    def __init__(
        self,
        config: PolicyConfig | None = None,
        *,
        control_enabled: bool = False,
    ) -> None:
        self.config = config or PolicyConfig()
        self.control_enabled = control_enabled

    def evaluate(
        self,
        operation: OperationClass | object,
        *,
        target: ResolvedTarget | None = None,
        value: ControlValue | None = None,
    ) -> PolicyDecision:
        """Return a decision without ever treating an evaluation failure as allow."""
        if not isinstance(operation, OperationClass):
            return PolicyDecision(
                decision=PolicyAction.DENY,
                operation_class=OperationClass.ADMINISTRATIVE,
                reason="Unknown operation classes are denied.",
                matched_rule="fail_closed.unknown_operation",
            )
        try:
            return self._evaluate(operation, target=target, value=value)
        except Exception:
            return PolicyDecision(
                decision=PolicyAction.DENY,
                operation_class=operation,
                target=target.entity_id if target is not None else None,
                reason="Policy evaluation failed closed.",
                matched_rule="fail_closed.policy_exception",
            )

    def _evaluate(
        self,
        operation: OperationClass,
        *,
        target: ResolvedTarget | None,
        value: ControlValue | None,
    ) -> PolicyDecision:
        if self.config.read_only and operation is not OperationClass.READ:
            return self._decision(
                PolicyAction.DENY,
                operation,
                target,
                "Hard read-only mode denies every non-read operation.",
                "hard_boundary.read_only",
            )
        if not self.control_enabled and operation is not OperationClass.READ:
            return self._decision(
                PolicyAction.DENY,
                operation,
                target,
                "Home Assistant controls are disabled by the server-wide control gate.",
                "hard_boundary.controls_disabled",
            )
        if operation is OperationClass.ADMINISTRATIVE:
            return self._decision(
                PolicyAction.DENY,
                operation,
                target,
                "Home Assistant administrative operations are prohibited.",
                "hard_boundary.administrative",
            )
        if operation is OperationClass.READ:
            return self._decision(
                PolicyAction.ALLOW,
                operation,
                target,
                "Read operations are allowed.",
                "operation.read",
            )
        if target is None:
            return self._decision(
                PolicyAction.DENY,
                operation,
                None,
                "A resolved canonical target is required before authorization.",
                "fail_closed.target_missing",
            )

        rule_action, matched_rule = self._matched_action(operation, target)
        if operation is OperationClass.SCENE_EXECUTION and rule_action is not PolicyAction.DENY:
            return self._decision(
                PolicyAction.CONFIRM_REQUIRED,
                operation,
                target,
                "Scenes remain blocked until server-verifiable confirmation is implemented.",
                "phase7.scene_confirmation_required",
            )
        if rule_action in {PolicyAction.ALLOW, PolicyAction.CONFIRM_REQUIRED}:
            value_error = self._value_error(target, value)
            if value_error is not None:
                return self._decision(
                    PolicyAction.DENY,
                    operation,
                    target,
                    value_error,
                    "value_policy",
                )
        return self._decision(
            rule_action,
            operation,
            target,
            _decision_reason(rule_action, matched_rule),
            matched_rule,
        )

    def _matched_action(
        self, operation: OperationClass, target: ResolvedTarget
    ) -> tuple[PolicyAction, str]:
        # Exact precedence: hard boundaries (handled above), protected target,
        # explicit entity, domain, operation class, then global default.
        if target.entity_id in self.config.protected_entities:
            return (
                self.config.protected_entities[target.entity_id],
                f"protected_entity.{target.entity_id}",
            )
        if target.entity_id in self.config.entity_rules:
            return self.config.entity_rules[target.entity_id], f"entity.{target.entity_id}"
        if target.domain in self.config.domain_rules:
            return self.config.domain_rules[target.domain], f"domain.{target.domain}"
        if operation in self.config.operation_rules:
            return self.config.operation_rules[operation], f"operation.{operation.value}"
        return self.config.global_default, "global_default"

    def _value_error(self, target: ResolvedTarget, value: ControlValue | None) -> str | None:
        if value is None:
            return None
        limits = self.config.values
        if target.domain == "climate":
            if value.temperature is not None and value.temperature_unit == "C":
                if not (
                    limits.climate_min_celsius <= value.temperature <= limits.climate_max_celsius
                ):
                    return "Requested Celsius temperature is outside the configured policy range."
            if value.temperature is not None and value.temperature_unit == "F":
                if not (
                    limits.climate_min_fahrenheit
                    <= value.temperature
                    <= limits.climate_max_fahrenheit
                ):
                    return (
                        "Requested Fahrenheit temperature is outside the configured policy range."
                    )
            if value.hvac_mode is not None and value.hvac_mode not in limits.allowed_hvac_modes:
                return "Requested HVAC mode is not allowed by policy."
        if target.domain == "media_player" and value.volume_level is not None:
            if value.volume_level > limits.max_media_volume:
                return "Requested media volume exceeds the configured policy maximum."
        if target.domain == "light":
            if value.brightness_percent is not None and not (
                limits.min_brightness_percent
                <= value.brightness_percent
                <= limits.max_brightness_percent
            ):
                return "Requested brightness is outside the configured policy range."
            if value.color_temperature_kelvin is not None and not (
                limits.min_color_temperature_kelvin
                <= value.color_temperature_kelvin
                <= limits.max_color_temperature_kelvin
            ):
                return "Requested color temperature is outside the configured policy range."
        if target.domain == "fan" and value.fan_percentage is not None:
            if not (limits.min_fan_percentage <= value.fan_percentage <= limits.max_fan_percentage):
                return "Requested fan percentage is outside the configured policy range."
        return None

    @staticmethod
    def _decision(
        action: PolicyAction,
        operation: OperationClass,
        target: ResolvedTarget | None,
        reason: str,
        matched_rule: str,
    ) -> PolicyDecision:
        return PolicyDecision(
            decision=action,
            operation_class=operation,
            target=target.entity_id if target is not None else None,
            reason=reason,
            matched_rule=matched_rule,
            confirmation_required=action is PolicyAction.CONFIRM_REQUIRED,
        )


def _decision_reason(action: PolicyAction, matched_rule: str) -> str:
    if action is PolicyAction.ALLOW:
        return f"The matched {matched_rule} policy allows this operation."
    if action is PolicyAction.CONFIRM_REQUIRED:
        return f"The matched {matched_rule} policy requires server-verified confirmation."
    return f"The matched {matched_rule} policy denies this operation."
