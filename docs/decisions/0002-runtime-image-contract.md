# 0002: Bind a Studio training runtime to a published runner image

Date: 2026-09-24
Status: accepted for bridge implementation; no image promoted yet.

## User journey and ownership

Studio sends its immutable build identity with an already validated training
request. Bridge resolves that build and training mode against a packaged catalog
and compiles a small VKong task bundle. The user never selects an image or syncs
source code. VKong CLI remains the transport and VKong owns the rental, workspace
authorization, logs and billing. The image contains Unsloth and bridge worker
code. The runner checks the bundle's expected runtime before it loads a model.

## Decision

`RuntimeIdentity` records an adapter name, exact full adapter source commit,
bridge build identifier, adapter/job/event contracts and remote platform. The
Unsloth catalog requires its adapter-specific contract and maps one or more
explicit Studio build identities to this runtime and an OCI image digest. It is
packaged with the bridge and reviewed at release time. An empty default catalog
means no production image has been promoted. Tests may inject a temporary catalog.

The compiler accepts an optional resolved runtime for the current dev seam;
such jobs use the new `vkong.connect.job.v2` document. Legacy v1 documents remain
parseable for existing local contract tests, but a release readiness check must
reject unbound v1 submissions. The runner compares v2 identity with a manifest
installed into the image. Catalog selection checks mode/platform and contract
identity before any CLI call. Both sides fail closed on unknown schemas.

Pin the base image, fork commit, bridge build and produced OCI manifest by digest.
An OCI digest string alone is not proof of provenance: release workflow must
inspect the built manifest, execute a clean-container preflight and promote only
after a GPU test. No digest is fabricated in the source tree.

## Failure and compatibility

No catalog entry or ambiguous entry gives an actionable error before rent. A
Studio upgrade does not reinterpret a previously persisted job: its runtime and
image digest remain bound to the original submission. CLI start still requires
a stable idempotency contract; the current VKong CLI does not provide it, so
this change does not enable live submission. Current HF output destination and
explicit cancellation semantics stay in place.

An exact worker commit per image is initially conservative. After tests prove
training compatibility, several UI-only Studio releases may point to the same
runtime. A developer override is not part of the normal user path.

## Alternatives and verification

Shipping Unsloth source in each job increases transfer, import and provenance
risks. Matching only the upstream package version misses fork-specific worker
changes. Rebuilding for every UI-only Studio release is unnecessary when the
training contract is unchanged. Dynamic image discovery adds a service and an
unreviewed trust source. The packaged catalog is sufficient for this phase.

Tests cover catalog ambiguity, unknown build/mode/platform, v1/v2 round-trip,
runtime mismatch before worker import, generated sync allowlist and sibling
Studio executor compatibility. Live image/GPU/CLI evidence is tracked separately.
