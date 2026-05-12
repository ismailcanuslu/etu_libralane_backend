import os
import unittest

from app.openlane_steps import CLASSIC_OPENLANE_STEP_IDS
from app.tools_catalog import TOOL_CATALOG, get_tool, list_tools


class ToolsCatalogTests(unittest.TestCase):
    def test_classic_step_catalog_entries(self) -> None:
        for step_id in CLASSIC_OPENLANE_STEP_IDS:
            action_id = "openlane-" + step_id.replace(".", "-").lower()
            spec = get_tool(action_id)
            self.assertIsNotNone(spec, action_id)
            assert spec is not None
            self.assertEqual(spec.image, os.environ.get("RUNNER_IMAGE_OPENLANE", "ghcr.io/efabless/openlane2:latest"))
            self.assertIn("openlane --only", " ".join(spec.cmd))
            self.assertIn(step_id, " ".join(spec.cmd))

    def test_openlane_tools_enabled_by_default(self) -> None:
        enabled = [tool for tool in list_tools() if tool.group == "openlane" and tool.enabled]
        self.assertEqual(len(enabled), len(CLASSIC_OPENLANE_STEP_IDS))

    def test_legacy_openlane_shortcuts_use_openlane_image(self) -> None:
        for action in ("pnr", "timing", "drc", "lvs", "gdsii", "openlane-classic"):
            spec = get_tool(action)
            self.assertIsNotNone(spec, action)
            assert spec is not None
            self.assertTrue(spec.enabled)
            self.assertIn("openlane", " ".join(spec.cmd))

    def test_catalog_size(self) -> None:
        self.assertGreaterEqual(len(TOOL_CATALOG), len(CLASSIC_OPENLANE_STEP_IDS) + 10)


if __name__ == "__main__":
    unittest.main()
