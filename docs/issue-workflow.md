# Issue and docs workflow

How work, bugs, and incidents are tracked for **vkong-connect**. Applies to
contributors and coding agents alike. The repository and its issues are
**public**: never paste secrets, tokens, signed URLs, private VKong control-plane
source details, or private account/workspace data.

## Where each kind of information lives

| Information | Single source | Checkboxes |
|---|---|---|
| Work in progress, bugs, backlog, status | GitHub Issues on `tlitech-hq/vkong-connect` | Yes |
| Drafts while GitHub Issues cannot be durably read/written | Gitignored `.local/issues/*.md` offline outbox | Temporary only |
| What an area does today, known limits, fix history | `docs/<area>/README.md` | No |
| Incidents (a rental, billing, or data problem caused by this code) | Issue labeled `incident`, postmortem in `docs/incidents/` | Only in the issue |
| Design rationale | `docs/architecture.md`, `docs/decisions/` | No; open work becomes issues |
| Studio-side work | Tracked here with `area/studio`; code lands in `tlitech-hq/unsloth-vkong` | Yes |

Docs describe the current state. They do not track progress: never add `[ ]`, `[~]`,
or `[!]` status items to product/design docs. Arbitrary local notes, report folders,
TODO comments and chat summaries are not a tracking system. The sole exception is the
`.local/issues/` offline outbox below: a transport buffer for later GitHub
reconciliation, never a second backlog.

## Tracking invariant

Any non-trivial work intended for a commit or PR has a GitHub issue, or an offline
draft while issue access is unavailable. This includes features, bug fixes,
refactors, contract changes, and documentation changes that need a reviewable
checklist. A truly mechanical typo may be committed directly when it does not change
behavior or policy and needs no follow-up.

```text
GitHub available
  -> search open and closed issues
  -> reuse an existing issue or create one
  -> work, evidence, PR (Fixes #<n> for closing work; Refs #<n> for partial work)

GitHub Issues cannot be durably read or written
  -> tell the user that tracking is offline
  -> create one gitignored .local/issues/<UTC timestamp>-<slug>.md draft
  -> local work and local commits may continue
  -> GitHub returns: search first, then create or update the issue
  -> read the issue back and verify checklist/evidence
  -> delete the reconciled local draft
```

A malformed command, invalid label, or bad request is not an outage: fix the request
and retry instead of using offline mode.

### Offline outbox

Create drafts from [`.github/OFFLINE_ISSUE_DRAFT.md`](../.github/OFFLINE_ISSUE_DRAFT.md)
at `.local/issues/<UTC timestamp>-<slug>.md` (for example
`.local/issues/20260929T101500Z-cli-envelope.md`). Give each draft a stable
`Offline-ID` containing a UUID and keep it across retries and handoffs.

- Never force-add or commit a draft. Preserve drafts through `git clean -X`/`-x`,
  worktree removal and machine changes; gitignore is not a backup.
- At the start of work, check `.local/issues/*.md` even though `git status` hides it.
- Local commits for that work carry an `Offline-Issue: <Offline-ID>` trailer (a tracking
  identifier, not authorship) until the draft is reconciled.
- Do not push, open a PR, cut a release, or claim completion for that work until the
  draft is reconciled.

### Reconciliation gate

1. Search open and closed issues by the exact `Offline-ID` and by area/keywords.
2. Merge into a matching active issue, or create one with the task/bug template and
   labels. Include the literal `Offline-ID: <id>` in the body or sync comment.
3. Read the issue back: marker, all checklist items (including unfinished work),
   facts, evidence, labels and commit references must be present.
4. Only then delete the draft. Before a create/comment request, record
   `not-sent` / `sent-unconfirmed` / `confirmed` in the draft; if a response is lost,
   do not resend automatically. Search for the marker first; an empty search is not
   proof the write failed.

### Publication gate

Before push, PR, merge or release, inspect the commit range being published:

1. Every non-trivial change maps to an issue; relevant drafts are reconciled and removed.
2. Every `Offline-Issue` trailer in the range resolves to a verified issue marker.
3. Use `Fixes #<n>` only when the PR meets the issue's closing criteria; otherwise
   `Refs #<n>` and leave the issue open.
4. Keep unfinished criteria unchecked. Add the issue/PR to the area README history;
   remove a known limit only when it is actually resolved and verified.

These are contributor checks, not hooks or CI guarantees.

## Writing issues

Issues, comments and PRs are written in English. Keep titles short; code identifiers
stay as they are. Every issue must be understandable by someone who does not know
the code. Order content from the user's point of view to the technical detail:

