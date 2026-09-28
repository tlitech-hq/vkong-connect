# Runtime

What runs on the rented GPU: the `vkong-connect-runner` entry point inside a
digest-pinned runner image, plus how a Studio build is mapped to that image before
anything is rented.

## Current behavior

- `vkong-connect-runner --job bridge-job.json` validates the job, checks the installed
  runtime manifest against the job's expected `RuntimeIdentity`, then loads the adapter.
  `--version` prints machine-readable build metadata.
- Image recipe `images/unsloth/Dockerfile` requires full fork and connect commits,
  verifies the installed Unsloth VCS commit, and writes a runtime manifest and
  provenance labels.
- Packaged image catalog maps explicit Studio build IDs and training mode/platform to
  an image digest; ambiguous or unknown entries fail with typed errors before rent.
  `BundleRequest.for_studio(...)` uses it.
- The packaged catalog is **empty**: no image has been built, published or promoted.
- **Development runtime** ([0005](../decisions/0005-current-cli-and-dev-runtime.md)): the
  official `unsloth/unsloth:studio` image by digest, with `init_cmd` installing
  vkong-connect and the fork's Studio backend at the user's installed commits. The runner
  applies Studio's own config builder on the GPU host. Not yet run on a GPU.

## Limits and known issues

- No published runner image; base digest and dependency set not pinned; not tested
  through VKong's real startup path (#5)
- Studio does not emit build metadata yet; resolver has no GPU/backend constraints (#4)
- Studio executor still takes the image from `UNSLOTH_VKONG_RUNNER_IMAGE` (#6)

## Code and design docs

- Code: `src/vkong_connect/runner.py`, `runtime_manifest.py`,
  `adapters/unsloth/image_catalog.py`, `adapters/unsloth/runtime_image.py`, `images/unsloth/`
- Design: [0002](../decisions/0002-runtime-image-contract.md),
  [images/unsloth/README.md](../../images/unsloth/README.md)

## History

- 2026-09-29 Development runtime added.
- 2026-09-24 Runtime identity, packaged catalog, runner preflight and image recipe added.
