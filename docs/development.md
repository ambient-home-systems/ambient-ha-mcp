# Development

## Prerequisites

- Python 3.12 or newer
- `uv`
- Docker with Compose (optional)
- Node.js only if using MCP Inspector

## Set up

```bash
cp .env.example .env
uv sync --all-extras
```

Create a dedicated Home Assistant long-lived access token and place it only in
the untracked `.env` file.

## Run

```bash
uv run ambient-ha-mcp
```

- MCP: `http://127.0.0.1:8000/mcp`
- health: `http://127.0.0.1:8000/health`

## Quality checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Normal tests use `httpx.MockTransport` and in-memory MCP clients; they never need
a real Home Assistant installation. Discovery fixtures deliberately keep entity
states and registry rows separate so tests exercise the same join rules as the
production adapters.

To opt into the real integration smoke test:

```bash
RUN_HA_INTEGRATION_TESTS=1 uv run pytest -m integration
```

The real test uses the same `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN`
variables. Never put those values in test code or CI repository variables unless
the CI environment and secret permissions have been reviewed.

The integration test exercises only authenticated REST/WebSocket reads: connection,
server metadata, registries and cache refresh, all 24 MCP tools, a small Recorder/
logbook window, Phase 4 views, automation discovery/traces where supported, and
privacy inspection against representative raw attributes. It checks results in
memory and never prints the configured URL, token, raw registry, automation
content, trace content, private attribute values, or user identifier. It never
executes an automation or service.

### Phase 3.5 live-validation status

Phase 3.5 remains blocked solely because `HOME_ASSISTANT_URL` and
`HOME_ASSISTANT_TOKEN` were unavailable in the validation runtime. Repository,
unit, protocol, lint, type, and package checks passed, but this is not a claim of
production validation against a real Home Assistant installation.

Phase 5 live validation is likewise outstanding when those variables are absent.
Phase 5 configuration and trace enrichment currently requires a Home Assistant
administrator token; use a dedicated validation account and keep the test opt-in.

Phase 6 policy tests are entirely local and do not need Home Assistant credentials.
The Phase 3.5–6 live read-only validation limitation remains outstanding when the
variables are absent; this is not a claim of real-installation validation.

Phase 6.5 adds a mandatory pre-write gate. When credentials are absent or any live
REST, WebSocket, registry, privacy, cache, historical, automation, or MCP-protocol
check fails, the result is `NO-GO FOR PHASE 7`. Passing local tests alone cannot
produce a go decision. See `docs/phase-6-5-validation.md`.

## Home Assistant App development

App metadata lives in `homeassistant-addon/`, and `repository.yaml` makes the GitHub
repository discoverable as a custom App repository. The root Dockerfile remains the
single image build context. Its launcher preserves standalone behavior unless
`AMBIENT_RUNTIME_MODE=home_assistant_app` is set by Supervisor.

App mode reads `/data/options.json`, accepts only documented non-secret settings,
requires `SUPERVISOR_TOKEN`, uses `http://supervisor/core`, and always forces
read-only operation. App runtime also supplies Supervisor's distinct
`ws://supervisor/core/websocket` endpoint instead of standalone `/api/websocket`
derivation. Because Supervisor makes that options document root-only, the
image bootstrap reads it before dropping groups, GID, and UID to the fixed
`ambient` account; the server then starts unprivileged. Compose starts as `ambient`
directly. Tests validate bootstrap ordering, safe version ordering, architecture
metadata, disabled network exposure, denied privileges, missing-token failure,
option bounds, and default policy denial.

The Home Assistant workflow uses the current official multi-architecture builder
actions. Pull requests lint metadata and build `amd64`/`aarch64` images without
publishing. Merging source code does not publish or advertise an App update.
An immutable `vMAJOR.MINOR.PATCH` tag publishes only that version and verifies its
multi-architecture manifest. A later, separate catalog-promotion PR may update
`homeassistant-addon/config.yaml`; CI rejects that PR unless both advertised
platforms are already pullable. Follow [the App release procedure](releasing.md)
exactly. Never combine image publication and catalog promotion in one commit or PR.

For a full App validation, add the repository to a disposable or approved Home
Assistant OS/Supervised host, install the App, leave its port disabled for startup,
verify container/log health, then temporarily assign a local port and test all 24
tools with MCP Inspector. Remove the port mapping afterward. Never publish it.

## Policy-security implementation notes

- `READ_ONLY=true` is the outer hard boundary. A non-read plan is considered only
  when both the environment value and an optional policy file set read-only false.
  Phase 6 still has no executor or write-capable client path in that state.
- Copy `policy.example.toml`, edit exact canonical IDs only, and set `POLICY_FILE`
  to its absolute path. The file is strict TOML: unknown keys or invalid values
  fail startup instead of being ignored.
- Precedence is hard read-only → hard administrative prohibition → protected
  entity → entity → domain → operation class → global default.
- Protected entities may deny or require confirmation, never allow.
- The planner authorizes only targets already resolved to canonical entity IDs.
  Ambiguous display-name matches require clarification; capability uncertainty,
  target/operation limits, or policy exceptions deny the plan.
- Value checks reject rather than clamp climate, media, light, and fan inputs.
- Confirmation is an unverified server-challenge model only. There is no
  `confirmed=true` shortcut and no issuer/verifier in Phase 6.
- `AuditEvent.safe_json()` recursively bounds and redacts private values. New audit
  fields must receive adversarial redaction tests before use.
- Area/floor IDs are present on targets for future integration, but location policy
  rules are deferred and must never use arbitrary display-name matching.

