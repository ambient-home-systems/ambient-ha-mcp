# MCP tool contracts

All tools are read-only and return structured models. Errors use stable codes and
safe messages; normal not-found and unsupported-feature outcomes are represented
in the result rather than raised as generic failures.

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

## Design rules

New tools must describe a recognizable user goal, expose the smallest useful
schema, normalize every upstream payload, bound arrays, and make partial data
explicit. Do not add a generic REST, WebSocket, or service-call escape hatch.
