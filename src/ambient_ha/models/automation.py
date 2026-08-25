"""Bounded, privacy-aware automation intelligence models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue

from ambient_ha.models.discovery import StrictModel

EvidenceCategory = Literal[
    "confirmed_by_context",
    "trace_confirmed",
    "strong_temporal_match",
    "possible_reference",
    "user_origin",
    "unrelated_or_unknown",
]
ReferenceType = Literal[
    "trigger_reference",
    "condition_reference",
    "action_target",
    "action_data_reference",
    "template_reference",
    "device_reference",
]


class AutomationSummary(StrictModel):
    """Compact metadata from an automation entity's current state."""

    entity_id: str
    friendly_name: str | None = None
    enabled: bool
    available: bool
    last_triggered: str | None = None
    mode: str | None = None


class AutomationListPage(StrictModel):
    automations: list[AutomationSummary] = Field(default_factory=list)
    total_matches: int
    returned: int
    limit: int
    truncated: bool


class AutomationConfigNode(StrictModel):
    """One sanitized top-level trigger, condition, or action block."""

    path: str
    kind: str
    data: dict[str, JsonValue] = Field(default_factory=dict)
    truncated: bool = False


class AutomationDefinition(StrictModel):
    """Normalized automation configuration, never raw YAML or unbounded JSON."""

    entity_id: str
    alias: str | None = None
    description: str | None = None
    enabled: bool
    available: bool
    mode: str | None = None
    triggers: list[AutomationConfigNode] = Field(default_factory=list)
    conditions: list[AutomationConfigNode] = Field(default_factory=list)
    actions: list[AutomationConfigNode] = Field(default_factory=list)
    configuration_available: bool
    complete: bool
    limitations: list[str] = Field(default_factory=list)
    truncated: bool = False
    content_is_untrusted_data: bool = True


class AutomationReference(StrictModel):
    automation_id: str
    entity_id: str
    reference_type: ReferenceType
    path: str
    confidence: Literal["explicit", "resolved_device", "static_text"]
    match_reason: str


class AutomationReferencesPage(StrictModel):
    entity_id: str
    references: list[AutomationReference] = Field(default_factory=list)
    total_matches: int
    returned: int
    limit: int
    truncated: bool
    complete: bool
    limitations: list[str] = Field(default_factory=list)


class AutomationTraceSummary(StrictModel):
    automation_id: str
    run_id: str
    timestamp: str | None = None
    finished_at: str | None = None
    state: str | None = None
    result: str | None = None
    last_step: str | None = None
    error: str | None = None
    not_triggered: bool = False


class AutomationTracesPage(StrictModel):
    automation_id: str
    traces: list[AutomationTraceSummary] = Field(default_factory=list)
    total_traces: int
    returned: int
    limit: int
    truncated: bool
    supported: bool


class AutomationTraceStep(StrictModel):
    order: int
    path: str
    kind: str
    timestamp: str | None = None
    result: JsonValue | None = None
    error: str | None = None
    child_run_id: str | None = None
    truncated: bool = False


class AutomationTrace(StrictModel):
    automation_id: str
    run_id: str
    timestamp: str | None = None
    finished_at: str | None = None
    state: str | None = None
    result: str | None = None
    trigger: JsonValue | None = None
    steps: list[AutomationTraceStep] = Field(default_factory=list)
    total_steps: int
    returned_steps: int
    truncated: bool
    error: str | None = None
    stop_reason: str | None = None
    context_id: str | None = None
    context_parent_id: str | None = None
    origin: Literal["automation", "user", "system", "unknown"] = "automation"
    content_is_untrusted_data: bool = True


class CausalityEvidence(StrictModel):
    source: Literal["automation", "user", "system", "unknown"]
    relationship: EvidenceCategory
    confidence: Literal["confirmed", "strong", "possible", "none"]
    event_timestamp: str
    execution_timestamp: str | None = None
    automation_id: str | None = None
    run_id: str | None = None
    context_relationship: Literal["same_context", "parent_context", "none"] = "none"
    supporting_facts: list[str] = Field(default_factory=list)


class ActivityCauseReport(StrictModel):
    entity_id: str
    start: str
    end: str
    state_changes_found: int
    evidence: list[CausalityEvidence] = Field(default_factory=list)
    total_evidence: int
    returned: int
    limit: int
    truncated: bool
    complete: bool
    limitations: list[str] = Field(default_factory=list)


class AutomationListResult(StrictModel):
    ok: bool
    message: str
    result: AutomationListPage | None = None
    error_code: str | None = None


class AutomationResult(StrictModel):
    ok: bool
    message: str
    found: bool
    supported: bool
    automation: AutomationDefinition | None = None
    error_code: str | None = None


class AutomationReferencesResult(StrictModel):
    ok: bool
    message: str
    result: AutomationReferencesPage | None = None
    error_code: str | None = None


class AutomationTracesResult(StrictModel):
    ok: bool
    message: str
    found: bool
    supported: bool
    result: AutomationTracesPage | None = None
    error_code: str | None = None


class AutomationTraceResult(StrictModel):
    ok: bool
    message: str
    found: bool
    supported: bool
    trace: AutomationTrace | None = None
    error_code: str | None = None


class ActivityCauseResult(StrictModel):
    ok: bool
    message: str
    found: bool
    result: ActivityCauseReport | None = None
    error_code: str | None = None
