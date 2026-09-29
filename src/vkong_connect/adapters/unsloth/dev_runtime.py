"""Development runtime: a public Unsloth image plus pinned fork/connect sources.

Until a runner image is published and promoted (see docs/runtime), a job can run on
the official ``unsloth/unsloth`` image pinned by digest. VKong's one-time ``init_cmd``
downloads vkong-connect and the fork's Studio backend at exact commits from GitHub
archives (no git, no source sync from the laptop). This is a development path: it is
slower to start, depends on GitHub availability, and is never a catalog entry.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from vkong_connect.errors import ConfigurationError

_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}")

DEV_ROOT = "/opt/vkong-connect-dev"
DEV_PYTHON = f"{DEV_ROOT}/bin/python"
# Official ``unsloth/unsloth:studio`` multi-arch index, resolved 2026-09-29.
DEFAULT_BASE_IMAGE = (
    "unsloth/unsloth@sha256:97d13e286ee3e84bf3a5866a7485a4955444c4df2a6009872099963552cdbe6b"
)


@dataclass(frozen=True)
class DevRuntime:
    base_image: str
    unsloth_fork_commit: str
    connect_commit: str
    fork_repo: str = "tlitech-hq/unsloth-vkong"
    connect_repo: str = "tlitech-hq/vkong-connect"

    def validate(self) -> None:
        if _IMAGE_RE.fullmatch(self.base_image) is None:
            raise ConfigurationError("dev runtime base_image must be pinned by sha256 digest")
        for name in ("unsloth_fork_commit", "connect_commit"):
            if _COMMIT_RE.fullmatch(getattr(self, name)) is None:
                raise ConfigurationError(f"dev runtime {name} must be a full 40-hex commit")
        for name in ("fork_repo", "connect_repo"):
            if _REPO_RE.fullmatch(getattr(self, name)) is None:
                raise ConfigurationError(f"dev runtime {name} must be owner/name")

    @property
    def studio_backend(self) -> str:
        return f"{DEV_ROOT}/unsloth-vkong-{self.unsloth_fork_commit}/studio/backend"

    def init_script(self) -> str:
        self.validate()
        connect_url = f"https://github.com/{self.connect_repo}/archive/{self.connect_commit}.tar.gz"
        fork_url = f"https://github.com/{self.fork_repo}/archive/{self.unsloth_fork_commit}.tar.gz"
        # The image carries several virtualenvs; pick the one that can run the Studio
        # worker (checked with find_spec, without importing torch) and pin it.
        return f"""set -eu
mkdir -p {DEV_ROOT}/bin
PY_FOUND=""
for candidate in /opt/*/bin/python3 /opt/*/.venv/bin/python3 /opt/*/*/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  [ -x "$candidate" ] || continue
  if "$candidate" -c "import importlib.util as u, sys; sys.exit(0 if all(u.find_spec(m) for m in ('unsloth', 'trl', 'structlog')) else 1)" 2>/dev/null; then
    PY_FOUND="$candidate"; break
  fi
done
[ -n "$PY_FOUND" ] || {{ echo "no Python with unsloth, trl and structlog in the base image" >&2; exit 1; }}
printf '#!/bin/sh\nexec %s "$@"\n' "$PY_FOUND" > {DEV_PYTHON}
chmod 755 {DEV_PYTHON}
{DEV_PYTHON} -m pip install --no-deps --no-cache-dir "{connect_url}"
{DEV_PYTHON} - <<'PY'
import io, pathlib, tarfile, urllib.request
root = pathlib.Path("{DEV_ROOT}")
root.mkdir(parents=True, exist_ok=True)
prefix = "{self.fork_repo.split('/')[1]}-{self.unsloth_fork_commit}/studio/backend/"
with urllib.request.urlopen("{fork_url}", timeout=600) as response:
    archive = tarfile.open(fileobj=io.BytesIO(response.read()), mode="r:gz")
members = [m for m in archive.getmembers() if m.name.startswith(prefix) and (m.isfile() or m.isdir())]
if not members:
    raise SystemExit("fork archive has no studio/backend")
target = root / "unsloth-vkong-{self.unsloth_fork_commit}"
for member in members:
    member.name = "studio/backend/" + member.name[len(prefix):]
archive.extractall(target, members=members, **({{"filter": "data"}} if hasattr(tarfile, "data_filter") else {{}}))
PY
test -f "{self.studio_backend}/core/training/worker.py"
"""


def _installed_commit(distribution: str, repo: str) -> str | None:
    """Commit recorded by pip for a ``git+https://github.com/<repo>`` install."""
    from importlib import metadata
    import json

    try:
        raw = metadata.distribution(distribution).read_text("direct_url.json")
    except metadata.PackageNotFoundError:
        return None
    if not raw:
        return None
    try:
        info = json.loads(raw)
    except ValueError:
        return None
    url = str(info.get("url", "")).removesuffix(".git").rstrip("/")
    if (info.get("dir_info") or {}).get("editable") and url.startswith("file://"):
        # ``install.sh --local`` installs the checkout in editable mode; use its HEAD.
        # Uncommitted or unpushed work does not reach the GPU host.
        return _checkout_commit(url[len("file://"):], repo)
    commit = (info.get("vcs_info") or {}).get("commit_id")
    if not url.endswith("github.com/" + repo) or not isinstance(commit, str):
        return None
    return commit if _COMMIT_RE.fullmatch(commit) else None


def _checkout_commit(path: str, repo: str) -> str | None:
    import subprocess
    from urllib.parse import unquote

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", unquote(path), *args], capture_output=True, text=True,
            timeout=10, check=True,
        ).stdout.strip()

    try:
        remotes = git("remote", "-v")
        commit = git("rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return None
    if repo not in remotes:
        return None
    return commit if _COMMIT_RE.fullmatch(commit) else None


def resolve_dev_runtime(environ: "dict[str, str] | None" = None) -> DevRuntime:
    """Build the dev runtime for the code installed on this machine.

    Commits come from ``VKONG_CONNECT_DEV_FORK_COMMIT`` / ``VKONG_CONNECT_DEV_CONNECT_COMMIT``
    or, for Git installs, pip's ``direct_url.json``. The base image comes from
    ``VKONG_CONNECT_DEV_BASE_IMAGE`` or :data:`DEFAULT_BASE_IMAGE`.
    """
    import os

    env = os.environ if environ is None else environ
    runtime = DevRuntime(
        base_image=env.get("VKONG_CONNECT_DEV_BASE_IMAGE") or DEFAULT_BASE_IMAGE,
        unsloth_fork_commit=(
            env.get("VKONG_CONNECT_DEV_FORK_COMMIT")
            or _installed_commit("unsloth", "tlitech-hq/unsloth-vkong") or ""
        ),
        connect_commit=(
            env.get("VKONG_CONNECT_DEV_CONNECT_COMMIT")
            or _installed_commit("vkong-connect", "tlitech-hq/vkong-connect") or ""
        ),
    )
    try:
        runtime.validate()
    except ConfigurationError as exc:
        raise ConfigurationError(
            "cannot determine the remote runtime: install unsloth-vkong and vkong-connect "
            "from GitHub, or set VKONG_CONNECT_DEV_FORK_COMMIT and "
            "VKONG_CONNECT_DEV_CONNECT_COMMIT to pushed commits"
        ) from exc
    return runtime
