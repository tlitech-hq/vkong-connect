"""Execute a validated Unsloth bridge job in the runner image."""

from __future__ import annotations

import importlib
import os
import queue
import sys
from pathlib import Path
from typing import Callable

from vkong_connect.contracts.adapters import PublishedArtifact, RunContext, RunResult
from vkong_connect.contracts.events import EventSink, EventType
from vkong_connect.errors import ConfigurationError, OutputPublicationError
from vkong_connect.security import redact_secrets

from .event_mapper import UnslothEventQueue
from .outputs import HuggingFaceOutputPublisher, OutputPublisher
from .schema import UnslothJob

Worker = Callable[..., None]


def _load_unsloth_worker() -> Worker:
    backend = os.environ.get("UNSLOTH_STUDIO_BACKEND")
    if backend:
        backend_path = Path(backend).expanduser().resolve()
        if not backend_path.is_dir():
            raise ConfigurationError(f"UNSLOTH_STUDIO_BACKEND is not a directory: {backend}")
        sys.path.insert(0, str(backend_path))
    else:
        # Unsloth ships Studio as the ``studio`` package, while its backend uses
        # historical top-level imports such as ``core`` and ``utils``. Discover
        # the installed package rather than assuming a checkout location.
        try:
            studio = importlib.import_module("studio")
        except ImportError as exc:
            raise ConfigurationError(
                "Unsloth Studio is unavailable in the runner image"
            ) from exc
        studio_file = getattr(studio, "__file__", None)
        if not studio_file:
            raise ConfigurationError("Cannot locate the installed Unsloth Studio package")
        backend_path = Path(studio_file).resolve().parent / "backend"
        if not backend_path.is_dir():
            raise ConfigurationError(
                "Installed Unsloth package does not contain the Studio backend"
            )
        sys.path.insert(0, str(backend_path))
    try:
        module = importlib.import_module("core.training.worker")
    except ImportError as exc:
        raise ConfigurationError(
            "Unsloth Studio backend is unavailable in the runner image"
        ) from exc
    worker = getattr(module, "run_training_process", None)
    if not callable(worker):
        raise ConfigurationError("Unsloth run_training_process entrypoint is unavailable")
    return worker


def _normalize_worker_config(config: dict) -> dict:
    """Apply Studio's own defaults on the GPU host when its builder is importable.

    Jobs may carry only the fields a user set in Studio. Studio's builder fills every
    other field with its current defaults and records the remote device backend, so
    the laptop's backend (for example ``mps``) never reaches a CUDA worker.
    """
    try:
        training = importlib.import_module("core.training.training")
    except ImportError:
        return dict(config)
    builder = getattr(training, "_build_training_worker_config", None)
    if not callable(builder):
        return dict(config)
    normalized = builder(dict(config))
    for key in ("local_datasets", "local_eval_datasets", "output_dir"):
        if key in config:
            normalized[key] = config[key]
    return normalized


def _hydrate_worker_secrets(config: dict) -> dict:
    result = dict(config)
    # Secret values live only in process memory. The persisted job schema rejects
    # these fields when they contain values.
    result["hf_token"] = os.environ.get("HF_TOKEN") or ""
    result["wandb_token"] = os.environ.get("WANDB_API_KEY") or ""
    result["allow_ambient"] = False
    return result


def _artifact_payload(artifact: PublishedArtifact) -> dict:
    return {
        "name": artifact.name,
        "kind": artifact.kind,
        "uri": artifact.uri,
        "revision": artifact.revision,
        "size_bytes": artifact.size_bytes,
        "checksum": artifact.checksum,
    }


def run_unsloth_job(
    job: UnslothJob,
    context: RunContext,
    sink: EventSink,
    *,
    worker: Worker | None = None,
    publisher: OutputPublisher | None = None,
    stop_queue: queue.Queue | None = None,
) -> RunResult:
    native_events = UnslothEventQueue(sink, context.workspace)
    cancellation = stop_queue or queue.Queue()
    selected_worker = worker or _load_unsloth_worker()
    worker_config = job.worker_config if worker is not None else _normalize_worker_config(job.worker_config)
    selected_publisher = publisher or HuggingFaceOutputPublisher()

    sink.emit(EventType.PHASE, {"phase": "starting"})
    try:
        selected_worker(
            event_queue=native_events,
            stop_queue=cancellation,
            config=_hydrate_worker_secrets(worker_config),
        )
    except BaseException as exc:
        # KeyboardInterrupt/SystemExit from framework code still need one terminal
        # event before the process exits. Do not include a stack or secret-bearing repr.
        safe_error = redact_secrets(exc)
        sink.emit(
            EventType.TERMINAL,
            {"status": "failed", "error": safe_error, "code": "unsloth_worker_crashed"},
        )
        return RunResult(status="failed", error=safe_error)

    terminal = native_events.terminal
    if terminal is None:
        message = "Unsloth worker exited without a terminal event"
        sink.emit(
            EventType.TERMINAL,
            {"status": "failed", "error": message, "code": "missing_terminal_event"},
        )
        return RunResult(status="failed", error=message)
    if terminal.status == "failed":
        sink.emit(
            EventType.TERMINAL,
            {"status": "failed", "error": terminal.error, "code": "training_failed"},
        )
        return RunResult(status="failed", output_dir=terminal.output_dir, error=terminal.error)
    if terminal.status == "cancelled":
        sink.emit(EventType.TERMINAL, {"status": "cancelled", "message": terminal.message})
        return RunResult(status="cancelled", output_dir=terminal.output_dir)
    if terminal.output_dir is None:
        message = "Unsloth completed without a publishable output directory"
        sink.emit(
            EventType.TERMINAL,
            {"status": "failed", "error": message, "code": "missing_output"},
        )
        return RunResult(status="failed", error=message)

    sink.emit(EventType.PHASE, {"phase": "publishing_output"})
    try:
        artifact = selected_publisher.publish(terminal.output_dir, job.output)
    except OutputPublicationError as exc:
        sink.emit(
            EventType.TERMINAL,
            {"status": "failed", "error": str(exc), "code": exc.code, "retriable": exc.retriable},
        )
        return RunResult(status="failed", output_dir=terminal.output_dir, error=str(exc))
    sink.emit(EventType.ARTIFACT, _artifact_payload(artifact))
    sink.emit(EventType.TERMINAL, {"status": "succeeded", "message": terminal.message})
    return RunResult(
        status="succeeded",
        output_dir=terminal.output_dir,
        artifacts=(artifact,),
    )
