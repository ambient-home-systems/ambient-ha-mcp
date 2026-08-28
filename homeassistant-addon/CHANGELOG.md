# Changelog

## 0.7.0

- Add seven policy-controlled semantic tools through one audited central executor.
- Require both `read_only: false` and `control_enabled: true`; upgrades and fresh
  installs retain safe `true`/`false` defaults.
- Require exact allowlists for switches and scripts, and keep scenes confirmation-blocked.
- Preserve prohibited domains, private/LAN-only deployment guidance, fixed service
  mappings, bounded verification, and the image-before-catalog release invariant.

## 0.6.9

- Accept bounded Home Assistant registry responses up to 16 MiB instead of inheriting
  the WebSocket dependency's 1 MiB default, which closed larger real inventories with
  code 1009.
- Preserve the internal Supervisor route, proxy bypass, App permissions, token-safe
  logging, 24 read-only tools, and Phase 7 gate.

## 0.6.8

- Bypass inherited system proxy configuration for the internal Supervisor
  WebSocket connection while preserving standalone proxy behavior.
- Prevent DEBUG transport-frame logging and redact quoted WebSocket authentication
  tokens as defense in depth.
- Preserve the existing Supervisor endpoint, App permissions, 24 read-only tools,
  and Phase 7 gate.

## 0.6.7

- Fix App-mode registry and automation WebSocket access by using Supervisor's
  documented `ws://supervisor/core/websocket` proxy.
- Preserve standalone `/api/websocket` routing, Supervisor-token authentication,
  the 24-tool read-only surface, and existing App permissions.
- Prevent Home Assistant from offering this update until its versioned `amd64` and
  `aarch64` images and multi-architecture manifest are published and verified.

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
