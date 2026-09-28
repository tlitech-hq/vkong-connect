"""Executable checks for the product-neutral client boundary."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from vkong_connect import VKongBridge
from vkong_connect.client.vkong_cli import RunStart
from vkong_connect.contracts.bundles import CompiledBundle, tree_digest
from vkong_connect.contracts.runtime import RuntimeIdentity
from vkong_connect.errors import ConfigurationError


ROOT = Path(__file__).resolve().parents[1] / "src" / "vkong_connect"


@dataclass
class ExampleRequest:
    """A test product, with no dependency on the Unsloth adapter or its schema."""

    job_id: str = "example-1"
    compiled: bool = False

    def compile(self, destination: Path) -> CompiledBundle:
        self.compiled = True
        destination.mkdir()
        (destination / "bridge-job.json").write_text("{}", encoding="utf-8")
        (destination / "vkong.yaml").write_text("app: example-app", encoding="utf-8")
        return CompiledBundle(
            path=destination,
            app_name="example-app",
            job_path=destination / "bridge-job.json",
            config_path=destination / "vkong.yaml",
            sha256=tree_digest(destination),
        )


class ArchitectureTests(unittest.TestCase):
    def test_public_client_import_does_not_load_product_adapters(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "\n".join([
                "import sys",
                "import vkong_connect",
                "loaded = [name for name in sys.modules if "
                "name.startswith(('vkong_connect.adapters', 'unsloth', 'torch', 'studio'))]",
                "assert not loaded, loaded",
            ])],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_core_does_not_import_product_layer(self) -> None:
        # Check relative as well as absolute imports, including TYPE_CHECKING.
        paths = [ROOT / "__init__.py", ROOT / "bridge.py", ROOT / "errors.py", ROOT / "security.py"]
        for directory in ("contracts", "client"):
            paths.extend((ROOT / directory).rglob("*.py"))
        for path in paths:
            with self.subTest(path=path):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        package = "vkong_connect" + (
                            "." + ".".join(path.relative_to(ROOT).parts[:-1])
                            if len(path.relative_to(ROOT).parts) > 1 else ""
                        )
                        module = (
                            resolve_name("." * node.level + (node.module or ""), package)
                            if node.level else (node.module or "")
                        )
                        names = [module]
                    for name in names:
                        self.assertFalse(
                            name.startswith((
                                "vkong_connect.adapters.", "unsloth", "studio", "torch"
                            )),
                            f"{path}:{node.lineno}: forbidden core dependency {name}",
                        )

    def test_second_product_prepares_and_submits_without_core_changes(self) -> None:
        cli = Mock()
        cli.validate.return_value = {"valid": True}
        cli.start_task.return_value = RunStart(
            "app_example", "example-app", "run_example", "vk_example",
            "running", 1.0, "USD", "vkong.cli.v1",
        )
        bridge = VKongBridge(cli)
        request = ExampleRequest()
        with tempfile.TemporaryDirectory() as directory:
            bundle = bridge.prepare(request, Path(directory))
            result = bridge.submit(bundle, idempotency_key="request-example")
            self.assertTrue(request.compiled)
            self.assertEqual(bundle.path, Path(directory) / request.job_id)
            self.assertEqual(result.run.app_name, "example-app")
            cli.start_task.assert_called_once_with(
                bundle.path, idempotency_key="request-example", app_name="example-app"
            )

    def test_invalid_job_identity_is_rejected_before_adapter_runs(self) -> None:
        for job_id in ("", ".", "..", "../other", "/tmp/other", "a/b", "a\\b", "C:other", "a" * 129):
            with self.subTest(job_id=job_id), tempfile.TemporaryDirectory() as directory:
                request = ExampleRequest(job_id)
                with self.assertRaises(ConfigurationError):
                    VKongBridge().prepare(request, Path(directory))
                self.assertFalse(request.compiled)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_unsloth_bundle_result_import_remains_compatible(self) -> None:
        from vkong_connect.adapters.unsloth.bundle import CompiledBundle as LegacyBundle

        self.assertIs(LegacyBundle, CompiledBundle)

    def test_runtime_contract_accepts_a_second_adapter_identity(self) -> None:
        identity = RuntimeIdentity(
            adapter_name="example", adapter_schema="example.v1",
            job_schema="example.job.v1", source_commit="a" * 40,
            bridge_build_id="b" * 40,
        )
        self.assertEqual(RuntimeIdentity.from_dict(identity.as_dict()), identity)
