"""High-level facade joining bundle compilation to VKong App/Run lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Iterator

from vkong_connect.client.vkong_cli import AppStatus, CLIContext, RunStart, VKongCLI, WorkspaceIdentity
from vkong_connect.contracts.bundles import BundleSource, CompiledBundle, tree_digest
from vkong_connect.contracts.events import BridgeEvent, parse_event_line
from vkong_connect.errors import ConfigurationError, ContractError


@dataclass(frozen=True)
class Readiness:
    cli_version: str
    cli_schema: str
    identity: WorkspaceIdentity


@dataclass(frozen=True)
class Submission:
    bundle: CompiledBundle
    run: RunStart


class VKongBridge:
    """Thin coordinator; VKong remains authoritative for lifecycle state."""

    def __init__(self, cli: VKongCLI | None = None) -> None:
        self.cli = cli or VKongCLI()

    def readiness(self) -> Readiness:
        version = self.cli.version()
        cli_version = version.get("version")
        schema = version.get("schema_version")
        if not isinstance(cli_version, str) or not cli_version:
            raise ContractError("VKong version response requires a version")
        if not isinstance(schema, str):
            raise ContractError("VKong version response requires a schema_version")
        return Readiness(
            cli_version=cli_version,
            cli_schema=schema,
            identity=self.cli.whoami(),
        )

    def prepare(self, request: BundleSource, staging_root: Path) -> CompiledBundle:
        # One portable component, never an absolute path or traversal. Do not
        # normalize identity: different caller IDs must not alias one directory.
        if not isinstance(request.job_id, str) or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", request.job_id
        ) is None:
            raise ConfigurationError(
                "job_id must be 1-128 ASCII letters, digits, underscores or hyphens, "
                "starting with a letter or digit"
            )
        destination = staging_root / request.job_id
        if not destination.exists() and not destination.is_symlink():
            return request.compile(destination)
        with tempfile.TemporaryDirectory(prefix=".vkong-retry-") as temporary:
            candidate = request.compile(Path(temporary) / request.job_id)
            if tree_digest(destination) != candidate.sha256:
                raise ConfigurationError(
                    "existing job bundle differs from retry request; refusing to submit"
                )
            return CompiledBundle(
                path=destination,
                app_name=candidate.app_name,
                job_path=destination / candidate.job_path.name,
                config_path=destination / candidate.config_path.name,
                sha256=candidate.sha256,
            )

    def submit(self, bundle: CompiledBundle, *, idempotency_key: str) -> Submission:
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ConfigurationError("submit requires a stable idempotency key")
        self._bind_submission(bundle, idempotency_key)
        validation = self.cli.validate(bundle.path)
        if validation.get("valid") is not True:
            raise ContractError("VKong rejected the generated task bundle")
        run = self.cli.start_task(
            bundle.path, idempotency_key=idempotency_key, app_name=bundle.app_name
        )
        if run.app_name != bundle.app_name:
            raise ContractError(
                f"VKong started unexpected App {run.app_name!r}; expected {bundle.app_name!r}"
            )
        return Submission(bundle=bundle, run=run)

    def _bind_submission(self, bundle: CompiledBundle, idempotency_key: str) -> None:
        """Persist retry identity outside the synced bundle before any CLI side effect."""
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", bundle.path.name) is None:
            raise ConfigurationError("bundle job directory has an invalid name")
        if tree_digest(bundle.path) != bundle.sha256:
            raise ConfigurationError("bundle changed after preparation; refusing to submit")
        context = getattr(self.cli, "context", None)
        if not isinstance(context, CLIContext):
            context = None
        identity = {
            "schema_version": "vkong.connect.submit.v1",
            "bundle_sha256": bundle.sha256,
            "idempotency_key_sha256": hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest(),
            "server_url": getattr(context, "server_url", None),
            "workspace_id": getattr(context, "workspace_id", None),
        }
        payload = (json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        marker = bundle.path.parent / f".{bundle.path.name}.submit.json"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(marker, flags, 0o600)
        except FileExistsError:
            read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(marker, read_flags)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode) or os.read(fd, 4097) != payload:
                    raise ConfigurationError(
                        "job was already submitted with another bundle, context or idempotency key"
                    )
            finally:
                os.close(fd)
            return
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            parent_fd = os.open(
                bundle.path.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except Exception:
            # Keep a possibly partially written marker: fail closed until an
            # operator inspects it, rather than allowing a second rental.
            raise

    def reconcile(self, app_id_or_name: str) -> AppStatus:
        return self.cli.app_show(app_id_or_name)

    def cancel(self, app_id_or_name: str) -> AppStatus:
        return self.cli.stop_app(app_id_or_name)

    def follow_events(
        self,
        run_id: str,
        *,
        after_event_sequence: int = 0,
        expected_job_id: str | None = None,
    ) -> Iterator[BridgeEvent]:
        """Replay the retained log and yield only new, validated bridge events.

        VKong log cursor and bridge event sequence are separate domains. The MVP
        deliberately replays the bounded Run log and deduplicates by event seq.
        """
        latest = after_event_sequence
        for item in self.cli.follow_logs(run_id):
            if item.get("truncated") is True:
                raise ContractError(f"VKong Run log was truncated for {run_id}")
            line = item.get("line")
            if not isinstance(line, str):
                continue
            event = parse_event_line(line)
            if event is None or event.seq <= latest:
                continue
            if expected_job_id is not None and event.job_id != expected_job_id:
                raise ContractError(
                    f"bridge event belongs to a different job than expected for {run_id}"
                )
            if event.seq != latest + 1:
                raise ContractError(
                    f"bridge event sequence gap for {run_id}: expected {latest + 1}, got {event.seq}"
                )
            latest = event.seq
            yield event
