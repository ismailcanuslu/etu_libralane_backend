import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DB_PATH", os.path.join(_TMP, "jobs.db"))
os.environ.setdefault("WORKSPACE_ROOT", os.path.join(_TMP, "workspace"))

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        get_settings.cache_clear()
        self.client = TestClient(app)

    def test_create_project_via_files_post_body(self) -> None:
        create = self.client.post("/files", json={"name": "demo-project"})
        self.assertEqual(create.status_code, 201)

    def test_project_and_object_roundtrip(self) -> None:
        create = self.client.post("/files/demo-project")
        self.assertEqual(create.status_code, 201)

        put = self.client.put(
            "/files/demo-project/objects/src/top.v",
            content=b"module top(); endmodule",
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(put.status_code, 201)

        listing = self.client.get("/files/demo-project/objects")
        self.assertEqual(listing.status_code, 200)
        payload = listing.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["objects"][0]["key"], "src/top.v")

        download = self.client.get("/files/demo-project/objects/src/top.v")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"module top(); endmodule")


if __name__ == "__main__":
    unittest.main()