Useful focused checks:

```bash
uv run pytest tests/unit/test_policy_core.py \
  tests/unit/test_policy_config.py tests/unit/test_policy_planning.py
uv run mypy
```

## Discovery implementation notes

- Current states come from `GET /api/states` or `GET /api/states/{entity_id}` and
  are never cached.
- Entity, device, area, and floor registries come from authenticated Home Assistant
  WebSocket registry-list commands.
- Registry snapshots use `REGISTRY_CACHE_TTL_SECONDS` (default 60, allowed 5–3600).
- `HomeAssistantClient.refresh_discovery_cache()` invalidates the snapshot for
  programmatic callers; the next request reloads all registries.
- Unknown area/floor registry commands are represented as unsupported features.

## Historical implementation notes

- History uses Home Assistant's official `GET /api/history/period/<timestamp>`
  endpoint with entity filters; aggregate changes use one batched history request.
- Logbook uses the official `GET /api/logbook/<timestamp>` endpoint.
- Tool timestamps must be ISO-8601 with an explicit UTC offset or `Z`; naive time
  is rejected to avoid ambiguous local/DST behavior.
- `HISTORY_DEFAULT_LOOKBACK_HOURS` defaults to 24 and
  `HISTORY_MAX_LOOKBACK_HOURS` defaults to 168. `HISTORY_MAX_EVENTS` defaults to
  500, `HISTORY_DEFAULT_LIMIT` defaults to 100, and `HISTORY_MAX_ENTITIES` defaults
  to 50.
- Recorder exclusions, retention/purges, disabled Recorder, and unavailable
  logbook data are normal conditions represented by structured results.

## Whole-home diagnostic implementation notes

- `BATTERY_WARNING_THRESHOLD` defaults to 20 percent and accepts 1–100.
- `IGNORED_DIAGNOSTIC_ENTITIES` is an optional comma-separated entity-ID list
  excluded from all aggregate Phase 4 views.
- Every Phase 4 tool performs one bulk state read and one cache lookup; it makes no
  serial per-entity state calls.
- Unavailable-duration filtering uses the current state's timezone-aware
  `last_changed`. Missing or invalid evidence is reported as incomplete and the
  affected entity is not assumed to meet the requested duration.
- Array limits default to 25 and are capped at 100. Home-summary details are capped
  at 10 per section and 10 attention items.

## Automation intelligence implementation notes

- Current automation metadata comes from fresh `GET /api/states` reads.
- Loaded definitions come from Home Assistant Core's read-only, admin-gated
  `automation/config` WebSocket command.
- Stored traces come from the read-only, admin-gated `trace/list`, `trace/get`, and
  `trace/contexts` WebSocket commands. Unknown commands produce feature-local
  unsupported results.
- The reference catalog is capped at 500 loaded automations, expires using
  `REGISTRY_CACHE_TTL_SECONDS`, and can be invalidated with
  `HomeAssistantClient.refresh_automation_cache()`.
- Automation results default to 25 and cap at 100; trace lists default to 10 and
  cap at 50; normalized trace details cap at 200 steps. Nested values cap at eight
  levels, 100 collection items, and 512-character strings, plus a shared 2,000-value
  / 20,000-text-character normalization budget per definition or trace.
- Static template discovery uses exact word-bounded entity IDs. Jinja is never
  rendered or executed, and any dynamic template makes completeness false.
- Causality confirmation is intentionally narrow. Direct context/parent linkage
  confirms a Home Assistant relationship. Trace confirmation additionally requires
  an executed `action/...` step with an explicit entity target within 10 seconds of
  the recorded state change. Timing plus a static reference is never confirmed.

Official sources reviewed for this implementation:

- [Home Assistant WebSocket API](https://developers.home-assistant.io/docs/api/websocket/)
- [Home Assistant context and permissions](https://developers.home-assistant.io/docs/auth_permissions/#the-context-object)
- [Home Assistant automation configuration command](https://github.com/home-assistant/core/blob/dev/homeassistant/components/automation/__init__.py)
- [Home Assistant trace WebSocket commands](https://github.com/home-assistant/core/blob/dev/homeassistant/components/trace/websocket_api.py)
- [Home Assistant trace models](https://github.com/home-assistant/core/blob/dev/homeassistant/components/trace/models.py)
- [Home Assistant stored-trace configuration](https://www.home-assistant.io/docs/automation/yaml/#number-of-debug-traces-stored)
- [Home Assistant App repository](https://developers.home-assistant.io/docs/apps/repository/)
- [Home Assistant App configuration](https://developers.home-assistant.io/docs/apps/configuration/)
- [Home Assistant App communication](https://developers.home-assistant.io/docs/apps/communication/)
- [Home Assistant App security](https://developers.home-assistant.io/docs/apps/security/)
- [Home Assistant App testing](https://developers.home-assistant.io/docs/apps/testing/)

These source-level WebSocket contracts are version-sensitive. Keep feature
detection and normalized unsupported results when updating them; do not substitute
filesystem scraping, `.storage` access, or unsupported write endpoints.

## Dependency changes

Edit `pyproject.toml`, then regenerate and review the cross-platform lock:

```bash
uv lock
uv sync --frozen --all-extras
```

The Docker build uses `uv sync --frozen` so its dependency graph must match the
committed lock file.

## Docker

```bash
docker build -t ambient-ha-mcp .
docker compose up --build
```

Compose mounts no source or secret files into the image; it passes `.env` values
as process environment variables and publishes only to loopback.
