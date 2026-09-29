# Studio integration

How Unsloth Studio users train on VKong: they configure training in Studio as usual and
press **Train on VKong**. The fork [`tlitech-hq/unsloth-vkong`](https://github.com/tlitech-hq/unsloth-vkong)
(branch `vkong`) only mounts routes and a button; the logic lives here in
`vkong_connect.integrations.unsloth_studio` ([0004](../decisions/0004-thin-unsloth-fork.md),
[0005](../decisions/0005-current-cli-and-dev-runtime.md)).

## Current behavior

- Install: `./install.sh --local` from the fork checkout, then
  `./vkong/install-vkong-connect.sh`; `vkong login`; a VKong secret `huggingface` with
  `HF_TOKEN`. See the fork's `vkong/README.md`.
- The button sends Studio's own training payload (built without the local HF token) to
  Studio's local routes `/api/remote-training/{readiness,jobs,jobs/{id},jobs/{id}/stop}`,
  mounted only when vkong-connect is installed. All VKong operations go through the CLI.
- The service strips secrets and laptop-only fields, stages uploaded JSON/JSONL/CSV
  datasets up to 50 MiB, compiles a dev-runtime bundle, and starts it in a background
  thread. Job records live in `~/.vkong-connect/studio/`; a Studio restart reconnects by
  App name.
- The UI shows job state (preparing, starting GPU, running, finished, failed, stopped),
  a Stop button, and a link to the output repository.
- Verified by service/route tests, frontend typecheck/lint/build, and a cost-free live
  `validate` of the generated bundle. Not yet run end-to-end on a GPU or clicked in a
  running Studio.

## Limits and known issues

- No loss chart or step progress: the CLI has no machine-readable Run log stream (#8)
- LoRA/QLoRA only; no checkpoint resume (#1)
- Development runtime only; slow first start; unpushed commits cannot run remotely (#5, #6)
- Branch model and scheduled upstream-sync check not set up yet (#13)

## Code and design docs

- Code: `src/vkong_connect/integrations/unsloth_studio/`; fork hooks listed in the fork's
  `vkong/VKONG_PATCHES.md`; fork UI in `studio/frontend/src/features/remote-training/`
- Contract checks: `integration_tests/test_unsloth_fork_surfaces.py`

## History

- 2026-09-29 "Train on VKong" button, local routes and service; executor moved out of the
  fork; fork synced to upstream Unsloth `757a3f6e8`.
- 2026-09-24 Executor binds explicit server/workspace context.
