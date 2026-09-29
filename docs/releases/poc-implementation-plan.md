# POC implementation plan

> **History:** superseded on 2026-09-29. Open work moved to GitHub Issues #3–#12
> (milestone "POC live release") and #1–#2; current behavior lives in the area
> READMEs under `docs/`. Do not update the checkboxes below.

Reviewed: 2026-09-24. This was the execution checklist for the
[architecture](../architecture.md).

## 1. Product decision and scope

Studio automatically selects a tested runner image for its training runtime.
Normal users never build/select an image or sync the Unsloth source checkout.
VKong CLI remains the sole bridge transport for validation, task submission,
file sync, status, logs, and cancellation. Do not call the control plane directly.

POC: identify the Unsloth runtime by exact TLI fork commit, together with the
bridge build and contract versions. Later, explicitly tested Studio releases
may share a runtime/image when their training interface remains compatible.
The upstream `unsloth` version string alone cannot identify a fork build.

The image contains Python, GPU dependencies, Unsloth worker, and bridge runner.
Each job syncs only config, a tiny launcher, and eligible local datasets through
the generated `vkong.yaml` allowlist. Hosted models/datasets download on the GPU.
HF/W&B credentials come from VKong workspace secrets, never synced documents.

```text
Studio build metadata ──► runtime compatibility resolver ──► image@sha256
Training configuration ─► adapter bundle compiler ─────────► job bundle
                                                            │
                                               vkong CLI validate/run/sync
                                                            │
                                               runner checks runtime identity
                                                            │
                                               train → publish → exit/auto-stop
```

Repository boundary for this work:

- `vkong-connect`: contracts, resolver, adapters, bundle, CLI transport, runner,
  image recipe, tests and development documentation.
- Unsloth fork: later companion changes for build identity, executor, history,
  event projection and UI; identified separately below.
- VKong control plane/CLI: external. Missing CLI capabilities are external blockers,
  not authorization to modify its code. Never work around them with terminal
  scraping, direct RPC, SSH, or a second lifecycle service.

Deferred: source-sync development mode, dynamic plugin installation, a new
control plane/SDK, remote resume, checkpoint-and-stop, native volume integration,
and public PyPI publication.

## 2. Review findings and evidence

Reference: VKong CLI and platform behavior as reviewed on 2026-09-24.

| Finding | Current evidence | Required action |
|---|---|---|
| Core/product boundary | Bridge `contracts/bundles.py` and `bridge.py` now accept `BundleSource`; the Unsloth adapter owns compilation | Verify and retain isolation; do not add Unsloth branches to core |
| No automatic image selection | Studio executor reads `UNSLOTH_VKONG_RUNNER_IMAGE` | Add build identity, compatibility catalog and resolver |
| Image pin is not compatibility proof | Bundle checks digest syntax; Dockerfile requires a nonempty fork ref, not an immutable commit | Verify source identity, actual registry manifest and built runtime metadata |
| CLI JSON exists but differs | CLI JSON uses an `{ok,data,code,error}` envelope; bridge expects flat `vkong.cli.v1` | Agree/test a supported machine contract; do not guess formats |
| Submit contract unavailable | `run` has no JSON output and no caller idempotency flag; request IDs are generated internally | Keep live submit blocked until equivalent durable capability is available |
| Workspace can drift | CLI chooses workspace from flag → environment → saved config; bridge had no bound context | Bind server/workspace ID per logical submission and all later operations |
| Log contract unavailable | No root `logs` command; `runs` has no `--app`; task logs are sequence/text with truncation | Establish cursor, retention and terminal reconciliation semantics |
| Native storage already exists | VKong Storage volumes and managed checkpoints | Describe it as unintegrated, not nonexistent; a current volume is not per-Run artifact history |
| Publication needs stronger proof | Bridge publisher permits absent commit OID and does not verify existing repo privacy | Require immutable output identity and enforce private destination policy |
| Studio integration incomplete | Executor exists; route/UI/history wiring is pending | Deliver after CLI and lifecycle contracts are proven |

Architecture direction: suitable for continued development. Live release: blocked
by CLI compatibility, context/recovery, and Studio integration. Fake CLI tests
cannot clear these blockers.

## 3. Ownership and contracts

