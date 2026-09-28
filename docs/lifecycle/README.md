# Lifecycle

The facade a caller uses to run one training job: prepare the bundle, submit it,
reconcile the App, follow events, and cancel. VKong stays authoritative for App, Run,
rental, log, stop and billing state; vkong-connect keeps no run database.

## Current behavior

- `readiness`, `prepare`, `submit`, `reconcile`, `follow_events`, `cancel` on
  `VKongBridge`.
- Retrying `prepare` recompiles and compares the bundle; only an identical regular-file
  tree is reused, and symlinks or changed bytes fail closed.
- Before the first CLI call, a sidecar outside the synced bundle binds bundle digest,
  server/workspace and the start-key hash; a changed retry is rejected.
- Event following deduplicates by sequence; gaps, wrong job IDs and truncated logs
  fail closed.
- Proven by fake-CLI tests only.

## Limits and known issues

- No durable submit intent, `submission_unknown` state, persisted log cursor, or
  restart/fault-injection tests yet (#9)
- Live submit/reconnect depends on the CLI contract (#8)

## Code and design docs

- Code: `src/vkong_connect/bridge.py`
- Design: [architecture.md](../architecture.md) §12, §14,
  [0003](../decisions/0003-bound-submit-and-retry.md)

## History

- 2026-09-24 Content-checked bundle retry and bound submission added.
