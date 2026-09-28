"""Remote training on VKong for Unsloth Studio, driven only through the VKong CLI.

Studio posts the same payload it sends to ``/api/train/start``. The service strips
laptop-only and secret fields, compiles a VKong task bundle, and starts it with
``vkong run --detach --auto-stop`` in a background thread (startup blocks while a
GPU is rented and the image is pulled). Job records are small JSON files; VKong
remains authoritative for App, Run, rental and billing state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import uuid
from typing import Any, Callable, Mapping

from vkong_connect.adapters.unsloth.bundle import BundleRequest, ComputeSpec
from vkong_connect.adapters.unsloth.dev_runtime import DevRuntime, resolve_dev_runtime
from vkong_connect.bridge import VKongBridge
from vkong_connect.client import CLIContext, VKongCLI
from vkong_connect.errors import BridgeError, ConfigurationError

DEFAULT_SERVER_URL = "https://vkong.tli-tech.com"
TERMINAL_STATES = frozenset({"finished", "failed", "stopped"})

_SECRET_FIELDS = frozenset(
    {"hf_token", "token", "access_token", "wandb_token", "wandb_api_key", "password"}
)
# Local Studio state and laptop paths that are meaningless on the GPU host.
_DROPPED_FIELDS = frozenset(
    {
        "start_request_id", "model_known_cached", "dataset_known_cached",
        "actual_model_repo_id", "model_snapshot_path", "dataset_snapshot_path",
        "tensorboard_dir", "output_dir", "allow_external_output_dir", "gpu_ids",
        "device_backend", "subject", "allow_ambient",
    }
)
_LOCAL_ONLY_FIELDS = ("model_local_path", "dataset_local_path")
_REPO_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
_JOB_ID_RE = re.compile(r"studio-[0-9]{8}t[0-9]{6}z-[0-9a-f]{8}")


def portable_worker_config(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[Path, ...], tuple[Path, ...]]:
    """Keep only what the remote worker needs; extract local datasets for staging."""
    worker = {key: value for key, value in payload.items() if value is not None}
    for field in _SECRET_FIELDS | _DROPPED_FIELDS:
        worker.pop(field, None)
    for field in _LOCAL_ONLY_FIELDS:
        if worker.pop(field, None):
            raise ConfigurationError(
                f"remote training needs a Hugging Face model and dataset; {field} is only on this machine"
            )
    if worker.get("resume_from_checkpoint"):
        raise ConfigurationError("resuming a checkpoint on VKong is not supported yet")
    if worker.get("s3_config"):
        raise ConfigurationError("S3 datasets are not supported for VKong training yet")
    if worker.get("training_type", "LoRA/QLoRA") != "LoRA/QLoRA" or worker.get("use_lora") is False:
        raise ConfigurationError("VKong training currently supports LoRA/QLoRA only")
    if not isinstance(worker.get("model_name"), str) or not worker["model_name"]:
        raise ConfigurationError("choose a model before training on VKong")
    local_train = tuple(Path(value) for value in worker.pop("local_datasets", None) or ())
    local_eval = tuple(Path(value) for value in worker.pop("local_eval_datasets", None) or ())
    if not local_train and not worker.get("hf_dataset"):
        raise ConfigurationError("choose a dataset before training on VKong")
    return worker, local_train, local_eval


@dataclass(frozen=True)
class ComputeChoice:
    gpu: str = "Any"
    num_gpus: int = 1
    max_dph: float = 1.0
    disk_gb: int = 100

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ComputeChoice":
        value = value or {}
        try:
            choice = cls(
                gpu=str(value.get("gpu") or "Any"),
                num_gpus=int(value.get("num_gpus") or 1),
                max_dph=float(value.get("max_dph") or 1.0),
                disk_gb=int(value.get("disk_gb") or 100),
            )
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("invalid compute choice") from exc
        ComputeSpec(
            gpu=choice.gpu, num_gpus=choice.num_gpus, max_dph=choice.max_dph,
            disk_gb=choice.disk_gb,
        ).validate()
        return choice


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RemoteTrainingService:
    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        vkong_binary: str | None = None,
        server_url: str | None = None,
        runtime_resolver: Callable[[], DevRuntime] = resolve_dev_runtime,
        cli_factory: Callable[[CLIContext | None], VKongCLI] | None = None,
    ) -> None:
        home = os.environ.get("VKONG_CONNECT_HOME")
        self.state_dir = (state_dir or Path(home or "~/.vkong-connect")).expanduser() / "studio"
        self.vkong_binary = vkong_binary or os.environ.get("VKONG_BIN") or "vkong"
        self.server_url = server_url or os.environ.get("VKONG_CONNECT_SERVER") or DEFAULT_SERVER_URL
        self._runtime_resolver = runtime_resolver
        self._cli_factory = cli_factory or (
            lambda context: VKongCLI(self.vkong_binary, context=context)
        )
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    # -- readiness --------------------------------------------------------

    def readiness(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ready": False, "cli_installed": False, "logged_in": False,
            "progress_supported": False,
        }
        cli = self._cli_factory(None)
        try:
            version = cli.version()
            result.update(cli_installed=True, cli_version=version.get("version"))
            identity = cli.whoami()
            result.update(logged_in=True, user=identity.user, workspace_id=identity.workspace)
        except BridgeError as exc:
            result["message"] = str(exc) if result["cli_installed"] else (
                "Install the VKong CLI and run `vkong login`."
            )
            if result["cli_installed"]:
                result["message"] = "Run `vkong login` in a terminal, then try again."
            return result
        try:
            runtime = self._runtime_resolver()
            result["runtime"] = {
                "kind": "development", "base_image": runtime.base_image,
                "unsloth_fork_commit": runtime.unsloth_fork_commit,
                "connect_commit": runtime.connect_commit,
            }
        except ConfigurationError as exc:
            result["message"] = str(exc)
            return result
        result["ready"] = True
        return result

    # -- jobs -------------------------------------------------------------

    def start(
        self, payload: Mapping[str, Any], *, output_repo_id: str,
        compute: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(output_repo_id, str) or not _REPO_ID_RE.fullmatch(output_repo_id):
            raise ConfigurationError("output repository must look like username/repo-name")
        worker, local_train, local_eval = portable_worker_config(payload)
        choice = ComputeChoice.from_mapping(compute)
        runtime = self._runtime_resolver()
        identity = self._cli_factory(None).whoami()
        job_id = (
            "studio-" + datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
            + "-" + uuid.uuid4().hex[:8]
        )
        request = BundleRequest(
            job_id=job_id,
            worker_config=worker,
            output_repo_id=output_repo_id,
            runner_image=runtime.base_image,
            dev_runtime=runtime,
            compute=ComputeSpec(
                gpu=choice.gpu, num_gpus=choice.num_gpus, max_dph=choice.max_dph,
                disk_gb=choice.disk_gb,
            ),
            local_datasets=local_train,
            local_eval_datasets=local_eval,
            secret_bundles=("huggingface",) + (("wandb",) if worker.get("enable_wandb") else ()),
        )
        record = {
            "job_id": job_id, "state": "preparing", "message": "Preparing the job",
            "created_at": _now(), "updated_at": _now(),
            "model_name": worker.get("model_name"), "output_repo_id": output_repo_id,
            "output_url": f"https://huggingface.co/{output_repo_id}",
            "compute": choice.__dict__, "server_url": self.server_url,
            "workspace_id": identity.workspace, "app_name": None, "app_id": None,
            "run_id": None, "stop_requested": False,
        }
        self._save(record)
        thread = threading.Thread(
            target=self._submit, args=(job_id, request), name=f"vkong-{job_id}", daemon=True
        )
        with self._lock:
            self._threads[job_id] = thread
        thread.start()
        return record

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs_dir = self.state_dir / "jobs"
        if not jobs_dir.is_dir():
            return []
        records = [self._load(path.stem) for path in jobs_dir.glob("studio-*.json")]
        return sorted(records, key=lambda item: item["created_at"], reverse=True)

    def get_job(self, job_id: str, *, refresh: bool = True) -> dict[str, Any]:
        record = self._load(job_id)
        if refresh and record["state"] not in TERMINAL_STATES:
            record = self._refresh(record)
        return record

    def stop_job(self, job_id: str) -> dict[str, Any]:
        record = self._update(job_id, stop_requested=True)
        if record["state"] in TERMINAL_STATES:
            return record
        if record["app_id"]:
            record = self._update(job_id, state="stopping", message="Stopping the GPU")
            threading.Thread(target=self._stop, args=(job_id,), daemon=True).start()
        else:
            record = self._update(job_id, message="Stop requested; waiting for VKong to start the App")
        return record

    # -- internals --------------------------------------------------------

    def _cli_for(self, record: Mapping[str, Any]) -> VKongCLI:
        return self._cli_factory(CLIContext(record["server_url"], record["workspace_id"]))

    def _submit(self, job_id: str, request: BundleRequest) -> None:
        try:
            record = self._load(job_id)
            bridge = VKongBridge(self._cli_for(record))
            bundle = bridge.prepare(request, self.state_dir / "bundles")
            self._update(
                job_id, state="starting", app_name=bundle.app_name,
                message="Renting a GPU and starting the job (first start pulls a large image)",
            )
            submission = bridge.submit(bundle, idempotency_key=job_id)
            record = self._update(
                job_id, state="running", app_id=submission.run.app_id,
                run_id=submission.run.run_id, message="Training on VKong",
            )
            if record["stop_requested"]:
                self._update(job_id, state="stopping", message="Stopping the GPU")
                self._stop(job_id)
        except BridgeError as exc:
            self._update(job_id, state="failed", message=str(exc)[:500])
        except Exception as exc:  # never lose a record to an unexpected error
            self._update(job_id, state="failed", message=f"Unexpected error: {type(exc).__name__}")
        finally:
            with self._lock:
                self._threads.pop(job_id, None)

    def _stop(self, job_id: str) -> None:
        record = self._load(job_id)
        try:
            status = VKongBridge(self._cli_for(record)).cancel(record["app_id"])
            if status.state == "stopped":
                self._update(job_id, state="stopped", message="Stopped; the GPU was released")
        except BridgeError as exc:
            self._update(job_id, message=f"Stop failed: {str(exc)[:300]}")

    def _refresh(self, record: dict[str, Any]) -> dict[str, Any]:
        job_id = record["job_id"]
        with self._lock:
            alive = job_id in self._threads
        if not record["app_id"]:
            if alive:
                return record
            # Studio restarted while starting: the App name is the job's identity.
            if record.get("app_name"):
                cli = self._cli_for(record)
                try:
                    named = cli._apps_named(record["app_name"])
                except BridgeError:
                    return record
                if len(named) == 1:
                    return self._update(
                        job_id, state="running", app_id=named[0]["id"],
                        message="Reconnected to the VKong App",
                    )
            return self._update(
                job_id, state="failed",
                message="Studio stopped before VKong confirmed the start",
            )
        if record["state"] == "stopping":
            return record
        cli = self._cli_for(record)
        try:
            status = cli.app_show(record["app_id"])
            runs = cli.runs(record["app_id"])
        except BridgeError as exc:
            return self._update(job_id, message=f"Could not refresh status: {str(exc)[:200]}")
        runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        run = runs[0] if runs else {}
        run_status = str(run.get("status") or "")
        reason = str(run.get("reason") or "")
        updates: dict[str, Any] = {"run_id": run.get("id") or record["run_id"], "gpu": run.get("gpu")}
        if run_status == "failed":
            updates.update(state="failed", message=reason or "The job failed on VKong")
        elif status.state == "stopped":
            if record["stop_requested"]:
                updates.update(state="stopped", message="Stopped; the GPU was released")
            else:
                updates.update(
                    state="finished",
                    message="Finished and the GPU was released; check the output repository",
                )
        else:
            updates.update(state="running", message="Training on VKong")
        return self._update(job_id, **updates)

    def _path(self, job_id: str) -> Path:
        if not _JOB_ID_RE.fullmatch(job_id):
            raise ConfigurationError("unknown job")
        return self.state_dir / "jobs" / f"{job_id}.json"

    def _load(self, job_id: str) -> dict[str, Any]:
        path = self._path(job_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigurationError("unknown job") from exc

    def _save(self, record: Mapping[str, Any]) -> None:
        path = self._path(record["job_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)

    def _update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            record = self._load(job_id)
            record.update(changes, updated_at=_now())
            self._save(record)
            return record
