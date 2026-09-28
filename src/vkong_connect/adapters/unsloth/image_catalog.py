"""Reviewed Studio build to immutable Unsloth runner image mapping."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from vkong_connect.contracts.runtime import RuntimeIdentity
from vkong_connect.errors import ConfigurationError, ContractError

CATALOG_SCHEMA = "vkong.connect.image-catalog.v1"
_BUILD = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_IMAGE = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}")


@dataclass(frozen=True)
class ImageCompatibility:
    studio_builds: tuple[str, ...]
    training_modes: tuple[str, ...]
    runtime: RuntimeIdentity
    image: str
    cli_contract: str

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ImageCompatibility":
        if not isinstance(value, Mapping) or set(value) != {
            "studio_builds", "training_modes", "runtime", "image", "cli_contract"
        }:
            raise ContractError("image compatibility entry has unsupported fields")
        builds = value["studio_builds"]
        modes = value["training_modes"]
        if not isinstance(builds, list) or not builds or any(
            not isinstance(item, str) or not _BUILD.fullmatch(item) for item in builds
        ) or len(builds) != len(set(builds)):
            raise ContractError("image entry requires unique portable Studio build IDs")
        if not isinstance(modes, list) or not modes or any(
            not isinstance(item, str) or not item.strip() for item in modes
        ) or len(modes) != len(set(modes)):
            raise ContractError("image entry requires unique training modes")
        image = value["image"]
        if not isinstance(image, str) or not _IMAGE.fullmatch(image):
            raise ContractError("image entry requires an OCI sha256 digest reference")
        if value["cli_contract"] != "vkong.cli.v1":
            raise ContractError("image entry requires a supported CLI contract")
        runtime = RuntimeIdentity.from_dict(value["runtime"])
        if (
            runtime.adapter_name != "unsloth" or runtime.adapter_schema != "unsloth.v1"
            or runtime.job_schema != "vkong.connect.job.v2"
        ):
            raise ContractError("Unsloth image entry has incompatible adapter/job contracts")
        return cls(
            studio_builds=tuple(builds),
            training_modes=tuple(modes),
            runtime=runtime,
            image=image,
            cli_contract=value["cli_contract"],
        )


@dataclass(frozen=True)
class ImageCatalog:
    entries: tuple[ImageCompatibility, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ImageCatalog":
        if not isinstance(value, Mapping) or set(value) != {"schema_version", "entries"}:
            raise ContractError("image catalog has unsupported fields")
        if value["schema_version"] != CATALOG_SCHEMA:
            raise ContractError("unsupported image catalog schema")
        entries = value["entries"]
        if not isinstance(entries, list):
            raise ContractError("image catalog entries must be an array")
        parsed = tuple(ImageCompatibility.from_dict(item) for item in entries)
        seen: set[tuple[str, str, str]] = set()
        for entry in parsed:
            for build in entry.studio_builds:
                for mode in entry.training_modes:
                    key = (build, mode, entry.runtime.platform)
                    if key in seen:
                        raise ContractError("ambiguous Studio build/mode/platform image mapping")
                    seen.add(key)
        return cls(parsed)

    @classmethod
    def from_path(cls, path: Path) -> "ImageCatalog":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ContractError("cannot read image catalog") from exc
        return cls.from_dict(value)

    @classmethod
    def packaged(cls) -> "ImageCatalog":
        package = resources.files("vkong_connect.adapters.unsloth")
        try:
            value = json.loads(package.joinpath("image-catalog.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ContractError("cannot read packaged image catalog") from exc
        return cls.from_dict(value)

    def resolve(
        self, studio_build_id: str, *, training_mode: str, platform: str = "linux/amd64"
    ) -> ImageCompatibility:
        matches = [
            entry for entry in self.entries
            if studio_build_id in entry.studio_builds
            and training_mode in entry.training_modes
            and platform == entry.runtime.platform
        ]
        if len(matches) != 1:
            raise ConfigurationError(
                "no published compatible Unsloth runner image for this Studio build, "
                "training mode and remote platform"
            )
        return matches[0]
