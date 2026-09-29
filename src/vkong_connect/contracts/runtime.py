"""Immutable training-runtime identity shared by catalog, job and runner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from vkong_connect.errors import ContractError

RUNTIME_SCHEMA = "vkong.connect.runtime.v1"
_COMMIT = re.compile(r"[0-9a-f]{40}")
_BUILD = re.compile(r"[0-9a-f]{40}")
_PLATFORMS = frozenset({"linux/amd64", "linux/arm64"})


@dataclass(frozen=True)
class RuntimeIdentity:
    adapter_name: str
    adapter_schema: str
    job_schema: str
    source_commit: str
    bridge_build_id: str
    event_version: int = 1
    platform: str = "linux/amd64"
    schema_version: str = RUNTIME_SCHEMA

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RuntimeIdentity":
        if not isinstance(value, Mapping):
            raise ContractError("runtime identity must be an object")
        expected = {
            "schema_version", "adapter_name", "adapter_schema", "job_schema",
            "source_commit", "bridge_build_id", "event_version", "platform",
        }
        if set(value) != expected:
            raise ContractError("runtime identity has missing or unsupported fields")
        identity = cls(**value)
        identity.validate()
        return identity

    def validate(self) -> None:
        if self.schema_version != RUNTIME_SCHEMA:
            raise ContractError(f"unsupported runtime identity schema: {self.schema_version!r}")
        if not isinstance(self.source_commit, str) or not _COMMIT.fullmatch(
            self.source_commit
        ):
            raise ContractError("runtime requires a full lowercase adapter source commit")
        if not isinstance(self.bridge_build_id, str) or not _BUILD.fullmatch(
            self.bridge_build_id
        ):
            raise ContractError("runtime requires a full lowercase bridge source commit")
        if not isinstance(self.adapter_name, str) or not re.fullmatch(
            r"[a-z][a-z0-9_-]{0,63}", self.adapter_name
        ):
            raise ContractError("runtime requires a portable adapter name")
        for name, value in (("adapter_schema", self.adapter_schema), ("job_schema", self.job_schema)):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
                raise ContractError(f"runtime requires a portable {name}")
        if type(self.event_version) is not int or self.event_version != 1:
            raise ContractError("runtime requires bridge event version 1")
        if not isinstance(self.platform, str) or self.platform not in _PLATFORMS:
            raise ContractError(f"unsupported remote platform: {self.platform!r}")

    def as_dict(self) -> dict[str, str | int]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "source_commit": self.source_commit,
            "bridge_build_id": self.bridge_build_id,
            "adapter_schema": self.adapter_schema,
            "job_schema": self.job_schema,
            "event_version": self.event_version,
            "platform": self.platform,
        }
