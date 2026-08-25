# MCP tool contracts

All tools are read-only and return structured models. Errors use stable codes and
safe messages; normal not-found and unsupported-feature outcomes are represented
in the result rather than raised as generic failures.

Phase 6 intentionally adds no public MCP tool. The discovery surface remains 24
read-only tools. Policy planning, confirmation requirements, and audit events are
internal architecture only and cannot execute a Home Assistant operation.

## Diagnostics

### `ha_connection_status`

Use first when a Home Assistant request fails. It reports reachability and
authentication independently and never includes a URL, token, authorization
header, raw response, or stack trace.

### `ha_server_info`

Returns only Home Assistant version, time zone, and string fields from the unit
system. Coordinates, location name, configuration paths, components, and unknown
configuration fields are excluded.

## Entity discovery

### `ha_get_entity(entity_id)`

Use when the exact `domain.object_id` is known. Returns fresh current state,
friendly name, availability, device, resolved area/floor, timestamps, and a
bounded allowlist of useful attributes. It returns `found: false` for a missing
entity. Human names should use search instead.

### `ha_search_entities(...)`

Accepts optional `query`, `domain`, `area`, `floor`, `state`, `available`, and
`limit` arguments. All supplied filters compose. Query matching is
case-insensitive across entity/object IDs, friendly names, devices, areas, and
floors. Entity/name matches outrank contextual location matches and ordering is
deterministic.

Results are compact and contain no attribute dictionaries. The default limit is
25 and the hard maximum is 100. `total_matches`, `returned`, and `truncated` make
partial results explicit.

Examples:

- `{"query": "garage light"}` finds human-named or ID-matched garage lights.
- `{"domain": "light", "state": "on", "area": "Kitchen"}` applies all three filters.
- `{"available": false}` lists entities whose current state is `unavailable`.

## Areas and floors

### `ha_list_areas()`

Returns compact area/floor/entity counts without embedding entity arrays.

### `ha_get_area(area, include_entities=false, limit=25)`

Resolves an area by ID or case-insensitive name and returns counts by domain.
Entity summaries are omitted unless explicitly requested, then capped at 50 with
truncation metadata. An entity registry area overrides its device's inherited
area.

### `ha_list_floors()`

Returns configured floors with level, area count, and entity count. Older Home
Assistant installations without the floor command return `supported: false`.

### `ha_get_floor(floor)`

Resolves a floor by ID or name and returns its compact areas plus entity counts by
domain. It does not embed every entity.

## Domain aggregation

### `ha_domain_summary(domain)`

Returns total, available, unavailable, unknown, and counts for every observed
state in a domain. The model is generic: it does not assume lights, sensors,
covers, climate entities, and other domains all use `on`/`off` semantics.

## Recorded history

These tools report recorded Home Assistant facts. They do not establish why an
event happened. Recorder retention, exclusions, purges, and unavailable components
can produce an empty or unavailable result without indicating a bridge failure.

All explicit timestamps must be ISO-8601 with an explicit UTC offset or `Z`.
Naive local timestamps are rejected so DST transitions cannot be interpreted
silently. The default historical window is 24 hours; the default maximum is 7 days.
Results are capped at 500 records and aggregate change queries at 50 candidate
entities by default. Every list reports `returned`, `total_*`, and `truncated`.

### `ha_get_entity_history(entity_id, start, end?, limit?, minimal_response?)`

Use for recorded state boundaries of one known entity: for example, when a door
opened, when a light turned on, or the duration of a state whose ending boundary is
also recorded. The result includes only safe selected attributes and opaque context
IDs where available. A duration is absent when its beginning lies outside the
requested window or its end is not known.

`minimal_response` defaults to true, using Home Assistant's efficient recorder
response while retaining the first/last metadata when supplied by Home Assistant.

### `ha_get_logbook(start, end?, entity_id?, limit?)`

Use for compact recorded activity facts, optionally for one exact entity. Entries
are normalized and messages that could contain URLs or credentials are redacted.
No raw logbook payload or context user ID is returned.

### `ha_get_recent_changes(...)`

Use for questions such as “what changed in the kitchen in the last hour?” It
accepts a relative `duration_minutes`, or explicit `start`/`end`, plus optional
area, floor, domain, and exact entity-ID filters. All filters compose. The bridge
resolves the current candidate entities once and makes a single bulk recorder
history request; it returns chronological state facts, not explanations.

## Whole-home summaries and diagnostics

