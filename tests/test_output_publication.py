from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from vkong_connect.adapters.unsloth.outputs import HuggingFaceOutputPublisher
from vkong_connect.adapters.unsloth.schema import OutputSpec, validate_job
from vkong_connect.errors import ConfigurationError, OutputPublicationError

OID = "a" * 40


class FakeHFAPI:
    private = True
    upload_oid = OID
    published_sha = OID
    uploads = 0

    def __init__(self, token):
        assert token == "test-token-abc"

    def create_repo(self, **kwargs):
        assert kwargs["private"] is True

    def repo_info(self, **kwargs):
        if "revision" in kwargs:
            return types.SimpleNamespace(private=self.private, sha=self.published_sha)
        return types.SimpleNamespace(private=self.private)

    def upload_folder(self, **kwargs):
        type(self).uploads += 1
        return types.SimpleNamespace(oid=self.upload_oid)


class OutputPublicationTests(unittest.TestCase):
    def setUp(self):
        FakeHFAPI.private = True
        FakeHFAPI.upload_oid = OID
        FakeHFAPI.published_sha = OID
        FakeHFAPI.uploads = 0

    def _publish(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "adapter.safetensors").write_bytes(b"weights")
            module = types.ModuleType("huggingface_hub")
            module.HfApi = FakeHFAPI
            with patch.dict(sys.modules, {"huggingface_hub": module}):
                return HuggingFaceOutputPublisher("test-token-abc").publish(
                    output, OutputSpec("huggingface", "user/result", True)
                )

    def test_pinned_private_output(self):
        artifact = self._publish()
        self.assertEqual(artifact.uri, "hf://user/result@" + OID)
        self.assertEqual(artifact.revision, OID)
        self.assertEqual(FakeHFAPI.uploads, 1)

    def test_existing_public_repo_is_not_uploaded(self):
        FakeHFAPI.private = False
        with self.assertRaisesRegex(OutputPublicationError, "public"):
            self._publish()
        self.assertEqual(FakeHFAPI.uploads, 0)

    def test_absent_or_unverified_commit_cannot_succeed(self):
        for oid, verified in ((None, OID), ("short", OID), (OID, "b" * 40)):
            with self.subTest(oid=oid, verified=verified):
                FakeHFAPI.upload_oid = oid
                FakeHFAPI.published_sha = verified
                with self.assertRaises(OutputPublicationError):
                    self._publish()

    def test_schema_rejects_public_output_before_training(self):
        document = {
            "schema_version": "vkong.connect.job.v1", "job_id": "job-1",
            "adapter": {"name": "unsloth", "schema_version": "unsloth.v1"},
            "spec": {
                "worker_config": {"model_name": "org/model"},
                "output": {"kind": "huggingface", "repo_id": "user/result", "private": False},
            },
        }
        with self.assertRaisesRegex(ConfigurationError, "private"):
            validate_job(document)
