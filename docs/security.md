# Security

## Current posture

This release is a local/private, read-only foundation. It does not implement
bridge OAuth, user management, service execution, device control, Home Assistant
administration, or supported public-internet exposure.

## Credentials

Set `HOME_ASSISTANT_TOKEN` at runtime. The settings model stores it as a Pydantic
`SecretStr`; code reveals it only when constructing the Home Assistant
`Authorization` header. The token is never part of a tool result or exception.

Do not commit:

- `.env` or alternate environment files;
- Home Assistant long-lived access tokens;
- passwords, OAuth credentials, certificates, or API keys;
- private Home Assistant URLs or exported configurations; or
- diagnostic output that contains private entity or location data.

If a token is committed, revoke it in Home Assistant immediately, rotate it, and
remove it from repository history using an appropriate secret-removal process.

## Least privilege

Home Assistant long-lived tokens inherit the permissions of their user. Create a
dedicated Home Assistant user for the bridge and grant no more access than the
deployment requires. The bridge performs authenticated REST `GET` requests and
read-only WebSocket registry commands only.

## Data minimization

The upstream `/api/config` response can include precise location and filesystem
information. The bridge allowlists only version, time zone, and unit-system data.
Do not return raw configuration objects from new tools.

Search, area, floor, and domain results contain compact entity/location metadata
and current state only. `ha_get_entity` uses a strict attribute allowlist intended
for useful device measurements and operating state. It excludes token, secret,
credential, URL, camera/stream, media-content, GPS, latitude, longitude, and
location-bearing keys, and rejects URL-like values. Attribute counts, string
lengths, and nested collections are bounded.

Entity state is never cached. Entity, device, area, and floor registry metadata is
cached in one in-process snapshot for `REGISTRY_CACHE_TTL_SECONDS` (60 seconds by
default), reducing access frequency without persisting household metadata.

## Logs

Application logs are structured JSON with timestamp, level, logger, message, and
optional exception information. Bearer values and common credential assignments
are redacted as defense in depth. Code must still avoid logging request headers,
environment dumps, raw Home Assistant responses, or URLs containing secrets.

## Network and transport

- MCP Host and Origin allowlists enable DNS-rebinding protection.
- Docker Compose binds to `127.0.0.1` by default.
- The container runs without root, Linux capabilities, or a writable root
  filesystem.
- `/health` is unauthenticated by design and returns only coarse readiness flags.
- Do not add a public hostname to the allowlist as a substitute for authentication.

## Future controls

Before adding any write tool, the project must have authenticated bridge users,
server-side authorization, narrow tool schemas, explicit sensitive-operation
classification, audit logging, replay/rate protections where appropriate, and
tests proving fail-closed behavior. MCP-host confirmations are helpful UX, but
they are not the authorization boundary.

## Reporting

Do not open a public issue containing a live credential or private Home Assistant
data. Revoke exposed credentials before sharing a minimized reproduction.
