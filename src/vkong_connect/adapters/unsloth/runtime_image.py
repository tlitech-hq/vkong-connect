"""Build-time proof that the runner contains the exact TLI Unsloth fork."""

from __future__ import annotations

import argparse
import json
from importlib import metadata

from vkong_connect.errors import ContractError


def verify_installed_unsloth_commit(expected: str) -> None:
    try:
        raw = metadata.distribution("unsloth").read_text("direct_url.json")
        document = json.loads(raw or "")
        if not isinstance(document, dict):
            raise ValueError("direct_url.json is not an object")
    except (metadata.PackageNotFoundError, ValueError, TypeError) as exc:
        raise ContractError("installed Unsloth has no verifiable VCS provenance") from exc
    vcs = document.get("vcs_info")
    actual = vcs.get("commit_id") if isinstance(vcs, dict) else None
    if actual != expected:
        raise ContractError("installed Unsloth commit does not match runner manifest")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify installed Unsloth fork commit")
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args(argv)
    verify_installed_unsloth_commit(args.expected_commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
