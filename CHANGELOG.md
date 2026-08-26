# Changelog

All notable changes to this project will be documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.6] - 2026-08-25

### Fixed

- Correct the real Home Assistant App startup failure caused by the `0.6.5`
  non-root entrypoint being unable to read Supervisor's root-only
  `/data/options.json` document.
- Use a minimal root bootstrap to read bounded App configuration, then drop
  supplementary groups, GID, and UID to the fixed `ambient` account before the MCP
  server starts. Standalone Compose continues to start directly as `ambient`.

### Documentation

- Record successful public publication of the versioned `0.6.5` Home Assistant App
  images and provide an operator-focused installation, troubleshooting, and
  sanitized live-validation handoff for Phase 6.6.

### Security

- Add no App privileges, host mappings, Supervisor API scope, write paths, service
  calls, or MCP tools. Startup fails closed if the unprivileged identity cannot be
  entered and verified.
- Preserve the mandatory `NO-GO FOR PHASE 7` decision until real Supervisor
  installation, live privacy inspection, and read-only integration validation pass.

## [0.6.5] - 2026-08-25

### Added

- Home Assistant App repository metadata, safe configuration schema, operator
  documentation, translations, container health, and disabled-by-default MCP port.
- A shared runtime launcher that preserves standalone behavior and selects
  Supervisor Core-proxy authentication in App mode.
- Official Home Assistant multi-architecture build/lint workflow for `amd64` and
  `aarch64` images published with version-aligned manifests.
- Opt-in live validation coverage for all 24 MCP tools, registry cache refresh,
  representative privacy filtering, and supported automation/history interfaces.

### Security

- App mode obtains `SUPERVISOR_TOKEN` only from the environment, never App options,
  and does not persist or log it.
- App startup hard-forces `READ_ONLY=true`, clears external policy configuration,
  rejects unknown options, and requests no Supervisor, Docker, ingress, host-network,
  filesystem, device, or privileged access.
- Phase 7 remains blocked until live Home Assistant and Supervisor App validation
  completes successfully.

## [0.6.0] - 2026-08-25

### Added

- Typed server-side `allow`, `deny`, and `confirm_required` policy decisions with
  canonical targets, explicit operation classes, deterministic precedence, and
  protected-entity rules.
- Strict optional TOML policy configuration, conservative defaults, hard target/
  operation limits, and bounded climate, lighting, media, and fan values.
- Internal dry-run action plans with capability checks, ambiguity handling, mixed
  target reporting, sanitized predicted service data, and no execution path.
- Future-compatible unverified confirmation requirements without a spoofable
  caller-supplied boolean.
- Bounded redacted audit events and a structured-log sink abstraction without a
  persistent database.
- Adversarial tests for prompt injection, privilege confusion, normalization,
  precedence, malformed configuration, policy errors, and audit-secret leakage.

### Security

- `READ_ONLY` is now an outer hard boundary that overrides every non-read rule and
  confirmation state.
- Home Assistant credential privilege is explicitly separated from Ambient MCP
  authorization; administrator access never grants administrative MCP permission.
- Administrative operations fail closed, scripts/switches default to deny, and
  opaque scenes/covers default to server-verified confirmation.
- Phase 6 introduces zero Home Assistant write/service-call paths and keeps all 24
  MCP tools read-only.

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
