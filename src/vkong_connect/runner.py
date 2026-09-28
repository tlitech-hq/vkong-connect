"""Remote bridge runner CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vkong_connect.adapters.registry import get_adapter
from vkong_connect.contracts.adapters import RunContext
from vkong_connect.contracts.events import EventSink, EventType
from vkong_connect.errors import BridgeError
from vkong_connect.runtime_manifest import load_installed_manifest, verify_runtime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one VKong bridge adapter job")
    parser.add_argument("--job", type=Path, help="Path to bridge-job.json")
    parser.add_argument("--version", action="store_true", help="Print installed runtime manifest JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.version:
        try:
            print(json.dumps(load_installed_manifest().as_dict(), sort_keys=True))
            return 0
        except BridgeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.job is None:
        _parser().error("--job is required unless --version is given")
    job_path = args.job.expanduser().resolve()
    fallback_job_id = "unknown"
    sink: EventSink | None = None
    try:
        value = json.loads(job_path.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("job_id"), str):
            fallback_job_id = value["job_id"]
        sink = EventSink(fallback_job_id, sys.stdout)
        if not isinstance(value, dict):
            raise ValueError("job document must be an object")
        adapter_value = value.get("adapter")
        if not isinstance(adapter_value, dict):
            raise ValueError("job adapter must be an object")
        adapter_name = adapter_value.get("name")
        adapter_schema = adapter_value.get("schema_version")
        if not isinstance(adapter_name, str) or not isinstance(adapter_schema, str):
            raise ValueError("job adapter requires name and schema_version")
        adapter = get_adapter(adapter_name, adapter_schema)
        job = adapter.validate_job(value)
        expected_runtime = getattr(job, "runtime", None)
        if expected_runtime is not None:
            verify_runtime(expected_runtime)
        context = RunContext(job_id=job.job_id, workspace=job_path.parent, spec=value["spec"])
        result = adapter.execute(job, context, sink)
        return 0 if result.status == "succeeded" else 1
    except (BridgeError, OSError, ValueError, json.JSONDecodeError) as exc:
        sink = sink or EventSink(fallback_job_id, sys.stdout)
        sink.emit(
            EventType.TERMINAL,
            {
                "status": "failed",
                "error": str(exc),
                "code": getattr(exc, "code", "invalid_job"),
                "retriable": bool(getattr(exc, "retriable", False)),
            },
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
