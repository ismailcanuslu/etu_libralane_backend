import unittest

from app.openlane1_flow_stages import (
    OPENLANE1_FLOW_STAGE_IDS,
    normalize_flow_steps,
)
from app.services.job_command import decode_job_command, encode_job_command
from app.tools_catalog import build_tool_command, get_tool


class Openlane1FlowStagesTests(unittest.TestCase):
    def test_normalize_all_returns_none(self) -> None:
        self.assertIsNone(normalize_flow_steps(list(OPENLANE1_FLOW_STAGE_IDS)))

    def test_normalize_subset_preserves_order(self) -> None:
        picked = ["synthesis", "floorplan", "placement"]
        self.assertEqual(normalize_flow_steps(picked), picked)

    def test_normalize_unknown_raises(self) -> None:
        with self.assertRaises(ValueError):
            normalize_flow_steps(["not_a_stage"])

    def test_encode_decode_with_flow_steps(self) -> None:
        argv = ["bash", "-lc", "echo test"]
        steps = ["synthesis", "placement"]
        raw = encode_job_command(argv, flow_steps=steps)
        decoded_argv, decoded_steps = decode_job_command(raw)
        self.assertEqual(decoded_argv, argv)
        self.assertEqual(decoded_steps, steps)

    def test_partial_flow_command_uses_partial_runner(self) -> None:
        spec = get_tool("openlane1-flow")
        assert spec is not None
        cmd = build_tool_command(
            spec,
            design_name="openlane/user_project_wrapper",
            flow_steps=["synthesis", "floorplan"],
        )
        joined = " ".join(cmd)
        self.assertIn("LIBRALANE_FLOW_STEPS", joined)
        self.assertIn("openlane_partial_flow.tcl", joined)


if __name__ == "__main__":
    unittest.main()
