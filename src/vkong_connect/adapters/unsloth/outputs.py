"""Output publishers for the Unsloth adapter."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

from vkong_connect.contracts.adapters import PublishedArtifact
from vkong_connect.errors import OutputPublicationError

from .schema import OutputSpec


class OutputPublisher(Protocol):
    def publish(self, output_dir: Path, output: OutputSpec) -> PublishedArtifact: ...


class HuggingFaceOutputPublisher:
    """Publish a complete training output directory to one HF model repository."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("HF_TOKEN")

    def publish(self, output_dir: Path, output: OutputSpec) -> PublishedArtifact:
        if not self.token:
            raise OutputPublicationError(
                "HF_TOKEN is required to publish the training output; configure a VKong secret"
            )
        if not output_dir.is_dir():
            raise OutputPublicationError(f"training output directory does not exist: {output_dir}")
        if not output.private:
            raise OutputPublicationError("remote output must be published privately")
        try:
            from huggingface_hub import HfApi

            api = HfApi(token=self.token)
            api.create_repo(
                repo_id=output.repo_id,
                repo_type="model",
                private=output.private,
                exist_ok=True,
            )
            existing = api.repo_info(repo_id=output.repo_id, repo_type="model")
            if existing.private is not True:
                raise OutputPublicationError(
                    "output repository is public; choose a private Hugging Face repository"
                )
            commit = api.upload_folder(
                repo_id=output.repo_id,
                repo_type="model",
                folder_path=str(output_dir),
                commit_message="Publish VKong training output",
            )
            revision = getattr(commit, "oid", None)
            if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
                raise OutputPublicationError("Hugging Face did not return an immutable commit ID")
            published = api.repo_info(
                repo_id=output.repo_id, repo_type="model", revision=revision
            )
            if published.private is not True or published.sha != revision:
                raise OutputPublicationError(
                    "published output revision could not be verified as private and immutable"
                )
        except OutputPublicationError:
            raise
        except Exception as exc:
            raise OutputPublicationError(
                f"failed to publish training output to {output.repo_id}"
            ) from exc
        uri = f"hf://{output.repo_id}"
        uri += f"@{revision}"
        size = sum(path.stat().st_size for path in output_dir.rglob("*") if path.is_file())
        return PublishedArtifact(
            name="model",
            kind="lora-adapter",
            uri=uri,
            revision=revision,
            size_bytes=size,
        )
