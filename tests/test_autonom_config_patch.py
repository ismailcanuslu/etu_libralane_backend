import unittest

from app.services.autonom_spec import validate_spec
from app.services.openlane_config_patch import patch_config_content, parse_config_bytes


class AutonomConfigPatchTests(unittest.TestCase):
    def test_scalar_patch_json(self) -> None:
        base = b'{"FP_CORE_UTIL": 50, "DESIGN_NAME": "test"}\n'
        spec = validate_spec(
            {
                "param": {
                    "flag": "FP_CORE_UTIL",
                    "kind": "scalar",
                    "start": 120,
                    "target": 90,
                    "step": -5,
                },
                "build_actions": ["synthesis"],
                "input_files": ["x"],
            }
        )
        out = patch_config_content(base, "openlane/w/config.json", spec["param"], 115)
        data = parse_config_bytes(out, "openlane/w/config.json")
        self.assertEqual(data["FP_CORE_UTIL"], 115)
        self.assertEqual(data["DESIGN_NAME"], "test")

    def test_dimension_pair_times_string(self) -> None:
        base = b'{"DIE_AREA": "150 150"}\n'
        spec = validate_spec(
            {
                "param": {
                    "flag": "DIE_AREA",
                    "kind": "dimension_pair",
                    "start": [150, 150],
                    "target": [90, 90],
                    "step": [-5, -5],
                    "serialize_as": "times_string",
                },
                "build_actions": ["synthesis"],
                "input_files": ["x"],
            }
        )
        out = patch_config_content(base, "config.json", spec["param"], [145, 145])
        data = parse_config_bytes(out, "config.json")
        self.assertEqual(data["DIE_AREA"], "145x145")

    def test_die_area_rect_patch(self) -> None:
        base = b'{"DIE_AREA": "0 0 150 150", "FP_SIZING": "absolute"}\n'
        spec = validate_spec(
            {
                "param": {
                    "flag": "DIE_AREA",
                    "kind": "die_area_rect",
                    "start": [0, 0, 150, 150],
                    "target": [0, 0, 90, 90],
                    "step": [0, 0, -5, -5],
                },
                "build_actions": ["synthesis"],
                "input_files": ["x"],
            }
        )
        out = patch_config_content(
            base, "config.json", spec["param"], "0 0 145 145"
        )
        data = parse_config_bytes(out, "config.json")
        self.assertEqual(data["DIE_AREA"], "0 0 145 145")


if __name__ == "__main__":
    unittest.main()
