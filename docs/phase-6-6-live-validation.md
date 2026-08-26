# Phase 6.6 sanitized live-validation report

Use this template on a real Home Assistant OS or supported Supervised installation.
It is deliberately read only. Do not run a service, script, scene, automation,
device control, configuration write, registry write, or Home Assistant restart.

Do not paste the Home Assistant URL, `SUPERVISOR_TOKEN`, access tokens, coordinates,
camera URLs, raw registries, complete attributes, automation definitions, traces,
user identifiers, webhook IDs, notification content, or other private values into
this report. Record counts, availability, and pass/fail results only.

## Current observed status

Version `0.6.6` installs, starts, remains running, and authenticates successfully
through the Supervisor REST proxy on Home Assistant `2026.8.3`. Live
`ha_list_areas` validation exposed a WebSocket routing defect: standalone
`/api/websocket` derivation produced the wrong Supervisor proxy path. Version
`0.6.7` explicitly configures `ws://supervisor/core/websocket`. Upgrade and
WebSocket/live-tool retesting remain outstanding, so the gate remains closed.

## Operator preflight

- [ ] Home Assistant OS or supported Supervised installation
- [ ] Architecture is `amd64` or `aarch64`
- [ ] Custom repository added:
      `https://github.com/ambient-home-systems/ambient-ha-mcp`
- [ ] Ambient App version `0.6.7` offered
- [ ] No Home Assistant token field appears in App configuration
- [ ] App port remains disabled during initial startup
- [ ] No router forwarding, public DNS, tunnel, or public reverse proxy configured

## Environment

| Field | Sanitized result |
| --- | --- |
| Validation date | |
| Home Assistant version | |
| Installation type | OS / Supervised |
| Host architecture | amd64 / aarch64 |
| Ambient version | 0.6.7 |
| App repository visible | PASS / FAIL |
| Versioned image pulled | PASS / FAIL |

## Installation and startup

1. Install **Ambient Home Assistant MCP** from the custom App repository.
2. Leave `8000/tcp` disabled and start the App.
3. Confirm the App remains running for at least two minutes.
4. Inspect the App log. Record only the outcome or sanitized error category.
5. Temporarily map an unused trusted-LAN host port to container port `8000/tcp`.
6. Add only the exact client hostname/IP and its `<hostname-or-IP>:*` form to
   `mcp_allowed_hosts`.
7. Request `http://<trusted-home-assistant-host>:<mapped-port>/health`.

| Check | Result | Safe note |
| --- | --- | --- |
| Installation | PASS / FAIL | |
| Initial start | PASS / FAIL | |
| Remained running | PASS / FAIL | |
| Supervisor authentication | PASS / FAIL | Do not include the token |
| Home Assistant connected | PASS / FAIL | Do not include the URL |
| Health response | PASS / DEGRADED / FAIL | |
| REST available | PASS / FAIL | |
| WebSocket available | PASS / FAIL | |
| HA version returned | PASS / FAIL | |
| Time zone returned | PASS / FAIL | Do not record precise location if sensitive |
| Unit system returned | PASS / FAIL | |

## Safe registry aggregates

Do not paste registry entries.

| Registry | Supported | Count | Result |
| --- | --- | ---: | --- |
| Entity | yes / no | | PASS / FAIL |
| Device | yes / no | | PASS / FAIL |
| Area | yes / no | | PASS / FAIL |
| Floor | yes / no | | PASS / CLEANLY UNSUPPORTED / FAIL |

Where naturally present, verify entity-to-device, entity-to-area, device-to-area,
and area-to-floor resolution internally. Record only PASS, NOT PRESENT, or FAIL.
Do not manufacture an entity-level area override.

## MCP Inspector

Temporarily expose the local port as described above, then run:

```bash
npx @modelcontextprotocol/inspector@latest
```

Connect Inspector to `http://<trusted-home-assistant-host>:<mapped-port>/mcp`.
Confirm exactly 24 tools. Derive entity, area, floor, domain, automation, and trace
inputs from real discovery results instead of assuming identifiers.

Use these result categories:

- `PASS`: a supported call returned a valid bounded response.
- `PASS — EMPTY`: the call succeeded but the installation has no matching data.
- `CLEANLY UNSUPPORTED`: Ambient returned a structured feature limitation.
- `FAIL`: an unexpected error, unbounded response, or incorrect result occurred.

