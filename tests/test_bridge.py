from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
import hashlib

from vkong_connect.adapters.unsloth.bundle import BundleRequest
from vkong_connect.bridge import VKongBridge
from vkong_connect.client.vkong_cli import AppStatus, RunStart, WorkspaceIdentity
from vkong_connect.contracts.events import EventSink, EventType
from vkong_connect.errors import ConfigurationError, ContractError


IMAGE = "registry.example/unsloth@sha256:" + "b" * 64


class FakeCLI:
    def __init__(self) -> None:
        self.validated = None
        self.started = None
        output = io.StringIO()
        sink = EventSink("job-1", output)
        sink.emit(EventType.PHASE, {"phase": "training"})
        sink.emit(EventType.METRIC, {"step": 1})
        self.log_lines = output.getvalue().splitlines()

    def version(self):
        return {"schema_version": "vkong.cli.v1", "version": "0.1.0"}

    def whoami(self):
        return WorkspaceIdentity("alice", "team", "vkong.cli.v1")

    def validate(self, path):
        self.validated = path
        return {"schema_version": "vkong.cli.v1", "valid": True}

    def start_task(self, path, *, idempotency_key, app_name=None):
        self.started = (path, idempotency_key)
        suffix = hashlib.sha256(b"job-1").hexdigest()[:8]
        return RunStart(
            app_id="app-1",
            app_name=f"unsloth-job-1-{suffix}",
            run_id="run-1",
            instance_id="vk-1",
            state="running",
            hourly_price=1.0,
            currency="USD",
            schema_version="vkong.cli.v1",
        )

    def app_show(self, app):
        return AppStatus("app-1", "unsloth-job-1", "running", "run-1", "vk-1", "vkong.cli.v1")

    def stop_app(self, app):
        return AppStatus("app-1", "unsloth-job-1", "stopping", "run-1", None, "vkong.cli.v1")

    def follow_logs(self, run_id):
        # Replay first event twice to exercise event-sequence deduplication.
        yield {"seq": 1, "line": self.log_lines[0]}
        yield {"seq": 2, "line": self.log_lines[0]}
        yield {"seq": 3, "line": self.log_lines[1]}


class BridgeFacadeTests(unittest.TestCase):
    def test_prepare_reuses_only_identical_bundle_on_retry(self) -> None:
        bridge = VKongBridge(FakeCLI())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = BundleRequest(
                job_id="job-1",
                worker_config={"model_name": "org/model", "hf_dataset": "org/data"},
                output_repo_id="user/result",
                runner_image=IMAGE,
            )
            first = bridge.prepare(request, root)
            second = bridge.prepare(request, root)
            self.assertEqual(first, second)
            bridge.submit(second, idempotency_key="same-start-request")
            bridge.submit(second, idempotency_key="same-start-request")
            with self.assertRaisesRegex(ConfigurationError, "another bundle, context or idempotency key"):
                bridge.submit(second, idempotency_key="different-start-request")
            changed = BundleRequest(
                job_id="job-1",
                worker_config={"model_name": "org/other", "hf_dataset": "org/data"},
                output_repo_id="user/result",
                runner_image=IMAGE,
            )
            with self.assertRaisesRegex(ConfigurationError, "differs from retry"):
                bridge.prepare(changed, root)
            first.job_path.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "differs from retry"):
                bridge.prepare(request, root)

    def test_prepare_rejects_symlink_in_existing_bundle(self) -> None:
        bridge = VKongBridge(FakeCLI())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = BundleRequest(
                job_id="job-1", worker_config={"model_name": "org/model"},
                output_repo_id="user/result", runner_image=IMAGE,
            )
            first = bridge.prepare(request, root)
            (first.path / "unsafe").symlink_to(first.job_path)
            with self.assertRaisesRegex(ConfigurationError, "symlink"):
                bridge.prepare(request, root)

    def test_prepare_submit_reconcile_cancel_and_follow(self) -> None:
        fake = FakeCLI()
        bridge = VKongBridge(fake)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = BundleRequest(
                job_id="job-1",
                worker_config={"model_name": "org/model", "hf_dataset": "org/data"},
                output_repo_id="user/result",
                runner_image=IMAGE,
            )
            bundle = bridge.prepare(request, root)
            submission = bridge.submit(bundle, idempotency_key="request-1")

            self.assertEqual(submission.run.run_id, "run-1")
            self.assertEqual(fake.validated, bundle.path)
            self.assertEqual(fake.started, (bundle.path, "request-1"))
            self.assertEqual(bridge.reconcile("app-1").state, "running")
            self.assertEqual(bridge.cancel("app-1").state, "stopping")
            self.assertEqual(
                [event.seq for event in bridge.follow_events("run-1")],
                [1, 2],
            )

    def test_event_gap_fails_closed(self) -> None:
        fake = FakeCLI()
        fake.log_lines = [fake.log_lines[1]]
        bridge = VKongBridge(fake)
        with self.assertRaisesRegex(ContractError, "sequence gap"):
            list(bridge.follow_events("run-1"))

    def test_wrong_job_and_truncated_logs_fail_closed(self) -> None:
        fake = FakeCLI()
        with self.assertRaisesRegex(ContractError, "different job"):
            list(VKongBridge(fake).follow_events("run-1", expected_job_id="other-job"))
        fake.follow_logs = lambda run_id: iter(({"truncated": True},))
        with self.assertRaisesRegex(ContractError, "truncated"):
            list(VKongBridge(fake).follow_events("run-1", expected_job_id="job-1"))


if __name__ == "__main__":
    unittest.main()
