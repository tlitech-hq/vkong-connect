# Outputs

Where the trained model goes. Until VKong has native artifacts, the runner publishes
the final adapter/model to a private Hugging Face repository using a VKong workspace
secret, and only then reports success so auto-stop is safe.

## Current behavior

- Final output published to a private Hugging Face repo; an existing public repo is
  rejected (`create_repo(private=True, exist_ok=True)` alone is not trusted).
- A successful publication must return an immutable commit OID before the `artifact`
  and terminal success events. Publication failure is job failure.
- This is the only durable output path. Proven by local tests with a fake publisher.

## Limits and known issues

- No output preflight; retries/concurrent jobs and partial uploads not fully defined;
  failed-upload tests incomplete (#10)
- No periodic checkpoints, remote resume, checkpoint-and-stop, or VKong-native
  artifacts; a remote machine-local checkpoint is not durable (#1)

## Code and design docs

- Code: `src/vkong_connect/adapters/unsloth/outputs.py`
- Design: [architecture.md](../architecture.md) §11–12

## History

- 2026-09-24 Private-repo check and required commit OID added.
