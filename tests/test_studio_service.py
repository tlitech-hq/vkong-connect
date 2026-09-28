from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from test_cli_envelope import FAKE_CLI
from vkong_connect.adapters.unsloth.dev_runtime import DEFAULT_BASE_IMAGE, DEV_PYTHON, DevRuntime
from vkong_connect.client import VKongCLI
from vkong_connect.errors import ConfigurationError
from vkong_connect.integrations.unsloth_studio import RemoteTrainingService, portable_worker_config

RUNTIME = DevRuntime(DEFAULT_BASE_IMAGE, "a" * 40, "b" * 40)
PAYLOAD = {
    "model_name": "unsloth/Qwen2.5-0.5B-Instruct", "hf_dataset": "yahma/alpaca-cleaned",
    "training_type": "LoRA/QLoRA", "use_lora": True, "max_steps": 30,
    "hf_token": "hf_very_secret", "start_request_id": "req-1", "gpu_ids": [0],
    "model_snapshot_path": "/Users/me/.cache/model", "device_backend": "mps",
    "tensorboard_dir": "/Users/me/runs", "local_datasets": None,
}


class PortableConfigTests(unittest.TestCase):
    def test_drops_secrets_and_laptop_state(self) -> None:
        worker, train, evaluation = portable_worker_config(PAYLOAD)
        for key in ("hf_token", "start_request_id", "gpu_ids", "model_snapshot_path",
                    "device_backend", "tensorboard_dir", "local_datasets"):
            self.assertNotIn(key, worker)
        self.assertEqual(worker["max_steps"], 30)
        self.assertEqual((train, evaluation), ((), ()))

    def test_rejects_unsupported_requests(self) -> None:
        for change in ({"model_local_path": "/models/x"}, {"training_type": "Full Finetuning"},
                       {"resume_from_checkpoint": "ckpt"}, {"hf_dataset": ""},
                       {"model_name": ""}):
            with self.subTest(change=change), self.assertRaises(ConfigurationError):
                portable_worker_config({**PAYLOAD, **change})


class RemoteTrainingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.binary = root / "vkong"
        self.binary.write_text(textwrap.dedent(FAKE_CLI), encoding="utf-8")
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IXUSR)
        self.state_path = root / "state.json"
        self.state_path.write_text(json.dumps(
            {"workspace": "ws_team", "apps": [], "runs": [], "calls": []}), encoding="utf-8")
        env = {"PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""),
               "FAKE_STATE": str(self.state_path)}
        self.service = RemoteTrainingService(
            state_dir=root / "home", server_url="https://vkong.test",
            runtime_resolver=lambda: RUNTIME,
            cli_factory=lambda context: VKongCLI(str(self.binary), timeout=10, env=env,
                                                 context=context),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def wait_for(self, job_id: str, *states: str) -> dict:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            record = self.service.get_job(job_id, refresh=False)
            if record["state"] in states:
                return record
            time.sleep(0.05)
        self.fail(f"job stayed {record['state']}: {record['message']}")

    def state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def test_readiness_reports_identity_and_runtime(self) -> None:
        ready = self.service.readiness()
        self.assertTrue(ready["ready"])
        self.assertEqual((ready["user"], ready["workspace_id"]), ("alice", "ws_team"))
        self.assertFalse(ready["progress_supported"])

        def missing() -> DevRuntime:
            raise ConfigurationError("cannot determine the remote runtime")

        self.service._runtime_resolver = missing
        self.assertFalse(self.service.readiness()["ready"])

    def test_train_starts_once_then_finishes_and_bundle_uses_dev_runtime(self) -> None:
        record = self.service.start(PAYLOAD, output_repo_id="alice/qwen-lora",
                                    compute={"gpu": "RTX 4090", "max_dph": 0.8})
        running = self.wait_for(record["job_id"], "running", "failed")
        self.assertEqual(running["state"], "running", running["message"])
        self.assertEqual((running["app_id"], running["workspace_id"]), ("app_1", "ws_team"))

        bundle = self.service.state_dir / "bundles" / record["job_id"]
        config = (bundle / "vkong.yaml").read_text(encoding="utf-8")
        self.assertIn(DEFAULT_BASE_IMAGE, config)
        self.assertIn("init_cmd: |", config)
        self.assertIn(DEV_PYTHON, config)
        self.assertIn('gpu: "RTX 4090"', config)
        job = json.loads((bundle / "bridge-job.json").read_text(encoding="utf-8"))
        self.assertNotIn("hf_token", job["spec"]["worker_config"])
        self.assertIn(RUNTIME.studio_backend, (bundle / "run_bridge.py").read_text())

        state = self.state()
        state["apps"][0]["status"] = "stopped"
        state["runs"][0]["status"] = "stopped"
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.service.get_job(record["job_id"])["state"], "finished")
        self.assertEqual(len([c for c in self.state()["calls"] if c[:1] == ["run"]]), 1)

    def test_failed_run_is_reported(self) -> None:
        record = self.service.start(PAYLOAD, output_repo_id="alice/qwen-lora")
        self.wait_for(record["job_id"], "running")
        state = self.state()
        state["runs"][0].update(status="failed", reason="workload exited with code 1")
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        failed = self.service.get_job(record["job_id"])
        self.assertEqual((failed["state"], failed["message"]),
                         ("failed", "workload exited with code 1"))

    def test_stop_releases_the_gpu(self) -> None:
        record = self.service.start(PAYLOAD, output_repo_id="alice/qwen-lora")
        self.wait_for(record["job_id"], "running")
        self.service.stop_job(record["job_id"])
        stopped = self.wait_for(record["job_id"], "stopped")
        self.assertTrue(stopped["stop_requested"])
        self.assertEqual(self.state()["apps"][0]["status"], "stopped")

    def test_rejects_bad_output_repository_and_unknown_job(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.service.start(PAYLOAD, output_repo_id="not a repo")
        with self.assertRaises(ConfigurationError):
            self.service.get_job("../../etc/passwd")
        self.assertEqual(self.service.list_jobs(), [])


if __name__ == "__main__":
    unittest.main()
