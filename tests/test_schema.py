from __future__ import annotations

import copy
import unittest

from vkong_connect.adapters.unsloth.schema import validate_job
from vkong_connect.errors import ConfigurationError


def valid_document() -> dict:
    return {
        "schema_version": "vkong.connect.job.v1",
        "job_id": "job-123",
        "adapter": {"name": "unsloth", "schema_version": "unsloth.v1"},
        "spec": {
            "worker_config": {
                "model_name": "unsloth/tiny-model",
                "hf_dataset": "org/data",
                "local_datasets": [],
            },
            "output": {
                "kind": "huggingface",
                "repo_id": "user/output-model",
                "private": True,
            },
        },
    }


class UnslothSchemaTests(unittest.TestCase):
    def test_valid_job_round_trips(self) -> None:
        job = validate_job(valid_document())
        self.assertEqual(job.job_id, "job-123")
        self.assertEqual(job.output.repo_id, "user/output-model")
        self.assertEqual(job.as_dict(), valid_document())

    def test_secret_value_is_rejected(self) -> None:
        document = valid_document()
        document["spec"]["worker_config"]["hf_token"] = "hf_secret"
        with self.assertRaisesRegex(ConfigurationError, "secret fields"):
            validate_job(document)

    def test_nested_custom_secret_like_value_is_rejected(self) -> None:
        document = valid_document()
        document["spec"]["worker_config"]["tracker"] = {
            "custom_api_key": "do-not-sync"
        }
        with self.assertRaisesRegex(ConfigurationError, "tracker.custom_api_key"):
            validate_job(document)

    def test_empty_legacy_secret_field_is_allowed(self) -> None:
        document = valid_document()
        document["spec"]["worker_config"]["hf_token"] = ""
        validate_job(document)

    def test_absolute_local_dataset_is_rejected(self) -> None:
        document = copy.deepcopy(valid_document())
        document["spec"]["worker_config"]["local_datasets"] = ["/tmp/data.jsonl"]
        with self.assertRaisesRegex(ConfigurationError, "inside the bundle"):
            validate_job(document)

    def test_local_model_is_rejected(self) -> None:
        document = copy.deepcopy(valid_document())
        document["spec"]["worker_config"]["model_name"] = "../model"
        with self.assertRaisesRegex(ConfigurationError, "hosted model"):
            validate_job(document)

    def test_local_snapshot_and_absolute_output_are_rejected(self) -> None:
        document = copy.deepcopy(valid_document())
        document["spec"]["worker_config"]["model_snapshot_path"] = "/cache/model"
        with self.assertRaisesRegex(ConfigurationError, "model_snapshot_path"):
            validate_job(document)

        document = copy.deepcopy(valid_document())
        document["spec"]["worker_config"]["output_dir"] = "/etc"
        with self.assertRaisesRegex(ConfigurationError, "remote workspace"):
            validate_job(document)

    def test_resume_is_rejected_until_materialization_exists(self) -> None:
        document = copy.deepcopy(valid_document())
        document["spec"]["worker_config"]["resume_from_checkpoint"] = "hf://user/checkpoint"
        with self.assertRaisesRegex(ConfigurationError, "resume is unavailable"):
            validate_job(document)


if __name__ == "__main__":
    unittest.main()