These tools classify one fresh bulk state snapshot joined to cached registry
metadata. They do not make serial per-entity requests, embed an LLM, expose raw
tracker attributes, or change Home Assistant. List limits default to 25 and are
capped at 100; whole-home section details and attention items are capped at 10.

Classification uses Home Assistant domain, `device_class`, state, unit, and
capabilities before names. A conservative word-boundary name fallback applies only
to otherwise unclassified binary-sensor or cover openings. Unsupported sections
are omitted rather than fabricated.

### `ha_get_home_summary()`

Returns a compact whole-home snapshot with total availability counts and only the
supported sections among occupancy, openings, lighting, climate, environment,
device health, safety, and energy. Sections use counts plus bounded factual details.
`attention_items` is deterministic and explicitly reports truncation.

### `ha_find_unavailable_entities(domain?, area?, floor?, minimum_duration?, limit?)`

Returns entities whose current state is exactly `unavailable`; unknown states are
counted separately. `minimum_duration` is minutes and uses the current state's
timezone-aware `last_changed`. If that evidence is missing or invalid, the entity
is not assumed to meet the duration and the page reports incomplete evidence. No
Recorder result is invented.

### `ha_find_low_batteries(threshold?, area?, floor?, limit?)`

Returns only `sensor` entities with device class `battery`, unit `%`, and a numeric
state from 0 through 100 at or below the threshold. The configured default is 20%.
Charging-state sensors, battery binary sensors, voltage sensors, and name-only
matches are excluded.

### `ha_get_openings(area?, floor?, opening_type?, state?, limit?)`

Classifies doors, windows, garage doors, and other openings. `opening_type` accepts
`door`, `window`, `garage_door`, or `opening`; normalized `state` accepts `open`,
`closed`, `unavailable`, `unknown`, or `any` and defaults to `open`. Cover states
`opening` and `closing` remain physically non-closed and normalize to `open`.

### `ha_get_lights_on(area?, floor?, limit?)`

Returns compact light entities whose current state is exactly `on`, including
resolved location and safe brightness when present. It has no control capability.

### `ha_diagnose_home(limit?)`

Returns deterministic findings with a category, severity, cautious message, and
the Home Assistant state/device-class evidence used. Exact severity rules are:

| Severity | Categories |
| --- | --- |
| `critical` | Active smoke or carbon-monoxide sensor reports |
| `warning` | Unavailable entity, low percentage battery, open garage, active moisture/problem sensor, disconnected connectivity sensor |
| `info` | Unknown entity state, open door, open window, or other open opening |

For binary sensors, smoke, carbon monoxide, moisture, and problem are active when
state is `on`; connectivity is a problem when state is `off`. A finding says only
what Home Assistant reports. It does not prove a physical emergency, explain why a
state occurred, contact emergency services, or trigger an automation.

`BATTERY_WARNING_THRESHOLD` configures the default battery threshold.
`IGNORED_DIAGNOSTIC_ENTITIES` can exclude a small comma-separated set of entity IDs
from all aggregate Phase 4 views without creating a policy/configuration DSL.

Limitations: entity semantics depend on correct Home Assistant device classes;
ignored or disabled entities are not present in the state inventory; and current
`last_changed` evidence may be missing. Classification intentionally prefers an
omission over an aggressive guess.

## Automation intelligence

All Phase 5 tools are read-only. They never execute, enable, disable, create, edit,
reload, or delete an automation and never call a Home Assistant service. Home
Assistant currently requires administrator permission for configuration and trace
commands. The bridge feature-detects unavailable commands and returns structured
limitations.

Automation content is untrusted data. Templates are inspected as text only and
never rendered. Configuration and trace structures are bounded to eight nested
levels, 100 items per collection, and 512 characters per string. Definitions
contain at most 100 nodes; full traces contain at most 200 normalized steps. Each
definition/trace also has a shared 2,000-value and 20,000-text-character budget.

### `ha_list_automations(query?, enabled?, limit?)`

Lists fresh compact metadata from current `automation.*` states: entity ID,
friendly name, enabled/available status, last-triggered timestamp, and mode. Search
uses the deterministic Phase 2 convention: exact entity/object/name matches rank
above prefixes and substrings, with stable name/entity ordering. The default limit
is 25 and hard maximum is 100. Complete configuration is not returned.

### `ha_get_automation(automation)`

