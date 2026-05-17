import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.run_preview import build_run_preview
from app.tools_catalog import get_tool


class RunPreviewTests(unittest.TestCase):
    def test_simulation_default_files_prefers_caravel_rtl(self) -> None:
        keys = [
            "verilog/rtl/defines.v",
            "verilog/rtl/user_module.v",
            "verilog/rtl/user_project_wrapper.v",
            "tb/tb_user_project_wrapper.v",
            "src/counter.v",
            "tb/counter_tb.v",
        ]
        objects = [SimpleNamespace(key=k) for k in keys]
        with (
            patch("app.services.run_preview.storage.list_objects", return_value=objects),
            patch("app.services.run_preview.get_pdk_runtime_info", return_value={}),
        ):
            preview = build_run_preview("demo", "simulation")

        self.assertCountEqual(
            preview["default_input_files"],
            [
                "verilog/rtl/defines.v",
                "verilog/rtl/user_module.v",
                "verilog/rtl/user_project_wrapper.v",
                "tb/tb_user_project_wrapper.v",
            ],
        )
        self.assertTrue(any("counter_tb" in w for w in preview["warnings"]))

    def test_command_display_shows_script_on_second_line(self) -> None:
        with (
            patch("app.services.run_preview.storage.list_objects", return_value=[]),
            patch("app.services.run_preview.get_pdk_runtime_info", return_value={}),
        ):
            preview = build_run_preview("demo", "simulation")

        display = preview["command_display"]
        self.assertTrue(display.startswith("bash -lc\n"))
        self.assertIn("[librelane] simulasyon basladi", display)


class SimulationCommandTests(unittest.TestCase):
    def test_simulation_cmd_is_valid_bash_script(self) -> None:
        spec = get_tool("simulation")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(spec.cmd[:2], ["bash", "-lc"])
        script = spec.cmd[2]
        self.assertIn('echo "[librelane] simulasyon basladi"', script)
        self.assertIn('echo "[librelane] simulasyon bitti exit=$?"', script)
        self.assertNotIn("exit='$?')'", script)

    def test_simulation_cmd_runs_under_bash_lc(self) -> None:
        import subprocess

        spec = get_tool("simulation")
        assert spec is not None
        script = (
            spec.cmd[2]
            .replace("iverilog -g2012", "true # iverilog")
            .replace("timeout --kill-after=15 600 vvp sim.vvp", "true # vvp")
            .replace("else vvp sim.vvp; fi", "else true; fi")
        )
        result = subprocess.run(
            ["bash", "-lc", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotIn("unexpected EOF", result.stderr)
        self.assertIn("[librelane] simulasyon basladi", result.stdout)


if __name__ == "__main__":
    unittest.main()
