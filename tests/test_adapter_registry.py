from __future__ import annotations

import unittest

from vkong_connect.adapters.registry import get_adapter
from vkong_connect.errors import ContractError


class AdapterRegistryTests(unittest.TestCase):
    def test_resolves_unsloth_by_versioned_identity(self) -> None:
        adapter = get_adapter("unsloth", "unsloth.v1")
        self.assertEqual(adapter.descriptor.name, "unsloth")
        self.assertFalse(adapter.descriptor.resumable)

    def test_unknown_adapter_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContractError, "does not support adapter"):
            get_adapter("vllm", "vllm.v1")


if __name__ == "__main__":
    unittest.main()
