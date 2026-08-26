# Home Assistant App installation

## Current status

The Phase 6.5 package is an experimental Home Assistant App (formerly add-on) for
`amd64` and `aarch64`. It is read only and exposes the same 24 tools as standalone
Ambient MCP. Real Supervisor installation validation is outstanding; do not treat
the package as production validated yet.

## Prerequisites

- Home Assistant OS or a supported Supervised installation with the Apps store.
- Access to add a custom App repository.
- A public `ghcr.io/ambient-home-systems/ambient-ha-mcp:0.6.5` image. The image is
  published by the main-branch workflow after this version is merged; its GHCR
  visibility must be public.

Home Assistant Container and Core installations do not provide Supervisor Apps.
Use the standalone Docker/Python route on those installation types.

## Install and start

1. Open **Settings → Apps → App store**.
2. In the repository menu, add
   `https://github.com/ambient-home-systems/ambient-ha-mcp`.
3. Refresh the store and select **Ambient Home Assistant MCP**.
4. Install version `0.6.5`.
5. Review Configuration. Do not add a token; no token option exists.
6. Leave `8000/tcp` disabled, start the App, and enable start-on-boot behavior as
   appropriate for the test host.
7. Inspect logs for normal MCP startup. Logs must not contain a Home Assistant URL,
   Supervisor token, entity dump, registry dump, or private attribute values.

Supervisor provides `SUPERVISOR_TOKEN` and the App uses the official Core proxy.
Missing Supervisor authentication causes a sanitized startup failure.

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
  package is public.
- **Supervisor authentication unavailable:** confirm this is running as the App,
  not by directly starting the image in App mode.
- **MCP Host rejected:** add only the exact hostname/IP used by the local client.
- **Degraded health:** the process is live, but Home Assistant is unreachable or
  rejected authentication. Check Supervisor/Core readiness without printing auth.
- **Recorder or traces unsupported:** these features may be disabled, excluded, or
  version-dependent; other read tools should continue to work.

## Uninstall

Stop and uninstall the App through Home Assistant. Remove the custom repository if
it is no longer needed. Ambient stores no token or database in App configuration;
Home Assistant manages normal App backup/removal behavior.
