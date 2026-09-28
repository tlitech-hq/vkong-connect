# Development conventions

Rules for contributors and agents working on **vkong-connect**.
Design: [architecture.md](architecture.md). Issues and labels: [issue-workflow.md](issue-workflow.md).

These are decision rules for the POC, not a claim that the current code meets every
target. What works today is in the area READMEs.

---

## 1. Ownership and dependency direction

vkong-connect is a translator and runner, **not a second VKong control plane**. VKong
owns authentication, workspaces, Apps, Runs, rentals, placement, secrets, logs, usage,
billing, and cleanup. Do not add a server, scheduler, run database, billing logic, or
provider abstraction here without a decision record.

| Layer | Owns | Must not |
|---|---|---|
| `vkong_connect.contracts` | Portable, versioned job/event/runtime/bundle shapes | Import any product adapter, Studio, Unsloth or PyTorch |
| `vkong_connect.client` | Typed, shell-free VKong CLI calls with bound context | Parse human output, read token files, choose a workspace implicitly |
| `vkong_connect.bridge` (facade) | Prepare, submit, reconcile, follow, cancel | Import a product adapter; create a second rental to reconcile |
| `vkong_connect.adapters.<product>` | Product request, compilation, worker mapping, publication | Leak product branches into core |
| `adapters/registry.py` | The one explicit composition root for trusted runner adapters | Load adapter code named by user JSON |
| Studio (fork) | Config, execution choice, submit intent, remote identity, cursor, UI | Put CLI subprocess logic in UI, trainers, or workers |

`tests/test_architecture.py` enforces core import isolation. Keep it passing.

## 2. Contract and safety invariants

- Treat CLI output as a versioned machine contract, not terminal prose. Fail clearly
  when the installed CLI does not satisfy the required schema or idempotent
  detached start.
- A retry after an ambiguous submit must never create a second billable rental.
  Preserve the start request's idempotency identity through reconciliation.
- Bundles are deterministic and isolated. Validate paths and size limits before
  staging; never copy model caches, arbitrary local files, or secret values into
  bundles, argv, logs, or events.
- Success means the requested artifact is durably published, not merely that the
  worker exited. Distinguish cancellation, execution failure, and publication failure.
- A stop acknowledgment is not proof that billing ended; wait for VKong's
  authoritative stopped state.
- Evolve external schemas (`vkong.connect.*`) by version with compatibility tests;
  never silently reinterpret a field. Unknown schemas fail closed.
- Do not fabricate image digests, release tags, or catalog entries.

## 3. Secrets

- Credentials come only from VKong workspace secrets at runtime (for example
  `HF_TOKEN`). Job documents containing secret values are rejected.
- Tests and docs use obviously fake values (`hf_very_secret`, `change-me-…`), never
  real tokens. Diagnostics go through `vkong_connect.security.redact_secrets`.
- If a secret was ever committed or pasted into an issue, rotate it. The repository
  and its issues are public.

## 4. Tests and evidence

Core code and tests use only the Python standard library.

```bash
make test          # 59 unit and fake-CLI contract tests
make integration   # sibling ../unsloth-vkong Studio executor + catalog/bundle check
make check         # both
```

- Add a focused regression test for every behavior change. Validate untrusted CLI
  output, job JSON, paths and event fields at ingress, and test the rejection.
- Keep evidence states separate: not implemented, implemented, local proof
  (`proof/local`), live proof (`proof/live`). Fake-CLI, fake-worker and sibling
  Studio tests prove the contract seam only, never CLI compatibility, GPU training,
  output durability, provider cleanup, or release readiness.
- Report checks you could not run (live CLI, image build, GPU) explicitly.

## 5. Naming

- Repository, distribution and CLI: `vkong-connect`, `vkong-connect-runner`.
  Python package: `vkong_connect`. Wire schemas: `vkong.connect.<name>.v<N>`.
- "Bridge" remains the name of the core facade concept (`VKongBridge`,
  `BridgeEvent`, `bridge-job.json`, `run_bridge.py`).
- The Studio fork is `tlitech-hq/unsloth-vkong`; its distribution, imports and
  `unsloth studio` command stay identical to upstream.

## 6. Change discipline

For a boundary, contract, dependency-direction, or lifecycle change, write a short
decision record in `docs/decisions/NNNN-<slug>.md` before implementation: user
journey, ownership and data flow, contract versions, trust boundaries, retry and
cancellation semantics, alternatives, and verification (including live checks not
yet possible). Use the `principal-architect` skill to review it. Local refactors need
no decision record. Keep PRs focused.

## 7. Docs map (keep in sync when behavior changes)

| Doc | Update when… |
|---|---|
| `docs/<area>/README.md` | Behavior, limits, or history of that area change |
| [architecture.md](architecture.md) | Ownership, CLI contract, bundle, adapter, or event design changes |
| `docs/decisions/` | A new cross-boundary decision is made |
| [releases/RELEASE.md](releases/RELEASE.md) | Every tagged version |
| `images/unsloth/README.md` | Image build/publication procedure changes |
| [issue-workflow.md](issue-workflow.md) | Labels, areas, or the issue/incident process |
| **This file** | Boundaries, invariants, secrets, test and evidence rules |

## 8. Authorship and attribution

Commits, pull requests, issues, and comments are authored by the person responsible
for the change, never by a tool. This applies to every AI or coding agent.

- No agent attribution anywhere in git or GitHub: no `Co-Authored-By` trailer naming an
  agent or model, no "Generated with ..." footer, no agent or model name, badge, or
  product link in commit messages, PR titles or descriptions, issues, or comments.
- The git author and committer are the human contributor's identity.
- Default attribution added by an agent tool must be removed before committing,
  opening a PR, or filing an issue. Project rules override tool defaults.
- An `Offline-Issue:` trailer is a tracking identifier, not attribution.
- Mentioning a tool as **subject matter** (for example `.agents/` configuration) is fine.
