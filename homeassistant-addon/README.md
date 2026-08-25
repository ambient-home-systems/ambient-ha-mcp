# Home Assistant add-on packaging

Full add-on packaging is intentionally deferred. Phase 6 runs as a standalone
Python process or Docker container. A later phase can add an ingress/config schema,
supervisor integration, image publishing, and add-on security review without
coupling those concerns to the Home Assistant client or MCP tool layers.

The Phase 6 policy architecture does not make this directory installable from the
Home Assistant UI and does not add any device-control capability.
