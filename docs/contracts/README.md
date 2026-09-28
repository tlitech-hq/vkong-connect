# Contracts

The versioned, product-neutral shapes that the caller (Studio), the connector core,
the remote runner and product adapters agree on: job documents, canonical training
events, runtime identity, and compiled bundles. Integrators and adapter authors read
this first.

## Current behavior

- Job documents: `vkong.connect.job.v1` and runtime-bound `vkong.connect.job.v2`,
  with JSON Schemas in `schemas/`. v2 requires pinned model commits and, for hosted
  datasets, dataset commits.
- Canonical line events (`VKONG_EVENT {...}`), types `phase`, `message`, `warning`,
  `metric`, `checkpoint`, `artifact`, `terminal`, with per-job sequence numbers.
- `RuntimeIdentity` (`vkong.connect.runtime.v1`): adapter, full adapter source commit,
  connect build, job/event/adapter contracts, remote platform.
- Core accepts any `BundleSource` and returns a generic `CompiledBundle`; it does not
  import Unsloth, Studio or PyTorch (enforced by `tests/test_architecture.py`).
- The runner resolves `(adapter name, schema version)` through a static registry; a
  second-product fixture proves the boundary in tests.
- Unknown schema versions fail closed. Proven by local tests only.

## Limits and known issues

- Only one real adapter (Unsloth); the boundary is not yet proven by a second product (#2)

## Code and design docs

- Code: `src/vkong_connect/contracts/`, `src/vkong_connect/adapters/registry.py`, `schemas/`
- Design: [architecture.md](../architecture.md) §7–8,
  [0001](../decisions/0001-development-foundation.md), [0002](../decisions/0002-runtime-image-contract.md)

## History

- 2026-09-29 Package and wire namespace renamed to `vkong_connect` / `vkong.connect.*`
  before any release.
- 2026-09-24 Product-neutral `BundleSource` boundary, runtime identity and v2 job
  document added.
