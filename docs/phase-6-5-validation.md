# Phase 6.5 integration gate

## Current decision

**NO-GO FOR PHASE 7 — live Home Assistant validation outstanding.**

The implementation, unit tests, protocol tests, static checks, and package build
can run without a Home Assistant instance. They cannot prove production integration
behavior. The validation environment did not contain `HOME_ASSISTANT_URL` and
`HOME_ASSISTANT_TOKEN`, Docker, or a Home Assistant Supervisor test host.

## Required evidence for GO

A `GO FOR PHASE 7` decision requires all of the following in the same reviewed
Phase 6.5 validation cycle:

1. REST reachability/authentication and safe server metadata pass.
2. WebSocket entity, device, area, and floor discovery passes or reports a
   feature-local supported absence.
3. All 24 MCP tools are discovered and called over the MCP protocol using actual
   entities without a service call or write.
4. Recorder/logbook and automation configuration/trace interfaces pass where
   supported and degrade structurally where unavailable.
5. Raw-versus-normalized inspection confirms private coordinates, URLs, tokens,
   credentials, camera/stream fields, and user IDs are absent while useful safe
   measurements remain.
6. Registry caching, manual refresh, fresh states, TTL expiry, response bounds,
   error sanitization, and prompt-injection fixtures pass.
7. The Home Assistant App image builds for `amd64` and `aarch64`, is installable on
   Supervisor, starts with Supervisor auth, serves health and all 24 tools locally,
   survives restart, upgrades/rolls back normally, and leaks no secret.
8. Source review confirms no Home Assistant write endpoint, service-call path,
   public control tool, executor, or confirmation bypass exists.

Any failure or missing evidence produces `NO-GO FOR PHASE 7`. A gate decision is
about readiness to begin controlled write-path engineering; it is not authorization
to expose Ambient MCP publicly or to skip Phase 7 safety design.

## Commands

```bash
uv sync --frozen --all-extras
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
RUN_HA_INTEGRATION_TESTS=1 uv run pytest -m integration -vv
npx @modelcontextprotocol/inspector@latest
docker build -t ambient-ha-mcp:0.6.5 .
```

Set `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` only in the secure process
environment. Never echo them, persist them in a report/fixture, or pass them to an
external service.
