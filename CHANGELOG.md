# Changelog

All notable changes to this project will be documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-08-25

### Added

- Read-only automation listing, bounded normalized configuration, static entity
  reference discovery, stored trace listing/detail, and activity-cause evidence tools.
- Feature-detected support for Home Assistant `automation/config`, `trace/list`,
  `trace/get`, and `trace/contexts` WebSocket commands.
- TTL-cached, manually refreshable, 500-automation reference index with conservative
  explicit entity, device, and inert template-text matching.
- Strict causality categories separating direct context proof and executed action
  evidence from temporal correlation and possible static references.
- Large-inventory, adversarial prompt-injection, secret-redaction, nested-trace,
  failure, unsupported-interface, and context-correlation tests.

### Security

- Automation content is treated as untrusted data, never executed as Jinja or
  interpreted as server instructions.
- Webhooks, URLs, tokens, credentials, notification targets/messages, and shell
  commands are redacted from normalized configuration and trace output.
- Home Assistant user identifiers are reduced to the privacy-preserving origin
  category `user` and never returned.

## [0.4.0] - 2026-08-25

### Added

- Compact whole-home summary across only the semantic sections supported by the
  current Home Assistant inventory.
- Bounded tools for unavailable entities, genuine percentage batteries, openings,
  and lights reporting on.
- Deterministic evidence-backed diagnostics with documented critical, warning, and
  informational severity rules.
- Large-inventory and response-size tests proving one bulk state read per tool and
  bounded output.

### Security

- Presence is summarized without raw tracker attributes or GPS coordinates.
- Safety messages state what Home Assistant reports without claiming that a sensor
  state proves a real-world emergency.

## [0.3.0] - 2026-08-25

### Added

- Read-only Recorder history, logbook, and semantic recent-change MCP tools.
- Offset-aware historical query validation with bounded lookback, events, and
  aggregate candidate entities.
- Normalized state transitions, conservative duration calculations, privacy-filtered
  logbook entries, and resolved recent-change facts.
- Opt-in Phase 1–3 live integration coverage without credentials in source or CI.

## [0.2.0] - 2026-08-25

### Added

- Fresh REST entity-state reads and authenticated WebSocket entity, device, area,
  and floor registry discovery.
- Typed registry joins with entity-over-device area precedence and area-to-floor
  resolution.
- Semantic tools for entity lookup/search, area/floor discovery, and generic
  domain state summaries.
- Deterministic multi-field search with composable filters, explicit result caps,
  truncation metadata, and normal not-found/unsupported results.
- A bounded registry TTL cache while keeping dynamic state uncached.
- Strict entity-attribute allowlisting and privacy filtering for URLs, tokens,
  camera streams, coordinates, credentials, and location metadata.
- Unit and MCP contract coverage for joins, ranking, limits, caching, privacy, and
  unsupported registry commands.

## [0.1.0] - 2026-08-25

### Added

- Typed, secret-aware environment configuration.
- Async Home Assistant REST connectivity and safe server-info reads.
- Semantic `ha_connection_status` and `ha_server_info` MCP tools.
- Structured redacted logging and a fail-closed Phase 1 policy seam.
- Liveness/readiness health response, Docker image, Compose configuration, tests,
  and foundational documentation.
