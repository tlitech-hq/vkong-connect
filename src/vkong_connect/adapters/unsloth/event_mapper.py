"""Map native Unsloth worker queue messages to bridge events."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vkong_connect.contracts.events import EventSink, EventType
from vkong_connect.errors import ConfigurationError
from vkong_connect.security import redact_secrets


@dataclass(frozen=True)
class NativeTerminal:
    status: str
    message: str
    error: str | None
    output_dir: Path | None


class UnslothEventQueue:
    """Queue-compatible event sink passed to Unsloth's existing worker."""

    def __init__(self, sink: EventSink, workspace: Path) -> None:
        self.sink = sink
        self.workspace = workspace.resolve()
        self.terminal: NativeTerminal | None = None
        self.output_dir: Path | None = None

    def put(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        event_type = event.get("type")
        if event_type == "model_load_started":
            self.sink.emit(EventType.PHASE, {"phase": "loading_model"})
            return
        if event_type == "model_load_completed":
            self.sink.emit(EventType.PHASE, {"phase": "loading_dataset"})
            return
        if event_type == "status":
            message = redact_secrets(event.get("message") or "").strip()
            if message:
                self.sink.emit(EventType.MESSAGE, {"message": message})
            return
        if event_type == "warning":
            message = redact_secrets(event.get("message") or "").strip()
            if message:
                self.sink.emit(EventType.WARNING, {"message": message})
            return
        if event_type == "progress":
            payload = {
                key: event.get(key)
                for key in (
                    "step",
                    "total_steps",
                    "epoch",
                    "loss",
                    "learning_rate",
                    "elapsed_seconds",
                    "eta_seconds",
                    "grad_norm",
                    "num_tokens",
                    "eval_loss",
                    "peak_memory_gb",
                )
                if key in event
            }
            self.sink.emit(EventType.METRIC, payload)
            return
        if event_type == "output_dir":
            self.output_dir = self._safe_output_dir(event.get("output_dir"))
            return
        if event_type == "complete":
            message = redact_secrets(event.get("status_message") or "Training completed")
            normalized = message.strip().lower()
            status = "cancelled" if normalized in {"training cancelled", "training stopped"} else "succeeded"
            output_dir = self._safe_output_dir(event.get("output_dir")) or self.output_dir
            self.terminal = NativeTerminal(
                status=status,
                message=message,
                error=None,
                output_dir=output_dir,
            )
            return
        if event_type == "error":
            error = redact_secrets(event.get("error") or "Unknown Unsloth training error")
            self.terminal = NativeTerminal(
                status="failed",
                message="Training failed",
                error=error,
                output_dir=self.output_dir,
            )
            return
        if event_type == "eval_configured":
            self.sink.emit(EventType.MESSAGE, {"message": "Evaluation configured"})
            return
        if event_type == "stall":
            message = redact_secrets(event.get("message") or "Model download stalled")
            self.sink.emit(EventType.WARNING, {"message": message, "code": "model_load_stall"})

    def _safe_output_dir(self, raw: Any) -> Path | None:
        if not isinstance(raw, str) or not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = self.workspace / path
        resolved = path.resolve()
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise ConfigurationError(
                "Unsloth reported an output directory outside the remote workspace"
            ) from exc
        return resolved
