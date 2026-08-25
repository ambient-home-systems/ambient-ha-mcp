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

## Discovery implementation notes

- Current states come from `GET /api/states` or `GET /api/states/{entity_id}` and
  are never cached.
- Entity, device, area, and floor registries come from authenticated Home Assistant
  WebSocket registry-list commands.
- Registry snapshots use `REGISTRY_CACHE_TTL_SECONDS` (default 60, allowed 5–3600).
- `HomeAssistantClient.refresh_discovery_cache()` invalidates the snapshot for
  programmatic callers; the next request reloads all registries.
- Unknown area/floor registry commands are represented as unsupported features.

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
