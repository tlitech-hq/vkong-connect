from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from vkong_connect.adapters.unsloth.runner import run_unsloth_job
from vkong_connect.adapters.unsloth.event_mapper import UnslothEventQueue
from vkong_connect.adapters.unsloth.schema import validate_job
from vkong_connect.contracts.adapters import PublishedArtifact, RunContext
from vkong_connect.contracts.events import EventSink, parse_event_line
from vkong_connect.errors import ConfigurationError, OutputPublicationError


def job_document() -> dict:
    return {
        "schema_version": "vkong.connect.job.v1",
        "job_id": "job-1",
        "adapter": {"name": "unsloth", "schema_version": "unsloth.v1"},
        "spec": {
            "worker_config": {"model_name": "org/model", "hf_dataset": "org/data"},
            "output": {"kind": "huggingface", "repo_id": "user/result", "private": True},
        },
    }


class FakePublisher:
    def publish(self, output_dir, output):
        return PublishedArtifact(
            name="model",
            kind="lora-adapter",
            uri="hf://user/result@commit-1",
            revision="commit-1",
            size_bytes=12,
        )


class FailingPublisher:
    def publish(self, output_dir, output):
        raise OutputPublicationError("upload failed")


class UnslothRunnerTests(unittest.TestCase):
    def test_output_directory_must_stay_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            sink = EventSink("job-1", io.StringIO())
            event_queue = UnslothEventQueue(sink, workspace)
            with self.assertRaisesRegex(ConfigurationError, "outside the remote workspace"):
                event_queue.put(
                    {"type": "output_dir", "output_dir": str(Path(directory) / "other")}
                )

    def test_success_is_emitted_only_after_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            output_dir = workspace / "output"
            output_dir.mkdir()
            (output_dir / "adapter.safetensors").write_bytes(b"weights")
            stream = io.StringIO()
            job = validate_job(job_document())

            def worker(*, event_queue, stop_queue, config):
                self.assertIn("hf_token", config)
                self.assertFalse(config["allow_ambient"])
                event_queue.put({"type": "model_load_started"})
                event_queue.put(
                    {"type": "progress", "step": 1, "total_steps": 2, "loss": 1.5}
                )
                event_queue.put({"type": "output_dir", "output_dir": str(output_dir)})
                event_queue.put(
                    {
                        "type": "complete",
                        "output_dir": str(output_dir),
                        "status_message": "Training completed",
                    }
                )

            result = run_unsloth_job(
                job,
                RunContext(job_id=job.job_id, workspace=workspace, spec=job_document()["spec"]),
                EventSink(job.job_id, stream),
                worker=worker,
                publisher=FakePublisher(),
            )

            self.assertEqual(result.status, "succeeded")
            events = [parse_event_line(line) for line in stream.getvalue().splitlines()]
            types = [event.type.value for event in events if event is not None]
            self.assertEqual(types[-2:], ["artifact", "terminal"])
            terminal = events[-1]
            assert terminal is not None
            self.assertEqual(terminal.payload["status"], "succeeded")

    def test_publication_failure_prevents_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            output_dir = workspace / "output"
            output_dir.mkdir()
            stream = io.StringIO()
            job = validate_job(job_document())

            def worker(*, event_queue, stop_queue, config):
                event_queue.put(
                    {
                        "type": "complete",
                        "output_dir": str(output_dir),
                        "status_message": "Training completed",
                    }
                )

            result = run_unsloth_job(
                job,
                RunContext(job_id=job.job_id, workspace=workspace, spec=job_document()["spec"]),
                EventSink(job.job_id, stream),
                worker=worker,
                publisher=FailingPublisher(),
            )
            self.assertEqual(result.status, "failed")
            events = [parse_event_line(line) for line in stream.getvalue().splitlines()]
            terminal = events[-1]
            assert terminal is not None
            self.assertEqual(terminal.payload["code"], "output_publication_failed")

    def test_worker_error_maps_to_failed_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stream = io.StringIO()
            job = validate_job(job_document())

            def worker(*, event_queue, stop_queue, config):
                event_queue.put({"type": "error", "error": "out of memory"})

            result = run_unsloth_job(
                job,
                RunContext(
                    job_id=job.job_id,
                    workspace=Path(directory),
                    spec=job_document()["spec"],
                ),
                EventSink(job.job_id, stream),
                worker=worker,
                publisher=FakePublisher(),
            )
            self.assertEqual(result.status, "failed")
            self.assertIn("out of memory", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
