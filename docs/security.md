# Security

## Current posture

This release is a local/private, read-only foundation. It does not implement
bridge OAuth, user management, service execution, device control, Home Assistant
administration, or supported public-internet exposure.

Phase 6 adds authorization and write-preparation architecture only. It introduces
no MCP write tool, Home Assistant service-call path, central executor, confirmation
verification endpoint, or persistent audit store. Dry-run plans always state that
execution is unavailable.

## Security objectives

- Keep Ambient MCP—not the MCP client and not Home Assistant credentials—the
  authoritative policy boundary.
- Require semantic target resolution to canonical entity IDs before authorization.
- Deny on ambiguity, unknown capabilities, malformed configuration, policy errors,
  and limit violations.
- Make partial authorization explicit and prevent silent subset execution.
- Bound control values and request size without silently changing the request.
- Treat all Home Assistant names, descriptions, templates, traces, and action data
  as untrusted data.
- Minimize and redact credentials and private action data in tool results, plans,
  exceptions, logs, and audit records.

## Trust boundaries

**ChatGPT / MCP client:** potentially mistaken, compromised, or influenced by
malicious content. Client-side confirmation and tool annotations are useful
additional defenses, never authorization.

**Ambient MCP:** the application authorization and safety boundary. Policy uses
typed operation data, canonical identifiers, validated configuration, and server
state—not natural-language instructions found in Home Assistant.

**Home Assistant:** trusted as the upstream automation system, while its entity,
registry, automation, template, and trace content is untrusted data from the MCP
and LLM perspective.

**Home Assistant credential:** supplies upstream permissions only. It does not
grant the MCP client or Ambient MCP any operation. An administrator-capable token
required for automation trace reads does not enable administrative MCP behavior.

## Threat model

Phase 6 tests and design address malicious or accidental LLM tool calls; prompt
injection in entity, area, floor, automation, script, scene, template, and trace
content; ambiguous or duplicate target names; dangerous switches; protected locks,
alarms, covers, valves, and utility equipment; opaque scene/script effects; mass
selection; giant target lists; request floods at the per-request bound; malformed
or contradictory policy; precedence and case-normalization bypasses; authorization
before target resolution; credential and service-data leakage; privilege confusion;
and attempted generic service or Home Assistant administrative actions.

The current controls do not authenticate public users, rate-limit a public service,
verify confirmations, inspect complete scene/script effects, or execute actions.
Those omissions are explicit: public exposure and all writes remain unsupported.

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

Phase 5 configuration and trace enrichment may require an administrator-capable
Home Assistant account. **Home Assistant administrator credentials do not grant
administrative permission to the MCP client.** Upstream capability and Ambient
authorization are separate. Phase 6 hard-denies administrative operations without
consulting token privilege.

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

Historical Recorder and logbook data uses the same attribute allowlist and URL/
credential filtering as current entity data. Logbook messages containing URL or
credential-like material are redacted. Historical data is never cached. Query
bounds limit default retention reads to 24 hours, at most 7 days, 500 returned
records, and 50 aggregate candidate entities by default.

Whole-home diagnostics operate on the same normalized inventory. Presence can be
counted or represented by a compact entity state, but raw `device_tracker`
attributes, latitude, longitude, GPS accuracy, and routes are never returned.
Summary details default to 10 items and diagnostic/list tools are capped at 100.

Safety findings are sensor-state reports, not declarations about physical reality.
The server never claims that an active smoke, carbon-monoxide, moisture, or problem
sensor proves an emergency, and it cannot contact emergency services.

Automation configuration and trace data are especially sensitive. Phase 5:

- reads loaded definitions and stored traces only through authenticated Home
  Assistant WebSocket commands and never reads `automations.yaml` or `.storage`;
- treats aliases, descriptions, templates, trigger values, action data, URLs, and
  messages as untrusted data, never instructions;
- never renders or executes Jinja and never executes services, scripts, scenes,
  automations, trace debugging, or breakpoints;
- recursively bounds returned structures and redacts URL values, webhook IDs,
  authorization/credential/secret/token/password/API-key fields, message/title/
  command content, notification targets, and shell-command targets; and
- uses context IDs internally while omitting Home Assistant context user IDs.
  A user-bearing context is represented only as `origin: user`.

Secret filtering is defense in depth, not permission to store credentials inside
automation text. Users should keep secrets in Home Assistant's supported secret
facilities and avoid embedding credentials in descriptions, messages, or URLs.

Automation configuration and trace commands require a Home Assistant administrator
in current Core. A valid non-admin token may be sufficient for ordinary state reads
but unable to use Phase 5 enrichment; that limitation is returned without enabling
any broader interface.

## Logs

Application logs are structured JSON with timestamp, level, logger, message, and
optional exception information. Bearer values and common credential assignments
are redacted as defense in depth. Code must still avoid logging request headers,
environment dumps, raw Home Assistant responses, or URLs containing secrets.

