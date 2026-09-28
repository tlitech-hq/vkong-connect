"""Product-neutral boundary for preparing a VKong task on the caller's machine."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import stat
from typing import Protocol

from vkong_connect.errors import ConfigurationError


@dataclass(frozen=True)
class CompiledBundle:
    path: Path
    app_name: str
    job_path: Path
    config_path: Path
    sha256: str


class BundleSource(Protocol):
    """Trusted adapter request; never loaded dynamically from a job document."""

    @property
    def job_id(self) -> str: ...

    def compile(self, destination: Path) -> CompiledBundle: ...


def tree_digest(root: Path) -> str:
    """Hash only an isolated regular-file tree; never follow staged symlinks."""
    if root.is_symlink() or not root.is_dir():
        raise ConfigurationError("bundle destination is not a regular directory")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ConfigurationError("bundle contains a symlink or special file")
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()
