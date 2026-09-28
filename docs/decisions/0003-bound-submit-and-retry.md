# 0003: Bound CLI context and content-checked bundle retry

Date: 2026-09-24
Status: accepted for the POC executor seam

Studio's remote executor must bind one HTTPS VKong server and immutable workspace
ID before a rental-affecting CLI call. The values come from explicit Studio
configuration; bridge and VKong CLI do not infer them from a mutable login
default. Missing configuration fails before bundle preparation. Local training
does not import the optional bridge.

For an ambiguous submit, Studio repeats the same job ID and start-request ID.
Bridge recompiles the requested bundle in a temporary directory. It reuses an
existing job bundle only when its complete regular-file tree has the same
digest as the newly compiled tree; symlinks or changed bytes fail closed. A
sidecar outside the synced bundle binds its digest, server/workspace and hash
of the start-request ID before the first CLI call. A retry with a different
binding is rejected. It then calls the CLI with the original idempotency key.
Neither bridge nor Studio
creates a second rental to reconcile a changed request. VKong remains the
authority for deduplicating the CLI start and owning cancellation/billing.

This fixes local pre-submit retry behavior, not the external CLI contract.
The real CLI still lacks versioned JSON and idempotent detached start. Studio's
route must not expose remote Start until it can persist remote identity and
project status/cancel, and a published image is available. The alternative of
blindly overwriting or blindly reusing a staged bundle risks billing a changed
request; relying on mutable CLI defaults risks acting in another workspace.

Tests cover missing/bound context, identical and changed bundle retries,
tampered/symlinked bundles, and unchanged local executor behavior. A live
reconnect/GPU test remains gated on the CLI and image release.
