# Unsloth adapter

Turns an Unsloth Studio training request into a small VKong task bundle, runs
Studio's existing worker (`run_training_process`) on the remote machine, and maps its
native events to canonical events.

## Current behavior

- Strict job validation; documents containing secret values are rejected.
- Deterministic, atomic bundle: `vkong.yaml`, `bridge-job.json`, `run_bridge.py`,
  `inputs/`. The sync allowlist is exactly those files.
- Inputs: hosted Hugging Face model/dataset references, and small local
  `.json`/`.jsonl`/`.csv` datasets staged into `inputs/`. Limits: 50 MiB per file,
  500 MiB per bundle, checked before rent.
- Generated App names are unique per logical job.
- Unsloth worker `status`/`progress`/`warning`/`complete`/`error` events are mapped to
  canonical events with secret redaction.
- Local model directories and `resume_from_checkpoint` are rejected in phase one.
- Proven by unit tests and the sibling Studio executor test; the worker has not run
  remotely.

## Limits and known issues

- No broad exclusion test for source trees, `.git`, venvs, caches, weights; approved
  input roots, symlink policy and content hashes not enforced (#7)
- Studio does not resolve hosted model/dataset revisions to commits yet (#7)

## Code and design docs

- Code: `src/vkong_connect/adapters/unsloth/` (`schema.py`, `bundle.py`, `adapter.py`,
  `runner.py`, `event_mapper.py`)
- Design: [architecture.md](../architecture.md) §6, §9–10

## History

- 2026-09-29 Worker entry point re-checked after syncing the fork to upstream Unsloth
  `757a3f6e8`; contract tests pass.
- 2026-09-24 v2 job with runtime identity and pinned revisions added.
