"""Compile a validated Unsloth request into a deterministic VKong task bundle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from vkong_connect.contracts.bundles import CompiledBundle, tree_digest
from vkong_connect.contracts.runtime import RuntimeIdentity
from vkong_connect.errors import ConfigurationError

from .dev_runtime import DEV_PYTHON, DevRuntime
from .image_catalog import ImageCatalog
from .schema import ADAPTER_NAME, ADAPTER_SCHEMA, JOB_SCHEMA, JOB_SCHEMA_V2, validate_job

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_BUNDLE_BYTES = 500 * 1024 * 1024
ALLOWED_DATASET_SUFFIXES = frozenset({".json", ".jsonl", ".csv"})
_NAME_RE = re.compile(r"[^a-z0-9-]+")
_SECRET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class ComputeSpec:
    gpu: str = "Any"
    num_gpus: int = 1
    cpu_cores: int = 8
    ram_gb: int = 32
    disk_gb: int = 100
    inet_down_mbps: int = 500
    max_dph: float = 2.0
    verified_only: bool = True

    def validate(self) -> None:
        if not self.gpu.strip():
            raise ConfigurationError("gpu must not be empty")
        for name, value in (
            ("num_gpus", self.num_gpus),
            ("cpu_cores", self.cpu_cores),
            ("ram_gb", self.ram_gb),
            ("disk_gb", self.disk_gb),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ConfigurationError(f"{name} must be a positive integer")
        if self.inet_down_mbps < 0:
            raise ConfigurationError("inet_down_mbps must be non-negative")
        if not 0 < float(self.max_dph) <= 1000:
            raise ConfigurationError("max_dph must be greater than zero and at most 1000")


@dataclass(frozen=True)
class BundleRequest:
    job_id: str
    worker_config: Mapping[str, Any]
    output_repo_id: str
    runner_image: str
    compute: ComputeSpec = field(default_factory=ComputeSpec)
    local_datasets: tuple[Path, ...] = ()
    local_eval_datasets: tuple[Path, ...] = ()
    secret_bundles: tuple[str, ...] = ("huggingface",)
    output_private: bool = True
    runtime: RuntimeIdentity | None = None
    approved_input_roots: tuple[Path, ...] = ()
    dev_runtime: DevRuntime | None = None

    @classmethod
    def for_studio(
        cls,
        *,
        studio_build_id: str,
        training_mode: str,
        catalog: ImageCatalog | None = None,
        platform: str = "linux/amd64",
        **kwargs: Any,
    ) -> "BundleRequest":
        """Select a published image; callers cannot supply an alternate image."""
        if "runner_image" in kwargs or "runtime" in kwargs:
            raise ConfigurationError("Studio image and runtime are selected by the catalog")
        selected = (catalog or ImageCatalog.packaged()).resolve(
            studio_build_id, training_mode=training_mode, platform=platform
        )
        worker_config = kwargs.get("worker_config")
        if not isinstance(worker_config, Mapping) or worker_config.get("training_type") != training_mode:
            raise ConfigurationError("Studio training mode does not match the selected image")
        return cls(runner_image=selected.image, runtime=selected.runtime, **kwargs)


    def compile(self, destination: Path) -> CompiledBundle:
        return compile_bundle(self, destination)


def _app_name(job_id: str) -> str:
    normalized = _NAME_RE.sub("-", job_id.lower()).strip("-")
    if not normalized:
        raise ConfigurationError("job_id cannot produce an empty VKong App name")
    suffix = hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:8]
    prefix = normalized[:45].rstrip("-")
    return f"unsloth-{prefix}-{suffix}"


def _validate_image(image: str) -> None:
    if "@sha256:" not in image:
        raise ConfigurationError("runner_image must be pinned by sha256 digest")
    digest = image.rsplit("@sha256:", 1)[1]
    if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
        raise ConfigurationError("runner_image has an invalid sha256 digest")


def _stage_files(
    files: tuple[Path, ...], root: Path, prefix: str,
    approved_roots: tuple[Path, ...],
) -> list[str]:
    staged: list[str] = []
    seen_names: set[str] = set()
    roots = tuple(value.expanduser().resolve() for value in approved_roots)
    for index, source_value in enumerate(files):
        if source_value.is_symlink():
            raise ConfigurationError(f"local dataset must not be a symlink: {source_value}")
        source = source_value.expanduser().resolve()
        if not source.is_file():
            raise ConfigurationError(f"local dataset is not a file: {source_value}")
        if roots and not any(source.is_relative_to(value) for value in roots):
            raise ConfigurationError(f"local dataset is outside approved input roots: {source_value}")
        if source.suffix.lower() not in ALLOWED_DATASET_SUFFIXES:
            raise ConfigurationError(f"unsupported local dataset format: {source.name}")
        name = source.name
        if name in seen_names:
            name = f"{index}-{name}"
        seen_names.add(name)
        relative = Path("inputs") / prefix / name
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            with os.fdopen(os.open(source, flags), "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ConfigurationError(f"local dataset is not a regular file: {source.name}")
                if before.st_size > MAX_FILE_BYTES:
                    raise ConfigurationError(f"local dataset exceeds 50 MiB: {source.name}")
                copied = 0
                with destination.open("wb") as target:
                    while chunk := stream.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > MAX_FILE_BYTES:
                            raise ConfigurationError(f"local dataset exceeds 50 MiB: {source.name}")
                        target.write(chunk)
                after = os.fstat(stream.fileno())
                if (
                    copied != before.st_size or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns
                    or before.st_ctime_ns != after.st_ctime_ns
                    or before.st_ino != after.st_ino
                ):
                    raise ConfigurationError(f"local dataset changed while staging: {source.name}")
        except OSError as exc:
            raise ConfigurationError(f"cannot stage local dataset: {source.name}") from exc
        staged.append(relative.as_posix())
    return staged


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_yaml(
    *, app_name: str, image: str, compute: ComputeSpec, secrets: tuple[str, ...],
    init_cmd: str | None = None, python: str = "python3",
) -> str:
    lines = [
        "type: task",
        f"app: {_yaml_string(app_name)}",
        f"gpu: {_yaml_string(compute.gpu)}",
        f"num_gpus: {compute.num_gpus}",
        f"cpu_cores: {compute.cpu_cores}",
        f"ram_gb: {compute.ram_gb}",
        f"disk_gb: {compute.disk_gb}",
        f"inet_down_mbps: {compute.inet_down_mbps}",
        f"max_dph: {float(compute.max_dph):g}",
        f"verified_only: {'true' if compute.verified_only else 'false'}",
        f"image: {_yaml_string(image)}",
    ]
    if secrets:
        lines.append("secrets:")
        lines.extend(f"  - {_yaml_string(secret)}" for secret in secrets)
    if init_cmd:
        lines.append("init_cmd: |")
        lines.extend(f"  {line}" if line else "" for line in init_cmd.rstrip("\n").split("\n"))
    lines.extend(
        [
            "srcs:",
            '  - "bridge-job.json"',
            '  - "run_bridge.py"',
            '  - "inputs/"',
            'work_dir: "."',
            "start_argv:",
            f"  - {_yaml_string(python)}",
            '  - "run_bridge.py"',
            '  - "--job"',
            '  - "bridge-job.json"',
            "",
        ]
    )
    return "\n".join(lines)


_DEV_RUNNER_PREAMBLE = """\
import os

