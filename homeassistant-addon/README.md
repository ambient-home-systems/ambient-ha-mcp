# Home Assistant add-on packaging

Full add-on packaging is intentionally deferred. Phase 1 runs as a standalone
Python process or Docker container. A later phase can add an ingress/config schema,
supervisor integration, image publishing, and add-on security review without
coupling those concerns to the Home Assistant client or MCP tool layers.

