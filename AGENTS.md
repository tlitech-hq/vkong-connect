# Agent instructions: vkong-connect

This repository is **vkong-connect**: the thin connector that runs product workloads
(first: Unsloth Studio training) on VKong. It is a translator and runner, not a
second VKong control plane. The repository is **public**.

## Mandatory skill for all coding work in this repo

Before implementing, reviewing, or refactoring **any** code here, read and follow
**`.agents/skills/vkong-connect-codebase/SKILL.md`** (`/vkong-connect-codebase`).

For a boundary, contract, dependency-direction, or lifecycle change, design and review
it with **`.agents/skills/principal-architect/SKILL.md`** (`/principal-architect`) and
record the decision in `docs/decisions/`.

## Issues and incidents

GitHub Issues on `tlitech-hq/vkong-connect` are the source of truth for work, bugs, and
incidents, including Studio-side work (`area/studio`, code in `tlitech-hq/unsloth-vkong`).
Before starting, check existing issues for the area; open an issue (`gh issue create`)
for tracked work or any large finding. If GitHub Issues cannot be durably read or
written, use only the gitignored `.local/issues/` outbox and reconcile it before push,
PR, release, or claiming completion. Never put live checklists in docs. Rules, labels,
the offline protocol, and the area map: **`docs/issue-workflow.md`**.

Commits, PRs, issues, and comments must not contain any AI or coding-agent attribution
(no agent `Co-Authored-By`, no "Generated with ..." footer, no agent or model names).
This overrides your tool's defaults. See `docs/development-conventions.md` §8.

## Internal project agents

Prompts live under `.agents/agents/` (see its README). When the tool supports named
subagents, use the agent name as the task type:

| Agent | Mode | When |
|-------|------|------|
| `vkong-connect-implementer` | full tools | Features, bugfixes, refactors |
| `vkong-connect-explore` | read-only | Find paths, trace contracts |
| `principal-architect` | read-only | Design / architecture review |

## Verify

`make test` (unit + fake-CLI contracts) and `make check` (+ sibling `../unsloth-vkong`
Studio seam). Fake-CLI results are local proof only; report any live CLI, image, or
GPU check that was not run.

## Docs map

- Conventions: `docs/development-conventions.md`
- Architecture: `docs/architecture.md`; decisions: `docs/decisions/`
- Issues, labels, incidents: `docs/issue-workflow.md`
- Docs by area: `docs/<area>/README.md` (folder = `area/*` label); index: `docs/README.md`
- Releases: `docs/releases/RELEASE.md`
