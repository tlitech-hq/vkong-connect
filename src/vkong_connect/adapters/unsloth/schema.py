"""Validation for the persisted Unsloth bridge job document."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from vkong_connect.contracts.runtime import RuntimeIdentity
from vkong_connect.errors import ConfigurationError, ContractError

JOB_SCHEMA = "vkong.connect.job.v1"
JOB_SCHEMA_V2 = "vkong.connect.job.v2"
ADAPTER_NAME = "unsloth"
ADAPTER_SCHEMA = "unsloth.v1"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HF_REPO_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_SECRET_KEYS = {
    "hf_token",
    "token",
    "access_token",
    "wandb_token",
    "wandb_api_key",
    "secret_access_key",
    "password",
}
_SECRET_KEY_SUFFIXES = ("_token", "_password", "_secret", "_api_key", "_credential")
_LOCAL_ONLY_PATH_FIELDS = (
    "model_local_path",
    "model_snapshot_path",
    "dataset_local_path",
    "dataset_snapshot_path",
)


@dataclass(frozen=True)
class OutputSpec:
    kind: str
    repo_id: str
    private: bool = True


@dataclass(frozen=True)
class UnslothJob:
    job_id: str
    worker_config: dict[str, Any]
    output: OutputSpec
    schema_version: str = JOB_SCHEMA
    adapter_schema: str = ADAPTER_SCHEMA
    runtime: RuntimeIdentity | None = None

    def as_dict(self) -> dict[str, Any]:
        document = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "adapter": {"name": ADAPTER_NAME, "schema_version": self.adapter_schema},
            "spec": {
                "worker_config": copy.deepcopy(self.worker_config),
                "output": {
                    "kind": self.output.kind,
                    "repo_id": self.output.repo_id,
                    "private": self.output.private,
                },
            },
        }
        if self.runtime is not None:
            document["runtime"] = self.runtime.as_dict()
        return document


def _find_secret_fields(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_string = str(key)
            normalized_key = key_string.lower().replace("-", "_")
            child_path = f"{path}.{key_string}" if path else key_string
            if (
                normalized_key in _SECRET_KEYS
                or normalized_key.endswith(_SECRET_KEY_SUFFIXES)
            ) and item not in (None, "", False):
                found.append(child_path)
            found.extend(_find_secret_fields(item, child_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_secret_fields(item, f"{path}[{index}]"))
    return found


def _validate_relative_input(path_value: str) -> None:
    path = PurePosixPath(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigurationError(f"remote input path must stay inside the bundle: {path_value}")
    if not path.parts or path.parts[0] != "inputs":
        raise ConfigurationError(f"local dataset must be staged below inputs/: {path_value}")


def _validate_workspace_relative_path(name: str, value: Any) -> None:
    if value in (None, ""):
        return
    if not isinstance(value, str):
        raise ConfigurationError(f"worker_config.{name} must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value.startswith("~"):
        raise ConfigurationError(f"worker_config.{name} must stay inside the remote workspace")


def validate_job(value: Mapping[str, Any]) -> UnslothJob:
    schema_version = value.get("schema_version")
    if schema_version not in (JOB_SCHEMA, JOB_SCHEMA_V2):
        raise ContractError(f"unsupported bridge job schema: {value.get('schema_version')!r}")
    required = {"schema_version", "job_id", "adapter", "spec"}
    if schema_version == JOB_SCHEMA_V2:
        required.add("runtime")
    if set(value) != required:
        raise ContractError("bridge job has missing or unsupported top-level fields")
    runtime = (
        RuntimeIdentity.from_dict(value["runtime"])
        if schema_version == JOB_SCHEMA_V2 else None
    )
    if runtime is not None and (
        runtime.adapter_name != ADAPTER_NAME or runtime.adapter_schema != ADAPTER_SCHEMA
        or runtime.job_schema != JOB_SCHEMA_V2
    ):
        raise ContractError("job runtime does not match the Unsloth adapter contract")
    job_id = value.get("job_id")
    if not isinstance(job_id, str) or _ID_RE.fullmatch(job_id) is None:
        raise ContractError("job_id must be 1-128 portable identifier characters")
    adapter = value.get("adapter")
    if not isinstance(adapter, Mapping):
        raise ContractError("adapter must be an object")
    if adapter.get("name") != ADAPTER_NAME or adapter.get("schema_version") != ADAPTER_SCHEMA:
        raise ContractError("job requires the unsloth.v1 adapter")
    spec = value.get("spec")
    if not isinstance(spec, Mapping):
        raise ContractError("spec must be an object")
    worker_config = spec.get("worker_config")
    if not isinstance(worker_config, Mapping):
        raise ContractError("spec.worker_config must be an object")
    worker_config = copy.deepcopy(dict(worker_config))
    secret_fields = _find_secret_fields(worker_config)
    if secret_fields:
        raise ConfigurationError(
            "job document contains secret fields: " + ", ".join(sorted(secret_fields))
        )
    model_name = worker_config.get("model_name")
    if not isinstance(model_name, str) or not model_name.strip():
        raise ConfigurationError("worker_config.model_name is required")
    if Path(model_name).is_absolute() or model_name.startswith(("./", "../", "~")):
        raise ConfigurationError("phase-one remote training requires a hosted model reference")
    if runtime is not None:
        if worker_config.get("training_type") != "LoRA/QLoRA" or worker_config.get("use_lora") is not True:
            raise ConfigurationError("runtime-bound remote jobs support LoRA/QLoRA only")
        if not isinstance(worker_config.get("model_revision"), str) or not _REVISION_RE.fullmatch(
            worker_config["model_revision"]
        ):
            raise ConfigurationError("runtime-bound model requires a pinned commit revision")
        if worker_config.get("hf_dataset") and (
            not isinstance(worker_config.get("dataset_revision"), str)
            or not _REVISION_RE.fullmatch(worker_config["dataset_revision"])
        ):
            raise ConfigurationError("runtime-bound dataset requires a pinned commit revision")
    for key in _LOCAL_ONLY_PATH_FIELDS:
        if worker_config.get(key):
            raise ConfigurationError(f"phase-one remote training does not accept {key}")
    _validate_workspace_relative_path("output_dir", worker_config.get("output_dir"))
    _validate_workspace_relative_path("tensorboard_dir", worker_config.get("tensorboard_dir"))
    for key in ("local_datasets", "local_eval_datasets"):
        paths = worker_config.get(key, [])
        if paths is None:
            paths = []
        if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            raise ConfigurationError(f"worker_config.{key} must be an array of paths")
        for path_value in paths:
            _validate_relative_input(path_value)
    resume = worker_config.get("resume_from_checkpoint")
    if resume:
        raise ConfigurationError(
            "phase-one remote resume is unavailable until checkpoint materialization is implemented"
        )
    output = spec.get("output")
    if not isinstance(output, Mapping) or output.get("kind") != "huggingface":
        raise ConfigurationError("phase-one output.kind must be 'huggingface'")
    repo_id = output.get("repo_id")
    if not isinstance(repo_id, str) or _HF_REPO_RE.fullmatch(repo_id) is None:
        raise ConfigurationError("output.repo_id must be a Hugging Face namespace/repository")
    private = output.get("private", True)
    if not isinstance(private, bool):
        raise ConfigurationError("output.private must be a boolean")
    if not private:
        raise ConfigurationError("phase-one remote output must be a private repository")
    return UnslothJob(
        job_id=job_id,
        worker_config=worker_config,
        output=OutputSpec(kind="huggingface", repo_id=repo_id, private=private),
        schema_version=schema_version,
        runtime=runtime,
    )
