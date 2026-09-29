# Infra

Packaging, development commands, CI, releases, and the live proof that gates a POC
release.

## Current behavior

- Standard-library-only package `vkong-connect` (`src/` layout); the image catalog is
  shipped as package data. `uv build --wheel` and a clean-venv install were verified on
  2026-09-24.
- `make test` (77 unit/fake-CLI tests; the 2 FastAPI route tests skip without FastAPI),
  `make integration` (5 contract checks of upstream Unsloth surfaces and fork hooks in
  `../unsloth-vkong`), `make check` (both). All pass as of 2026-09-29.
- `integration_tests/live_smoke.py` is a manual live transport smoke test (rents a GPU;
  `--dry-run` is free).
- CI (`.github/workflows/ci.yml`) runs `make test` and an installed-package catalog
  check on Ubuntu and macOS, Python 3.10 and 3.13.
- Not published to PyPI; the POC installs from pinned TLI Git refs only.

## Limits and known issues

- Supported Python/OS matrix not declared; Windows lacks a fake-CLI fixture (#3)
- No live GPU/Hugging Face/VKong end-to-end proof; nothing released (#12)

## Code and design docs

- Code: `pyproject.toml`, `Makefile`, `.github/`, `integration_tests/`
- Design: [releases/](../releases/README.md)

## History

- 2026-09-29 Renamed to `vkong-connect` and moved to `tlitech-hq`; issue workflow,
  area docs and templates adopted.
- 2026-09-24 Make targets, CI and cross-repository check added.
