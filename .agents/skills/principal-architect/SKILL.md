---
name: principal-architect
description: >
  Principal architect for vkong-connect: design a boundary, contract, integration or
  lifecycle change before implementation, or review code/diffs against the design
  docs and core concepts (not a control plane, core/adapter isolation, CLI machine
  contract, one logical start, billing honesty, durable success, versioned contracts,
  pinned runtime, secrets). Use for /principal-architect, architecture review, design
  compliance, or after large changes.
metadata:
  short-description: "Design and architecture review"
---

# /principal-architect

Two modes. Both are read-only with respect to code.

## Mode A: design (before implementation)

Produce a decision record draft for `docs/decisions/NNNN-<slug>.md` covering:

- the user journey and the exact problem;
- ownership and data flow across caller, core, adapter, runner, and VKong;
- contract versions, trust boundaries, credentials, artifacts, retry and cancellation;
- alternatives and why the choice is proportionate to the POC;
- incremental implementation and verification, including live checks not yet possible;
- the GitHub issue(s) it resolves or creates.

Ask for a product decision when a choice changes user cost, data movement, or durable
outputs.

## Mode B: design-compliance review

1. Scope: default is uncommitted + unpushed changes (`git status`, `git diff`,
   `git log origin/main..HEAD`); otherwise the paths or feature the user named.
2. Spawn the **principal-architect** subagent (prompt in
   `.agents/agents/principal-architect.md`). If named subagents are unavailable, use a
   read-only agent with that prompt body, filling in the scope.
3. Present its report without diluting blockers; add a short summary and next actions.
4. Do not implement fixes unless the user asks. Out-of-scope blockers become issues.

Reference checklist: `.agents/skills/principal-architect/references/core-concepts.md`.
