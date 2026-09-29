# Internal project agents

Reusable repo-scoped prompts under `vkong-connect/.agents/agents/`. `AGENTS.md`
describes when to use them. An agent runtime may map these to named subagents, task
types, or read-only review passes.

| Agent | Mode | Use when |
|-------|------|----------|
| [principal-architect](principal-architect.md) | read-only | Design-compliance / architecture review |
| [vkong-connect-implementer](vkong-connect-implementer.md) | full | Features, fixes, refactors in this repo |
| [vkong-connect-explore](vkong-connect-explore.md) | read-only | "Where is X", contract tracing, pre-change recon |

## Skills (related)

| Skill | Agent pair |
|-------|------------|
| `vkong-connect-codebase` | implementer, explorer |
| `principal-architect` | principal-architect agent |

When named subagents are supported, use the prompt filename as the task type.
Otherwise load the prompt directly.