| Owner | Responsibility |
|---|---|
| Studio | User choices, build metadata, input authorization, durable submit intent, remote identity/cursors, charts/history, result loading |
| Bridge core | Portable contracts, compatibility validation, lifecycle delegation, structured errors/events |
| Unsloth adapter | Worker config validation, eligible input staging, worker invocation, native-event mapping and output publication |
| Runner image release | Immutable code/dependencies, runtime metadata, tested GPU platform and image digest |
| VKong CLI/control plane | Login, workspace authorization, file transfer, placement, durable start identity, App/Run lifecycle, stop, logs and billing |

Persist no credentials in release metadata, job bundles or Studio history.
Studio stores a projection of remote state; bridge has no run database. A local
projection never overrides VKong's resource or billing state.

Proposed compatibility record (schema to implement, not an existing API):

```text
catalog_schema
studio_build_id / allowed_studio_builds
training_runtime_id
unsloth_fork_commit
bridge_runner_build_id
compatible_client_contracts
adapter_schema + job_schema + event_schema
required_cli_contract/capabilities
remote_platform + GPU/backend constraints
image_ref@sha256:<digest>
```

Keep catalog data product-specific and validation primitives generic. Ship the
reviewed catalog as package data with the release; no selection service is
needed. Unknown builds fail before rent. Do not fall back to `latest`, nearest
version, upstream image, or local execution. Editable/dirty installs are not
supported release identities; provide an explicit developer override only if
its provenance and compatibility can be verified, clearly marked untested.

The laptop's CPU architecture does not choose the GPU image architecture. The
remote platform does. Store resolved compatibility metadata and bundle hash with
each job; reconnect keeps that original identity even after Studio upgrades.

## 4. Step-by-step implementation checklist

Unchecked items are pending even if a partial implementation exists. Complete
each gate with evidence before promoting the corresponding capability.

### Step 0 — Establish the local development baseline

Owner: bridge. No external prerequisite.

- [x] Verify generic bundle boundary, compatibility imports and second-product fixture.
- [x] Correct the existing architecture test's relative-import false positive:
  `contracts.adapters` is a neutral contract, not the product `adapters` package.
- [x] Add reproducible development commands and CI for unit/contract tests.
- [ ] Declare tested Python/OS matrix; current executable fake CLI uses POSIX
  shebangs, so Windows needs a real supported fixture before claiming coverage.
- [x] Run the sibling Studio executor contract against the local bridge package.
- [x] Record source revisions, commands, results and skipped checks in status docs.

Gate: repeatable local tests without GPU, login or optional ML dependencies;
importing core does not import Studio, Unsloth or PyTorch.

### Step 1 — Define runtime identity and catalog schema

Owner: bridge, with build-metadata producer in the Studio fork.

- [x] Define versioned `RuntimeIdentity` and `ImageCompatibility` contracts/schema.
- [x] Require full immutable fork and bridge commits in runtime identity; include
  bridge build identity and explicit job/event/adapter contracts.
- [ ] Emit Studio build metadata during packaging; do not inspect an unrelated
  working directory's Git HEAD or trust upstream package version alone.
- [ ] Define supported training modes, remote architecture and GPU backend constraints.
- [x] Package catalog resources in a wheel and test installed-package loading.
- [x] Reject duplicate/ambiguous entries, unknown schema, invalid digest and
  unsupported builds with stable errors.

Gate: fixtures resolve exactly one intended runtime entry or fail clearly.
No actual image digest may be invented to fill a catalog entry.

### Step 2 — Make runner image production reproducible

Owner: bridge image/release workflow; build/publish is an explicit release action.

- [ ] Pin base image digest, full fork commit, bridge source/build and dependency set.
- [x] Require full fork/bridge commit arguments and verify installed Unsloth's
  VCS commit from package metadata during image build. Published image proof is pending.
- [x] Embed generation of runtime manifest and provenance labels in the image recipe
  (build and published-image proof still pending).
- [x] Add runner `--version` machine output and pre-training compatibility check that reports installed
  build metadata and checks job compatibility before loading a model.
- [ ] Verify worker imports without laptop source mounts or UI build dependencies.
- [ ] Resolve and verify the published manifest digest and remote platform.
- [ ] Test the image through VKong's actual startup path; a custom inherited
  Docker ENTRYPOINT alone is not proof that VKong executes it.
- [ ] Promote the catalog entry only after image and supported GPU evidence exists.

Gate: exact source tuple → retrievable digest → matching runtime manifest.
Keep old immutable images available for the supported release/reconnect window.

### Step 3 — Resolve image automatically before submission