| Tool | Result | Safe note |
| --- | --- | --- |
| `ha_connection_status` | | |
| `ha_server_info` | | |
| `ha_get_entity` | | |
| `ha_search_entities` | | |
| `ha_list_areas` | | |
| `ha_get_area` | | |
| `ha_list_floors` | | |
| `ha_get_floor` | | |
| `ha_domain_summary` | | |
| `ha_get_entity_history` | | |
| `ha_get_logbook` | | |
| `ha_get_recent_changes` | | |
| `ha_get_home_summary` | | |
| `ha_find_unavailable_entities` | | |
| `ha_find_low_batteries` | | |
| `ha_get_openings` | | |
| `ha_get_lights_on` | | |
| `ha_diagnose_home` | | |
| `ha_list_automations` | | |
| `ha_get_automation` | | |
| `ha_find_automations_for_entity` | | |
| `ha_get_automation_traces` | | |
| `ha_get_automation_trace` | | |
| `ha_find_activity_cause` | | |

## History and diagnostics

Use existing entities and recorded activity. Do not create a state change for the
test.

| Check | Result | Safe note |
| --- | --- | --- |
| State transitions and timestamps | | |
| Empty-history handling | | |
| Recorder exclusion handling | | |
| Proven duration behavior | | |
| Recent changes | | |
| Battery percentage classification | | No voltage/charging false positives |
| Door/window/garage classification | | |
| Unknown/unavailable handling | | |
| Lights-on aggregation | | |
| Temperature/humidity handling | | |
| Safety/problem classifications | | Do not activate sensors |

## Automation intelligence and Supervisor permissions

Never trigger an automation to create test evidence. Dynamic-template limitations
and an absence of stored traces are not failures by themselves.

| Interface | Result | Permission/availability note |
| --- | --- | --- |
| Automation listing | | |
| Configuration retrieval | | |
| Static reference index | | |
| Trace listing | | |
| Trace retrieval | | |
| Trace contexts | | |
| Activity-cause evidence | | |

If Supervisor authentication can read ordinary states but an administrator-gated
automation command is denied, record `CLEANLY UNSUPPORTED — PERMISSION` and the
sanitized error category. Do not add or return a personal administrator token.

## Privacy comparison

Select at least one entity with a rich attribute set in Home Assistant Developer
Tools and compare it internally with the normalized MCP entity. Do not copy the raw
values here.

| Sensitive class | Present in raw source | Excluded from MCP | Result |
| --- | --- | --- | --- |
| Coordinates/location details | yes / no | yes / no | |
| Device-tracker details | yes / no | yes / no | |
| Camera/stream URLs | yes / no | yes / no | |
| Tokens/credentials/authorization | yes / no | yes / no | |
| Webhook identifiers | yes / no | yes / no | |
| Notification targets/messages | yes / no | yes / no | |
| User identifiers | yes / no | yes / no | |
| Private URLs | yes / no | yes / no | |
| Automation secret-like content | yes / no | yes / no | |
| Safe measurements retained | yes / no | yes / no | |

Any sensitive value reaching MCP is a material failure. Stop validation and report
only its field class, affected tool, and entity domain—not the value.

## Response bounds

| Surface | Bounded | Truncation metadata correct | Result |
| --- | --- | --- | --- |
| Entity search/inventory | | | |
| History/logbook | | | |
| Diagnostics | | | |
| Automation definitions | | | |
| Automation traces | | | |

## Restart, upgrade, and rollback

Restart only the Ambient App—not Home Assistant—and verify reconnection, registry
cache repopulation, health, and MCP recovery.

| Check | Result | Safe note |
| --- | --- | --- |
| Ambient App restart | | |
| Reconnected to Home Assistant | | |
| Registry cache repopulated | | |
| MCP recovered | | |
| Upgrade | DEFERRED unless a corrected version is required | |
| Rollback | DOCUMENTED / OPERATOR-APPROVED TEST / NOT RUN | |

No meaningless version is published solely to test an upgrade. The supported
non-destructive rollback is restoration of a Home Assistant backup containing the
prior App version or installation of a previously published version from an
approved test repository.

## Sanitized issues

For each failure record only:

- affected check/tool;
- Ambient and Home Assistant versions;
- architecture and installation type;
- sanitized error category/message;
- whether the failure is repeatable; and
- whether other read-only functions still work.

Do not attach full App logs until they have been reviewed and redacted.

## Gate decision

- [ ] Real App installation succeeded.
- [ ] Supervisor authentication, REST, and WebSocket succeeded.
- [ ] Representative Phase 1–5 tools succeeded.
- [ ] Real raw-versus-normalized privacy inspection passed.
- [ ] Hard read-only regression tests passed.
- [ ] Source review found no write path.
- [ ] No unresolved critical/high security defect exists.

If every required item passes, the reviewed result may be `GO FOR PHASE 7`.
Otherwise the required result remains:

**NO-GO FOR PHASE 7 — live Home Assistant validation outstanding.**

After testing, remove the host-port mapping and any temporary MCP Host allowlist
entries. Do not begin Phase 7 from this report alone; return it for review.
