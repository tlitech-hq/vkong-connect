from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vkong_connect.adapters.unsloth.bundle import BundleRequest, compile_bundle
from vkong_connect.errors import ConfigurationError


IMAGE = "registry.example/unsloth@sha256:" + "a" * 64


class BundleCompilerTests(unittest.TestCase):
    def test_compiles_deterministic_bundle_and_stages_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "train.jsonl"
            dataset.write_text('{"text":"hello"}\n', encoding="utf-8")
            request = BundleRequest(
                job_id="Job_ABC",
                worker_config={"model_name": "org/model", "hf_dataset": "org/data"},
                output_repo_id="user/result",
                runner_image=IMAGE,
                local_datasets=(dataset,),
                secret_bundles=("huggingface", "wandb"),
            )

            first = compile_bundle(request, root / "bundle-one")
            second = compile_bundle(request, root / "bundle-two")

            self.assertEqual(first.sha256, second.sha256)
            self.assertRegex(first.app_name, r"^unsloth-job-abc-[0-9a-f]{8}$")
            job = json.loads(first.job_path.read_text(encoding="utf-8"))
            self.assertEqual(
                job["spec"]["worker_config"]["local_datasets"],
                ["inputs/train/train.jsonl"],
            )
            self.assertIsNone(job["spec"]["worker_config"]["hf_dataset"])
            self.assertTrue((first.path / "inputs" / "train" / "train.jsonl").is_file())
            config = first.config_path.read_text(encoding="utf-8")
            self.assertIn("type: task", config)
            self.assertIn("verified_only: true", config)
            self.assertIn('  - "huggingface"', config)
            self.assertIn('  - "inputs/"', config)

    def test_refuses_unpinned_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = BundleRequest(
                job_id="job-1",
                worker_config={"model_name": "org/model"},
                output_repo_id="user/result",
                runner_image="registry.example/unsloth:latest",
            )
            with self.assertRaisesRegex(ConfigurationError, "pinned"):
                compile_bundle(request, Path(directory) / "bundle")

    def test_never_overwrites_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "bundle"
            destination.mkdir()
            request = BundleRequest(
                job_id="job-1",
                worker_config={"model_name": "org/model"},
                output_repo_id="user/result",
                runner_image=IMAGE,
            )
            with self.assertRaisesRegex(ConfigurationError, "already exists"):
                compile_bundle(request, destination)

    def test_rejects_non_finite_or_non_json_worker_config(self) -> None:
        for invalid in (float("nan"), {"not", "json"}):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                request = BundleRequest(
                    job_id="job-1",
                    worker_config={"model_name": "org/model", "invalid": invalid},
                    output_repo_id="user/result",
                    runner_image=IMAGE,
                )
                with self.assertRaisesRegex(ConfigurationError, "finite JSON"):
                    compile_bundle(request, Path(directory) / "bundle")

    def test_approved_input_roots_and_symlink_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            allowed = root / "approved"
            allowed.mkdir()
            outside = root / "outside.jsonl"
            outside.write_text('{"text":"private"}\n', encoding="utf-8")
            alias = allowed / "alias.jsonl"
            alias.symlink_to(outside)

            def request(path):
                return BundleRequest(
                    job_id="job-1", worker_config={"model_name": "org/model"},
                    output_repo_id="user/result", runner_image=IMAGE,
                    local_datasets=(path,), approved_input_roots=(allowed,),
                )

            with self.assertRaisesRegex(ConfigurationError, "outside approved"):
                compile_bundle(request(outside), root / "outside-bundle")
            with self.assertRaisesRegex(ConfigurationError, "symlink"):
                compile_bundle(request(alias), root / "symlink-bundle")
            self.assertFalse((root / "outside-bundle").exists())
            self.assertFalse((root / "symlink-bundle").exists())


if __name__ == "__main__":
    unittest.main()
