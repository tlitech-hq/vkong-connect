from __future__ import annotations

import unittest
from unittest.mock import Mock

from vkong_connect.errors import ConfigurationError, VKongNotInstalledError

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ImportError:  # vkong-connect itself does not depend on FastAPI
    FastAPI = None


@unittest.skipIf(FastAPI is None, "FastAPI is not installed")
class StudioRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        from vkong_connect.integrations.unsloth_studio import create_router

        self.service = Mock()
        self.calls: list[str] = []

        def auth() -> str:
            self.calls.append("auth")
            return "subject"

        app = FastAPI()
        app.include_router(create_router(auth, self.service), prefix="/api/remote-training")
        self.client = TestClient(app)

    def test_routes_delegate_to_service_behind_auth(self) -> None:
        self.service.readiness.return_value = {"ready": True}
        self.service.start.return_value = {"job_id": "studio-1", "state": "preparing"}
        self.service.list_jobs.return_value = []
        self.service.get_job.return_value = {"job_id": "studio-1", "state": "running"}
        self.service.stop_job.return_value = {"job_id": "studio-1", "state": "stopping"}

        self.assertTrue(self.client.get("/api/remote-training/readiness").json()["ready"])
        started = self.client.post("/api/remote-training/jobs", json={
            "training": {"model_name": "m"}, "output_repo_id": "u/r", "compute": {"gpu": "Any"},
        })
        self.assertEqual(started.status_code, 200)
        self.service.start.assert_called_once_with(
            {"model_name": "m"}, output_repo_id="u/r", compute={"gpu": "Any"}
        )
        self.assertEqual(self.client.get("/api/remote-training/jobs").json(), {"jobs": []})
        self.assertEqual(self.client.get("/api/remote-training/jobs/studio-1").json()["state"], "running")
        self.assertEqual(
            self.client.post("/api/remote-training/jobs/studio-1/stop").json()["state"], "stopping"
        )
        self.assertEqual(len(self.calls), 5)

    def test_errors_map_to_http_status(self) -> None:
        self.assertEqual(self.client.post("/api/remote-training/jobs", json={}).status_code, 400)
        self.service.start.side_effect = ConfigurationError("choose a dataset")
        response = self.client.post("/api/remote-training/jobs", json={"training": {}})
        self.assertEqual((response.status_code, response.json()["detail"]), (400, "choose a dataset"))
        self.service.get_job.side_effect = VKongNotInstalledError("VKong CLI was not found")
        self.assertEqual(self.client.get("/api/remote-training/jobs/studio-1").status_code, 503)


if __name__ == "__main__":
    unittest.main()
