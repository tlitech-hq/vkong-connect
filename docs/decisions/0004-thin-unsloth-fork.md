# 0004: Keep the Unsloth fork a thin, rebasable patch

Date: 2026-09-29
Status: accepted; executor moved and fork reduced to hooks on 2026-09-29 (0005). Branch model and scheduled sync pending. Tracked in #13.

## Problem and user journey

Maintainers must follow upstream Unsloth releases (the fork was 705 commits behind on
2026-09-29) without re-porting the VKong integration each time. A Studio user should
get upstream fixes quickly and still see the same "Train on VKong" flow.

Today the fork edits two upstream files (`README.md`, `pyproject.toml`) and adds a
Studio executor, its test, and two design docs. The coming route/UI wiring (#11) would
touch more upstream files. Every upstream-owned line we change is a potential merge
conflict on each bump.

## Decision

Minimize and fence the fork's upstream-owned surface; move everything else here.

1. **Integration code lives in vkong-connect.** Move `VKongTrainingExecutor` and its
   tests from the fork into `vkong_connect.integrations.unsloth_studio`. It already
   has no Studio imports: it consumes Studio's worker-config dict and calls the
   connect facade. Changes to it then ship by bumping the connect pin, not by editing
   the fork.
2. **Fork keeps only hooks.** The fork may contain: the `vkong` optional extra, a
   top-of-README notice, one lazily-imported execution-selection hook in the training
   route, and one UI mount point. New fork files are preferred over edits to upstream
   files; each edit to an upstream file stays a few lines and is listed in the fork's
   `VKONG_PATCHES.md` inventory.
3. **Branch model.** In `tlitech-hq/unsloth-vkong`, `main` mirrors upstream exactly;
   the integration lives on a `vkong` branch as a short patch series on top. A bump is
   `git fetch upstream && git switch vkong && git rebase upstream/main` (or merge),
   then `make check` from vkong-connect.
4. **Detect breakage before a human bumps.** A scheduled workflow in the fork fetches
   upstream, applies the `vkong` branch, and runs the vkong executor/contract tests,
   opening an issue on failure. vkong-connect adds a contract test that asserts the
   upstream surfaces it depends on without importing heavy ML packages:
   `run_training_process(*, event_queue, stop_queue, config)` and the worker event
   kinds mapped in `adapters/unsloth/event_mapper.py`.

## Alternatives

- **Keep the executor in the fork** (0001's original split): every executor fix is a
  fork edit and every upstream bump risks conflicts in more files.
- **Upstream a pluggable remote-executor hook to Unsloth**: best long-term, removes
  the fork's route edit entirely, but depends on upstream acceptance. Pursue after the
  POC proves the seam; nothing here blocks it.
- **Monkeypatch Studio at runtime from vkong-connect**: no fork edits, but fragile and
  silent when upstream internals change. Rejected.

## Compatibility and verification

Supersedes 0001's placement of the executor only; ownership of Studio persistence and
UI projection stays with Studio. The worker-config dict and worker event kinds become
explicit contract surfaces tested on every bump. Verification: fork diff against
upstream limited to the inventory, `make check` green after a rebase onto current
upstream, and the scheduled sync job reporting a failure on an intentionally broken
signature.
