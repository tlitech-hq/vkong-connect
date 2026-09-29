"""Build-time runner identity and remote pre-training compatibility check."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from vkong_connect.contracts.runtime import RuntimeIdentity
from vkong_connect.errors import ContractError

MANIFEST_SCHEMA = "vkong.connect.runner-manifest.v1"
MANIFEST_ENV = "VKONG_CONNECT_RUNTIME_MANIFEST"


@dataclass(frozen=True)
class RunnerManifest:
    runtime: RuntimeIdentity
    schema_version: str = MANIFEST_SCHEMA

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RunnerManifest":
        if not isinstance(value, Mapping) or set(value) != {"schema_version", "runtime"}:
            raise ContractError("runner manifest has missing or unsupported fields")
        if value["schema_version"] != MANIFEST_SCHEMA:
            raise ContractError("unsupported runner manifest schema")
        return cls(RuntimeIdentity.from_dict(value["runtime"]))

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "runtime": self.runtime.as_dict()}


def load_installed_manifest() -> RunnerManifest:
    value = os.environ.get(MANIFEST_ENV)
    if not value:
        raise ContractError("runner image has no runtime manifest")
    try:
        document = json.loads(Path(value).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("runner image runtime manifest is unreadable") from exc
    return RunnerManifest.from_dict(document)


def verify_runtime(expected: RuntimeIdentity) -> RunnerManifest:
    installed = load_installed_manifest()
    if installed.runtime != expected:
        raise ContractError("runner image is incompatible with this job's training runtime")
    return installed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a verified runner image manifest")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--adapter-name", required=True)
    parser.add_argument("--adapter-schema", required=True)
    parser.add_argument("--job-schema", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--bridge-build-id", required=True)
    parser.add_argument("--platform", default="linux/amd64")
    args = parser.parse_args(argv)
    identity = RuntimeIdentity(
        adapter_name=args.adapter_name,
        adapter_schema=args.adapter_schema,
        job_schema=args.job_schema,
        source_commit=args.source_commit,
        bridge_build_id=args.bridge_build_id,
        platform=args.platform,
    )
    manifest = RunnerManifest(identity)
    args.output.write_text(
        json.dumps(manifest.as_dict(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
