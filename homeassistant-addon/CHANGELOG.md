# Changelog

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
