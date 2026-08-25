"""Redacted audit-event model and lightweight sink abstraction."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ambient_ha.logging import redact_secrets
from ambient_ha.policy.models import ActionPlan, OperationClass, PolicyAction

_SENSITIVE_KEY = re.compile(
    r"(?i)(authorization|token|secret|password|credential|api[_-]?key|webhook|"
    r"camera|stream|url|uri|command|shell|message|notification|access[_-]?code)"
)
_URL_VALUE = re.compile(r"(?i)\b(?:https?|rtsp|wss?)://")
_MAX_DEPTH = 6
_MAX_ITEMS = 50
_MAX_STRING = 256


def sanitize_audit_value(value: object, *, _depth: int = 0) -> object:
    """Recursively bound and redact service/audit data before serialization."""
    if _depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                result["_truncated"] = True
                break
            safe_key = str(key)[:_MAX_STRING]
            if _SENSITIVE_KEY.search(safe_key):
                result[safe_key] = "[REDACTED]"
            else:
                result[safe_key] = sanitize_audit_value(item, _depth=_depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        list_result = [
            sanitize_audit_value(item, _depth=_depth + 1) for item in list(value)[:_MAX_ITEMS]
        ]
        if len(value) > _MAX_ITEMS:
            list_result.append("[TRUNCATED]")
        return list_result
    if isinstance(value, str):
        if _URL_VALUE.search(value):
            return "[REDACTED]"
        return redact_secrets(value[:_MAX_STRING])
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return redact_secrets(str(value)[:_MAX_STRING])


class AuditEvent(BaseModel):
    """A safe, structured future-action audit event."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    request_id: str
    correlation_id: str
    mcp_tool: str
    operation_class: OperationClass
    action: str
    resolved_targets: list[str] = Field(default_factory=list)
    policy_decision: PolicyAction
    confirmation_state: str
    execution_result: str = "not_executed_phase_6"
    reason: str
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_plan(
        cls, plan: ActionPlan, *, metadata: Mapping[str, object] | None = None
    ) -> AuditEvent:
        """Create an audit event whose metadata has already crossed redaction."""
        safe_metadata = sanitize_audit_value(metadata or {})
        return cls(
            request_id=plan.request_id,
            correlation_id=plan.correlation_id,
            mcp_tool=plan.mcp_tool,
            operation_class=plan.operation_class,
            action=plan.action,
            resolved_targets=sorted(
                set(plan.allowed_targets + plan.denied_targets + plan.confirmation_targets)
            ),
            policy_decision=plan.overall_decision,
            confirmation_state=(
                plan.confirmation.status if plan.confirmation is not None else "not_required"
            ),
            reason=plan.reason,
            metadata=safe_metadata if isinstance(safe_metadata, dict) else {},
        )

    def safe_json(self) -> str:
        """Serialize through a final defense-in-depth sanitizer."""
        safe = sanitize_audit_value(self.model_dump(mode="json"))
        return json.dumps(safe, separators=(",", ":"), ensure_ascii=False)


class AuditSink(Protocol):
    """Minimal sink interface; no persistent database is introduced in Phase 6."""

    def emit(self, event: AuditEvent) -> None:
        """Emit one already-redacted audit event."""
        ...


class StructuredLogAuditSink:
    """Optional JSON-log sink suitable for later append-only routing."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("ambient_ha.audit")

    def emit(self, event: AuditEvent) -> None:
        self._logger.info("audit_event=%s", event.safe_json())
