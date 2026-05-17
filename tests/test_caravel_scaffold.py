import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.caravel_layout import (
    CARAVEL_WRAPPER_DESIGN,
    find_caravel_openlane_design,
    has_caravel_scaffold,
)
from app.services.openlane_layout import resolve_design_name, verilog_glob_shell_var
from app.services.openlane_layout import flow_input_keys
from app.services.project_scaffold import (
    GUIDE_FILENAME,
    ensure_caravel_guide,
    ensure_missing_caravel_flow_files,
    scaffold_openlane_project,
)


class CaravelScaffoldTests(unittest.TestCase):
    def test_scaffold_creates_caravel_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_id = "demo-caravel"
            base = Path(tmp) / project_id

            with patch("app.services.project_scaffold.project_dir", return_value=base):
                created = scaffold_openlane_project(project_id)

            self.assertGreater(len(created), 5)
            self.assertTrue((base / "verilog/rtl/user_project_wrapper.v").is_file())
            self.assertTrue((base / "openlane/user_project_wrapper/config.json").is_file())
            self.assertTrue((base / "openlane/user_module/config.json").is_file())
            self.assertTrue((base / "caravel/README.md").is_file())
            self.assertTrue((base / GUIDE_FILENAME).is_file())

    def test_ensure_guide_on_existing_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_id = "legacy-proj"
            base = Path(tmp) / project_id
            base.mkdir()
            rtl = base / "verilog/rtl"
            rtl.mkdir(parents=True)
            (rtl / "user_module.v").write_text("// legacy\n", encoding="utf-8")
            (rtl / "user_project_wrapper.v").write_text("// legacy wrapper\n", encoding="utf-8")
            wrapper_cfg = base / "openlane/user_project_wrapper"
            wrapper_cfg.mkdir(parents=True)
            (wrapper_cfg / "config.json").write_text("{}", encoding="utf-8")

            with patch("app.services.project_scaffold.project_dir", return_value=base):
                created = scaffold_openlane_project(project_id)
                self.assertEqual(created, [])
                added = ensure_caravel_guide(project_id)
                self.assertTrue(added)
                self.assertTrue((base / GUIDE_FILENAME).is_file())
                again = ensure_caravel_guide(project_id)
                self.assertFalse(again)
                self.assertIn("GDS ≠ tape-out", (base / GUIDE_FILENAME).read_text(encoding="utf-8"))

            with patch("app.services.caravel_layout.project_dir", return_value=base):
                self.assertTrue(has_caravel_scaffold(project_id))
                self.assertEqual(find_caravel_openlane_design(project_id), CARAVEL_WRAPPER_DESIGN)

            with patch("app.services.openlane_layout.project_dir", return_value=base):
                with patch("app.services.openlane_layout.has_caravel_scaffold", return_value=True):
                    self.assertEqual(resolve_design_name(project_id), CARAVEL_WRAPPER_DESIGN)

    def test_verilog_glob_prefers_caravel_rtl(self) -> None:
        script = verilog_glob_shell_var()
        self.assertIn("verilog/rtl", script)

    def test_ensure_missing_flow_files_for_legacy_rtl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_id = "legacy-flow"
            base = Path(tmp) / project_id
            rtl = base / "verilog/rtl"
            rtl.mkdir(parents=True)
            (rtl / "user_project_wrapper.v").write_text("// rtl\n", encoding="utf-8")

            with patch("app.services.project_scaffold.project_dir", return_value=base):
                created = ensure_missing_caravel_flow_files(project_id)

            self.assertIn("flow.tcl", created)
            self.assertIn("openlane/user_project_wrapper/config.json", created)
            self.assertTrue((base / "openlane/user_project_wrapper/config.json").is_file())

            with (
                patch("app.services.openlane_layout.project_dir", return_value=base),
                patch("app.services.caravel_layout.project_dir", return_value=base),
            ):
                keys = flow_input_keys(project_id)
            self.assertIn("flow.tcl", keys)
            self.assertIn("openlane/user_project_wrapper/config.json", keys)
            self.assertTrue(any(k.endswith(".v") for k in keys))


if __name__ == "__main__":
    unittest.main()
