# Release notes

No version has been released. The POC is installed from pinned Git refs only; a
release requires the live proof in #12 and a promoted runner image (#5).

## Cutting a release

1. All milestone issues for the release are closed with `proof/local` and, where
   required, `proof/live` evidence.
2. Tag the connect commit, then pin that tag in the fork's `vkong` extra and tag the
   fork. Never fabricate a tag or image digest.
3. Record CLI version, fork/connect commits, image digest and untested cases here.

## Unreleased

- Unsloth Studio "Train on VKong": `vkong_connect.integrations.unsloth_studio` service and
  routes, development runtime on `unsloth/unsloth:studio`, remote config normalization
  with Studio's own builder.
- Works with the current VKong CLI JSON envelope; start guarded by job-unique App name.

- Renamed from `vkong-bridge`: distribution `vkong-connect`, package `vkong_connect`,
  runner `vkong-connect-runner`, wire schemas `vkong.connect.*`. No compatibility
  alias; nothing had been released.
