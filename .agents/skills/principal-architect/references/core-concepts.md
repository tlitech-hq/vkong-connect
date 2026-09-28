# vkong-connect core concepts (architect cheat sheet)

Canonical detail lives in `docs/`. This file is the review checklist only.

## Ownership

| Owner | Responsibility |
|---|---|
| Studio (fork) | User choices, build identity, durable submit intent, remote identity and cursors, UI projection, result loading |
| Connect core | Portable contracts, compatibility validation, CLI transport, lifecycle delegation, structured errors/events |
| Product adapter | Job validation, input staging, bundle compilation, worker invocation, event mapping, output publication |
| Runner image | Immutable code/deps, runtime manifest, tested GPU platform, digest |
| VKong | Auth, workspace, placement, rentals, App/Run lifecycle, logs, secrets, billing, stop |

## Flow

```text
Studio build + validated request
  -> resolver (packaged catalog) -> image@sha256
  -> adapter compiles bundle (vkong.yaml, bridge-job.json, run_bridge.py, inputs/)
  -> vkong CLI (bound server/workspace): validate -> run --detach --auto-stop --idempotency-key
  -> runner checks runtime identity -> adapter runs worker -> VKONG_EVENT lines
  -> publish output (immutable revision) -> terminal success -> exit -> auto-stop
Studio: reconcile by IDs, follow logs by cursor, cancel -> wait for authoritative stopped
```

## Concepts to check

1. Not a control plane (no server/scheduler/run DB/billing)
2. Core/adapter isolation (static registry, no product imports in core)
3. CLI as versioned machine contract (no prose parsing, bound context, no token files)
4. One logical start (stable idempotency key, content-checked retry)
5. Billing honesty (stopped state is authoritative)
6. Success = durable, private, pinned output
7. Minimal, deterministic bundle within sync limits
8. Versioned contracts, fail closed on unknown versions
9. Pinned runtime (digest, full commits), no fabricated identities
10. Secrets only via VKong workspace secrets; redacted everywhere
11. Local training unchanged; VKong path optional and lazy
12. Evidence levels kept separate (local vs live)
