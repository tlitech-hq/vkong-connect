# Docs

Docs are grouped by **area**. Folder names match the `area/*` issue labels, so docs,
issues, and code are split the same way. Each area's `README.md` says what the area
does today, its known limits (linked to issues), and its history. GitHub Issues are the
source of truth for open work. When GitHub Issues cannot be durably read or written,
drafts wait only in the gitignored `.local/issues/` outbox; they are reconciled before
push, PR, release, or claiming completion, and never live in docs.
See [issue-workflow.md](issue-workflow.md).

## Start here

| Doc | Purpose |
|---|---|
| [architecture.md](architecture.md) | Design: ownership, CLI contract, bundle, adapter and event protocols |
| [development-conventions.md](development-conventions.md) | Boundaries, contracts, secrets, tests and evidence, authorship |
| [issue-workflow.md](issue-workflow.md) | Issues, labels, areas, incidents |
| [decisions/](decisions/) | Decision records for cross-boundary changes |

## Areas

| Area | Scope |
|---|---|
| [contracts](contracts/README.md) | Job, event, runtime and bundle contracts; JSON schemas; adapter registry |
| [cli](cli/README.md) | VKong CLI transport and bound server/workspace context |
| [lifecycle](lifecycle/README.md) | Prepare, submit, reconcile, follow, cancel; retry safety |
| [runtime](runtime/README.md) | Remote runner, runtime identity, image recipe, catalog and resolver |
| [adapter-unsloth](adapter-unsloth/README.md) | Unsloth job schema, bundle compiler, input staging, event mapping |
| [outputs](outputs/README.md) | Output publication, checkpoints, artifacts |
| [studio](studio/README.md) | Unsloth Studio integration (code in `tlitech-hq/unsloth-vkong`) |
| [infra](infra/README.md) | Packaging, CI, dev tooling, release and live proof |

Also: [releases](releases/README.md) (release notes, POC plan history) and
[incidents](incidents/README.md) (postmortems).

## Layout rules

- `docs/<area>/README.md`: current state, limits, history. Written in English.
- `docs/<area>/<topic>.md`: design docs that still describe how the area works.
- `docs/decisions/NNNN-<slug>.md`: decision records for boundary, contract, or
  lifecycle changes (see [development-conventions.md](development-conventions.md#6-change-discipline)).
- Completed or superseded plans stay in their folder, start with a `> **History:**`
  note, and are listed in the area or releases README. Do not update their checkboxes.
- A PR that changes behavior updates the area README in the same PR.
- This repository is public. Never include secrets, credentials, signed URLs, private
  VKong control-plane source paths or revisions, or private account/workspace data.

### Area README template

```markdown
# <Area>

<One paragraph: what it is, for whom.>

## Current behavior
What works today from the user's point of view, and where it is proven
(local tests vs live VKong/GPU).

## Limits and known issues
- <limit or bug in plain words> (#<issue>)

## Code and design docs
- Code: `<paths>`
- Design: <links>

## History
- YYYY-MM-DD <what changed, in plain words> (#<issue or PR>)
```
