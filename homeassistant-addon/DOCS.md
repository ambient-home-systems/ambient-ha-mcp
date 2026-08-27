# Ambient Home Assistant MCP

This experimental Home Assistant App runs the same Ambient MCP server image as the
standalone deployment. It uses Home Assistant Supervisor's Core API proxy and the
short-lived `SUPERVISOR_TOKEN`; no long-lived access token is entered in App options.

Phase 6.6 remains strictly read only. The launcher always sets `READ_ONLY=true`,
and the published MCP surface contains only the 24 Phase 1–5 read tools. Phase 6
policy planning types are not executable and are not exposed as MCP tools.

## Install

1. In Home Assistant, open **Settings → Apps → App store**.
2. Open the repository menu and add
   `https://github.com/ambient-home-systems/ambient-ha-mcp`.
3. Install **Ambient Home Assistant MCP**.
4. Review the Configuration tab, then start the App.
5. Check the App log for a normal startup message and use the container health check
   or `/health` endpoint for liveness.

The public multi-architecture image exists at
`ghcr.io/ambient-home-systems/ambient-ha-mcp:0.6.7`, matching the currently
advertised `config.yaml` version. New versions are never advertised until their
versioned `amd64` and `aarch64` images and manifest are already pullable.

The launcher reads Supervisor's root-only options document during a minimal
container bootstrap, then drops to the unprivileged `ambient` user before the MCP
server starts. Version `0.6.5` could install but could not complete this startup.
The `0.6.8` candidate selects Supervisor's documented
`ws://supervisor/core/websocket` proxy for registry and automation reads, bypasses
system proxy discovery for that internal connection, and prevents DEBUG frame
logging. It becomes an offered update only after image-first publication and
verification complete.

## Local endpoint access

Port `8000/tcp` is disabled by default. This keeps the unauthenticated MCP transport off
the LAN. For temporary local validation, assign a host port in the App Network settings,
then add the exact hostname (and `hostname:*` form) used by the client to
`mcp_allowed_hosts`. Do not use a global wildcard and do not expose this port through a
router, tunnel, reverse proxy, or public DNS.

The Streamable HTTP endpoint is `http://<home-assistant-host>:<assigned-port>/mcp` and
health is `/health`. Home Assistant ingress is intentionally disabled; ingress is a UI
proxy and is not the authentication boundary for an MCP client.

## Options

Options only tune safe, bounded read behavior: logging, request/cache timeouts, history
bounds, low-battery diagnostics, diagnostic exclusions, and the MCP Host allowlist.
There is no token option and no option that disables read-only mode.

## Security limitations

Home Assistant authenticates the App to Core through Supervisor. That does **not**
authenticate clients connecting to the MCP HTTP endpoint. Keep the endpoint local and
disabled when not testing. Remote ChatGPT connectivity requires a separately designed
authenticated deployment and is outside Phase 6.6.

Live validation against a real Home Assistant instance must pass before any Phase 7
write/control work can begin. Use the repository's Phase 6.6 sanitized validation
template when returning installation results.
