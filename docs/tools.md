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

## Design rules

New tools must describe a recognizable user goal, expose the smallest useful
schema, normalize every upstream payload, bound arrays, and make partial data
explicit. Do not add a generic REST, WebSocket, or service-call escape hatch.
