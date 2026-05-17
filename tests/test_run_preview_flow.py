import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.run_preview import build_run_preview


class RunPreviewFlowTests(unittest.TestCase):
    def test_openlane_flow_default_includes_config_and_flow_tcl(self) -> None:
        keys = [
            "verilog/rtl/user_project_wrapper.v",
            "flow.tcl",
            "openlane/user_project_wrapper/config.json",
        ]
        objects = [SimpleNamespace(key=k) for k in keys]
        with (
            patch("app.services.run_preview.storage.list_objects", return_value=objects),
            patch("app.services.run_preview.get_pdk_runtime_info", return_value={}),
            patch(
                "app.services.run_preview.flow_input_keys",
                return_value=[
                    "flow.tcl",
                    "openlane/user_project_wrapper/config.json",
                    "verilog/rtl/user_project_wrapper.v",
                ],
            ),
        ):
            preview = build_run_preview("demo", "openlane1-flow")

        defaults = preview["default_input_files"]
        self.assertIn("flow.tcl", defaults)
        self.assertIn("openlane/user_project_wrapper/config.json", defaults)


if __name__ == "__main__":
    unittest.main()
