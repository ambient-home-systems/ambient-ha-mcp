"""The single Phase 7 authorization, execution, verification, and audit pipeline."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from uuid import uuid4

from ambient_ha.ha.client import HomeAssistantGateway
from ambient_ha.ha.control import (
    operation_class_for,
    resolved_target_for,
    service_call_for,
    service_name_for,
    state_matches_intent,
)
from ambient_ha.ha.exceptions import HomeAssistantError
from ambient_ha.models.control import (
    ControlDomain,
    ControlIntent,
    ControlResult,
    ControlStatus,
    ControlTargetResult,
)
from ambient_ha.models.discovery import EntityDetail
from ambient_ha.policy.audit import AuditEvent, AuditSink, StructuredLogAuditSink
from ambient_ha.policy.models import (
    ActionPlan,
    ActionRequest,
    OperationClass,
    PolicyAction,
    normalize_entity_id,
)
from ambient_ha.policy.planning import ActionPlanner

LOGGER = logging.getLogger(__name__)


class _ControlPreparationError(Exception):
    """Safe internal rejection raised before an authorization plan can be built."""


class ActionExecutor:
    """Only component authorized to cross from a semantic intent to an HA write."""

    def __init__(
        self,
        gateway: HomeAssistantGateway,
        planner: ActionPlanner,
        *,
        audit_sink: AuditSink | None = None,
        verification_timeout_seconds: float = 3.0,
        verification_interval_seconds: float = 0.25,
    ) -> None:
        self._gateway = gateway
        self._planner = planner
        self._audit = audit_sink or StructuredLogAuditSink()
        self._verification_timeout = verification_timeout_seconds
        self._verification_interval = verification_interval_seconds

    def reject_invalid(
        self,
        *,
        mcp_tool: str,
        domain: ControlDomain,
        action: str,
        entity_ids: list[str],
    ) -> ControlResult:
        """Audit and return a fail-closed result for pre-resolution input rejection."""
        request_id = uuid4().hex
        correlation_id = uuid4().hex
        safe_ids: list[str] = []
        for value in entity_ids[:20]:
            try:
                safe_ids.append(normalize_entity_id(value))
            except (AttributeError, ValueError):
                continue
        message = "The semantic control request is invalid and requires corrected input."
        event = AuditEvent(
            request_id=request_id,
            correlation_id=correlation_id,
            mcp_tool=mcp_tool,
            operation_class=_operation_for_domain(domain),
            action=action,
            resolved_targets=safe_ids,
            policy_decision=PolicyAction.DENY,
            confirmation_state="not_required",
            execution_result="invalid_request",
            reason=message,
            metadata={"submitted_target_count": min(len(entity_ids), 1000)},
        )
        try:
            self._audit.emit(event)
        except Exception:
            LOGGER.exception("Unable to emit the invalid Home Assistant action audit event")
        return ControlResult(
            ok=False,
            status=ControlStatus.CLARIFICATION_REQUIRED,
            message=message,
            request_id=request_id,
            correlation_id=correlation_id,
            action=action,
            targets=[
                ControlTargetResult(
                    entity_id=entity_id,
                    status=ControlStatus.CLARIFICATION_REQUIRED,
                    message=message,
                )
                for entity_id in safe_ids
            ],
            policy_decision=PolicyAction.DENY.value,
            matched_rules=["input_validation.invalid"],
            error_code="invalid_request",
        )

    async def execute(self, intent: ControlIntent) -> ControlResult:
        request_id = uuid4().hex
        correlation_id = uuid4().hex
        plan: ActionPlan | None = None
        try:
            entities, missing = await self._gateway.resolve_control_entities(intent.entity_ids)
            normalized_intent = intent if missing else await self._normalize_climate_unit(intent)
            targets = [resolved_target_for(entity, normalized_intent) for entity in entities]
            service_name = service_name_for(normalized_intent)
            plan = self._planner.plan(
                ActionRequest(
                    request_id=request_id,
                    correlation_id=correlation_id,
                    mcp_tool=normalized_intent.mcp_tool,
                    operation_class=operation_class_for(normalized_intent),
                    action=normalized_intent.action.value,
                    targets=targets,
                    ambiguous_candidate_ids=missing,
                    value=normalized_intent.value,
                    operation_count=1,
                    predicted_service=f"{normalized_intent.domain.value}.{service_name}",
                    predicted_payload={"entity_id": normalized_intent.entity_ids},
                )
            )
            if not plan.executable or plan.overall_decision is not PolicyAction.ALLOW:
                result = _blocked_result(plan, normalized_intent.entity_ids)
                self._emit(plan, execution_result=result.status.value)
                return result

            before = {entity.entity_id: entity for entity in entities}
            service_call = service_call_for(normalized_intent)
            # A pre-execution audit failure must fail closed. This is the final point before
            # the only Home Assistant write call in the application.
            self._audit.emit(
                AuditEvent.from_plan(
                    plan,
                    execution_result="authorized_pending_execution",
                    metadata={
                        "service": plan.predicted_service,
                        "target_count": len(plan.allowed_targets),
                    },
                )
            )
            await self._gateway.execute_control(service_call)
            verification_error_code: str | None = None
            try:
                target_results, status = await self._verify(normalized_intent, before)
            except HomeAssistantError as exc:
                verification_error_code = exc.code
                target_results = _accepted_unverified_results(normalized_intent, before)
                status = ControlStatus.ACCEPTED
            except Exception:
                LOGGER.exception("Unexpected failure while verifying a Home Assistant action")
                verification_error_code = "internal_error"
                target_results = _accepted_unverified_results(normalized_intent, before)
                status = ControlStatus.ACCEPTED
            result = ControlResult(
                ok=True,
                status=status,
                message=_success_message(status),
                request_id=request_id,
                correlation_id=correlation_id,
                action=normalized_intent.action.value,
                targets=target_results,
                policy_decision=plan.overall_decision.value,
                matched_rules=[decision.matched_rule for decision in plan.decisions],
                error_code=(
                    f"verification_{verification_error_code}"
                    if verification_error_code is not None
                    else None
                ),
            )
            self._emit(
                plan,
                execution_result=status.value,
                metadata={
                    "verified_targets": sum(
                        item.status is ControlStatus.VERIFIED for item in target_results
                    ),
                    "accepted_targets": sum(
                        item.status is ControlStatus.ACCEPTED for item in target_results
                    ),
                    "verification_error_code": verification_error_code,
                },
            )
            return result
        except _ControlPreparationError as exc:
            self._emit_unplanned_failure(
                intent,
                request_id=request_id,
                correlation_id=correlation_id,
                execution_result="unsupported",
                error_code="unsupported_unit_system",
                reason=str(exc),
            )
            return _unplanned_result(
                intent,
                request_id,
                correlation_id,
                status=ControlStatus.UNSUPPORTED,
                message=str(exc),
                error_code="unsupported_unit_system",
                matched_rule="capability.unknown",
            )
        except HomeAssistantError as exc:
            if plan is not None:
                self._emit(plan, execution_result="failed", metadata={"error_code": exc.code})
            else:
                self._emit_unplanned_failure(
                    intent,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    execution_result="failed",
                    error_code=exc.code,
                    reason=str(exc),
                )
            return _failed_result(
                intent,
                request_id,
                correlation_id,
                message=str(exc),
                error_code=exc.code,
                plan=plan,
            )
        except Exception:
            LOGGER.exception("Unexpected failure in the central Home Assistant action executor")
            if plan is not None:
                self._emit(
                    plan,
                    execution_result="failed",
                    metadata={"error_code": "internal_error"},
                )
            else:
                self._emit_unplanned_failure(
                    intent,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    execution_result="failed",
                    error_code="internal_error",
                    reason="The bridge could not safely prepare the Home Assistant action.",
                )
            return _failed_result(
                intent,
                request_id,
                correlation_id,
                message="The bridge could not safely complete the Home Assistant action.",
                error_code="internal_error",
                plan=plan,
            )

    async def _normalize_climate_unit(self, intent: ControlIntent) -> ControlIntent:
        value = intent.value
        if intent.domain is not ControlDomain.CLIMATE or value is None or value.temperature is None:
            return intent
        server = await self._gateway.get_server_info()
        raw_unit = (server.unit_system or {}).get("temperature")
        unit = raw_unit.replace("°", "").upper() if raw_unit else None
        if unit not in {"C", "F"}:
            raise _ControlPreparationError(
                "Home Assistant's configured temperature unit is unavailable."
            )
        if value.temperature_unit == unit:
            return intent
        converted = (
            value.temperature * 9 / 5 + 32
            if value.temperature_unit == "C"
            else (value.temperature - 32) * 5 / 9
        )
        return intent.model_copy(
            update={
                "value": value.model_copy(
                    update={"temperature": round(converted, 2), "temperature_unit": unit}
                )
            }
        )

    async def _verify(
        self,
        intent: ControlIntent,
        before: Mapping[str, EntityDetail],
    ) -> tuple[list[ControlTargetResult], ControlStatus]:
        if intent.domain in {ControlDomain.SCENE, ControlDomain.SCRIPT}:
            return (
                [
                    ControlTargetResult(
                        entity_id=entity_id,
                        status=ControlStatus.ACCEPTED,
                        before_state=before[entity_id].state if entity_id in before else None,
                        message=(
                            "Home Assistant accepted an action without a stable state to verify."
                        ),
                    )
                    for entity_id in intent.entity_ids
                ],
                ControlStatus.ACCEPTED,
            )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._verification_timeout
        after: dict[str, EntityDetail] = {}
        while True:
            entities, _missing = await self._gateway.resolve_control_entities(intent.entity_ids)
            after = {entity.entity_id: entity for entity in entities}
            matches = [
                state_matches_intent(after[entity_id], intent) if entity_id in after else False
                for entity_id in intent.entity_ids
            ]
            if all(match is True for match in matches) or loop.time() >= deadline:
                break
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(self._verification_interval, remaining))

        results: list[ControlTargetResult] = []
        verified = 0
        for entity_id in intent.entity_ids:
            current = after.get(entity_id)
            match = state_matches_intent(current, intent) if current is not None else False
            if match is True:
                verified += 1
                target_status = ControlStatus.VERIFIED
                message = (
                    "The requested state was verified after Home Assistant accepted the action."
                )
            else:
                target_status = ControlStatus.ACCEPTED
                message = (
                    "Home Assistant accepted the action, but the requested state was not verified."
                )
            results.append(
                ControlTargetResult(
                    entity_id=entity_id,
                    status=target_status,
                    before_state=before[entity_id].state if entity_id in before else None,
                    after_state=current.state if current is not None else None,
                    message=message,
                )
            )
        if verified == len(results):
            status = ControlStatus.VERIFIED
        elif verified:
            status = ControlStatus.PARTIALLY_VERIFIED
        else:
            status = ControlStatus.ACCEPTED
        return results, status

    def _emit(
        self,
        plan: ActionPlan,
        *,
        execution_result: str,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        try:
            self._audit.emit(
                AuditEvent.from_plan(
                    plan,
                    execution_result=execution_result,
                    metadata=metadata,
                )
            )
        except Exception:
            # A final/denial audit failure cannot undo a completed action. The pre-write
            # audit above is intentionally not routed through this containment path.
            LOGGER.exception("Unable to emit the final Home Assistant action audit event")

    def _emit_unplanned_failure(
        self,
        intent: ControlIntent,
        *,
        request_id: str,
        correlation_id: str,
        execution_result: str,
        error_code: str,
        reason: str,
    ) -> None:
        try:
            self._audit.emit(
                AuditEvent(
                    request_id=request_id,
                    correlation_id=correlation_id,
                    mcp_tool=intent.mcp_tool,
                    operation_class=operation_class_for(intent),
                    action=intent.action.value,
                    resolved_targets=intent.entity_ids[:20],
                    policy_decision=PolicyAction.DENY,
                    confirmation_state="not_required",
                    execution_result=execution_result,
                    reason=reason,
                    metadata={"error_code": error_code},
                )
            )
        except Exception:
            LOGGER.exception("Unable to emit the failed Home Assistant action audit event")


def _blocked_result(plan: ActionPlan, entity_ids: list[str]) -> ControlResult:
    rules = [decision.matched_rule for decision in plan.decisions]
    if plan.clarification_required:
        status = ControlStatus.CLARIFICATION_REQUIRED
        error_code = "clarification_required"
    elif plan.overall_decision is PolicyAction.CONFIRM_REQUIRED:
        status = ControlStatus.CONFIRMATION_REQUIRED
        error_code = "confirmation_required"
    elif "hard_boundary.read_only" in rules:
        status = ControlStatus.READ_ONLY
        error_code = "read_only"
    elif "hard_boundary.controls_disabled" in rules:
        status = ControlStatus.CONTROLS_DISABLED
        error_code = "controls_disabled"
    elif any(rule.startswith("capability.") or rule == "value_policy" for rule in rules):
        status = ControlStatus.UNSUPPORTED
        error_code = "unsupported"
    else:
        status = ControlStatus.DENIED
        error_code = "denied"
    return ControlResult(
        ok=False,
        status=status,
        message=plan.reason,
        request_id=plan.request_id,
        correlation_id=plan.correlation_id,
        action=plan.action,
        targets=[
            ControlTargetResult(
                entity_id=entity_id,
                status=status,
                message=plan.reason,
            )
            for entity_id in entity_ids
        ],
        policy_decision=plan.overall_decision.value,
        matched_rules=rules,
        confirmation_status=plan.confirmation.status if plan.confirmation else None,
        error_code=error_code,
    )


def _failed_result(
    intent: ControlIntent,
    request_id: str,
    correlation_id: str,
    *,
    message: str,
    error_code: str,
    plan: ActionPlan | None,
) -> ControlResult:
    return ControlResult(
        ok=False,
        status=ControlStatus.FAILED,
        message=message,
        request_id=request_id,
        correlation_id=correlation_id,
        action=intent.action.value,
        targets=[
            ControlTargetResult(
                entity_id=entity_id,
                status=ControlStatus.FAILED,
                message="The action did not complete.",
            )
            for entity_id in intent.entity_ids
        ],
        policy_decision=plan.overall_decision.value if plan else PolicyAction.DENY.value,
        matched_rules=[decision.matched_rule for decision in plan.decisions] if plan else [],
        error_code=error_code,
    )


def _unplanned_result(
    intent: ControlIntent,
    request_id: str,
    correlation_id: str,
    *,
    status: ControlStatus,
    message: str,
    error_code: str,
    matched_rule: str,
) -> ControlResult:
    return ControlResult(
        ok=False,
        status=status,
        message=message,
        request_id=request_id,
        correlation_id=correlation_id,
        action=intent.action.value,
        targets=[
            ControlTargetResult(
                entity_id=entity_id,
                status=status,
                message=message,
            )
            for entity_id in intent.entity_ids
        ],
        policy_decision=PolicyAction.DENY.value,
        matched_rules=[matched_rule],
        error_code=error_code,
    )


def _accepted_unverified_results(
    intent: ControlIntent,
    before: Mapping[str, EntityDetail],
) -> list[ControlTargetResult]:
    message = "Home Assistant accepted the action, but state verification was unavailable."
    return [
        ControlTargetResult(
            entity_id=entity_id,
            status=ControlStatus.ACCEPTED,
            before_state=before[entity_id].state if entity_id in before else None,
            message=message,
        )
        for entity_id in intent.entity_ids
    ]


def _success_message(status: ControlStatus) -> str:
    if status is ControlStatus.VERIFIED:
        return "Home Assistant accepted the action and every requested state was verified."
    if status is ControlStatus.PARTIALLY_VERIFIED:
        return "Home Assistant accepted the action and some requested states were verified."
    return "Home Assistant accepted the action; a stable resulting state was not verified."


def _operation_for_domain(domain: ControlDomain) -> OperationClass:
    if domain is ControlDomain.CLIMATE:
        return OperationClass.CLIMATE_CONTROL
    if domain is ControlDomain.SWITCH:
        return OperationClass.SENSITIVE_CONTROL
    if domain is ControlDomain.SCENE:
        return OperationClass.SCENE_EXECUTION
    if domain is ControlDomain.SCRIPT:
        return OperationClass.SCRIPT_EXECUTION
    return OperationClass.NORMAL_CONTROL
