"""Framework-neutral adapter types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from .events import EventSink


@dataclass(frozen=True)
class AdapterDescriptor:
    name: str
    schema_version: str
    operations: tuple[str, ...]
    output_kinds: tuple[str, ...]
    resumable: bool


@dataclass(frozen=True)
class RunContext:
    job_id: str
    workspace: Path
    spec: dict


@dataclass(frozen=True)
class PublishedArtifact:
    name: str
    kind: str
    uri: str
    revision: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None


@dataclass(frozen=True)
class RunResult:
    status: str
    output_dir: Path | None = None
    error: str | None = None
    artifacts: tuple[PublishedArtifact, ...] = field(default_factory=tuple)


class RunnerAdapter(Protocol):
    """Adapter boundary used by the framework-neutral remote entry point."""

    descriptor: AdapterDescriptor

    def validate_job(self, document: Mapping[str, Any]) -> Any: ...

    def execute(self, job: Any, context: RunContext, events: EventSink) -> RunResult: ...
