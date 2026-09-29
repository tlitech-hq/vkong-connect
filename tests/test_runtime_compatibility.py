from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vkong_connect.adapters.unsloth.bundle import BundleRequest, compile_bundle
from vkong_connect.adapters.unsloth.image_catalog import ImageCatalog
from vkong_connect.adapters.unsloth.runtime_image import verify_installed_unsloth_commit
from vkong_connect.adapters.unsloth.schema import validate_job
from vkong_connect.contracts.runtime import RuntimeIdentity
from vkong_connect.errors import ConfigurationError, ContractError
from vkong_connect.runner import main as runner_main
from vkong_connect.runtime_manifest import RunnerManifest, main as manifest_main, verify_runtime

IMAGE = "registry.example/unsloth@sha256:" + "a" * 64
def runtime(source: str, bridge: str) -> RuntimeIdentity:
    return RuntimeIdentity(
        adapter_name="unsloth", adapter_schema="unsloth.v1",
        job_schema="vkong.connect.job.v2", source_commit=source,
        bridge_build_id=bridge,
    )


RUNTIME = runtime("b" * 40, "c" * 40)


def catalog_entry(*, builds=None, runtime=RUNTIME, modes=None, image=IMAGE):
    return {
        "studio_builds": builds or ["studio-one"],
        "training_modes": modes or ["LoRA/QLoRA"],
        "runtime": runtime.as_dict(),
        "image": image,
        "cli_contract": "vkong.cli.v1",
    }


