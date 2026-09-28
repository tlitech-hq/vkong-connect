"""Contract checks against the sibling ../unsloth-vkong checkout, without importing ML packages.

These are the upstream Unsloth surfaces vkong-connect depends on and the fork's hooks
(see docs/decisions/0004-thin-unsloth-fork.md). Run after every upstream bump.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

FORK = Path(__file__).resolve().parents[2] / "unsloth-vkong"
BACKEND = FORK / "studio" / "backend"
FRONTEND = FORK / "studio" / "frontend" / "src"


def _function(path: Path, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {path}")


@unittest.skipUnless(BACKEND.is_dir(), "sibling unsloth-vkong checkout is unavailable")
class UnslothForkSurfaceTests(unittest.TestCase):
    def test_worker_entrypoint_signature(self) -> None:
        worker = _function(BACKEND / "core" / "training" / "worker.py", "run_training_process")
        self.assertEqual(
            [arg.arg for arg in worker.args.kwonlyargs], ["event_queue", "stop_queue", "config"]
        )

    def test_worker_config_builder_exists(self) -> None:
        builder = _function(
            BACKEND / "core" / "training" / "training.py", "_build_training_worker_config"
        )
        self.assertEqual([arg.arg for arg in builder.args.args], ["values"])

    def test_worker_events_mapped_by_adapter_are_still_emitted(self) -> None:
        source = (BACKEND / "core" / "training" / "worker.py").read_text(encoding="utf-8")
        for event_type in ("status", "progress", "complete", "error"):
            with self.subTest(event_type=event_type):
                self.assertIn(f'"type": "{event_type}"', source)

    def test_frontend_payload_builder_exists(self) -> None:
        mappers = (FRONTEND / "features" / "training" / "api" / "mappers.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn("export function buildTrainingStartPayload(", mappers)

    def test_fork_hooks_are_present(self) -> None:
        main = (BACKEND / "main.py").read_text(encoding="utf-8")
        self.assertIn("from vkong_connect.integrations.unsloth_studio import create_router", main)
        self.assertIn('prefix = "/api/remote-training"', main)
        cta = (FRONTEND / "features" / "studio" / "wizard" / "start-training-cta.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("<TrainOnVKong", cta)


if __name__ == "__main__":
    unittest.main()
