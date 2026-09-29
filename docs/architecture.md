# vkong-connect architecture

Design reference for the connector between product workloads (first: Unsloth
Studio) and VKong. What works today, known limits and history live in the area
READMEs listed in [docs/README.md](README.md); open work lives in
[GitHub Issues](https://github.com/tlitech-hq/vkong-connect/issues). Illustrative
release tags and proposed CLI commands below are design targets, not published
or available capabilities. Image selection and the minimal job bundle are refined
in [decisions/0002](decisions/0002-runtime-image-contract.md).

## 1. Decision

`vkong-connect` is a thin adapter and runner project. It is not another control
plane.

VKong already owns Apps, Runs, GPU placement, rentals, workspaces, secrets,
logs, infrastructure metrics, usage, billing, and cleanup. Reimplementing those
features in the bridge would create two sources of truth and two lifecycle
systems for one workload.

The bridge has one job: translate a product-specific training request into a
VKong task and translate that task's output back into a product-neutral stream
of training events and artifacts.

```text
Unsloth Studio
    |
    | VKongTrainingExecutor
    v
vkong CLI (machine-readable contract)
    |
    v
VKong App + Run + rental
    |
    v
bridge-runner --adapter unsloth
    |
    +-- Unsloth worker
    +-- structured progress events
    +-- checkpoint/final output publication
```

The first integration uses the installed VKong CLI. A future shared
`vkong-client` SDK may replace subprocess calls, but the backend semantics and
the adapter contract should remain unchanged.

### Proof-of-concept distribution

The initial integration is an experimental fork, not an official Unsloth
release. Keep the existing Python distribution name, imports, and CLI unchanged:

```text
distribution: unsloth
Python import: import unsloth
CLI:           unsloth studio
```

Only the repository is distinguished, for example
`github.com/tlitech-hq/unsloth-vkong`. Do not publish the fork or bridge to PyPI
during the proof of concept. Testers install the fork directly from Git into a
dedicated virtual environment.

The fork exposes a `vkong` extra whose dependency is pinned to a tagged bridge
revision:

```toml
[project.optional-dependencies]
vkong = [
    "vkong-connect @ git+https://github.com/tlitech-hq/vkong-connect.git@v0.1.0",
]
```

The resulting one-command installation is:

```bash
python -m pip install \
  "unsloth[vkong] @ git+https://github.com/tlitech-hq/unsloth-vkong.git@vkong-poc-v0.1.0"
```

Use a moving branch such as `vkong-poc` only for development. Tester
instructions use an immutable tag or commit so the Unsloth fork, bridge, runner
image, and CLI compatibility can be reproduced.

## 2. Current VKong capabilities

The public VKong documentation establishes the following behavior:

- An App groups its Runs, logs, metrics, usage, deployment history, and active
  rental.
- `type: task` is intended for training and other finite workloads.
- `vkong run --detach` lets a task survive terminal disconnection.
- `--auto-stop` destroys the rental after the remote process exits.
- Run logs and history remain available after the rental stops.
- Workspace secrets are injected as environment variables without being
  copied with project files.
- Normal workflows operate on Apps; direct instance commands are compatibility
  and operator tools.

Relevant documentation:

- <https://vkong.tli-tech.com/docs/app-lifecycle>
- <https://vkong.tli-tech.com/docs/cli/run>
- <https://vkong.tli-tech.com/docs/cli/project-config>
- <https://vkong.tli-tech.com/docs/dashboard>
- <https://vkong.tli-tech.com/docs/usage-and-credit>

Two present limitations directly affect remote training:

1. Generated files and checkpoints stay in the remote workspace; artifact
   download is documented as a planned workflow.
2. Source sync allows at most 50 MiB per file and 500 MiB in total, and excludes
   common model/checkpoint files. It is not a general model-data transport.

## 3. Scope and ownership

### VKong owns

- authentication and selected workspace;
- App and Run identity;
- provider access, capacity search, and GPU placement;
- rental state and machine lifecycle;
- project sync and workspace secrets;
- logs and infrastructure metrics;
- hourly price, usage, credit, and billing;
- stop and auto-stop behavior.

### Bridge core owns

- a small adapter interface;
- generation of a deterministic VKong task bundle;
- invocation of the VKong CLI through a stable JSON contract;
- canonical training event framing;
- adapter/runner version compatibility;
- mapping remote output references to the caller.

### Unsloth adapter owns

- validating and translating an Unsloth worker config;
- starting the existing Unsloth training worker remotely;
- translating native worker events to canonical events;
- periodic checkpoint publication (deferred after the first vertical slice);
- final adapter/model publication;
- resume compatibility checks.

### Unsloth Studio owns

- local-versus-VKong selection and UX;
- existing model/dataset/training validation;
- local run history and presentation;
- calling the bridge client;
- projecting canonical events into the existing charts/status UI;
- downloading or loading a published result.

## 4. What this repository contains

```text
vkong-connect/
  src/vkong_connect/
    client/
      vkong_cli.py          # typed argv-based CLI wrapper, bound context
    contracts/
      adapters.py           # adapter protocol and descriptor
      bundles.py            # product-neutral BundleSource / CompiledBundle
      events.py             # canonical training events
      runtime.py            # RuntimeIdentity
    adapters/
      registry.py           # trusted, versioned runner-adapter lookup
      unsloth/
        adapter.py          # Unsloth adapter implementation
        schema.py           # accepted Unsloth job documents (v1, v2)
        bundle.py           # deterministic task bundle compiler
        image_catalog.py    # packaged Studio build -> image resolver
        image-catalog.json  # promoted images (empty until first promotion)
        runtime_image.py    # image build-time fork verification
        runner.py           # remote entrypoint
        event_mapper.py     # Unsloth event -> canonical event
        outputs.py          # final output publication
    bridge.py               # prepare/submit/reconcile/follow/cancel facade
    runner.py               # validate and invoke the remote adapter
    runtime_manifest.py     # installed runtime manifest and preflight
    security.py             # secret redaction
  images/unsloth/           # runner image recipe
  schemas/                  # published JSON contracts
  tests/                    # unit and fake-CLI contract tests
  integration_tests/        # sibling Studio contract check
  docs/
```

There is no bridge API server, scheduler, run database, billing subsystem, or
provider abstraction in the initial design.

## 5. Required VKong CLI contract

The current human-readable CLI is sufficient for manual use but not a safe API
for Studio. The integration must not scrape terminal prose or TUI output.

The minimum machine-readable commands are:

```text
vkong version --json
vkong whoami --json
vkong validate -C <dir> --json
vkong run -C <dir> --detach --auto-stop --idempotency-key <key> --json
vkong app show <name-or-id> --json
vkong runs --app <name-or-id> --json
vkong logs <run-id> --follow --format jsonl
vkong app stop <name-or-id> --yes --json
```

If command names differ, the capabilities must still exist. JSON schemas and
exit codes are versioned CLI contracts, not incidental formatting.

A successful detached start needs at least:

```json
{
  "schema_version": "vkong.cli.v1",
  "app_id": "app_123",
  "app_name": "unsloth-01J...",
  "run_id": "run_123",
  "instance_id": "vk_123",
  "state": "running",
  "hourly_price": 1.2,
  "currency": "USD"
}
```

Errors need a stable `code`, human message, `retriable` flag, and non-zero exit
status. Creation needs a caller-supplied idempotency key or an equivalent way to
reconcile an ambiguous start without creating a second rental.

Until this contract exists, an automated Studio integration should be treated
as blocked. A developer-only prototype may wrap current CLI output, but that
parser must not become the production interface.

## 6. Generated task bundle

For every submitted job, the bridge creates an isolated, deterministic bundle:

```text
<staging-root>/<job-id>/
  vkong.yaml
  bridge-job.json
  run_bridge.py
  inputs/                 # only eligible small local inputs
```

Example generated `vkong.yaml`:

```yaml
type: task
app: unsloth-01JEXAMPLE
gpu: Any
num_gpus: 1
cpu_cores: 8
ram_gb: 32
disk_gb: 100
inet_down_mbps: 500
max_dph: 2.0
verified_only: true
image: registry.example/vkong/unsloth-runner@sha256:<digest>
secrets:
  - huggingface
  - wandb
srcs:
  - bridge-job.json
  - run_bridge.py
  - inputs/
work_dir: .
start_argv:
  - python3
  - run_bridge.py
  - --job
  - bridge-job.json
```

Rules:

- App names are unique per logical training job so an old rental is never
  silently reused.
- The image is pinned by digest and records compatible bridge and Unsloth
  versions.
- No access token is written into YAML, JSON, argv, synced files, or events.
- Local absolute paths are replaced by paths inside `inputs/`.
- The compiler rejects files and bundles above VKong sync limits before rent.
- Model weights and checkpoints are never sent through normal project sync.

## 7. Adapter contract

The first SDK is Python because the Unsloth worker is Python. Its concepts stay
language-neutral so later adapters need not be Python implementations.

```python
class RunnerAdapter(Protocol):
    descriptor: AdapterDescriptor

    def validate_job(self, document: Mapping[str, Any]) -> Any: ...
    def execute(self, job: Any, context: RunContext, events: EventSink) -> RunResult: ...
```

An `AdapterDescriptor` declares:

- adapter name and schema version;
- compatible runner/Unsloth versions;
- supported operations and training modes;
- accepted input types;
- output types;
- checkpoint/resume capability;
- minimum runtime/CUDA requirements.

The framework-neutral runner resolves `(name, schema_version)` through a static
registry and then delegates validation and execution. The runner only loads
adapters shipped in its image; it does not install or execute arbitrary adapter
code supplied by a user.

## 8. Canonical event protocol

The remote process writes one structured event per line. It may use a prefix so
ordinary library logs remain readable:

```text
VKONG_EVENT {"v":1,"seq":12,"type":"metric","payload":{"step":8,"loss":1.42}}
```

Every event contains:

```json
{
  "v": 1,
  "job_id": "01J...",
  "seq": 12,
  "time": "2026-09-20T10:00:00Z",
  "type": "metric",
  "payload": {}
}
```

Initial event types:

- `phase`: loading model, loading dataset, configuring, training, finalizing;
- `message`: human-readable status;
- `warning`: non-fatal issue;
- `metric`: step, total steps, epoch, loss, learning rate, gradient norm,
  tokens, elapsed time, and ETA when known;
- `checkpoint`: durable checkpoint URI and step;
- `artifact`: final output URI, kind, size, and checksum when known;
- `terminal`: succeeded, failed, or cancelled with stable error information.

Sequence numbers allow Studio to deduplicate replayed log lines. A terminal
success event is emitted only after the required final output has been
published successfully.

## 9. Unsloth runner

The initial runner reuses Unsloth's current entry point:

```python
run_training_process(
    event_queue=event_sink_adapter,
    stop_queue=cancellation_adapter,
    config=normalized_worker_config,
)
```

The queue-compatible event sink maps existing `status`, `progress`, `warning`,
`output_dir`, `complete`, and `error` events to the canonical protocol. This
avoids maintaining a second trainer implementation.

The runner must:

1. verify adapter, image, and Unsloth version compatibility;
2. resolve pinned Hugging Face model and dataset references;
3. use VKong-injected `HF_TOKEN`/`WANDB_API_KEY` without logging them;
4. start training and emit structured progress;
5. publish periodic resumable checkpoints when enabled;
6. publish the final adapter/model;
7. emit a terminal event and exit with the correct status.

## 10. Input policy

The first vertical slice supports:

- a hosted Hugging Face model reference;
- a hosted Hugging Face dataset reference;
- small local JSON/JSONL/CSV datasets copied into the generated bundle.

Pinned model/dataset revisions and remote checkpoint materialization are
required before the workflow is considered production-reproducible.

Phase one explicitly rejects:

- local model directories;
- local checkpoints;
- any source file over 50 MiB;
- any generated bundle over 500 MiB;
- dataset formats excluded by VKong sync;
- paths escaping the approved staging directory.

Large local datasets require a later native VKong artifact/upload workflow or
an explicit upload to Hugging Face/S3 before submission.

## 11. Output and checkpoint strategy

### Phase one: publish to Hugging Face

Until VKong has native artifact download, the runner publishes to a private
Hugging Face repository using a VKong workspace secret. The result event returns
a pinned repository/revision reference. Studio can then materialize it using its
existing Hugging Face support.

This avoids building a temporary bridge object store and makes `--auto-stop`
safe: the task exits only after publication succeeds.

Intermediate checkpoint policy:

- save at a configured interval;
- upload only complete checkpoint directories;
- publish a checkpoint event after upload succeeds;
- retain the latest N checkpoints by default;
- never report a local remote-machine path as resumable output.

### Later: native VKong artifacts

When VKong adds artifacts, replace the publisher implementation, not the
adapter/event/Studio contracts. Desired capabilities are:

```text
vkong artifact list <run-id> --json
vkong artifact download <run-id> <name>
```

## 12. Cancellation

`vkong app stop` is infrastructure cancellation. It must not be presented as a
successful "stop and save" unless the remote worker first confirms a durable
checkpoint.

Target checkpoint-enabled behavior:

- checkpoints are published periodically (not yet implemented in the POC);
- Cancel warns that progress after the last published checkpoint may be lost;
- Studio calls `vkong app stop ... --yes --json`;
- the run can resume only from the latest published checkpoint.

The desired later VKong capability is a task control signal such as
`checkpoint-and-stop`. The runner saves and publishes, exits cleanly, and then
auto-stop releases the rental.

## 13. Authentication and secrets

For the CLI-backed integration:

- Studio calls `vkong whoami --json` to check readiness.
- If login is required, Studio directs the user through `vkong login`.
- The bridge never reads the VKong CLI credential store directly.
- Workspace selection and authorization remain VKong concerns.
- Model registry and experiment tracker tokens are referenced by VKong secret
  bundle name.

Browser and CLI sessions are distinct according to VKong documentation. A web
dashboard login alone must not be treated as CLI readiness.

## 14. Failure behavior

- Ambiguous create: reconcile through idempotency key/App identity; never start
  a second rental speculatively.
- Capacity unavailable: surface a retriable placement error.
- User/config error: fail without retry.
- CLI disconnect: reconnect to the existing Run/log stream.
- Studio shutdown: the detached task continues; Studio reconciles on restart.
- Output publication failure: task fails and does not claim success.
- Lost machine/preemption: resume is offered only from a published checkpoint.
- Cancellation: stop the App and wait for VKong state `stopped` before claiming
  billing has ended.

## 15. Implementation phases

### Phase 0: make VKong scriptable

- Define and implement versioned JSON output for identity, validation, run,
  App/Run lookup, logs, and stop.
- Add start idempotency/reconciliation.
- Add a reconnectable Run log stream.
- Freeze the canonical training event schema.

Exit: a shell-free test client can start one task, lose its connection,
reconcile it, follow logs, and stop it without parsing human text.

### Phase 1: manual Unsloth runner

- Build a digest-pinned runner image.
- Run one supported LoRA/QLoRA configuration from an explicit JSON file.
- Use only HF-hosted model/dataset inputs.
- Emit structured events and publish the final private HF repository.
- Package `vkong-connect` for direct Git installation and create a tagged POC
  release; do not publish it to PyPI yet.

Exit: `vkong run --detach --auto-stop` produces a loadable adapter and retained
progress logs.

### Phase 2: bridge client and bundle compiler

- Implement typed CLI wrapper and deterministic bundle generation.
- Add compatibility and sync-limit validation.
- Add small local dataset staging.
- Add progress reconnection and checkpoint events.

Exit: an integration test can submit, disconnect, reconnect, complete, and
resolve the published output.

### Phase 3: Unsloth Studio integration

Implement the companion plan in the Unsloth fork. Local training must remain
the default and retain its current behavior.

### Phase 4: native artifacts and shared SDK

- Add VKong-native artifact upload/download.
- Extract a supported `vkong-client` SDK shared by CLI and integrations.
- Replace the CLI transport without changing adapter contracts.
- Add safe checkpoint-and-stop if VKong exposes task control.

### Phase 5: second adapter proof

Implement a materially different adapter without changing VKong App/Run
lifecycle or the canonical event protocol. Required core changes indicate that
Unsloth-specific behavior leaked across the adapter boundary.

## 16. Acceptance criteria

- No second control plane or run database is introduced.
- No human-readable CLI output is parsed in production code.
- Repeating an ambiguous start cannot create two billable rentals.
- Closing Studio does not stop a detached training task.
- Restarting Studio reconnects to the same App and Run.
- Success is impossible until final output publication succeeds.
- Auto-stop releases compute after success or failure.
- UI never claims billing stopped until VKong reports the App stopped.
- Tokens never appear in generated files, argv, logs, or events.
- Local training works unchanged when VKong is absent.
- The POC is installed from an explicit TLI GitHub URL in an isolated virtual
  environment and cannot be mistaken for the upstream PyPI installation
  instructions.
