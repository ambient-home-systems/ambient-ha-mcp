# Home Assistant App release procedure

## Non-negotiable invariant

Home Assistant must never advertise an Ambient App version before that exact
versioned image is publicly pullable for every architecture listed in
`homeassistant-addon/config.yaml`.

The catalog version is a user-facing availability promise, not a build trigger.
Changing `homeassistant-addon/config.yaml` causes Home Assistant to display an
update. If the matching image or multi-architecture manifest is missing or still
being published, users receive an update that cannot install. That release order is
prohibited for the lifetime of this project.

## Required two-stage release

### Stage 1 — publish and verify the image

1. Merge the release source, package version, tests, documentation, and changelogs.
2. Do **not** change the advertised version in
   `homeassistant-addon/config.yaml`. It may intentionally trail the Python package
   version while a candidate is being prepared.
3. After CI passes, create the immutable tag `vMAJOR.MINOR.PATCH` on the reviewed
   release commit.
4. The `Publish Home Assistant App` workflow builds and pushes the versioned
   `amd64` and `aarch64` images and then publishes the generic versioned manifest.
5. The workflow must finish successfully and verify both `linux/amd64` and
   `linux/arm64` from `ghcr.io/ambient-home-systems/ambient-ha-mcp:VERSION`.
6. Independently confirm that the versioned manifest is publicly pullable. Do not
   proceed based only on individual architecture jobs.

Do not publish or install from `latest`. Versioned references are the release
contract and the rollback mechanism.

### Stage 2 — promote the App catalog

1. Open a separate PR that changes the advertised version in
   `homeassistant-addon/config.yaml` to the already published version.
2. Do not include runtime code changes in the catalog-promotion PR.
3. CI runs `Verify advertised App image exists`. It fails closed unless the exact
   public versioned manifest contains both supported platforms.
4. Merge the catalog-promotion PR only after every check passes.
5. Refresh an approved Home Assistant test host, confirm the update appears, and
   perform the documented read-only upgrade validation.

The catalog-promotion PR is the only event that should make a new update visible to
Home Assistant users. A source merge, package-version bump, tag creation, build
start, architecture-image push, or partial manifest publication must not do so.

## Forbidden release shortcuts

- Never bump `homeassistant-addon/config.yaml` in the source-release PR.
- Never use a `main` push as both the catalog advertisement and image build trigger.
- Never promote after only one architecture succeeds.
- Never assume a successful build means the generic manifest is already pullable.
- Never ask users to repeatedly retry an update whose image is missing.
- Never move or reuse an existing version tag.
- Never overwrite a versioned image after catalog promotion; publish a new patch
  version instead.

## Release incident recovery

If Home Assistant ever advertises an update that cannot be pulled:

1. Treat it as a release incident.
2. Immediately restore `homeassistant-addon/config.yaml` to the last known pullable
   version and merge that metadata-only rollback.
3. Confirm Home Assistant no longer offers the broken update after repository data
   refreshes.
4. Diagnose and publish the candidate image without re-advertising it.
5. Promote it only through the two-stage process above after independent manifest
   verification.
6. Record the cause and corrective action in both changelogs and the completion
   report.

User trust takes priority over release speed. If publication state is uncertain,
the catalog remains on the previous working version.

## Repository enforcement

The `main` branch must require pull requests and the status check named
`Verify advertised App image exists`. Direct pushes, force pushes, and bypasses for
catalog-version changes must remain disabled. Repository administrators must treat
those branch protections as part of the release system, not as optional workflow
preferences.

If GitHub rules are temporarily unavailable or misconfigured, do not promote an
App version. Restore enforcement first. A CI check that runs only after an
unreviewed direct push cannot prevent Home Assistant from observing that push.
