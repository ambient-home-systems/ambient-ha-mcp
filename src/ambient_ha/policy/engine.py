"""Minimal fail-closed policy seam for future control phases."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class OperationClass(StrEnum):
    """High-level operation sensitivity independent of an LLM confirmation UI."""

    READ = "read"
    NORMAL_CONTROL = "normal_control"
    SENSITIVE_CONTROL = "sensitive_control"
    ADMINISTRATIVE = "administrative"


class PolicyDecision(BaseModel):
    """A stable result that can later be included in an audit event."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str


class PolicyEngine:
    """Allow reads and deny every control class in the current read-only release."""

    def evaluate(self, operation: OperationClass) -> PolicyDecision:
        """Make a deterministic, server-side authorization decision."""
        if operation is OperationClass.READ:
            return PolicyDecision(allowed=True, reason="Read operations are allowed.")
        return PolicyDecision(
            allowed=False,
            reason="Control and administrative operations are disabled.",
        )