Accepts an `automation.object_id` or bare object ID. When Home Assistant supports
`automation/config`, returns a bounded normalized definition with triggers,
conditions, actions, mode, and enabled state. It never returns raw YAML. Loaded
configuration may differ by Home Assistant version, and an automation unavailable
through this command returns explicit availability/limitation metadata.

### `ha_find_automations_for_entity(entity_id, limit?)`

Searches the in-memory reference index for exact trigger/condition `entity_id`
references, action targets/data, device IDs that resolve to the entity's registry
device, and exact entity IDs visible in inert Jinja text. It uses word-bounded
entity-ID matching and does not use broad name substrings.

Dynamic templates, runtime-generated entity IDs, blueprints, variables, area/label
expansion, and indirection can hide references. If any dynamic template or missing/
truncated configuration is present, `complete` is false. A returned reference says
only that configuration refers to the entity; it does not prove the automation ran
or caused a change.

The reference index is process-local, capped at 500 loaded automations, uses the
registry-cache TTL, and is refreshable with
`HomeAssistantClient.refresh_automation_cache()`. It has no database and cannot
remain stale indefinitely.

### `ha_get_automation_traces(automation, limit?)`

Returns only compact recent stored-run metadata from `trace/list`, newest first.
The default is 10 and maximum is 50. No traces is a successful empty result. Home
Assistant normally retains only a small configured number of traces and may clear
them during reloads/restarts, so absence is not proof that an automation never ran.

### `ha_get_automation_trace(automation, run_id)`

Returns one stored trace from `trace/get`, preserving execution order and path
strings such as `action/0`, `condition/0`, nested `choose`, `if`, `parallel`, and
sequence paths. It includes bounded trigger data, result/error/stop evidence,
timestamps, and context/parent IDs. User IDs, raw variables, raw configuration,
messages, commands, URLs, credentials, notification targets, and other secret-like
content are omitted or redacted.

### `ha_find_activity_cause(entity_id, timestamp?, start?, end?, window_seconds?, limit?)`

Accepts either one offset-aware ISO-8601 timestamp with a surrounding window
(default 60 seconds, maximum 600), or an explicit offset-aware start/end range.
It composes the existing Recorder history normalizer, trace contexts, trace
execution facts, and the reference index. It returns evidence records, not causal
prose.

Evidence categories are exact:

| Category | Criteria | Confidence |
| --- | --- | --- |
| `confirmed_by_context` | State context equals a stored automation trace context, or the state's parent context directly equals it. | `confirmed` |
| `trace_confirmed` | An executed `action/...` trace result explicitly contains the entity as an `entity_id` target and the action is within 10 seconds of the state change. | `confirmed` |
| `strong_temporal_match` | A statically referencing automation has a trace inside the window, but no confirming context or executed-target timing proof. | `strong` |
| `possible_reference` | Static configuration references the entity without matching execution evidence. | `possible` |
| `user_origin` | Recorder recorded a user-bearing context; the identifier is omitted. | `confirmed` for origin only |
| `unrelated_or_unknown` | No supported automation evidence was found. | `none` |

The word `confirmed` is never assigned merely because timestamps are near or an
automation references an entity. `user_origin` confirms only that Home Assistant
recorded a user context, not which human or which UI action. Results can be
incomplete when Recorder retention, configuration access, stored traces, or dynamic
templates limit evidence.

## Design rules

New tools must describe a recognizable user goal, expose the smallest useful
schema, normalize every upstream payload, bound arrays, and make partial data
explicit. Do not add a generic REST, WebSocket, or service-call escape hatch.

## Phase 6 internal policy contracts

These are application models, not callable MCP tools:

- `PolicyDecision` carries `allow`, `deny`, or `confirm_required`, operation class,
  reason, matched rule, canonical target, and safe policy metadata.
- `ResolvedTarget` accepts a canonical entity ID, matching domain, canonical
  area/floor IDs, and capability status. It rejects friendly names and other
  untrusted Home Assistant text.
- `ActionRequest` represents an already-resolved internal semantic request. It has
  no caller-spoofable confirmation field.
- `ActionPlan` explicitly lists allowed, denied, and confirmation targets; limit
  results; sanitized predicted service data; ambiguity; and confirmation state.
  It always has `executable: false` and `execution_available: false` in Phase 6.
- `AuditEvent` records policy facts without tokens, authorization data, webhooks,
  URLs, camera streams, command/message content, or other secret-like service data.

The planner denies unknown capabilities, ambiguous targets, missing canonical
targets, excessive targets/operations, value-policy violations, and any policy
failure. It does not perform partial execution and makes no network call.
