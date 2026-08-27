# Ambient Home Assistant MCP

This experimental Home Assistant App runs the same Ambient MCP server image as the
standalone deployment. It uses Home Assistant Supervisor's Core API proxy and the
short-lived `SUPERVISOR_TOKEN`; no long-lived access token is entered in App options.

The validated v0.6.9 baseline contains 24 read-only tools. Phase 7 adds seven
semantic control tools through one central executor. Fresh installs and upgrades
remain read only because `read_only` defaults to true and `control_enabled` defaults
to false. Both settings must be deliberately changed before any control can execute.

## Install

1. In Home Assistant, open **Settings → Apps → App store**.
2. Open the repository menu and add
   `https://github.com/ambient-home-systems/ambient-ha-mcp`.
3. Install **Ambient Home Assistant MCP**.
4. Review the Configuration tab, then start the App.
5. Check the App log for a normal startup message and use the container health check
   or `/health` endpoint for liveness.

The public multi-architecture image exists at
`ghcr.io/ambient-home-systems/ambient-ha-mcp:0.6.9`, matching the currently
advertised `config.yaml` version. New versions are never advertised until their
versioned `amd64` and `aarch64` images and manifest are already pullable.

The launcher reads Supervisor's root-only options document during a minimal
container bootstrap, then drops to the unprivileged `ambient` user before the MCP
server starts. Version `0.6.5` could install but could not complete this startup.
Version `0.6.9` selects Supervisor's documented
`ws://supervisor/core/websocket` proxy for registry and automation reads, bypasses
system proxy discovery for that internal connection, prevents DEBUG frame logging,
and accepts bounded registry messages up to 16 MiB rather than inheriting the
dependency's 1 MiB default. Its complete 24-tool live validation passed.

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

The currently advertised v0.6.9 metadata exposes bounded read options only. After
the v0.7.0 image is published and verified, its separate catalog-promotion PR must
atomically add the two control gates and exact switch/scene/script allowlists while
defaulting to read-only/disabled. There is never a token, generic service,
script-variable, or arbitrary-payload option.

## Security limitations

Home Assistant authenticates the App to Core through Supervisor. That does **not**
authenticate clients connecting to the MCP HTTP endpoint. Keep the endpoint local and
disabled when not testing. Remote ChatGPT connectivity requires a separately designed
authenticated deployment and remains outside Phase 7. Do not enable controls on a
publicly reachable MCP port.
