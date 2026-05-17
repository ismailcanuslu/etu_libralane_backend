import unittest

from app.services.autonom_spec import list_iteration_values, validate_spec


class AutonomSpecTests(unittest.TestCase):
    def test_scalar_decreasing_sequence(self) -> None:
        spec = {
            "param": {
                "flag": "FP_CORE_UTIL",
                "kind": "scalar",
                "start": 120,
                "target": 110,
                "step": -5,
            },
            "build_actions": ["synthesis"],
            "input_files": ["openlane/x/config.json"],
        }
        values = list_iteration_values(validate_spec(spec))  # type: ignore[arg-type]
        self.assertEqual(values, [120.0, 115.0, 110.0])

    def test_dimension_pair_sequence(self) -> None:
        spec = {
            "param": {
                "flag": "DIE_AREA",
                "kind": "dimension_pair",
                "start": [150, 150],
                "target": [140, 140],
                "step": [-5, -5],
                "serialize_as": "space_pair",
            },
            "build_actions": ["openlane1-flow"],
            "input_files": ["cfg.json"],
        }
        values = list_iteration_values(validate_spec(spec))  # type: ignore[arg-type]
        self.assertEqual(values, [[150, 150], [145, 145], [140, 140]])

    def test_scalar_increasing(self) -> None:
        spec = {
            "param": {
                "flag": "X",
                "kind": "scalar",
                "start": 10,
                "target": 20,
                "step": 5,
            },
            "build_actions": ["lint"],
            "input_files": ["a.json"],
        }
        self.assertEqual(
            list_iteration_values(validate_spec(spec)),  # type: ignore[arg-type]
            [10.0, 15.0, 20.0],
        )


if __name__ == "__main__":
    unittest.main()
