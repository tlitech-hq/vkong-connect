from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from vkong_connect.security import redact_secrets


class SecurityTests(unittest.TestCase):
    def test_known_environment_secrets_are_redacted(self) -> None:
        with patch.dict(os.environ, {"HF_TOKEN": "hf_very_secret"}, clear=False):
            self.assertEqual(
                redact_secrets("request failed for hf_very_secret"),
                "request failed for [REDACTED]",
            )

    def test_tiny_values_are_not_used_as_redaction_needles(self) -> None:
        with patch.dict(os.environ, {"HF_TOKEN": "abc"}, clear=False):
            self.assertEqual(redact_secrets("abc is ordinary text"), "abc is ordinary text")


if __name__ == "__main__":
    unittest.main()
