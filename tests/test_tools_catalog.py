import json
import os
import unittest

from app.openlane1_manifest import load_openlane1_manifest, manifest_hub_keys
from app.tools_catalog import TOOL_CATALOG, get_tool, list_tools


class ToolsCatalogTests(unittest.TestCase):
    def test_manifest_has_sixteen_hub_keys(self) -> None:
        keys = manifest_hub_keys()
        self.assertEqual(len(keys), 16)
        self.assertEqual(
            keys,
            [
                "klayout",
                "replace",
                "opendp",
                "route",
                "cugr",
                "drcu",
                "opensta",
                "yosys",
                "antmicro_yosys",
                "magic",
                "openroad_app",
                "padring",
                "netgen",
                "vlogtoverilog",
                "openphysyn",
                "cvc",
            ],
        )

    def test_manifest_entries_are_valid(self) -> None:
        manifest = load_openlane1_manifest()
        for entry in manifest["tools"]:
            self.assertTrue(entry.get("hub_key"))
            enabled = bool(entry.get("enabled", True))
            resolved = entry.get("resolved_bins") or []
            if enabled:
                self.assertTrue(resolved, entry["hub_key"])
            self.assertIn("probe_argv", entry)
            self.assertIn("smoke_argv", entry)

    def test_openlane1_smoke_and_probe_actions_exist(self) -> None:
        for hub_key in manifest_hub_keys():
            smoke = get_tool(f"openlane1-{hub_key}")
            probe = get_tool(f"openlane1-{hub_key}-probe")
            self.assertIsNotNone(smoke, hub_key)
            self.assertIsNotNone(probe, hub_key)
            assert smoke is not None
            assert probe is not None
            self.assertEqual(
                smoke.image,
                os.environ.get("RUNNER_IMAGE_OPENLANE", "efabless/openlane:ci2504-dev-amd64"),
            )
            self.assertEqual(smoke.group, "openlane1")
            self.assertEqual(probe.kind, "probe")

    def test_openlane1_flow_action(self) -> None:
        spec = get_tool("openlane1-flow")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.kind, "flow")
        self.assertTrue(spec.requires_verilog)
        self.assertTrue(spec.requires_config)

    def test_catalog_size(self) -> None:
        self.assertGreaterEqual(len(TOOL_CATALOG), 16 * 2 + 6)

    def test_manifest_json_is_parseable(self) -> None:
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "app" / "openlane1_manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["image"], "efabless/openlane:ci2504-dev-amd64")
        self.assertEqual(len(data["tools"]), 16)


if __name__ == "__main__":
    unittest.main()
