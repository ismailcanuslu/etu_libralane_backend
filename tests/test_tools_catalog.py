import json
import os
import unittest

from app.openlane1_manifest import load_openlane1_manifest, manifest_hub_keys
from app.tools_catalog import TOOL_CATALOG, _flow_script, build_tool_command, get_tool, list_tools

WEB_TOOL_IDS = frozenset(
    {
        "smoke-test",
        "lint",
        "simulation",
        "synthesis",
        "verification",
        "openlane1-flow",
    }
)


class ToolsCatalogTests(unittest.TestCase):
    def test_manifest_has_fifteen_hub_keys(self) -> None:
        keys = manifest_hub_keys()
        self.assertEqual(len(keys), 15)
        self.assertNotIn("antmicro_yosys", keys)
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

    def test_web_catalog_has_only_user_facing_tools(self) -> None:
        catalog_ids = {spec.id for spec in list_tools()}
        self.assertEqual(catalog_ids, WEB_TOOL_IDS)

    def test_no_openlane1_smoke_or_probe_in_catalog(self) -> None:
        for tool_id in TOOL_CATALOG:
            self.assertFalse(tool_id.startswith("openlane1-") and tool_id != "openlane1-flow", tool_id)
            self.assertFalse(tool_id.endswith("-probe"), tool_id)

    def test_formal_removed_from_catalog(self) -> None:
        self.assertNotIn("formal", TOOL_CATALOG)
        self.assertIsNone(get_tool("formal"))

    def test_openlane1_flow_action(self) -> None:
        spec = get_tool("openlane1-flow")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.kind, "flow")
        self.assertTrue(spec.requires_verilog)
        self.assertTrue(spec.requires_config)
        self.assertEqual(spec.group, "build")

    def test_flow_script_uses_path_flow_not_dot_slash(self) -> None:
        script = _flow_script("user_project_wrapper")
        self.assertIn("command -v flow.tcl", script)
        self.assertIn("exec flow.tcl -design 'user_project_wrapper'", script)
        self.assertNotIn("././flow.tcl", script)
        self.assertNotIn('./"$FLOW"', script)

    def test_build_tool_command_for_flow(self) -> None:
        spec = get_tool("openlane1-flow")
        assert spec is not None
        cmd = build_tool_command(spec, design_name="user_project_wrapper")
        self.assertEqual(cmd[0], "bash")
        self.assertEqual(cmd[1], "-lc")
        self.assertIn("exec flow.tcl -design 'user_project_wrapper'", cmd[2])

    def test_all_catalog_tools_use_openlane_runner(self) -> None:
        expected = os.environ.get("RUNNER_IMAGE_OPENLANE", "efabless/openlane:ci2504-dev-amd64")
        for spec in list_tools():
            self.assertEqual(
                spec.image,
                expected,
                f"{spec.id} beklenen runner imajini kullanmiyor",
            )

    def test_core_tools_enabled_and_use_openlane_runner(self) -> None:
        expected = os.environ.get("RUNNER_IMAGE_OPENLANE", "efabless/openlane:ci2504-dev-amd64")
        for action in ("smoke-test", "lint", "simulation", "synthesis", "verification"):
            spec = get_tool(action)
            self.assertIsNotNone(spec, action)
            assert spec is not None
            self.assertTrue(spec.enabled, action)
            self.assertEqual(spec.image, expected)

    def test_shell_tools_use_bash_lc(self) -> None:
        for action in ("smoke-test", "lint", "simulation", "synthesis", "verification"):
            spec = get_tool(action)
            assert spec is not None
            self.assertEqual(spec.cmd[0], "bash", action)
            self.assertEqual(spec.cmd[1], "-lc", action)

    def test_manifest_json_is_parseable(self) -> None:
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "app" / "openlane1_manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["image"], "efabless/openlane:ci2504-dev-amd64")
        self.assertEqual(len(data["tools"]), 15)


if __name__ == "__main__":
    unittest.main()
