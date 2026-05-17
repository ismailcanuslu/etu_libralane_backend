import os
import tempfile
import unittest
from unittest.mock import patch

from app.core import storage
from app.core.workspace_paths import WorkspacePathError


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_patch = patch(
            "app.core.workspace_paths.get_settings",
            return_value=type("Settings", (), {"workspace_root": self.temp_dir.name})(),
        )
        self.settings_patch.start()

    def tearDown(self) -> None:
        self.settings_patch.stop()
        self.temp_dir.cleanup()

    def test_nested_write_and_read(self) -> None:
        storage.ensure_project("demo-project")
        storage.write_bytes("demo-project", "src/top.v", b"module top(); endmodule")
        content = storage.read_bytes("demo-project", "src/top.v")
        self.assertEqual(content, b"module top(); endmodule")

    def test_exclude_jobs_prefix_on_copy(self) -> None:
        dst = os.path.join(self.temp_dir.name, "job-workspace")
        os.makedirs(dst, exist_ok=True)
        with (
            patch("app.services.project_scaffold.scaffold_openlane_project", return_value=[]),
            patch("app.services.project_scaffold.ensure_caravel_guide", return_value=False),
        ):
            storage.ensure_project("demo-project")
            storage.write_bytes("demo-project", "design.v", b"rtl")
            storage.write_bytes("demo-project", "_jobs/job-1/log.txt", b"log")
            copied = storage.copy_project_to_dir(
                "demo-project",
                "",
                dst,
                exclude_prefixes=["_jobs/"],
            )
        self.assertEqual(len(copied), 1)
        self.assertTrue(os.path.isfile(os.path.join(dst, "design.v")))
        self.assertFalse(os.path.exists(os.path.join(dst, "_jobs")))

    def test_path_traversal_is_rejected(self) -> None:
        storage.ensure_project("demo-project")
        with self.assertRaises(WorkspacePathError):
            storage.read_bytes("demo-project", "../secret.txt")


if __name__ == "__main__":
    unittest.main()
