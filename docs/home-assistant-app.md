# Home Assistant App installation

## Current status

The currently advertised `0.6.9` package is the live-validated read-only baseline
for the experimental Home Assistant App (formerly add-on) on `amd64` and `aarch64`.
It passed all 24 read tools on a real Home Assistant installation. Version `0.6.5`
installed but could not start because its
non-root entrypoint could not read Supervisor's root-only options file. `0.6.6`
corrected startup, then live validation exposed an incorrect WebSocket route through
the Supervisor proxy. Version `0.6.7` selected the documented Supervisor WebSocket
endpoint. Version `0.6.8` explicitly bypassed system proxies in App mode and
prevented DEBUG authentication-frame logging, but live discovery still failed when
a real registry response exceeded the WebSocket dependency's 1 MiB default receive
limit. Version `0.6.9` applies an explicit 16 MiB ceiling and was published,
promoted, installed, and validated only after both architecture images and the
public manifest were verified. Phase 7 source adds gated controls but remains
unreleased until its own review, publication, catalog promotion, and live checks.

## Prerequisites

- Home Assistant OS or a supported Supervised installation with the Apps store.
- Access to add a custom App repository.
- Network access from Home Assistant Supervisor to GitHub and GHCR.

The version-aligned release image is
`ghcr.io/ambient-home-systems/ambient-ha-mcp:0.6.9`. Home Assistant selects the
matching architecture from its multi-architecture manifest. A newer version is not
eligible for catalog promotion until the same versioned reference is independently
verified for both supported platforms.

Home Assistant Container and Core installations do not provide Supervisor Apps.
Use the standalone Docker/Python route on those installation types.

## Install and start

1. Open **Settings → Apps → App store**.
2. Open the top-right menu, select **Repositories**, and add
   `https://github.com/ambient-home-systems/ambient-ha-mcp`.
3. Select **Add**, close the repository dialog, and refresh the App store.
4. Select **Ambient Home Assistant MCP**. If it does not appear, use **Check for
   updates** in the store menu and refresh the browser once.
5. Install the version currently offered by Home Assistant. Do not install a
   candidate version from an unverified image reference.
6. Review Configuration. Do not add a token; no token option exists.
7. Leave `8000/tcp` disabled, start the App, and enable start-on-boot behavior as
   appropriate for the test host.
8. Inspect logs for normal MCP startup. Logs must not contain a Home Assistant URL,
   Supervisor token, entity dump, registry dump, or private attribute values.

Supervisor provides `SUPERVISOR_TOKEN` and the App uses the official Core proxy.
Missing Supervisor authentication causes a sanitized startup failure.

The launcher configures REST through `http://supervisor/core` and WebSocket through
`ws://supervisor/core/websocket`. It disables system-proxy discovery for this
internal App-network WebSocket transport. Standalone deployments do not receive
these overrides and continue to derive `/api/websocket` from `HOME_ASSISTANT_URL`
with their existing automatic proxy behavior.

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
4. On v0.6.9, confirm exactly 24 tools. A reviewed Phase 7 candidate exposes 31.
   Call representative discovery/history/diagnostic/automation tools and check
   `http://<host>:<port>/health` before considering any explicitly designated write.
5. Remove the host-port assignment after validation.

Use [the sanitized Phase 6.6 report template](phase-6-6-live-validation.md) to
record installation, tool, privacy, restart, and permission results without copying
private Home Assistant data.

Never use `*`, publish the port, forward it at the router, or place it behind an
unauthenticated tunnel/reverse proxy. Home Assistant ingress is intentionally not
used because it is a UI proxy, not the MCP client's authentication mechanism.

## Options

The advertised v0.6.9 metadata covers bounded read settings and exact MCP Host
headers. Phase 7 launcher code supports independent `read_only` and
`control_enabled` gates plus exact switch/scene/script allowlists, but those options
must not appear in the catalog until the v0.7.0 image is published and verified.
The separate catalog-promotion PR adds the schema and translations atomically with
the version change, using safe `true`/`false` defaults.

Once promoted, writes require both gates to be deliberately changed. Lights, fans,
media players, and climate entities then remain subject to capabilities, values,
limits, verification, and audit. Switches, scenes, and scripts additionally require
exact entity IDs in their corresponding allowlists; scenes still remain blocked until
secure server-verifiable confirmation exists. There is no Home Assistant
token, external policy file, generic service, caller confirmation, script-variable,
or raw-payload option.

## Upgrade and rollback

App image tags exactly match the advertised `version` in `config.yaml`. The image
must exist first; only a later catalog-promotion PR may make Home Assistant display
the update. Review the App changelog, then use the normal Home Assistant update
flow. Maintainers must follow [the App release procedure](releasing.md). To roll
back during experimental validation, restore a Home Assistant backup containing the
prior App version or install a previously published version through an approved
local test repository. Configuration contains no credentials and no Ambient database.

## Troubleshooting

- **Image not found/unauthorized:** confirm the versioned GHCR image exists and the
  package is public. Treat any advertised version with a missing image as a release
  incident: immediately restore the last pullable catalog version and do not ask
  users to retry a broken update.
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
  `0.6.8` starts, uses the correct route, and bypasses system proxies, but larger
  registries can still exceed its 1 MiB transport receive limit. Upgrade through
  the verified catalog to the currently advertised `0.6.9` release. Do not paste
  Supervisor tokens or private URLs into an issue.
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
