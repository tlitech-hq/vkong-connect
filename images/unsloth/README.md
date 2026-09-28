# Unsloth runner image

This image layers `vkong-connect` onto an Unsloth GPU image built from the
experimental `tlitech-hq/unsloth-vkong` fork. It must not silently fall back to an
upstream or moving image in a reproducible training run.

The base must already be published at an immutable registry digest. The bridge
build also needs full 40-character source commits for the fork and bridge.
From the directory containing both repositories:

```bash
docker build \
  -f vkong-connect/images/unsloth/Dockerfile \
  --build-arg BASE_IMAGE='<published-unsloth-base@sha256:64-hex-digest>' \
  --build-arg UNSLOTH_FORK_COMMIT='<full-40-hex-fork-commit>' \
  --build-arg BRIDGE_BUILD_ID='<full-40-hex-bridge-commit>' \
  --build-arg REMOTE_PLATFORM=linux/amd64 \
  -t ghcr.io/tlitech-hq/vkong-connect-unsloth:<release-tag> \
  vkong-connect
```

`UNSLOTH_FORK_COMMIT` is mandatory. This build reinstalls
`https://github.com/tlitech-hq/unsloth-vkong` at that ref even if the base image was
originally built with upstream Unsloth defaults. This makes an accidentally
misnamed local base image fail-safe rather than silently shipping upstream.

Run `vkong-connect-runner --version` inside the built image and compare its
runtime manifest with the two source commits and intended remote platform.
Then push the image, resolve its registry manifest digest, inspect its labels,
and run a small worker/GPU proof through VKong before adding an entry to
`src/vkong_connect/adapters/unsloth/image-catalog.json`. That catalog is empty
until a real compatible image has been promoted.

Push the image, resolve its registry digest, and pass the immutable
`...@sha256:<64 hex>` reference to `BundleRequest.runner_image`. The compiler
rejects tags because the bridge job must identify the exact environment used.

The image build checks that the installed Unsloth package contains Studio's
training worker and that the bridge can resolve it. The digest identifies the
built registry manifest, not the base image. A full build is not a local unit
test: it downloads the GPU stack and requires Docker/BuildKit.