# Development runtime: Studio backend installed by init_cmd at a pinned fork commit.
os.environ.setdefault("UNSLOTH_STUDIO_BACKEND", {backend!r})
"""

_RUNNER_SCRIPT = """\
from vkong_connect.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
"""


def compile_bundle(request: BundleRequest, destination: Path) -> CompiledBundle:
    """Create a new bundle atomically; never overwrite an existing destination."""
    request.compute.validate()
    _validate_image(request.runner_image)
    if request.dev_runtime is not None:
        request.dev_runtime.validate()
        if request.runtime is not None:
            raise ConfigurationError("a job uses either a catalog runtime or a dev runtime")
        if request.runner_image != request.dev_runtime.base_image:
            raise ConfigurationError("dev runtime jobs run on the dev runtime base image")
    if request.runtime is not None:
        request.runtime.validate()
        if (request.local_datasets or request.local_eval_datasets) and not request.approved_input_roots:
            raise ConfigurationError("runtime-bound local datasets require approved input roots")
    if destination.exists():
        raise ConfigurationError(f"bundle destination already exists: {destination}")
    if len(set(request.secret_bundles)) != len(request.secret_bundles):
        raise ConfigurationError("secret bundle names must be unique")
    for secret in request.secret_bundles:
        if _SECRET_NAME_RE.fullmatch(secret) is None:
            raise ConfigurationError(f"invalid VKong secret bundle name: {secret!r}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        (temporary / "inputs").mkdir()
        worker_config = dict(request.worker_config)
        staged_train = _stage_files(
            request.local_datasets, temporary, "train", request.approved_input_roots
        )
        staged_eval = _stage_files(
            request.local_eval_datasets, temporary, "eval", request.approved_input_roots
        )
        if staged_train:
            worker_config["local_datasets"] = staged_train
            worker_config["hf_dataset"] = None
        if staged_eval:
            worker_config["local_eval_datasets"] = staged_eval
        job_document = {
            "schema_version": JOB_SCHEMA_V2 if request.runtime is not None else JOB_SCHEMA,
            "job_id": request.job_id,
            "adapter": {"name": ADAPTER_NAME, "schema_version": ADAPTER_SCHEMA},
            "spec": {
                "worker_config": worker_config,
                "output": {
                    "kind": "huggingface",
                    "repo_id": request.output_repo_id,
                    "private": request.output_private,
                },
            },
        }
        if request.runtime is not None:
            job_document["runtime"] = request.runtime.as_dict()
        validated = validate_job(job_document)
        try:
            serialized_job = json.dumps(
                validated.as_dict(),
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("worker_config must contain finite JSON values") from exc
        (temporary / "bridge-job.json").write_text(serialized_job + "\n", encoding="utf-8")
        launcher = _RUNNER_SCRIPT
        if request.dev_runtime is not None:
            launcher = (
                _DEV_RUNNER_PREAMBLE.format(backend=request.dev_runtime.studio_backend)
                + "\n" + _RUNNER_SCRIPT
            )
        (temporary / "run_bridge.py").write_text(launcher, encoding="utf-8")
        app_name = _app_name(request.job_id)
        (temporary / "vkong.yaml").write_text(
            _render_yaml(
                app_name=app_name,
                image=request.runner_image,
                compute=request.compute,
                secrets=request.secret_bundles,
                init_cmd=(
                    request.dev_runtime.init_script() if request.dev_runtime is not None else None
                ),
                python=DEV_PYTHON if request.dev_runtime is not None else "python3",
            ),
            encoding="utf-8",
        )
        size = sum(path.stat().st_size for path in temporary.rglob("*") if path.is_file())
        if size > MAX_BUNDLE_BYTES:
            raise ConfigurationError("generated bundle exceeds VKong's 500 MiB sync limit")
        sha256 = tree_digest(temporary)
        os.replace(temporary, destination)
        return CompiledBundle(
            path=destination,
            app_name=app_name,
            job_path=destination / "bridge-job.json",
            config_path=destination / "vkong.yaml",
            sha256=sha256,
        )
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