Owner: bridge resolver; Studio passes its build identity.

- [ ] Add compute/GPU constraints to the pure resolver; build/mode/platform → image resolution is implemented.
- [x] Validate client/runner job, adapter and event contract compatibility explicitly.
- [x] Return typed errors for missing/unsupported catalog entries.
- [ ] Replace the normal user path's image environment requirement with resolver output.
- [ ] Keep any developer image override separate and subject to the same validation.
- [x] Test multiple Studio UI releases using an explicitly shared runtime, and a
  changed worker/config selecting a new runtime rather than the old image.
- [ ] Test macOS laptop → Linux GPU selection and unsupported GPU/backend rejection.

Gate: supported releases need no user image configuration; unknown builds fail
locally before a billable operation. Runtime checks inside the image are a second
defense, not the first compatibility check after rent.

### Step 4 — Harden the minimal job bundle

Owner: bridge adapter/compiler.

- [x] Extend the job contract with expected runtime identity; explicitly version
  breaking changes and preserve/reject older documents according to policy.
- [x] Keep sync allowlist to `bridge-job.json`, `run_bridge.py`, `inputs/`.
- [ ] Add a broader exclusion test for source trees, `.git`, venvs, caches and weights; current tests check bundle contents and token omission.
- [ ] Enforce approved input roots, path containment and symlink policy; reject
  oversized or changing inputs and record content hashes.
- [x] Preserve 50 MiB/file and 500 MiB/bundle limits with metadata included.
- [ ] Resolve hosted model/dataset revisions in Studio; v2 bundle rejects missing
  commit pins and does not assume a mutable HF branch is reproducible.
- [ ] Bind bundle digest to logical submission; retries reuse the prepared bundle
  or verify its contents instead of overwriting it or preparing a new job.

Gate: identical supported inputs yield identical content; invalid inputs fail
before rent. Configuration-only changes never require rebuilding runtime code.

### Step 5 — Close the actual CLI contract and context gap

Owner: bridge transport; missing VKong capability is an external dependency.
This checklist does not authorize changes in the VKong CLI.

- [x] Inventory current CLI commands/envelopes against the bridge contract.
- [ ] Agree a versioned contract/profile; normalize supported JSON into typed bridge
  results without assuming today's flat fake responses are the real interface.
- [x] Define bound HTTPS server/workspace context; pass its explicit workspace ID
  on every scoped command. Never read token files.
- [ ] Test ambient workspace/server changes between readiness, start, reconnect and stop.
- [ ] Require detached start, auto-stop, caller-stable logical submission identity,
  recoverable App/Run IDs and machine-readable retained logs.
- [ ] Finish transport error/timeout coverage: malformed output, executable paths,
  subprocess cleanup and secret-safe diagnostics. stdout JSON is separated from
  bounded stderr diagnostics.
- [ ] Add full actual CLI fixtures and read-only capability probes. A local
  `vkong version --json` probe confirmed the current unversioned envelope;
  readiness must report all unsupported capabilities before attempting submit.

Gate: a supported CLI satisfies the contract. Until then, keep live submission
disabled and continue Steps 1–4 and fake lifecycle work. Do not silently weaken
idempotency or switch transport to bypass the blocker.

### Step 6 — Make submit, reconnect and cancel recoverable

Owner: bridge contracts + Studio persistence companion work.

- [ ] Studio durably records intent before submit: server/workspace, job ID,
  start key, runtime/image, bundle hash and output destination.
- [ ] One logical Start uses one key, including concurrent clicks and retries.
- [ ] Lost response/timeout enters `submission_unknown`, retaining identity;
  reconcile the existing operation, never create a fresh key automatically.
- [ ] Reconcile by scoped immutable IDs/start identity, not display App name alone.
- [ ] Separate training result, artifact durability and compute/stop state.
- [ ] Persist log transport cursor independently of bridge event sequence; bind
  events to expected job/Run and commit UI projection + cursor atomically.
- [ ] Define log truncation/gap behavior and independent terminal-state lookup;
  missing retained logs cannot imply success or trigger resubmission.
- [ ] Bound reconnect backoff; authorization loss stops polling with an actionable
  status and does not imply the remote rental has stopped.
- [ ] Cancel is idempotent; remain `stopping` until authoritative completion.
- [ ] Test process restart/DB reopen, response loss, duplicate/out-of-order events,
  stale Run, delayed stop, publication failure and failed auto-stop.

