"""Typed wrapper for VKong's machine-readable CLI.

Two response profiles are accepted and normalized into the same typed results:

* ``vkong.cli.v1``: the versioned contract this project proposes (fake CLI in tests).
* ``vkong.cli.envelope``: the ``{ok, data, code, error}`` envelope that released CLIs
  print for their JSON-enabled commands today. ``run`` has no JSON output or caller
  idempotency key there, and there is no machine-readable log stream, so start is
  guarded by the job-unique App name and log following is unavailable.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import urlsplit

from vkong_connect.errors import (
    CapabilityUnavailableError,
    ContractError,
    VKongCLIError,
    VKongNotInstalledError,
)

ENVELOPE_SCHEMA = "vkong.cli.envelope"


@dataclass(frozen=True)
class WorkspaceIdentity:
    user: str
    workspace: str
    schema_version: str


@dataclass(frozen=True)
class RunStart:
    app_id: str
    app_name: str
    run_id: str
    instance_id: str | None
    state: str
    hourly_price: float | None
    currency: str | None
    schema_version: str
    reconciled: bool = False


@dataclass(frozen=True)
class AppStatus:
    app_id: str
    app_name: str
    state: str
    run_id: str | None
    instance_id: str | None
    schema_version: str


@dataclass(frozen=True)
class CLIContext:
    """Immutable server/workspace selection for one logical submission."""

    server_url: str
    workspace_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.server_url, str):
            raise ContractError("CLI context requires an HTTPS server origin")
        try:
            parsed = urlsplit(self.server_url)
            port = parsed.port
        except ValueError as exc:
            raise ContractError("CLI context requires a valid HTTPS server origin") from exc
        if (
            parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")
            or port == 0
        ):
            raise ContractError("CLI context requires an HTTPS server origin")
        if not isinstance(self.workspace_id, str) or not re.fullmatch(
            r"ws_[A-Za-z0-9_-]{1,125}", self.workspace_id
        ):
            raise ContractError("CLI context requires an immutable ws_ workspace ID")


class VKongCLI:
    """Invoke VKong without a shell and accept JSON only."""

    def __init__(
        self,
        binary: str = "vkong",
        *,
        timeout: float = 60.0,
        start_timeout: float = 3600.0,
        env: Mapping[str, str] | None = None,
        context: CLIContext | None = None,
    ) -> None:
        self.binary = binary
        self.timeout = timeout
        self.start_timeout = start_timeout
        self.context = context
        self.env = dict(env) if env is not None else dict(os.environ)
        if context is not None:
            self.env["SERVER_PUBLIC_URL"] = context.server_url
            self.env["VKONG_WORKSPACE"] = context.workspace_id

    def _require_context(self) -> CLIContext:
        if self.context is None:
            raise ContractError("VKong command requires bound server and workspace IDs")
        return self.context

    def _argv(self, args: Sequence[str]) -> list[str]:
        argv = [self.ensure_installed()]
        if self.context is not None:
            argv.extend(["--workspace", self.context.workspace_id])
        return [*argv, *args]

    def ensure_installed(self) -> str:
        if os.path.sep in self.binary or (os.path.altsep and os.path.altsep in self.binary):
            candidate = Path(self.binary)
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        else:
            found = shutil.which(self.binary, path=(self.env or os.environ).get("PATH"))
            if found:
                return found
        raise VKongNotInstalledError(
            "VKong CLI was not found. Install it from https://vkong.tli-tech.com/download"
        )

    def version(self) -> dict[str, Any]:
        return self._run_json(["version", "--json"])

    def whoami(self) -> WorkspaceIdentity:
        value = self._run_json(["whoami", "--json"])
        if self._schema(value) == ENVELOPE_SCHEMA:
            identity = WorkspaceIdentity(
                user=self._required_string(value, "login"),
                workspace=self._required_string(value, "workspace_id"),
                schema_version=ENVELOPE_SCHEMA,
            )
            if self.context is not None and identity.workspace != self.context.workspace_id:
                raise ContractError(
                    "VKong CLI resolved a different workspace than the bound context"
                )
            return identity
        return WorkspaceIdentity(
            user=self._required_string(value, "user"),
            workspace=self._required_string(value, "workspace"),
            schema_version=self._schema(value),
        )

    def validate(self, project_dir: Path) -> dict[str, Any]:
        value = self._run_json(["validate", "-C", str(project_dir), "--json"])
        if self._schema(value) == ENVELOPE_SCHEMA:
            # A successful envelope means the project loaded and its init scan passed.
            return {**value, "valid": value.get("scan") in ("clean", "allowed")}
        return value

    def start_task(
        self, project_dir: Path, *, idempotency_key: str, app_name: str | None = None
    ) -> RunStart:
        self._require_context()
        if not idempotency_key:
            raise ContractError("idempotency_key must not be empty")
        if self._profile() == ENVELOPE_SCHEMA:
            if not app_name:
                raise ContractError("starting with the current VKong CLI requires the job App name")
            return self._start_task_envelope(project_dir, app_name)
        value = self._run_json(
            [
                "run",
                "-C",
                str(project_dir),
                "--detach",
                "--auto-stop",
                "--idempotency-key",
                idempotency_key,
                "--json",
            ],
            timeout=max(self.timeout, self.start_timeout),
        )
        price = value.get("hourly_price")
        if price is not None:
            try:
                price = float(price)
            except (TypeError, ValueError) as exc:
                raise ContractError("VKong hourly_price must be numeric or null") from exc
            if price < 0 or not math.isfinite(price):
                raise ContractError("VKong hourly_price must be finite and non-negative")
        return RunStart(
            app_id=self._required_string(value, "app_id"),
            app_name=self._required_string(value, "app_name"),
            run_id=self._required_string(value, "run_id"),
            instance_id=self._optional_string(value, "instance_id"),
            state=self._required_string(value, "state"),
            hourly_price=price,
            currency=self._optional_string(value, "currency"),
            schema_version=self._schema(value),
        )

    def _profile(self) -> str:
        profile = getattr(self, "_detected_profile", None)
        if profile is None:
            profile = self._schema(self.version())
            self._detected_profile = profile
        return profile

    def _start_task_envelope(self, project_dir: Path, app_name: str) -> RunStart:
        """Start once per job-unique App name; never parse the CLI's human output.

        VKong records the App and Run before renting, so an App with this name means
        an earlier attempt already reached VKong: reconcile it instead of renting again.
        """
        existing = self._apps_named(app_name)
        if not existing:
            argv = self._argv(["run", "-C", str(project_dir), "--detach", "--auto-stop"])
            timeout = max(self.timeout, self.start_timeout)
            try:
                result = subprocess.run(
                    argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                    env=self.env, timeout=timeout, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise VKongCLIError(
                    "VKong run did not finish starting in time; reconcile before retrying",
                    exit_code=124, retriable=True, details={"app_name": app_name},
                ) from exc
            existing = self._apps_named(app_name)
            if result.returncode != 0:
                raise VKongCLIError(
                    "VKong run failed",
                    exit_code=result.returncode,
                    stderr=(result.stderr + result.stdout)[-4096:],
                    details={"app_name": app_name, "app_ids": [app["id"] for app in existing]},
                )
            if not existing:
                raise ContractError(f"VKong run succeeded but App {app_name!r} was not found")
            reconciled = False
        else:
            reconciled = True
        if len(existing) != 1:
            raise ContractError(
                f"{len(existing)} VKong Apps are named {app_name!r}; refusing to guess"
            )
        status = self.app_show(existing[0]["id"])
        run_id = status.run_id or self._latest_run_id(status.app_id)
        if run_id is None:
            raise ContractError(f"VKong App {status.app_id} has no Run")
        return RunStart(
            app_id=status.app_id, app_name=status.app_name, run_id=run_id,
            instance_id=status.instance_id, state=status.state, hourly_price=None,
            currency=None, schema_version=ENVELOPE_SCHEMA, reconciled=reconciled,
        )

    def _apps_named(self, app_name: str) -> list[dict[str, Any]]:
        value = self._run_json(["app", "list", "--json"])
        apps = value.get("apps")
        if not isinstance(apps, list) or not all(isinstance(item, dict) for item in apps):
            raise ContractError("VKong app list response must contain an array of objects")
        named = [app for app in apps if app.get("name") == app_name]
        for app in named:
            self._required_string(app, "id")
        return named

    def _latest_run_id(self, app_id: str) -> str | None:
        runs = self.runs(app_id)
        runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return self._optional_string(runs[0], "id") if runs else None

    def _envelope_app_status(self, value: Mapping[str, Any]) -> AppStatus:
        app = value.get("app")
        if not isinstance(app, dict):
            raise ContractError("VKong app response requires an app object")
        run = value.get("active_run")
        if run is not None and not isinstance(run, dict):
            raise ContractError("VKong active_run must be an object or null")
        instance = (run or {}).get("instance_id") or app.get("active_instance_id") or None
        return AppStatus(
            app_id=self._required_string(app, "id"),
            app_name=self._required_string(app, "name"),
            state=self._required_string(app, "status"),
            run_id=self._optional_string(run, "id") if run else None,
            instance_id=instance if isinstance(instance, str) else None,
            schema_version=ENVELOPE_SCHEMA,
        )

    def app_show(self, app: str) -> AppStatus:
        self._require_context()
        value = self._run_json(["app", "show", app, "--json"])
        if self._schema(value) == ENVELOPE_SCHEMA:
            return self._envelope_app_status(value)
        return AppStatus(
            app_id=self._required_string(value, "app_id"),
            app_name=self._required_string(value, "app_name"),
            state=self._required_string(value, "state"),
            run_id=self._optional_string(value, "run_id"),
            instance_id=self._optional_string(value, "instance_id"),
            schema_version=self._schema(value),
        )

    def runs(self, app: str) -> list[dict[str, Any]]:
        self._require_context()
        if self._profile() == ENVELOPE_SCHEMA:
            if not app.startswith("app_"):
                raise ContractError("listing Runs with the current VKong CLI requires an App ID")
            value = self._run_json(["runs", "--json"])
            runs = value.get("runs")
            if not isinstance(runs, list) or not all(isinstance(item, dict) for item in runs):
                raise ContractError("VKong runs response must contain an array of objects")
            return [item for item in runs if item.get("app_id") == app]
        value = self._run_json(["runs", "--app", app, "--json"])
        runs = value.get("runs")
        if not isinstance(runs, list) or not all(isinstance(item, dict) for item in runs):
            raise ContractError("VKong runs response must contain an array of objects")
        self._schema(value)
        return runs

    def stop_app(self, app: str) -> AppStatus:
        self._require_context()
        value = self._run_json(["app", "stop", app, "--yes", "--json"])
        if self._schema(value) == ENVELOPE_SCHEMA:
            return self._envelope_app_status(value)
        return AppStatus(
            app_id=self._required_string(value, "app_id"),
            app_name=self._required_string(value, "app_name"),
            state=self._required_string(value, "state"),
            run_id=self._optional_string(value, "run_id"),
            instance_id=self._optional_string(value, "instance_id"),
            schema_version=self._schema(value),
        )

    def follow_logs(self, run_id: str, *, after: int | None = None) -> Iterator[dict[str, Any]]:
        self._require_context()
        if self._profile() == ENVELOPE_SCHEMA:
            raise CapabilityUnavailableError(
                "the installed VKong CLI has no machine-readable Run log stream; "
                "training progress is unavailable until it does"
            )
        argv = self._argv(["logs", run_id, "--follow", "--format", "jsonl"])
        if after is not None:
            argv.extend(["--after", str(after)])
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=self.env,
        )
        assert process.stdout is not None
        assert process.stderr is not None
        diagnostics: list[str] = []

        def collect_stderr() -> None:
            # Drain concurrently so a chatty CLI cannot block its own stdout.
            for line in process.stderr:
                diagnostics.append(line)
                if len(diagnostics) > 80:
                    diagnostics.pop(0)

        stderr_thread = threading.Thread(target=collect_stderr, daemon=True)
        stderr_thread.start()
        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    process.terminate()
                    raise ContractError("VKong log stream emitted non-JSON output") from exc
                if not isinstance(value, dict):
                    process.terminate()
                    raise ContractError("VKong log stream item must be an object")
                yield value
            exit_code = process.wait()
            stderr_thread.join(timeout=5)
            if exit_code != 0:
                raise VKongCLIError(
                    "VKong log stream failed",
                    exit_code=exit_code,
                    stderr="".join(diagnostics)[-4096:],
                )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if process.stdout is not None:
                process.stdout.close()
            process.stderr.close()
            stderr_thread.join(timeout=5)

    def _run_json(self, args: Sequence[str], *, timeout: float | None = None) -> dict[str, Any]:
        argv = self._argv(args)
        try:
            result = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=self.env,
                timeout=timeout or self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise VKongCLIError(
                "VKong CLI command timed out",
                exit_code=124,
                retriable=True,
            ) from exc
        value = self._decode_object(result.stdout, stream="stdout")
        if type(value.get("ok")) is bool and "schema_version" not in value:
            return self._unwrap_envelope(value, result)
        if result.returncode != 0:
            error = value.get("error") if isinstance(value.get("error"), dict) else value
            raise VKongCLIError(
                str(error.get("message") or "VKong CLI command failed"),
                exit_code=result.returncode,
                stderr=result.stderr[-4096:],
                cli_code=self._optional_string(error, "code"),
                retriable=bool(error.get("retriable", False)),
                details=value,
            )
        self._schema(value)
        return value

    def _unwrap_envelope(self, value: Mapping[str, Any], result: Any) -> dict[str, Any]:
        if value["ok"] is not True or result.returncode != 0:
            code = value.get("code")
            message = value.get("error")
            raise VKongCLIError(
                message if isinstance(message, str) and message else "VKong CLI command failed",
                exit_code=result.returncode or 1,
                stderr=result.stderr[-4096:],
                cli_code=code if isinstance(code, str) else None,
                details=dict(value),
            )
        data = value.get("data", {})
        if not isinstance(data, dict):
            raise ContractError("VKong CLI envelope data must be a JSON object")
        return {**data, "schema_version": ENVELOPE_SCHEMA}

    @staticmethod
    def _decode_object(raw: str, *, stream: str) -> dict[str, Any]:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractError(f"VKong CLI {stream} was not one JSON object") from exc
        if not isinstance(value, dict):
            raise ContractError(f"VKong CLI {stream} must be a JSON object")
        return value

    @staticmethod
    def _schema(value: Mapping[str, Any]) -> str:
        schema = value.get("schema_version")
        if schema == ENVELOPE_SCHEMA:
            return schema
        if not isinstance(schema, str) or not schema.startswith("vkong.cli.v1"):
            raise ContractError(f"unsupported VKong CLI schema: {schema!r}")
        return schema

    @staticmethod
    def _required_string(value: Mapping[str, Any], key: str) -> str:
        result = value.get(key)
        if not isinstance(result, str) or not result:
            raise ContractError(f"VKong CLI response requires non-empty {key!r}")
        return result

    @staticmethod
    def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
        result = value.get(key)
        if result is None:
            return None
        if not isinstance(result, str):
            raise ContractError(f"VKong CLI response field {key!r} must be a string or null")
        return result
