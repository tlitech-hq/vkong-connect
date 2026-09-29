# 0001: Development foundation across Studio, bridge, and VKong

Date: 2026-09-24
Status: accepted for local architecture and development checks; remote product
integration remains blocked on the CLI contract and Studio persistence.

## Problem and user journey

A Studio user chooses VKong for training, connects an account/workspace once,
sees compute cost and output destination, and starts, follows, reconnects, and
cancels from Studio. CLI installation and implementation details belong in
onboarding/support. Billing and data destination remain visible user choices.

The existing facade imports Unsloth's bundle compiler, despite the documented
framework-neutral boundary. Existing tests exercise only that product. The
repositories also lack a single development entry point and an explicit
distinction between local contract evidence and a releasable integration.

## Decision

Adopt the VKong control-plane project's discipline: canonical ownership docs, narrow dependencies,
invariants enforced by tests, and separate local and live release gates. Do not
copy its control-plane packages, provider layer, database, or deployment stack.

- Studio owns configuration, execution selection, persisted submit intent,
  remote identity, event cursor, and UI projection. It keeps the local default.
- Bridge contracts own portable bundle/event types. A trusted in-process
  `BundleSource` exposes `job_id` and `compile(destination)`. The facade accepts
  that protocol and returns a generic `CompiledBundle`; it has no product import.
- Each product adapter owns its concrete request, compilation, worker mapping,
  and publication. Unsloth's existing `BundleRequest` gains the protocol method;
  its module re-exports `CompiledBundle` for source compatibility.
- `adapters/registry.py` is the remote composition root: the one explicit place
  wiring trusted runner adapters. User job JSON cannot select an import path.
- VKong CLI owns login and transport; VKong owns workspace authorization,
  idempotency enforcement, Apps/Runs, rentals, logs, secrets, and billing.

No CLI/job/event wire version changes are needed for this refactor. Existing
`bridge.prepare(request, root)` and Studio executor calls remain valid. Invalid
job IDs that are not portable directory components fail before compilation.

## Trust, failure, and compatibility

`BundleSource` is developer-supplied code, not untrusted JSON or a plugin loader.
Job documents and CLI responses remain validated at ingress. Staging validates
the job directory name before invoking an adapter; adapter validation still
owns file eligibility, secrets, size limits, and deterministic output.

Keep the existing HF output destination, explicit remote cancellation, and
auto-stop request. This change neither enables paid work nor changes data
movement. Publication failure is failure, and a stop acknowledgment is not proof
that billing ended. No durable intermediate checkpoint is promised in phase one.

Before live release, the CLI contract must bind immutable workspace/App/Run IDs,
reconcile the same start identity after response loss, and expose retained logs.
Studio must persist intent before submission and apply each event with its cursor
atomically. Ambient CLI workspace selection alone is insufficient for reconnect.
These are required next steps, not capabilities of today's facade.

## Alternatives

Keeping a default Unsloth compiler in core preserves the dependency violation.
A dynamic local plugin registry adds packaging and trust policy without a second
real integration. A request protocol preserves the current call shape and lets a
small second-product fixture prove the boundary. An HTTP bridge service or a new
VKong SDK would expand lifecycle and transport responsibilities prematurely.

## Implementation and verification

1. Move bundle result/protocol types to `contracts/bundles.py`; delegate prepare
   through the protocol and preserve Unsloth's public imports.
2. Prove core import isolation, second-product preparation/submission, and path
   rejection, alongside existing bundle/worker/CLI tests.
3. Add local Make targets and CI for dependency-free unit/contract checks. Run
   the real sibling Studio executor test separately against the bridge checkout.
4. Track remaining CLI, Studio, image, and GPU gates in the development docs.

Review and verification remain separate. Passing fake subprocess/worker tests
does not prove CLI compatibility, GPU training, output durability on failure,
provider cleanup, or release readiness.
