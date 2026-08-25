# Ambient Home Assistant MCP

Ambient Home Assistant MCP is a secure, semantic bridge that gives ChatGPT and
other MCP clients purpose-built access to Home Assistant. It is the server
foundation for the future user-facing **Ambient Home Assistant** application.

> **Phase 1 status:** foundational, local/private, and read-only. This release
> exposes connection diagnostics and a safe subset of server metadata. It cannot
> control devices or change Home Assistant.

## What it is—and what it is not

The bridge is an abstraction and security layer. Over time, it can choose among
Home Assistant REST, WebSocket, and native MCP/Assist interfaces while presenting
small, semantic tools to the model.

It is **not**:

- a replacement for Home Assistant;
- an unrestricted Home Assistant administrator API;
- a generic API wrapper exposed to an LLM; or
- a reverse proxy for Home Assistant's `/api/mcp` endpoint.

## Architecture

```mermaid
flowchart TD
    C[ChatGPT or MCP client] -->|MCP| A[Ambient Home Assistant MCP]
    A --> T[Semantic tools]
    A --> P[Policy and security]
    A --> N[Normalized data and diagnostics]
    T --> H[Home Assistant client facade]
    P --> H
    N --> H
    H --> R[REST API]
    H -. future .-> W[WebSocket API]
    H -. selective future use .-> M[HA MCP or Assist API]
```

MCP tools never make raw HTTP requests. They depend on `HomeAssistantClient`,
which owns interface selection and immediately normalizes upstream responses.
See [the architecture decision record](docs/architecture.md).

## Phase 1 capabilities

| Surface | Purpose |
| --- | --- |
| `ha_connection_status` | Reports reachability and authentication state without exposing credentials. |
| `ha_server_info` | Returns only version, time zone, and unit-system metadata. |
| `GET /health` | Reports application liveness and separate Home Assistant readiness. |

No service calls, state changes, or administrative endpoints are implemented.

## Security model

- Home Assistant tokens come only from runtime configuration and use Pydantic
  secret types.
- Logs are structured and redact bearer tokens and common credential fields.
- Raw `/api/config` data is reduced to an allowlisted model before it can reach a
  tool result.
- MCP transport Host and Origin allowlists protect against DNS rebinding.
- The Phase 1 policy engine allows reads and fails closed for every control class.
- The container runs as a non-root user with a read-only filesystem in Compose.

Never commit `.env`, Home Assistant tokens, credentials, private URLs, or
certificates. See [Security](docs/security.md) before any deployment work.

## Quick start

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
# Edit .env and provide HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN.
uv sync --all-extras
uv run ambient-ha-mcp
```

The Streamable HTTP MCP endpoint is `http://127.0.0.1:8000/mcp`; health is at
`http://127.0.0.1:8000/health`.

Inspect the tools locally:

```bash
npx @modelcontextprotocol/inspector@latest
```

Then connect the Inspector to `http://127.0.0.1:8000/mcp`.

## Development commands

```bash
uv sync --all-extras          # install
uv run ambient-ha-mcp         # run locally
uv run pytest                 # unit tests; real HA tests skip by default
uv run ruff check .           # lint
uv run ruff format --check .  # formatting check
uv run mypy                   # type check
docker build -t ambient-ha-mcp .
docker compose up --build
```

Regenerate the dependency lock after an intentional dependency change:

```bash
uv lock
```

## Docker Compose

Copy `.env.example` to `.env`, supply the two required Home Assistant settings,
and run `docker compose up --build`. Compose publishes only to host loopback.

The Docker health probe tests **application liveness**. A temporary Home Assistant
outage changes `/health` to `status: degraded`, but leaves HTTP status 200 so the
orchestrator does not restart a healthy bridge in a loop.

## Documentation

- [Architecture](docs/architecture.md)
- [Security](docs/security.md)
- [Tool contracts](docs/tools.md)
- [Development](docs/development.md)
- [ChatGPT setup and Phase 1 limitations](docs/chatgpt-setup.md)

## License

MIT. See [LICENSE](LICENSE).

