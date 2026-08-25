# MCP tool contracts

Phase 1 tools are diagnostic and read-only. They return structured models so an
LLM does not need to parse prose to determine success.

## `ha_connection_status`

Use first when a Home Assistant request fails.

Returns:

- `status`: `connected`, `authentication_failed`, `unreachable`, or `error`;
- `reachable`: whether Home Assistant responded;
- `authenticated`: whether the configured token was accepted;
- `message`: a safe next-step description; and
- `error_code`: a stable machine-readable code when a failure occurred.

The result never includes a URL, token, authorization header, raw response, or
stack trace.

## `ha_server_info`

Returns:

- `available` and a safe message;
- `server.version`;
- `server.time_zone`; and
- string fields from `server.unit_system`.

It deliberately excludes latitude, longitude, location name, configuration
directories, loaded components, external directories, allowlists, entity data,
and all unknown fields.

## Tool design rules

Future tools should describe a recognizable user goal, expose the smallest useful
schema, and return normalized data. Do not add a generic REST/WebSocket/service
caller. Tool descriptions should tell an LLM when to use the tool, what it returns,
and important limits.

