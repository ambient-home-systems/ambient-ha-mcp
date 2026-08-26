# Home Assistant App installation

## Current status

The `0.6.7` package is an experimental Home Assistant App (formerly add-on) for
`amd64` and `aarch64`. Its versioned multi-architecture image is published by the
main-branch release workflow and must be publicly pullable before installation. It
is read only and exposes the same 24 tools as
standalone Ambient MCP. Version `0.6.5` installed but could not start because its
non-root entrypoint could not read Supervisor's root-only options file. `0.6.6`
corrected startup, then live validation exposed an incorrect WebSocket route through
the Supervisor proxy. `0.6.7` explicitly selects the documented Supervisor
WebSocket endpoint. Complete live validation is outstanding; do not treat the
package as production validated yet.

## Prerequisites

- Home Assistant OS or a supported Supervised installation with the Apps store.
- Access to add a custom App repository.
- Network access from Home Assistant Supervisor to GitHub and GHCR.

The version-aligned release image is
`ghcr.io/ambient-home-systems/ambient-ha-mcp:0.6.7`. It becomes installable after
the main-branch publication workflow completes. Home Assistant selects the matching
architecture from its multi-architecture manifest.

Home Assistant Container and Core installations do not provide Supervisor Apps.
Use the standalone Docker/Python route on those installation types.

## Install and start

1. Open **Settings → Apps → App store**.
2. Open the top-right menu, select **Repositories**, and add
   `https://github.com/ambient-home-systems/ambient-ha-mcp`.
3. Select **Add**, close the repository dialog, and refresh the App store.
4. Select **Ambient Home Assistant MCP**. If it does not appear, use **Check for
   updates** in the store menu and refresh the browser once.
5. Install version `0.6.7`.
6. Review Configuration. Do not add a token; no token option exists.
7. Leave `8000/tcp` disabled, start the App, and enable start-on-boot behavior as
   appropriate for the test host.
8. Inspect logs for normal MCP startup. Logs must not contain a Home Assistant URL,
   Supervisor token, entity dump, registry dump, or private attribute values.

Supervisor provides `SUPERVISOR_TOKEN` and the App uses the official Core proxy.
Missing Supervisor authentication causes a sanitized startup failure.

The launcher configures REST through `http://supervisor/core` and WebSocket through
`ws://supervisor/core/websocket`. Standalone deployments do not receive this
override and continue to derive `/api/websocket` from `HOME_ASSISTANT_URL`.

Supervisor stores `/data/options.json` for root-only access. The App entrypoint
reads and validates that file during a short root bootstrap, then initializes the
`ambient` supplementary groups, GID, and UID before starting the MCP server. No
Home Assistant, Supervisor, host, device, or Linux privilege was added to App
metadata for this bootstrap.

## Local MCP validation

The HTTP MCP transport does not authenticate client users. For temporary local
testing only:

1. Assign a local host port to internal `8000/tcp` in the Network section.
2. Add the exact hostname used by the client, plus its `hostname:*` form, to
   `mcp_allowed_hosts`. If using an IP address, add the exact IP and `IP:*`.
3. Connect MCP Inspector to `http://<host>:<port>/mcp`.
4. Confirm exactly 24 tools, call representative discovery/history/diagnostic/
   automation tools, and check `http://<host>:<port>/health`.
5. Remove the host-port assignment after validation.

Use [the sanitized Phase 6.6 report template](phase-6-6-live-validation.md) to
record installation, tool, privacy, restart, and permission results without copying
private Home Assistant data.

Never use `*`, publish the port, forward it at the router, or place it behind an
unauthenticated tunnel/reverse proxy. Home Assistant ingress is intentionally not
used because it is a UI proxy, not the MCP client's authentication mechanism.

## Options

Configuration covers log level, Home Assistant request timeout, registry cache
TTL, Recorder query bounds, low-battery threshold, ignored diagnostic entity IDs,
and exact allowed MCP Host headers. Supervisor validates basic ranges, and the
Python settings layer validates cross-field history limits. Unknown launcher
options fail startup instead of silently expanding authority.

There is no Home Assistant URL, token, read-only toggle, policy file, generic
service, or control option. App mode always uses the shared server implementation
with `READ_ONLY=true`.

## Upgrade and rollback

App image tags exactly match the `version` in `config.yaml`. Review the App
changelog, then use the normal Home Assistant update flow. To roll back during
experimental validation, restore a Home Assistant backup containing the prior App
version or install a previously published version through an approved local test
repository. Configuration contains no credentials and no Ambient database.

## Troubleshooting

- **Image not found/unauthorized:** confirm the versioned GHCR image exists and the
  package is public. Version `0.6.7` is expected at the exact image shown above.
- **Unsupported architecture:** this release supports only `amd64` and `aarch64`.
  It will not install on `armv7`, `armhf`, or `i386` systems.
- **App does not appear:** confirm the repository URL is exact, run **Check for
  updates**, refresh the browser, and inspect **Settings → System → Logs →
  Supervisor** for repository or metadata errors.
- **Supervisor authentication unavailable:** confirm this is running as the App,
  not by directly starting the image in App mode.
- **MCP Host rejected:** add only the exact hostname/IP used by the local client.
- **Degraded health:** the process is live, but Home Assistant is unreachable or
  rejected authentication. Check Supervisor/Core readiness without printing auth.
- **Startup failure:** restore the documented option defaults and restart only the
  Ambient App. Unknown options and invalid bounds intentionally fail closed.
- **Installed but immediately stops with no App log:** inspect **Settings → System
  → Logs → Supervisor** for the container exit category. Version `0.6.5` has a
  known `/data/options.json` permission defect; install `0.6.6` or later. Version
  `0.6.6` starts but uses the wrong Supervisor WebSocket proxy route; install
  `0.6.7` for live discovery validation. Do not
  paste Supervisor tokens or private URLs into an issue.
- **Health endpoint unreachable:** the App port is disabled by default. Confirm the
  App is running, then temporarily assign a trusted-LAN host port if HTTP validation
  is required.
- **Port conflict:** choose a different unused host port in the Network section;
  the container port remains `8000/tcp`.
- **Recorder or traces unsupported:** these features may be disabled, excluded, or
  version-dependent; other read tools should continue to work.

## Uninstall

Stop and uninstall the App through Home Assistant. Remove the custom repository if
it is no longer needed. Ambient stores no token or database in App configuration;
Home Assistant manages normal App backup/removal behavior.
