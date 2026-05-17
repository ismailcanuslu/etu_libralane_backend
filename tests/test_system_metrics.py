import unittest
from unittest.mock import patch

from app.services.system_metrics import collect_system_metrics


class SystemMetricsTests(unittest.TestCase):
    def test_collect_returns_core_sections(self) -> None:
        with patch("app.services.system_metrics.psutil.cpu_percent", return_value=12.5):
            data = collect_system_metrics()
        self.assertIn("cpu", data)
        self.assertIn("memory", data)
        self.assertIn("disks", data)
        self.assertIn("network", data)
        self.assertIn("gpus", data)
        self.assertIn("runtime", data)
        self.assertIn("metrics_scope", data["runtime"])
        self.assertIsInstance(data["disks"], list)
        self.assertIn("usage_percent", data["cpu"])


if __name__ == "__main__":
    unittest.main()
