"""Internal, network-free dry-run planning for future semantic controls."""

from __future__ import annotations

from ambient_ha.policy.audit import sanitize_audit_value
from ambient_ha.policy.engine import PolicyEngine
from ambient_ha.policy.models import (
    ActionPlan,
    ActionRequest,
    ConfirmationRequirement,
    MassActionResult,
    OperationClass,
    PolicyAction,
    PolicyDecision,
)


class ActionPlanner:
    """Build explicit authorization plans for the central action executor."""

    def __init__(self, policy: PolicyEngine, *, execution_available: bool = False) -> None:
        self._policy = policy
        self._execution_available = execution_available

    def plan(self, request: ActionRequest) -> ActionPlan:
        """Create a bounded plan; only an all-allow plan may become executable."""
        limits = self._policy.config.limits
        mass_allowed = (
            len(request.targets) <= limits.max_entities_per_action
            and request.operation_count <= limits.max_operations_per_request
        )
        mass_reason = None
        if len(request.targets) > limits.max_entities_per_action:
            mass_reason = "Target count exceeds the configured action limit."
        elif request.operation_count > limits.max_operations_per_request:
            mass_reason = "Operation count exceeds the configured request limit."
        mass_result = MassActionResult(
            allowed=mass_allowed,
            target_count=len(request.targets),
            operation_count=request.operation_count,
            max_targets=limits.max_entities_per_action,
            max_operations=limits.max_operations_per_request,
            reason=mass_reason,
        )

        if request.ambiguous_candidate_ids:
            return self._blocked_plan(
                request,
                mass_result,
                reason="Target resolution is ambiguous and requires clarification.",
                matched_rule="target_resolution.ambiguous",
                clarification_required=True,
            )
        if request.operation_class is not OperationClass.READ and not request.targets:
            return self._blocked_plan(
                request,
                mass_result,
                reason="No resolved canonical target was supplied.",
                matched_rule="target_resolution.missing",
            )
        decisions: list[PolicyDecision] = []
        for target in request.targets:
            if not target.capability_known:
                decisions.append(
                    PolicyDecision(
                        decision=PolicyAction.DENY,
                        operation_class=request.operation_class,
                        target=target.entity_id,
                        reason=target.capability_reason
                        or "Target capability is unknown; planning fails closed.",
                        matched_rule="capability.unknown",
                    )
                )
            elif not target.capability_supported:
                decisions.append(
                    PolicyDecision(
                        decision=PolicyAction.DENY,
                        operation_class=request.operation_class,
                        target=target.entity_id,
                        reason=target.capability_reason
                        or "The target does not support the requested capability.",
                        matched_rule="capability.unsupported",
                    )
                )
            else:
                decisions.append(
                    self._policy.evaluate(
                        request.operation_class,
                        target=target,
                        value=request.value,
                    )
                )

        if request.operation_class is OperationClass.READ and not decisions:
            decisions.append(self._policy.evaluate(OperationClass.READ))

        if not mass_allowed:
            return self._blocked_plan(
                request,
                mass_result,
                reason=mass_reason or "Mass-action policy denied the request.",
                matched_rule="mass_action.limit",
                denied_targets=[target.entity_id for target in request.targets],
            )

        allowed = [item.target for item in decisions if item.allowed and item.target is not None]
        denied = [
            item.target
            for item in decisions
            if item.decision is PolicyAction.DENY and item.target is not None
        ]
        confirmation = [
            item.target
            for item in decisions
            if item.decision is PolicyAction.CONFIRM_REQUIRED and item.target is not None
        ]
        if denied:
            overall = PolicyAction.DENY
            reason = "At least one resolved target is denied; partial execution is not authorized."
        elif confirmation:
            overall = PolicyAction.CONFIRM_REQUIRED
            reason = "At least one target requires server-verified confirmation."
        else:
            overall = PolicyAction.ALLOW
            reason = "All resolved targets pass the current policy dry run."

        confirmation_requirement = (
            ConfirmationRequirement(
                correlation_id=request.correlation_id,
                scope=confirmation,
            )
            if confirmation
            else None
        )
        return ActionPlan(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            mcp_tool=request.mcp_tool,
            operation_class=request.operation_class,
            action=request.action,
            overall_decision=overall,
            decisions=decisions,
            allowed_targets=allowed,
            denied_targets=denied,
            confirmation_targets=confirmation,
            mass_action=mass_result,
            confirmation=confirmation_requirement,
            predicted_service=request.predicted_service,
            predicted_payload=_sanitized_mapping(request.predicted_payload),
            executable=overall is PolicyAction.ALLOW and self._execution_available,
            execution_available=self._execution_available,
            reason=reason,
        )

    @staticmethod
    def _blocked_plan(
        request: ActionRequest,
        mass_action: MassActionResult,
        *,
        reason: str,
        matched_rule: str,
        clarification_required: bool = False,
        denied_targets: list[str] | None = None,
    ) -> ActionPlan:
        decision = PolicyDecision(
            decision=PolicyAction.DENY,
            operation_class=request.operation_class,
            reason=reason,
            matched_rule=matched_rule,
        )
        return ActionPlan(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            mcp_tool=request.mcp_tool,
            operation_class=request.operation_class,
            action=request.action,
            overall_decision=PolicyAction.DENY,
            decisions=[decision],
            denied_targets=denied_targets or [],
            clarification_required=clarification_required,
            ambiguous_candidate_ids=request.ambiguous_candidate_ids,
            mass_action=mass_action,
            predicted_service=request.predicted_service,
            predicted_payload=_sanitized_mapping(request.predicted_payload),
            executable=False,
            execution_available=False,
            reason=reason,
        )


def _sanitized_mapping(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    sanitized = sanitize_audit_value(value)
    return sanitized if isinstance(sanitized, dict) else {"value": "[REDACTED]"}
