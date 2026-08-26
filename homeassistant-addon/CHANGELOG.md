# Changelog

## 0.6.6

- Fix Home Assistant startup by reading Supervisor's root-only options document
  before dropping to the unprivileged `ambient` server identity.
- Keep App permissions, the 24-tool read-only MCP surface, and disabled default
  host port unchanged.

## 0.6.5

- Add Supervisor-proxy authentication without a manual Home Assistant token.
- Enforce read-only app startup and safe, bounded App options.
- Add container health checking and an optional local MCP port, disabled by default.
- Support `amd64` and `aarch64` through the published multi-architecture image.
