"""Pure normalization, indexing, trace, and evidence helpers for automations."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import JsonValue

from ambient_ha.ha.exceptions import HomeAssistantUnexpectedResponse
from ambient_ha.ha.history import parse_timestamp
from ambient_ha.models.automation import (
    AutomationConfigNode,
    AutomationDefinition,
    AutomationListPage,
    AutomationReference,
    AutomationReferencesPage,
    AutomationSummary,
    AutomationTrace,
    AutomationTracesPage,
    AutomationTraceStep,
    AutomationTraceSummary,
    ReferenceType,
)

MAX_CONFIG_NODES = 100
MAX_NESTING_DEPTH = 8
MAX_COLLECTION_ITEMS = 100
MAX_STRING_LENGTH = 512
MAX_TRACE_STEPS = 200
MAX_NORMALIZED_TEXT_CHARS = 20_000
MAX_NORMALIZED_VALUES = 2_000
MAX_REFERENCE_SCAN_VALUES = 10_000
_ENTITY_PATTERN = re.compile(r"(?<![a-z0-9_])([a-z0-9_]+\.[a-z0-9_]+)(?![a-z0-9_])")
_URL_PATTERN = re.compile(r"(?:https?|rtsp|wss?)://", re.IGNORECASE)
_SECRET_TEXT_PATTERN = re.compile(
    r"(?:bearer\s+[a-z0-9._~+/-]+|(?:token|secret|password|api[_-]?key)\s*[:=])",
    re.IGNORECASE,
)
_SENSITIVE_KEY_MARKERS = (
    "access_token",
    "api_key",
    "authorization",
    "camera",
    "credential",
    "entity_picture",
    "gps",
    "latitude",
    "longitude",
    "media_content",
    "password",
    "secret",
    "stream",
    "token",
    "url",
    "user_id",
    "webhook",
)
_SENSITIVE_CONTENT_KEYS = {"command", "message", "title"}


@dataclass(frozen=True, slots=True)
class AutomationCatalog:
    """One bounded cacheable snapshot of loaded automation configurations."""

    supported: bool
    configurations: dict[str, dict[str, Any]]
    missing: frozenset[str]
    entity_device_ids: dict[str, str]
    truncated: bool = False


@dataclass(slots=True)
class _NormalizationBudget:
    remaining_chars: int = MAX_NORMALIZED_TEXT_CHARS
    remaining_values: int = MAX_NORMALIZED_VALUES
    truncated: bool = False

    def consume(self, value: str) -> str:
        if self.remaining_values <= 0 or self.remaining_chars <= 0:
            self.truncated = True
            return "[truncated]"
        self.remaining_values -= 1
        allowed = min(MAX_STRING_LENGTH, self.remaining_chars)
        result = value[:allowed]
        self.remaining_chars -= len(result)
        if len(value) > allowed:
            self.truncated = True
        return result


def list_automations(
    states: Iterable[Mapping[str, Any]],
    *,
    query: str | None,
    enabled: bool | None,
    limit: int,
) -> AutomationListPage:
    """Normalize and deterministically rank current automation entities."""
    wanted = _normalize_search(query) if query else ""
    ranked: list[tuple[int, AutomationSummary]] = []
    for state in states:
        entity_id = _text(state.get("entity_id"))
        if entity_id is None or not entity_id.startswith("automation."):
            continue
        state_value = (_text(state.get("state")) or "unknown").casefold()
        summary = _automation_summary(state, entity_id, state_value)
        if enabled is not None and summary.enabled is not enabled:
            continue
        score = _automation_match_score(summary, wanted) if wanted else 0
        if wanted and score == 0:
            continue
        ranked.append((score, summary))
    ranked.sort(
        key=lambda item: (
            -item[0],
            (item[1].friendly_name or item[1].entity_id).casefold(),
            item[1].entity_id.casefold(),
        )
    )
    matches = [item[1] for item in ranked]
    return AutomationListPage(
        automations=matches[:limit],
        total_matches=len(matches),
        returned=min(len(matches), limit),
        limit=limit,
        truncated=len(matches) > limit,
    )


def normalize_automation_definition(
    entity_state: Mapping[str, Any],
    config: Mapping[str, Any] | None,
    *,
    supported: bool,
) -> AutomationDefinition:
    """Create a bounded configuration view while treating all content as untrusted data."""
    entity_id = _text(entity_state.get("entity_id")) or "automation.unknown"
    state_value = (_text(entity_state.get("state")) or "unknown").casefold()
    attrs = entity_state.get("attributes")
    attributes = attrs if isinstance(attrs, Mapping) else {}
    limitations: list[str] = []
    if not supported:
        limitations.append("Home Assistant does not expose the automation/config command.")
    elif config is None:
        limitations.append("Configuration is unavailable for this loaded automation.")
    if config is None:
        return AutomationDefinition(
            entity_id=entity_id,
            alias=_bounded_text(attributes.get("friendly_name")),
            enabled=state_value == "on",
            available=state_value != "unavailable",
            mode=_bounded_text(attributes.get("mode")),
            configuration_available=False,
            complete=False,
            limitations=limitations,
        )

    budget = _NormalizationBudget()
    triggers = _config_nodes(config, "triggers", "trigger", budget=budget)
    conditions = _config_nodes(config, "conditions", "condition", budget=budget)
    actions = _config_nodes(config, "actions", "action", budget=budget)
    truncated = _structure_exceeds_bounds(config) or budget.truncated
    dynamic_template = _contains_dynamic_template(config)
    if truncated:
        limitations.append("Configuration was truncated to the documented structure limits.")
    if dynamic_template:
        limitations.append("Dynamic templates are preserved as inert data and are not evaluated.")
    return AutomationDefinition(
        entity_id=entity_id,
        alias=_safe_text(config.get("alias")) or _bounded_text(attributes.get("friendly_name")),
        description=_safe_text(config.get("description")),
        enabled=state_value == "on",
        available=state_value != "unavailable",
        mode=_safe_text(config.get("mode")) or _bounded_text(attributes.get("mode")),
        triggers=triggers,
        conditions=conditions,
        actions=actions,
        configuration_available=True,
        complete=not truncated and not dynamic_template,
        limitations=limitations,
        truncated=truncated,
    )


def find_automation_references(
    catalog: AutomationCatalog,
    entity_id: str,
    *,
    limit: int,
) -> AutomationReferencesPage:
    """Find conservative explicit, device-resolved, and static-template references."""
    target_device_id = catalog.entity_device_ids.get(entity_id)
    references: list[AutomationReference] = []
    dynamic_templates = False
    config_truncated = False
    for automation_id in sorted(catalog.configurations):
        config = catalog.configurations[automation_id]
        dynamic_templates = dynamic_templates or _contains_dynamic_template(config)
        config_truncated = config_truncated or _structure_exceeds_bounds(config)
        references.extend(
            _references_in_config(
                automation_id,
                config,
                entity_id=entity_id,
                target_device_id=target_device_id,
            )
        )
    unique = {(item.automation_id, item.reference_type, item.path): item for item in references}
    ordered = sorted(
        unique.values(),
        key=lambda item: (item.automation_id, item.path, item.reference_type),
    )
    limitations: list[str] = []
    if not catalog.supported:
        limitations.append("Home Assistant does not expose automation configuration.")
    if catalog.missing:
        limitations.append("Some loaded automation configurations were unavailable.")
    if catalog.truncated:
        limitations.append("The automation reference index reached its configured bound.")
    if config_truncated:
        limitations.append("Some automation configuration exceeded the reference scan bounds.")
    if dynamic_templates:
        limitations.append("Dynamic templates can hide references and are never executed.")
    complete = (
        catalog.supported
        and not catalog.missing
        and not catalog.truncated
        and not config_truncated
        and not dynamic_templates
    )
    return AutomationReferencesPage(
        entity_id=entity_id,
        references=ordered[:limit],
        total_matches=len(ordered),
        returned=min(len(ordered), limit),
        limit=limit,
        truncated=len(ordered) > limit,
        complete=complete,
        limitations=limitations,
    )


def normalize_trace_summaries(
    automation_id: str,
    payload: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    supported: bool,
) -> AutomationTracesPage:
    """Normalize compact trace metadata, newest first, without raw trace bodies."""
    traces = [
        summary for raw in payload if (summary := _trace_summary(automation_id, raw)) is not None
    ]
    traces.sort(key=lambda item: item.timestamp or "", reverse=True)
    return AutomationTracesPage(
        automation_id=automation_id,
        traces=traces[:limit],
        total_traces=len(traces),
        returned=min(len(traces), limit),
        limit=limit,
        truncated=len(traces) > limit,
        supported=supported,
    )


def normalize_automation_trace(
    automation_id: str,
    run_id: str,
    raw: Mapping[str, Any],
    *,
    max_steps: int = MAX_TRACE_STEPS,
) -> AutomationTrace:
    """Flatten trace buckets in recorded order while preserving meaningful paths."""
    raw_trace = raw.get("trace")
    if not isinstance(raw_trace, Mapping):
        raise HomeAssistantUnexpectedResponse(
            "Home Assistant returned a malformed automation trace body."
        )
    raw_context = raw.get("context")
    if raw_context is not None and not isinstance(raw_context, Mapping):
        raise HomeAssistantUnexpectedResponse(
            "Home Assistant returned malformed automation trace context data."
        )
    buckets = raw_trace
    budget = _NormalizationBudget()
    steps: list[AutomationTraceStep] = []
    for path, entries in buckets.items():
        if not isinstance(path, str) or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            result, result_truncated = _safe_json(entry.get("result"), budget=budget)
            child_id = entry.get("child_id")
            child_run_id = None
            if isinstance(child_id, Mapping):
                child_run_id = _bounded_text(child_id.get("run_id"))
            steps.append(
                AutomationTraceStep(
                    order=len(steps),
                    path=path[:MAX_STRING_LENGTH],
                    kind=_trace_step_kind(path),
                    timestamp=_bounded_text(entry.get("timestamp")),
                    result=result,
                    error=_safe_text(entry.get("error")),
                    child_run_id=child_run_id,
                    truncated=result_truncated,
                )
            )
    timestamp, finished = _trace_timestamps(raw)
    context_values = raw_context if isinstance(raw_context, Mapping) else {}
    trigger, trigger_truncated = _safe_json(raw.get("trigger"), budget=budget)
    total_steps = len(steps)
    error = _safe_text(raw.get("error"))
    result = _safe_text(raw.get("script_execution"))
    return AutomationTrace(
        automation_id=automation_id,
        run_id=run_id,
        timestamp=timestamp,
        finished_at=finished,
        state=_bounded_text(raw.get("state")),
        result=result,
        trigger=trigger,
        steps=steps[:max_steps],
        total_steps=total_steps,
        returned_steps=min(total_steps, max_steps),
        truncated=total_steps > max_steps or trigger_truncated or budget.truncated,
        error=error,
        stop_reason=error or result,
        context_id=_bounded_text(context_values.get("id")),
        context_parent_id=_bounded_text(context_values.get("parent_id")),
        origin="automation",
    )


def trace_explicitly_targets_entity(raw: Mapping[str, Any], entity_id: str) -> bool:
    """Return true only when an executed trace result explicitly names the entity."""
    return trace_target_execution_timestamp(raw, entity_id) is not None


def trace_target_execution_timestamp(raw: Mapping[str, Any], entity_id: str) -> str | None:
    """Return an executed action timestamp only for an explicit entity target."""
    trace = raw.get("trace")
    if not isinstance(trace, Mapping):
        return None
    for path, entries in trace.items():
        if not isinstance(path, str) or not path.startswith("action/"):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            result = entry.get("result")
            if _contains_explicit_entity_value(result, entity_id):
                return _bounded_text(entry.get("timestamp"))
    return None


def trace_start(raw: Mapping[str, Any]) -> datetime | None:
    timestamp, _finished = _trace_timestamps(raw)
    if timestamp is None:
        return None
    try:
        return parse_timestamp(timestamp)
    except Exception:
        return None


def _automation_summary(
    state: Mapping[str, Any], entity_id: str, state_value: str
) -> AutomationSummary:
    raw_attrs = state.get("attributes")
    attrs = raw_attrs if isinstance(raw_attrs, Mapping) else {}
    return AutomationSummary(
        entity_id=entity_id,
        friendly_name=_bounded_text(attrs.get("friendly_name")),
        enabled=state_value == "on",
        available=state_value != "unavailable",
        last_triggered=_bounded_text(attrs.get("last_triggered")),
        mode=_bounded_text(attrs.get("mode")),
    )


def _automation_match_score(summary: AutomationSummary, query: str) -> int:
    entity = _normalize_search(summary.entity_id)
    object_id = _normalize_search(summary.entity_id.partition(".")[2])
    name = _normalize_search(summary.friendly_name or "")
    if query in {entity, object_id}:
        return 100
    if query == name:
        return 90
    if object_id.startswith(query) or name.startswith(query):
        return 70
    if query in entity or query in name:
        return 50
    return 0


def _config_nodes(
    config: Mapping[str, Any],
    plural_key: str,
    singular_key: str,
    *,
    budget: _NormalizationBudget,
) -> list[AutomationConfigNode]:
    value = config.get(plural_key, config.get(singular_key, []))
    items = value if isinstance(value, list) else [value]
    if len(items) > MAX_CONFIG_NODES:
        budget.truncated = True
    nodes: list[AutomationConfigNode] = []
    for index, item in enumerate(items[:MAX_CONFIG_NODES]):
        if not isinstance(item, Mapping):
            continue
        safe, truncated = _safe_mapping(item, budget=budget)
        kind_value = item.get(singular_key)
        kind = _bounded_text(kind_value) or _bounded_text(item.get("platform")) or singular_key
        nodes.append(
            AutomationConfigNode(
                path=f"{plural_key}/{index}",
                kind=kind,
                data=safe,
                truncated=truncated,
            )
        )
    return nodes


def _references_in_config(
    automation_id: str,
    config: Mapping[str, Any],
    *,
    entity_id: str,
    target_device_id: str | None,
) -> list[AutomationReference]:
    found: list[AutomationReference] = []
    for path, key, value in _walk(config):
        lowered_key = key.casefold()
        if lowered_key == "entity_id":
            values = value if isinstance(value, list) else [value]
            if any(item == entity_id for item in values if isinstance(item, str)):
                reference_type = _reference_type(path)
                found.append(
                    AutomationReference(
                        automation_id=automation_id,
                        entity_id=entity_id,
                        reference_type=reference_type,
                        path=path,
                        confidence="explicit",
                        match_reason="The automation configuration explicitly names the entity.",
                    )
                )
        elif lowered_key == "device_id" and target_device_id is not None:
            values = value if isinstance(value, list) else [value]
            if any(item == target_device_id for item in values if isinstance(item, str)):
                found.append(
                    AutomationReference(
                        automation_id=automation_id,
                        entity_id=entity_id,
                        reference_type="device_reference",
                        path=path,
                        confidence="resolved_device",
                        match_reason=(
                            "A device reference resolves to the entity's registered device."
                        ),
                    )
                )
        elif isinstance(value, str) and _is_template(value):
            if entity_id in _ENTITY_PATTERN.findall(value.casefold()):
                found.append(
                    AutomationReference(
                        automation_id=automation_id,
                        entity_id=entity_id,
                        reference_type="template_reference",
                        path=path,
                        confidence="static_text",
                        match_reason="A non-executed template string contains the exact entity ID.",
                    )
                )
        elif isinstance(value, str) and path.startswith("actions/") and value == entity_id:
            found.append(
                AutomationReference(
                    automation_id=automation_id,
                    entity_id=entity_id,
                    reference_type="action_data_reference",
                    path=path,
                    confidence="explicit",
                    match_reason="Action data explicitly equals the entity ID.",
                )
            )
    return found


def _reference_type(path: str) -> ReferenceType:
    if path.startswith(("triggers/", "trigger/")):
        return "trigger_reference"
    if path.startswith(("conditions/", "condition/")):
        return "condition_reference"
    if "/target/" in f"/{path}/" or path.endswith("target/entity_id"):
        return "action_target"
    return "action_data_reference"


def _walk(
    value: Any,
    path: str = "",
    *,
    depth: int = 0,
    remaining: list[int] | None = None,
) -> Iterable[tuple[str, str, Any]]:
    if remaining is None:
        remaining = [MAX_REFERENCE_SCAN_VALUES]
    if remaining[0] <= 0 or depth >= MAX_NESTING_DEPTH:
        return
    if isinstance(value, Mapping):
        for key, child in list(value.items())[:MAX_COLLECTION_ITEMS]:
            if remaining[0] <= 0:
                return
            if not isinstance(key, str):
                continue
            remaining[0] -= 1
            child_path = f"{path}/{key}" if path else key
            yield child_path, key, child
            yield from _walk(child, child_path, depth=depth + 1, remaining=remaining)
    elif isinstance(value, list):
        for index, child in enumerate(value[:MAX_COLLECTION_ITEMS]):
            if remaining[0] <= 0:
                return
            remaining[0] -= 1
            child_path = f"{path}/{index}" if path else str(index)
            yield from _walk(child, child_path, depth=depth + 1, remaining=remaining)


def _trace_summary(automation_id: str, raw: Mapping[str, Any]) -> AutomationTraceSummary | None:
    run_id = _bounded_text(raw.get("run_id"))
    if run_id is None:
        return None
    timestamp, finished = _trace_timestamps(raw)
    return AutomationTraceSummary(
        automation_id=automation_id,
        run_id=run_id,
        timestamp=timestamp,
        finished_at=finished,
        state=_bounded_text(raw.get("state")),
        result=_bounded_text(raw.get("script_execution")),
        last_step=_bounded_text(raw.get("last_step")),
        error=_safe_text(raw.get("error")),
        not_triggered=raw.get("not_triggered") is True,
    )


def _trace_timestamps(raw: Mapping[str, Any]) -> tuple[str | None, str | None]:
    timestamp = raw.get("timestamp")
    if not isinstance(timestamp, Mapping):
        return None, None
    return _bounded_text(timestamp.get("start")), _bounded_text(timestamp.get("finish"))


def _trace_step_kind(path: str) -> str:
    lowered = path.casefold()
    for kind in ("trigger", "condition", "choose", "if", "parallel", "sequence", "action"):
        if kind in lowered.split("/"):
            return kind
    return lowered.split("/", 1)[0] or "step"


def _safe_mapping(
    value: Mapping[str, Any], *, budget: _NormalizationBudget
) -> tuple[dict[str, JsonValue], bool]:
    result, truncated = _safe_json(value, budget=budget)
    return (result if isinstance(result, dict) else {}), truncated


def _safe_json(
    value: Any,
    *,
    depth: int = 0,
    key: str | None = None,
    budget: _NormalizationBudget | None = None,
) -> tuple[JsonValue, bool]:
    active_budget = budget or _NormalizationBudget()
    if active_budget.remaining_values <= 0 or active_budget.remaining_chars <= 0:
        active_budget.truncated = True
        return "[truncated]", True
    if key is not None and _sensitive_key(key):
        return active_budget.consume("[redacted]"), active_budget.truncated
    if value is None or isinstance(value, bool | int | float):
        active_budget.remaining_values -= 1
        return value, False
    if isinstance(value, str):
        if _URL_PATTERN.search(value) or _SECRET_TEXT_PATTERN.search(value):
            return active_budget.consume("[redacted]"), active_budget.truncated
        if key in {"action", "service"} and value.startswith(("notify.", "shell_command.")):
            redacted = f"{value.partition('.')[0]}.[redacted]"
            return active_budget.consume(redacted), active_budget.truncated
        result = active_budget.consume(value)
        return result, active_budget.truncated
    if depth >= MAX_NESTING_DEPTH:
        return "[truncated]", True
    if isinstance(value, Mapping):
        output: dict[str, JsonValue] = {}
        truncated = len(value) > MAX_COLLECTION_ITEMS
        for raw_key, child in list(value.items())[:MAX_COLLECTION_ITEMS]:
            if not isinstance(raw_key, str):
                truncated = True
                continue
            safe_child, child_truncated = _safe_json(
                child,
                depth=depth + 1,
                key=raw_key,
                budget=active_budget,
            )
            output[raw_key[:MAX_STRING_LENGTH]] = safe_child
            truncated = truncated or child_truncated
        return output, truncated
    if isinstance(value, list | tuple):
        output_list: list[JsonValue] = []
        truncated = len(value) > MAX_COLLECTION_ITEMS
        for child in value[:MAX_COLLECTION_ITEMS]:
            safe_child, child_truncated = _safe_json(child, depth=depth + 1, budget=active_budget)
            output_list.append(safe_child)
            truncated = truncated or child_truncated
        return output_list, truncated
    return active_budget.consume(str(value)), True


def _safe_text(value: Any) -> str | None:
    text = _bounded_text(value)
    if text is None:
        return None
    if _URL_PATTERN.search(text) or _SECRET_TEXT_PATTERN.search(text):
        return "[redacted]"
    return text


def _sensitive_key(key: str) -> bool:
    lowered = key.casefold()
    return lowered in _SENSITIVE_CONTENT_KEYS or any(
        marker in lowered for marker in _SENSITIVE_KEY_MARKERS
    )


def _bounded_text(value: Any) -> str | None:
    return value[:MAX_STRING_LENGTH] if isinstance(value, str) and value else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _normalize_search(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _is_template(value: str) -> bool:
    return "{{" in value or "{%" in value


def _contains_dynamic_template(value: Any) -> bool:
    if isinstance(value, str):
        return _is_template(value)
    return any(
        isinstance(child, str) and _is_template(child) for _path, _key, child in _walk(value)
    )


def _structure_exceeds_bounds(
    value: Any, *, depth: int = 0, remaining: list[int] | None = None
) -> bool:
    if remaining is None:
        remaining = [MAX_REFERENCE_SCAN_VALUES]
    if remaining[0] <= 0:
        return True
    remaining[0] -= 1
    if depth >= MAX_NESTING_DEPTH and isinstance(value, Mapping | list | tuple):
        return True
    if isinstance(value, Mapping):
        return len(value) > MAX_COLLECTION_ITEMS or any(
            _structure_exceeds_bounds(child, depth=depth + 1, remaining=remaining)
            for child in value.values()
        )
    if isinstance(value, list | tuple):
        return len(value) > MAX_COLLECTION_ITEMS or any(
            _structure_exceeds_bounds(child, depth=depth + 1, remaining=remaining)
            for child in value
        )
    return isinstance(value, str) and len(value) > MAX_STRING_LENGTH


def _contains_explicit_entity_value(value: Any, entity_id: str) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == "entity_id":
                values = child if isinstance(child, list) else [child]
                if any(item == entity_id for item in values if isinstance(item, str)):
                    return True
            if isinstance(child, Mapping | list | tuple) and _contains_explicit_entity_value(
                child, entity_id
            ):
                return True
    if isinstance(value, list | tuple):
        return any(
            _contains_explicit_entity_value(child, entity_id)
            for child in value
            if isinstance(child, Mapping | list | tuple)
        )
    return False
