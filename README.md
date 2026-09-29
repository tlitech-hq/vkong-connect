# vkong-connect

Thin connector for running product workloads on [VKong](https://vkong.tli-tech.com).
Integrations such as Unsloth Studio translate their native configuration and events
through vkong-connect, while VKong remains the source of truth for Apps, Runs,
provisioning, secrets, usage, billing, and cleanup. There is no server or run database
here.

> **Status: proof of concept, not released.** The core is implemented and verified
> with a fake VKong CLI. Live use is blocked on a versioned VKong CLI contract (#8)
> and a published runner image (#5). Open work:
> [milestone "POC live release"](https://github.com/tlitech-hq/vkong-connect/milestone/1).

## What it does

- Versioned job, event and runtime contracts (`vkong.connect.*`) with JSON Schemas
- Typed, shell-free wrapper for the machine-readable VKong CLI with bound server/workspace
- Deterministic, atomic `vkong.yaml` task bundles with small staged datasets
- Prepare / submit / reconcile / follow / cancel facade with content-checked retries
- Remote runner with runtime-identity preflight and an Unsloth adapter
- Final output publication to a private Hugging Face repository before success

## Development

Core package and tests use only the Python standard library.

```bash
make test     # unit and fake-CLI contract tests
make check    # + Studio executor seam, needs ../unsloth-vkong checked out alongside
```

Remote entry point: `vkong-connect-runner --job bridge-job.json`. Runner image recipe:
[images/unsloth](images/unsloth/README.md).

The Studio side lives in the experimental fork
[`tlitech-hq/unsloth-vkong`](https://github.com/tlitech-hq/unsloth-vkong).

## Docs

Start at [docs/README.md](docs/README.md): architecture, conventions, the issue
workflow, and one README per area describing current behavior and known limits.
Contributors and coding agents: read [AGENTS.md](AGENTS.md).
