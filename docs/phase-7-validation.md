# Phase 7 safe-control validation

Phase 7 must pass local review before any real Home Assistant write. Never paste a
token, private URL, entity inventory, exact location, camera data, automation
content, or secret into this report.

## Automated gate

- [ ] Full pytest suite passes; direct Home Assistant tests skip by default.
- [ ] Ruff lint and format checks pass.
- [ ] Strict mypy passes.
- [ ] Wheel and source distribution build.
- [ ] MCP discovery reports 31 unique tools with valid schemas.
- [ ] No tool exposes `confirmed`, arbitrary service/domain, raw payload, media URL,
      script variables, automation execution, or a prohibited control domain.
- [ ] Read-only and controls-disabled tests prove that either gate blocks writes.
- [ ] Capability, value, exact-target, mass-action, mixed-policy, confirmation,
      verification, audit, and error-path tests pass.
- [ ] The App catalog still advertises the previous pullable image until the new
      multi-architecture candidate is published and independently verified.

## Read-only candidate validation

Install the candidate with `read_only: true`, `control_enabled: false`, and the MCP
port disabled. Verify startup, Supervisor authentication, REST, WebSocket, health,
all 24 read tools, seven control schemas, privacy, cache/restart behavior, and that
representative control calls return `read_only` without a Home Assistant service
call. Temporarily expose the port only on a trusted LAN and remove it afterward.

## Explicit safe-light write

This is the only initial live write category. The operator must provide one exact,
harmless light ID; the test must never search for or automatically select a target.

```bash
RUN_HA_WRITE_TESTS=1
AMBIENT_HA_TEST_LIGHT_ENTITY=light.explicit_safe_test_light
```

Required procedure:

1. Confirm the ID was deliberately designated and is a harmless light.
2. Read and retain its original `on`/`off` state.
3. Perform exactly one opposite-state action through the central executor.
4. Require a `verified` result.
5. Restore the original state in a `finally` path.
6. Require restoration verification and a fresh final state equal to the original.
7. Confirm pre-write and final audit events contain no secrets or private values.

Do not run automatic live writes for switches, scenes, scripts, media players,
fans, climate, covers/garage doors, locks, alarms, valves, buttons, sirens, vacuums,
remotes, or automations.

## Release gate

Publish the immutable v0.7.0 `amd64` and `arm64` images and verify the public
manifest first. Only then open the separate catalog-promotion PR. That PR changes
the advertised version and atomically introduces the Phase 7 App option schema with
these safe defaults:

```yaml
read_only: true
control_enabled: false
allowed_switch_entities: []
allowed_scene_entities: []
allowed_script_entities: []
```

Do not promote if any image, schema, default, automated check, read-only candidate
check, safe-light restoration, audit, or privacy check fails.
