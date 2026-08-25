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
discovery, a small entity-history query, a small logbook query, a small
recent-change query, and all Phase 4 whole-home diagnostic views. It skips cleanly
when opt-in is absent and never prints the configured URL or token.

### Phase 3.5 live-validation status

Phase 3.5 remains blocked solely because `HOME_ASSISTANT_URL` and
`HOME_ASSISTANT_TOKEN` were unavailable in the validation runtime. Repository,
unit, protocol, lint, type, and package checks passed, but this is not a claim of
production validation against a real Home Assistant installation.

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