Phase 6 audit events use the same principle with recursive, bounded sanitization.
Authorization headers, tokens, passwords, API keys, webhook values, URLs, camera
streams, commands, shell data, notification/message content, and credential-like
keys are redacted. The audit sink is an abstraction with an optional structured-log
implementation; no database or append-only file store is introduced.

## Network and transport

- MCP Host and Origin allowlists enable DNS-rebinding protection.
- Docker Compose binds to `127.0.0.1` by default.
- The container runs without root, Linux capabilities, or a writable root
  filesystem.
- `/health` is unauthenticated by design and returns only coarse readiness flags.
- Do not add a public hostname to the allowlist as a substitute for authentication.

## Ambient authorization model

Policy outcomes are exactly `allow`, `deny`, or `confirm_required`. Operation
classes are `read`, `normal_control`, `climate_control`, `sensitive_control`,
`scene_execution`, `script_execution`, and `administrative`.

The shipped defaults are conservative:

| Scope | Default |
| --- | --- |
| Read | Allow |
| Light, fan | Allow when hard read-only is eventually disabled |
| Media player | Allow subject to volume bounds |
| Climate | Allow subject to temperature and HVAC-mode bounds |
| Switch | Deny unless an exact entity is explicitly authorized |
| Cover | Confirmation required; garage covers should normally be protected/denied |
| Scene | Confirmation required because effects may be opaque |
| Script | Deny unless an exact canonical entity is explicitly authorized later |
| Lock, alarm control panel, valve | Deny |
| Automation execution/editing and HA administration | Hard deny |

These rule defaults do not make Phase 6 capable of execution. `READ_ONLY=true`
still denies all non-read planning, and no writer exists.

### Policy precedence

Precedence is deterministic: hard read-only, hard administrative prohibition,
protected entity, explicit entity rule, domain rule, operation-class rule, global
default. A broad allow cannot override a more specific deny. Protected entities
may only deny or require confirmation; configuration cannot mark them allowed.

Policy configuration is strict TOML selected by `POLICY_FILE`. Unknown keys,
decisions, operation classes, malformed entity IDs, negative/excessive limits,
invalid ranges, contradictory minimum/maximum bounds, and attempts to deny the
READ operation fail configuration loading. Entity/domain keys are trimmed and
case-normalized, and duplicates after normalization are rejected.

Hard read-only is fail-safe across two sources: non-read planning is possible only
when both `READ_ONLY=false` and the policy file has `read_only=false`. With no
policy file, the file-level default remains true.

### Target and mass-action boundary

The required order is intent → semantic resolution → canonical entity IDs →
capability validation → policy. Display names are not policy inputs. Canonical
`domain.object_id` syntax is validated and the supplied domain must match the ID.
Unknown or unsupported capability fails closed. Ambiguous candidates produce a
clarification-required plan and are never guessed.

Defaults allow at most 20 entities per action and 10 operations per request. A
limit violation denies the entire plan. Mixed plans explicitly list allowed,
denied, and confirmation targets; any denied target makes the overall plan deny.

### Value policy

Typed checks cover Celsius/Fahrenheit climate ranges, allowed HVAC modes, light
brightness and color-temperature ranges, media volume, and fan percentage. Inputs
outside schema or policy bounds are rejected, never clamped. Default policy limits
are documented in `policy.example.toml` and are configurable only through the
validated schema.

### Scripts, scenes, and sensitive domains

Names do not establish safety. A script named “Safe Bedroom Light” can perform
arbitrary services; scripts therefore default to deny. Scenes can affect an opaque
set of locks, covers, switches, or climate entities and default to confirmation
required. Switches default to deny because their real-world functions vary widely.
Locks, alarms, valves, and administration default to deny. Exact protected entity
rules provide a higher-precedence deny/confirmation boundary.

### Prompt injection

Entity friendly names, area/floor names, automation aliases/descriptions, script
or scene names, Jinja, trace/action messages, and state text are never interpreted
as policy or confirmation. The policy request schema rejects those fields. It
accepts only canonical IDs, typed operation/value data, capability facts, and
validated server configuration. Jinja remains inert and is never executed.

### Confirmation model

`confirm_required` produces a scoped `required_unverified` confirmation requirement
with a correlation ID and a future server-verifiable challenge concept. No model
accepts a caller-supplied `confirmed=true` flag. Phase 6 has no confirmation issuer,
verifier, or executor, so confirmation cannot cause an action. A later phase must
define expiration, replay protection, identity binding, and server verification.

### Known limitations

- Area/floor IDs are carried in resolved targets, but area/floor policy rules are
  deferred to avoid fragile display-name matching.
- Scene and script effects are not introspected and remain opaque.
- Confirmation verification, bridge-user identity, replay protection, durable
  audit storage, and request-rate enforcement are not implemented.
- Live Home Assistant validation has not run because credentials were unavailable.
- There is intentionally no write path to validate in Phase 6.

## Reporting

Do not open a public issue containing a live credential or private Home Assistant
data. Revoke exposed credentials before sharing a minimized reproduction.
