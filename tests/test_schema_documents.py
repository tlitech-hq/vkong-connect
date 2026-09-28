from __future__ import annotations

import json
import unittest
from pathlib import Path

from vkong_connect.adapters.unsloth.schema import ADAPTER_SCHEMA, JOB_SCHEMA
from vkong_connect.contracts.events import EVENT_VERSION, EventType
from vkong_connect.contracts.runtime import RUNTIME_SCHEMA
from vkong_connect.adapters.unsloth.image_catalog import CATALOG_SCHEMA
from vkong_connect.adapters.unsloth.schema import JOB_SCHEMA_V2


ROOT = Path(__file__).resolve().parents[1]


class PublishedSchemaTests(unittest.TestCase):
    def test_published_event_schema_matches_code(self) -> None:
        value = json.loads((ROOT / "schemas" / "bridge-event-v1.schema.json").read_text())
        self.assertEqual(value["properties"]["v"]["const"], EVENT_VERSION)
        self.assertEqual(
            set(value["properties"]["type"]["enum"]),
            {event_type.value for event_type in EventType},
        )

    def test_published_job_schema_matches_code(self) -> None:
        value = json.loads((ROOT / "schemas" / "unsloth-job-v1.schema.json").read_text())
        self.assertEqual(value["properties"]["schema_version"]["const"], JOB_SCHEMA)
        self.assertEqual(
            value["properties"]["adapter"]["properties"]["schema_version"]["const"],
            ADAPTER_SCHEMA,
        )

    def test_runtime_and_catalog_schemas_match_code(self) -> None:
        runtime = json.loads((ROOT / "schemas" / "runtime-identity-v1.schema.json").read_text())
        catalog = json.loads((ROOT / "schemas" / "image-catalog-v1.schema.json").read_text())
        job = json.loads((ROOT / "schemas" / "unsloth-job-v2.schema.json").read_text())
        self.assertEqual(runtime["properties"]["schema_version"]["const"], RUNTIME_SCHEMA)
        self.assertEqual(catalog["properties"]["schema_version"]["const"], CATALOG_SCHEMA)
        self.assertEqual(job["properties"]["schema_version"]["const"], JOB_SCHEMA_V2)


if __name__ == "__main__":
    unittest.main()
