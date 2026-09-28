# 0005: Work with today's VKong CLI and a development runtime

Date: 2026-09-29
Status: accepted for the POC. Tracked in #8, #11, #13.

## Problem and user journey

A Studio user should configure training as usual, press **Train on VKong**, and get a
private Hugging Face model, without waiting for the versioned CLI contract (#8) or a
published runner image (#5).

## Decision

1. **Accept the CLI's current JSON envelope.** `VKongCLI` normalizes
   `{ok, data, code, error}` (profile `vkong.cli.envelope`) into the same typed results
   as the proposed `vkong.cli.v1`. VKong is still reached only through the CLI.
2. **Start once per job-unique App name.** `run` has no JSON or idempotency key. VKong
   records the App and Run before renting, so before `run --detach --auto-stop` the client
   lists Apps: an App with the job's generated name means an earlier attempt reached VKong
   and is reconciled instead of renting again; two such Apps fail closed. The CLI's human
   output is never parsed; App and Run IDs come from `app list/show` and `runs`.
3. **No progress stream.** Without a machine-readable log command, `follow_logs` raises
   `CapabilityUnavailableError` and Studio shows job state only.
4. **Development runtime.** Jobs run on the official `unsloth/unsloth:studio` image pinned
   by digest. `init_cmd` picks the image's Python that has `unsloth`, `trl` and
   `structlog`, installs vkong-connect and extracts the fork's `studio/backend` from GitHub
   archives at the exact commits installed on the user's machine. The runner applies
   Studio's `_build_training_worker_config` on the GPU host so defaults and the device
   backend come from the remote Studio code.
5. **Studio integration lives here.** `vkong_connect.integrations.unsloth_studio` provides
   the service and the FastAPI routes Studio mounts at `/api/remote-training`
   (0004); the fork adds a 9-line mount and a 2-line button hook.

## Risks and limits

- A narrow race remains if two processes start the same job concurrently between the App
  check and `run`; Studio starts each job once from one process.
- Killing Studio during `run --detach` leaves the App recorded; on restart the job
  reconnects by App name or is marked failed. The GPU still auto-stops when the task ends.
- Dev runtime depends on GitHub availability, pulls a large image, and only runs pushed
  commits. It is never promoted to the image catalog.
- Run `status`/`reason` are shown as VKong reports them; success means the App stopped
  after the task ended and the output repository should be checked.

## Alternatives

Parsing `run` output was rejected (not a contract). Calling the control-plane API was
rejected (VKong owns the API; connect uses the CLI only). Building and publishing a
runner image first (#5) remains the release path but blocked a usable POC.

## Verification

Unit and fake-CLI tests for both CLI profiles, the Studio service and routes (FastAPI
routes tested in a FastAPI environment). Live, cost-free checks on 2026-09-29 against the
real CLI: readiness, `validate` of a dev-runtime Studio bundle (security scan clean),
`app show`, `runs`. A live GPU run is pending.
