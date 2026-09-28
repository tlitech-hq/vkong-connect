# Internal project skills

Tool-neutral, repo-scoped skills under `vkong-connect/.agents/skills/`. `AGENTS.md` is
the discovery entry point for any coding agent; it says which skill to load.

| Skill | Slash | Role |
|-------|-------|------|
| [vkong-connect-codebase](vkong-connect-codebase/SKILL.md) | `/vkong-connect-codebase` | **Default** for all coding work in this repo |
| [principal-architect](principal-architect/SKILL.md) | `/principal-architect` | Boundary/contract design and design-compliance review |

## Verify

```bash
test -f .agents/skills/vkong-connect-codebase/SKILL.md
rg '.agents/skills' AGENTS.md
```
