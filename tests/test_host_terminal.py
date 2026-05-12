import os
import unittest

os.environ.setdefault("ENABLE_HOST_TERMINAL", "false")

from app.core.config import get_settings
from app.services.host_shell import host_terminal_status


class HostTerminalStatusTests(unittest.TestCase):
    def test_status_reports_disabled(self) -> None:
        get_settings.cache_clear()
        status = host_terminal_status()
        self.assertFalse(status["available"])
        self.assertEqual(status["mode"], "disabled")


if __name__ == "__main__":
    unittest.main()
