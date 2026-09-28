# CLI transport

How vkong-connect talks to VKong: only through the installed `vkong` CLI, with typed,
shell-free subprocess calls and an explicitly bound server and workspace. It never
parses human output, reads token files, or calls the control plane directly.

## Current behavior

- Typed wrapper for `version`, `whoami`, `validate`, detached `run`, `app show`,
  `runs`, `logs --follow`, and `app stop`, accepting JSON/JSONL only. stdout JSON is
  separated from bounded stderr diagnostics.
- Rental-affecting calls require a `CLIContext` with an HTTPS server and immutable
  workspace ID; Studio's default executor binds it explicitly.
- Detached, auto-stop, idempotent start request is modeled.
- **Works with today's CLI** (profile `vkong.cli.envelope`, [0005](../decisions/0005-current-cli-and-dev-runtime.md)):
  `{ok,data,code,error}` responses are normalized into the same typed results. `run` is
  started once per job-unique App name and reconciled through `app list/show` and `runs`;
  its human output is never parsed. `whoami` must match the bound workspace.
- Verified live at no cost on 2026-09-29: readiness, `validate`, `app show`, `runs`.
  A live `run` has not been exercised yet.

## Limits and known issues

- No machine-readable Run log stream, so no training progress (`CapabilityUnavailableError`);
  `run` has no caller idempotency key, leaving a narrow concurrent-start race (#8)
- No tests yet for ambient workspace/server changes between readiness, start,
  reconnect and stop (#8)
- Transport error/timeout coverage incomplete: malformed output, executable paths,
  subprocess cleanup (#8)

## Code and design docs

- Code: `src/vkong_connect/client/vkong_cli.py`
- Design: [architecture.md](../architecture.md) §5, §13,
  [0003](../decisions/0003-bound-submit-and-retry.md)

## History

- 2026-09-29 Current CLI envelope supported; start guarded by job-unique App name (0005).
- 2026-09-24 Current CLI envelopes inventoried; bound server/workspace context required.