1. **User flow:** what the Studio user, integrator, or operator was doing, step by step.
2. **Expected vs actual, and impact:** what they expected, what happened, what it cost
   (money, rental time, lost output, blocked work).
3. **Technical details:** code paths, contracts, confirmed cause versus guesses.

Do not open with module names or error codes. PR descriptions follow the same order.
Issues, comments, PRs, and commits never carry AI or coding-agent attribution; see
[development-conventions.md](development-conventions.md#8-authorship-and-attribution).

## Labels

Every issue has exactly one **type**, one primary **area**, and a **severity** when it
is a bug or incident. Add a second area only when the issue truly spans both.

| Group | Labels |
|---|---|
| Type | `bug`, `incident`, `enhancement`, `tech-debt`, `documentation`, `ops` (image publication, catalog promotion, cleanup) |
| Severity | `sev1` lost money or data, or an unstoppable rental; `sev2` a feature is broken; `sev3` annoying but usable |
| Proof | `proof/local` verified by unit/contract/fake-CLI tests; `proof/live` verified with the real VKong CLI, image and GPU |
| Status | `blocked/vkong` waiting on a VKong CLI or platform capability |
| Source | `from/user` reported by a user |

### Areas

Choose by domain, not by the directory you happened to edit.

| Label | Scope | Main code |
|---|---|---|
| `area/contracts` | Job, event, runtime, bundle contracts; JSON schemas; adapter registry and boundary | `src/vkong_connect/contracts/`, `adapters/registry.py`, `schemas/` |
| `area/cli` | VKong CLI transport, envelopes, bound server/workspace context, readiness probes | `src/vkong_connect/client/` |
| `area/lifecycle` | Prepare, submit, reconcile, follow, cancel; retry and idempotency binding | `src/vkong_connect/bridge.py` |
| `area/runtime` | Remote runner, runtime identity/manifest, image recipe, catalog and resolver | `runner.py`, `runtime_manifest.py`, `adapters/unsloth/image_catalog.py`, `runtime_image.py`, `images/` |
| `area/adapter-unsloth` | Unsloth job schema, bundle compiler, input staging, worker invocation, event mapping | `src/vkong_connect/adapters/unsloth/` (except outputs and image) |
| `area/outputs` | Output publication, checkpoints, artifacts | `adapters/unsloth/outputs.py` |
| `area/studio` | Unsloth Studio executor, route/UI, history, readiness | `tlitech-hq/unsloth-vkong`: `studio/backend/core/training/executors/` |
| `area/infra` | Packaging, CI, Makefile, releases, live proof | `pyproject.toml`, `Makefile`, `.github/`, `integration_tests/` |

Tests belong to the area they exercise.

## Before starting work

1. Check `.local/issues/*.md` for pending offline drafts. Read the area's
   `docs/<area>/README.md` and its design docs as needed.
2. Look for existing work and past fixes:

   ```bash
   gh issue list -l area/lifecycle
   gh issue list --search "idempotency" --state all
   ```

3. If an issue exists, work against it and post progress there instead of opening a
   duplicate.

## While working

Fix small problems inside the task's scope. Open a GitHub issue for anything
**large**: outside the current scope, `sev1`/`sev2`, needs more than one PR, an
incident, or needs a decision from a person.

```bash
gh issue create -R tlitech-hq/vkong-connect --title "..." \
  --label bug,sev2,area/lifecycle --body-file body.md
```

Use the matching template structure (bug, incident, task). Split a large issue into
sub-issues when parts can land independently.

## Finishing

1. Pass the publication gate. The final PR contains `Fixes #<n>`; partial PRs use
   `Refs #<n>`.
2. The same PR updates `docs/<area>/README.md` when behavior changes: remove a known
   limit only when verified resolved, and add one dated History line linking the PR
   or issue.
3. Comment verification evidence on the issue and add `proof/local` or `proof/live`.
   A fake-CLI test never counts as live proof.

## Incidents

An incident is a real rental, billing, or data problem caused by vkong-connect, for
example a duplicate rental after a retry, a rental left running, or a published
output reported as successful but missing.

1. Open an `incident` issue with a severity as soon as it is confirmed. Reference
   App/Run IDs only if they are safe to publish; otherwise say where they are recorded
   privately.
2. Contain first (stop the rental through VKong). Then write the postmortem in
   `docs/incidents/YYYY-MM-DD-<slug>.md` and link it from the issue.
3. Each follow-up becomes a sub-issue. The incident closes when its closing criteria
   are met, not when the rental is released.

## Statistics

```bash
gh issue list -l bug -l area/cli --state all
gh issue list -l blocked/vkong
gh issue list --milestone "POC live release"
```
