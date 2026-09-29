from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from vkong_connect.adapters.unsloth import runner as runner_module
from vkong_connect.adapters.unsloth.runner import _load_unsloth_worker
from vkong_connect.errors import ConfigurationError


class UnslothLoaderTests(unittest.TestCase):
    def test_discovers_backend_below_installed_studio_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            studio_root = Path(directory) / "studio"
            backend = studio_root / "backend"
            backend.mkdir(parents=True)
            studio = SimpleNamespace(__file__=str(studio_root / "__init__.py"))

            def worker(**kwargs):
                return None

            worker_module = SimpleNamespace(run_training_process=worker)

            def import_module(name):
                if name == "studio":
                    return studio
                if name == "core.training.worker":
                    return worker_module
                raise ImportError(name)

            with patch.dict("os.environ", {}, clear=True), patch(
                "vkong_connect.adapters.unsloth.runner.importlib.import_module",
                side_effect=import_module,
            ), patch.object(runner_module.sys, "path", []):
                self.assertIs(_load_unsloth_worker(), worker)
                self.assertEqual(str(backend.resolve()), sys.path[0])

    def test_reports_missing_studio_as_configuration_error(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch(
            "vkong_connect.adapters.unsloth.runner.importlib.import_module",
            side_effect=ImportError("studio"),
        ):
            with self.assertRaisesRegex(ConfigurationError, "Studio is unavailable"):
                _load_unsloth_worker()


if __name__ == "__main__":
    unittest.main()
