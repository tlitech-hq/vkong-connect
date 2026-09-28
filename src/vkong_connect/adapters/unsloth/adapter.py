"""Unsloth implementation of the bridge's remote adapter boundary."""

from __future__ import annotations

from typing import Any, Mapping

from vkong_connect.contracts.adapters import AdapterDescriptor, RunContext, RunResult
from vkong_connect.contracts.events import EventSink

from .runner import run_unsloth_job
from .schema import UnslothJob, validate_job


class UnslothAdapter:
    descriptor = AdapterDescriptor(
        name="unsloth",
        schema_version="unsloth.v1",
        operations=("train",),
        output_kinds=("huggingface",),
        resumable=False,
    )

    def validate_job(self, document: Mapping[str, Any]) -> UnslothJob:
        return validate_job(document)

    def execute(
        self,
        job: UnslothJob,
        context: RunContext,
        events: EventSink,
    ) -> RunResult:
        return run_unsloth_job(job, context, events)