Gate: fault-injection tests prove no duplicate logical start and correct recovery.
Real provider cleanup and billing completion still require Step 9.

### Step 7 — Make final output verifiable

Owner: Unsloth adapter/publisher. Keep private HF as current output policy.

- [ ] Preflight output configuration and required workspace secret references
  where a supported capability exists; validate credentials again in runner.
- [x] Check existing repository privacy; `create_repo(private=True, exist_ok=True)`
  alone must not satisfy the private-output guarantee.
- [x] Require a successful publication with immutable commit OID before emitting
  `artifact` and terminal success; reject missing revision.
- [ ] Define retries/concurrent jobs so every result references its own immutable
  revision and a partial upload cannot be presented as a completed artifact.
- [ ] Test failed upload and output containment at publisher boundary; absent OID
  and existing public repo are covered.
- [ ] Show publication failure and possible data loss honestly: auto-stop can remove
  unpublished local output. Do not add indefinite paid retention implicitly.

Gate: emitted success identifies a private, loadable, pinned artifact. Native
VKong volumes/checkpoint APIs remain separate integration work with their own
durability, resume, data movement and cost decision.

### Step 8 — Wire the Studio experience

Owner: Unsloth fork companion work, after bridge APIs stabilize.

- [ ] Select local/VKong after common validation and before local GPU admission.
- [ ] Keep bridge optional/lazy; prove local training without bridge or VKong CLI.
- [ ] Add connection/workspace readiness and automatic runtime/image resolution.
- [ ] Show compute choice, hourly ceiling (not a total budget), output destination
  and auto-stop; hide image/CLI/App internals in normal training controls.
- [ ] Integrate durable intent/history and event projection from Step 6.
- [ ] Closing/reopening Studio reconnects to the same job; an upgrade preserves
  old job runtime/contract metadata and supports or clearly blocks old replay.
- [ ] Provide remote Cancel with no unsupported Stop-and-Save/resume claim.
- [ ] Add load/download pinned result actions without treating remote paths as local.
- [ ] Keep feature unavailable until readiness gates pass; no silent local fallback.

Gate: user completes the flow inside Studio after initial connection, without
writing YAML, selecting image digests or operating instance IDs.

### Step 9 — Release and real GPU proof

Owner: coordinated bridge/image/Studio release; requires a supported CLI and
separately authorized account, budget and publication destination.

- [ ] Install pinned fork + bridge refs in a clean venv; no fabricated release tags.
- [ ] Prove published image starts on the declared supported GPU/platform.
- [ ] Train a small supported LoRA/QLoRA job and verify its pinned private artifact.
- [ ] Close/reopen Studio during training and verify history/event recovery.
- [ ] Prove cancel and auto-stop, including failure handling and remaining rentals.
- [ ] Verify authoritative stopped state before claiming compute billing ended.
- [ ] Check generated files, logs and argv for secret leakage.
- [ ] Record CLI version, fork/bridge commits, image digest, test environment,
  App/Run IDs, cleanup evidence and untested cases without credentials.
- [ ] Publish compatibility mapping with the release and document support/rollback.

Gate: sign off local, real CLI, image, GPU and Studio E2E evidence separately.
A small successful job does not prove multi-GPU, every GPU backend, large datasets,
remote resume, or provider failure recovery.

## 5. Implementation order and review units

Recommended small changes:

1. Baseline/architecture tests and dev commands (Step 0).
2. Runtime schemas, catalog and pure resolver (Steps 1 and 3).
3. Image metadata/build verification, then publish tested entries (Step 2).
4. Runtime-aware minimal bundle (Step 4).
5. CLI profiles/context/readiness (Step 5; live path externally blocked).
6. Recovery/event contracts and tests (Step 6).
7. Publication guarantees (Step 7; can proceed independently).
8. Studio companion integration (Step 8).
9. Authorized live evidence and release promotion (Step 9).

No step is complete just because code is written. For each change record:

```text
Scope / owner:
Source commits and contract versions:
Behavior implemented:
Local checks and results:
CLI/image/GPU/E2E evidence, or explicitly not run:
Remaining blockers and compatibility impact:
```

Local commands already available (no rental or network required):

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m unittest discover \
  -s ../unsloth-vkong/studio/backend/tests -p test_vkong_training_executor.py -v
```

Do not mark a cross-repository test as proof of runtime execution: its CLI is fake.
