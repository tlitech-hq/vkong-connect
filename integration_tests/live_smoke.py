"""Live transport smoke test against the real VKong CLI. Rents a GPU briefly.

Not part of ``make check``. It proves the connect core against a real VKong
workspace without the Unsloth runner image: start once, retry reconciles the same
App instead of renting again, auto-stop ends the rental, and the final App state is
read back. It never parses the CLI's human output.

    PYTHONPATH=src python3 integration_tests/live_smoke.py \
        --vkong /path/to/vkong --workspace ws_... [--max-dph 0.6] [--dry-run]

``--dry-run`` stops after readiness and ``vkong validate`` and costs nothing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid

from vkong_connect import VKongBridge
from vkong_connect.client import CLIContext, VKongCLI
from vkong_connect.contracts.bundles import CompiledBundle, tree_digest

# python:3.12-slim multi-arch index, resolved from Docker Hub on 2026-09-29.
IMAGE = "python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f"

WORKLOAD = """\
import json, time
for seq, (kind, payload) in enumerate(
    [("phase", {"phase": "smoke"}), ("terminal", {"status": "succeeded"})], start=1
):
    print("VKONG_EVENT " + json.dumps({"v": 1, "job_id": "%(job_id)s", "seq": seq,
          "time": time.strftime("%%Y-%%m-%%dT%%H:%%M:%%SZ", time.gmtime()),
          "type": kind, "payload": payload}), flush=True)
    time.sleep(10)
"""


@dataclass(frozen=True)
class SmokeBundle:
    """A product-neutral BundleSource: the core must accept it unchanged."""

    job_id: str
    max_dph: float

    @property
    def app_name(self) -> str:
        return f"connect-smoke-{self.job_id[-12:]}"

    def compile(self, destination: Path) -> CompiledBundle:
        destination.mkdir(parents=True)
        job_path = destination / "smoke.py"
        job_path.write_text(WORKLOAD % {"job_id": self.job_id}, encoding="utf-8")
        config_path = destination / "vkong.yaml"
        config_path.write_text(
            "\n".join([
                "type: task",
                f'app: "{self.app_name}"',
                'gpu: "Any"',
                "num_gpus: 1",
                "disk_gb: 20",
                f"max_dph: {self.max_dph}",
                f'image: "{IMAGE}"',
                "srcs:",
                '  - "smoke.py"',
                'work_dir: "."',
                "start_argv:",
                '  - "python3"',
                '  - "smoke.py"',
                "",
            ]),
            encoding="utf-8",
        )
        return CompiledBundle(
            path=destination, app_name=self.app_name, job_path=job_path,
            config_path=config_path, sha256=tree_digest(destination),
        )


def log(message: str, **fields: object) -> None:
    print(json.dumps({"t": time.strftime("%H:%M:%S"), "msg": message, **fields}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vkong", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--server", default="https://vkong.tli-tech.com")
    parser.add_argument("--max-dph", type=float, default=0.6)
    parser.add_argument("--timeout-min", type=float, default=25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cli = VKongCLI(args.vkong, context=CLIContext(args.server, args.workspace))
    bridge = VKongBridge(cli)
    ready = bridge.readiness()
    log("readiness", cli=ready.cli_version, schema=ready.cli_schema,
        user=ready.identity.user, workspace=ready.identity.workspace)

    job_id = "smoke-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="vkong-connect-smoke-") as staging:
        bundle = bridge.prepare(SmokeBundle(job_id, args.max_dph), Path(staging))
        log("prepared", app=bundle.app_name, sha256=bundle.sha256[:12])
        if args.dry_run:
            valid = cli.validate(bundle.path).get("valid")
            log("dry run: validated only, nothing rented", valid=valid)
            return 0 if valid else 1

        started = time.monotonic()
        submission = bridge.submit(bundle, idempotency_key=job_id)
        run = submission.run
        log("started", app_id=run.app_id, run_id=run.run_id, instance=run.instance_id,
            state=run.state, reconciled=run.reconciled, seconds=round(time.monotonic() - started))
        try:
            retry = bridge.submit(bundle, idempotency_key=job_id)
            assert retry.run.reconciled and retry.run.app_id == run.app_id, retry
            log("retry reconciled the same App without renting", app_id=retry.run.app_id)

            deadline = time.monotonic() + args.timeout_min * 60
            status = bridge.reconcile(run.app_id)
            while status.state != "stopped" and time.monotonic() < deadline:
                time.sleep(15)
                status = bridge.reconcile(run.app_id)
                log("status", state=status.state, instance=status.instance_id)
        finally:
            status = bridge.reconcile(run.app_id)
            if status.state != "stopped":
                log("stopping App explicitly", state=status.state)
                status = bridge.cancel(run.app_id)
        runs = cli.runs(run.app_id)
        log("final", app_state=status.state,
            runs=[{k: r.get(k) for k in ("id", "status", "reason", "gpu")} for r in runs])
        return 0 if status.state == "stopped" and runs and runs[0].get("status") != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