class RuntimeCompatibilityTests(unittest.TestCase):
    def test_packaged_catalog_is_empty_until_a_real_image_is_promoted(self):
        self.assertEqual(ImageCatalog.packaged().entries, ())
        with self.assertRaisesRegex(ConfigurationError, "no published compatible"):
            ImageCatalog.packaged().resolve("studio-one", training_mode="LoRA/QLoRA")

    def test_explicit_ui_sharing_and_worker_change(self):
        other = runtime("d" * 40, "e" * 40)
        catalog = ImageCatalog.from_dict({
            "schema_version": "vkong.connect.image-catalog.v1",
            "entries": [
                catalog_entry(builds=["studio-one", "studio-ui-only"]),
                catalog_entry(builds=["studio-new-worker"], runtime=other,
                              image="registry.example/unsloth@sha256:" + "f" * 64),
            ],
        })
        a = catalog.resolve("studio-one", training_mode="LoRA/QLoRA")
        b = catalog.resolve("studio-ui-only", training_mode="LoRA/QLoRA")
        c = catalog.resolve("studio-new-worker", training_mode="LoRA/QLoRA")
        self.assertEqual(a.image, b.image)
        self.assertNotEqual(a.runtime, c.runtime)
        for build, mode, platform in (
            ("unknown", "LoRA/QLoRA", "linux/amd64"),
            ("studio-one", "Full Finetuning", "linux/amd64"),
            ("studio-one", "LoRA/QLoRA", "linux/arm64"),
        ):
            with self.subTest(build=build, mode=mode, platform=platform):
                with self.assertRaises(ConfigurationError):
                    catalog.resolve(build, training_mode=mode, platform=platform)

    def test_ambiguous_and_invalid_catalog_fail_closed(self):
        for entries in (
            [catalog_entry(), catalog_entry()],
            [catalog_entry(image="registry.example/unsloth:latest")],
            [catalog_entry(builds=["studio-one", "studio-one"])],
        ):
            with self.subTest(entries=entries), self.assertRaises(ContractError):
                ImageCatalog.from_dict({
                    "schema_version": "vkong.connect.image-catalog.v1", "entries": entries
                })

    def test_studio_request_compiles_v2_job_with_only_job_files(self):
        catalog = ImageCatalog.from_dict({
            "schema_version": "vkong.connect.image-catalog.v1",
            "entries": [catalog_entry()],
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = BundleRequest.for_studio(
                studio_build_id="studio-one", training_mode="LoRA/QLoRA", catalog=catalog,
                job_id="job-1",
                worker_config={
                    "model_name": "org/model", "model_revision": "1" * 40,
                    "hf_dataset": "org/data", "dataset_revision": "2" * 40,
                    "training_type": "LoRA/QLoRA", "use_lora": True,
                },
                output_repo_id="user/result",
            )
            bundle = compile_bundle(request, root / "job")
            value = json.loads(bundle.job_path.read_text(encoding="utf-8"))
            job = validate_job(value)
            self.assertEqual(job.schema_version, "vkong.connect.job.v2")
            self.assertEqual(job.runtime, RUNTIME)
            self.assertEqual(bundle.config_path.name, "vkong.yaml")
            self.assertEqual(
                {p.relative_to(bundle.path).as_posix() for p in bundle.path.rglob("*") if p.is_file()},
                {"vkong.yaml", "bridge-job.json", "run_bridge.py"},
            )
            self.assertNotIn("unsloth/", bundle.config_path.read_text(encoding="utf-8"))

    def test_runner_rejects_wrong_runtime_before_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = BundleRequest(
                job_id="job-1", worker_config={
                    "model_name": "org/model", "model_revision": "1" * 40,
                    "training_type": "LoRA/QLoRA", "use_lora": True,
                },
                output_repo_id="user/result", runner_image=IMAGE, runtime=RUNTIME,
            )
            bundle = compile_bundle(request, root / "job")
            manifest = root / "installed.json"
            wrong = RunnerManifest(runtime("d" * 40, "c" * 40))
            manifest.write_text(json.dumps(wrong.as_dict()), encoding="utf-8")
            output = io.StringIO()
            with patch.dict("os.environ", {"VKONG_CONNECT_RUNTIME_MANIFEST": str(manifest)}), \
                 patch("sys.stdout", output), \
                 patch("vkong_connect.adapters.unsloth.runner._load_unsloth_worker") as worker:
                exit_code = runner_main(["--job", str(bundle.job_path)])
            self.assertEqual(exit_code, 2)
            self.assertIn("incompatible", output.getvalue())
            worker.assert_not_called()

    def test_built_manifest_reports_and_verifies_exact_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            self.assertEqual(manifest_main([
                "--output", str(path),
                "--adapter-name", "unsloth", "--adapter-schema", "unsloth.v1",
                "--job-schema", "vkong.connect.job.v2",
                "--source-commit", RUNTIME.source_commit,
                "--bridge-build-id", RUNTIME.bridge_build_id,
            ]), 0)
            output = io.StringIO()
            with patch.dict("os.environ", {"VKONG_CONNECT_RUNTIME_MANIFEST": str(path)}), \
                 patch("sys.stdout", output):
                self.assertEqual(verify_runtime(RUNTIME).runtime, RUNTIME)
                self.assertEqual(runner_main(["--version"]), 0)
            self.assertEqual(json.loads(output.getvalue())["runtime"], RUNTIME.as_dict())

    def test_image_build_checks_installed_fork_commit(self):
        class FakeDistribution:
            def read_text(self, name):
                assert name == "direct_url.json"
                return json.dumps({"vcs_info": {"commit_id": RUNTIME.source_commit}})

        with patch("vkong_connect.adapters.unsloth.runtime_image.metadata.distribution", return_value=FakeDistribution()):
            verify_installed_unsloth_commit(RUNTIME.source_commit)
            with self.assertRaises(ContractError):
                verify_installed_unsloth_commit("d" * 40)

    def test_legacy_v1_is_parseable_and_new_runtime_cannot_be_put_in_v1(self):
        document = {
            "schema_version": "vkong.connect.job.v1", "job_id": "job-1",
            "adapter": {"name": "unsloth", "schema_version": "unsloth.v1"},
            "spec": {
                "worker_config": {"model_name": "org/model"},
                "output": {"kind": "huggingface", "repo_id": "user/result", "private": True},
            },
        }
        self.assertIsNone(validate_job(document).runtime)
        document["runtime"] = RUNTIME.as_dict()
        with self.assertRaises(ContractError):
            validate_job(document)

    def test_runtime_bound_jobs_reject_unpinned_inputs_and_unapproved_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "train.jsonl"
            dataset.write_text('{"text":"hello"}\n', encoding="utf-8")
            config = {
                "model_name": "org/model", "training_type": "LoRA/QLoRA",
                "use_lora": True, "local_datasets": [],
            }
            request = BundleRequest(
                job_id="job-unpinned", worker_config=config,
                output_repo_id="user/result", runner_image=IMAGE, runtime=RUNTIME,
            )
            with self.assertRaisesRegex(ConfigurationError, "pinned commit"):
                compile_bundle(request, root / "unpinned")
            config["model_revision"] = "1" * 40
            request = BundleRequest(
                job_id="job-unapproved", worker_config=config,
                output_repo_id="user/result", runner_image=IMAGE,
                runtime=RUNTIME, local_datasets=(dataset,),
            )
            with self.assertRaisesRegex(ConfigurationError, "approved input roots"):
                compile_bundle(request, root / "unapproved")
