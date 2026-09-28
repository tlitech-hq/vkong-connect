"""Registry of adapters intentionally baked into the trusted runner image."""

from __future__ import annotations

from vkong_connect.contracts.adapters import RunnerAdapter
from vkong_connect.errors import ContractError

from .unsloth.adapter import UnslothAdapter


_ADAPTERS: tuple[RunnerAdapter, ...] = (UnslothAdapter(),)
_BY_ID = {
    (adapter.descriptor.name, adapter.descriptor.schema_version): adapter
    for adapter in _ADAPTERS
}


def get_adapter(name: str, schema_version: str) -> RunnerAdapter:
    try:
        return _BY_ID[(name, schema_version)]
    except KeyError as exc:
        raise ContractError(
            f"runner image does not support adapter {name!r} schema {schema_version!r}"
        ) from exc
