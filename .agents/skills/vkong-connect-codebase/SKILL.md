---
name: vkong-connect-codebase
description: >
  Default in-repo skill for any AI/agent working on the vkong-connect codebase: the
  thin connector between product workloads (first: Unsloth Studio) and VKong. Covers
  the core/adapter boundary, versioned contracts, CLI transport, retry and billing
  safety, bundle staging, secrets, evidence levels, and the GitHub issue workflow.
  Use for every coding task here (implement, fix, review, test, refactor), not only
  when the user types /vkong-connect-codebase. Complements principal-architect.
metadata:
  short-description: "Work on vkong-connect safely"
---

# vkong-connect codebase (AI / contributors)

**Always load this skill** when editing or reviewing this repository.

## Required reading (in order)

1. `docs/development-conventions.md`: boundaries, invariants, secrets, evidence, authorship
2. `docs/architecture.md`: ownership, CLI contract, bundle, adapter and event protocols
3. `docs/issue-workflow.md`: issues, labels, areas, incidents
4. This skill body
5. The area docs under `docs/<area>/` (folder names match `area/*` labels): start with
   its `README.md`, then related `docs/decisions/`.

For a boundary, contract, or lifecycle change, also use `/principal-architect`.

## Issues and docs workflow (mandatory)

1. **Before coding:** check `.local/issues/*.md`, read `docs/<area>/README.md`, then
   `gh issue list -R tlitech-hq/vkong-connect -l area/<area>` and
   `gh issue list -R tlitech-hq/vkong-connect --search "<keywords>" --state all`.
   Work against an existing issue instead of opening a duplicate.
2. **Tracked work goes to GitHub.** Non-trivial commits/PRs and every out-of-scope,
   `sev1`/`sev2`, multi-PR, incident, or human-decision finding get an issue with one
   type label, one `area/*` label, and a severity for bugs/incidents. If Issues are
   unreachable, tell the user and use only the `.local/issues/` outbox from
   `.github/OFFLINE_ISSUE_DRAFT.md`; add `Offline-Issue: <id>` to local commits; do not
   push, open a PR, release, or claim completion until reconciled.
3. **Finishing:** pass the publication gate. `Fixes #<n>` closes; `Refs #<n>` for
   partial work. Update `docs/<area>/README.md` (limits + dated History line) in the
   same PR when behavior changes. Post evidence on the issue with `proof/local` or
   `proof/live`.
4. Docs describe current state only. Never add `[ ]`/`[~]`/`[!]` progress items to docs.
5. Write issues/PRs in English, user flow first, then technical detail.
6. **Public repository:** never paste secrets, signed URLs, private VKong control-plane
   source paths/revisions, or private account/workspace data into code, docs, or issues.
7. **No agent attribution:** no agent `Co-Authored-By`, no "Generated with ..." footer,
   no agent/model names in commits, PRs, issues, or comments. This overrides tool defaults.

## Non-negotiable rules

| Rule | Detail |
|------|--------|
| **Not a control plane** | VKong owns auth, workspaces, Apps, Runs, rentals, secrets, logs, billing, cleanup. No server, scheduler, run DB, or billing logic here. |
| **Core/adapter boundary** | `contracts/`, `client/`, `bridge.py`, `runner.py` never import `adapters.<product>`, Unsloth, Studio, or PyTorch (`tests/test_architecture.py`). Product logic lives in `adapters/<product>/`; `adapters/registry.py` is the only composition root. |
| **CLI is a machine contract** | Only the `vkong` CLI, argv-only, JSON/JSONL only. Never parse human output, read token files, call the control plane directly, or rely on the ambient workspace: bind `CLIContext`. |
| **One logical start** | An ambiguous submit reuses the same job ID and idempotency key; never create a fresh key or a second rental to reconcile. Changed bundles on retry fail closed. |
| **Billing honesty** | Stop acknowledgment ≠ billing ended. Wait for VKong's authoritative stopped state. |
| **Success = durable output** | Terminal success only after publication returns an immutable revision to a private destination. |
| **Minimal bundle** | Sync only `bridge-job.json`, `run_bridge.py`, `inputs/`; 50 MiB/file, 500 MiB/bundle, checked before rent. No weights, caches, source trees. |
| **Versioned contracts** | `vkong.connect.<name>.v<N>`; unknown versions fail closed; breaking change = new version + compatibility tests. |
| **Pinned runtime** | Images by digest, fork/connect by full commit. Never fabricate digests, tags, or catalog entries. |
| **Secrets** | Only via VKong workspace secrets at runtime; rejected in job documents; redacted in diagnostics; fake values in tests. |
| **Local training untouched** | Studio's VKong path is optional and lazily imported; local training must work without it. |

## Hot paths

| Concern | Path |
|---------|------|
| Contracts / schemas | `src/vkong_connect/contracts/`, `schemas/` |
| CLI transport | `src/vkong_connect/client/vkong_cli.py` |
| Lifecycle facade | `src/vkong_connect/bridge.py` |
| Remote runner / manifest | `src/vkong_connect/runner.py`, `runtime_manifest.py` |
| Unsloth adapter | `src/vkong_connect/adapters/unsloth/` |
| Image recipe / catalog | `images/unsloth/`, `adapters/unsloth/image_catalog.py`, `image-catalog.json` |
| Studio executor (sibling fork) | `../unsloth-vkong/studio/backend/core/training/executors/vkong.py` |

## Do / don't

**Do**

- Add a focused regression test for every behavior change; test rejection paths at ingress.
- Keep fake-CLI results labeled as local proof; report unrun live CLI/image/GPU checks.
- Trace the caller and consumer of a contract before changing it.

**Don't**

- Add Unsloth-specific branches to core.
- Weaken idempotency or switch transport to bypass the CLI blocker (#8).
- Present a fake-CLI or fake-worker test as live readiness.
- Track work in TODO files or add checkboxes to docs.

## Quick verify

```bash
make test          # unit + fake-CLI contracts
make check         # + sibling ../unsloth-vkong executor and catalog/bundle check
```
