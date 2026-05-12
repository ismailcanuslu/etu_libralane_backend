import os
import unittest

os.environ.setdefault("OLLAMA_HOST_START_COMMAND", "")

from app.core.config import get_settings
from app.services.ollama_runtime import build_ollama_host_start_command


class OllamaRuntimeTests(unittest.TestCase):
    def test_default_host_start_uses_ollama_run_model(self) -> None:
        get_settings.cache_clear()
        command = build_ollama_host_start_command()
        self.assertIn("nsenter", command)
        self.assertIn("ollama run", command)
        self.assertIn("gemma4:26b", command)
        self.assertIn("nohup", command)

    def test_custom_host_start_command_is_preserved(self) -> None:
        get_settings.cache_clear()
        os.environ["OLLAMA_HOST_START_COMMAND"] = "systemctl start ollama"
        get_settings.cache_clear()
        self.assertEqual(build_ollama_host_start_command(), "systemctl start ollama")
        os.environ.pop("OLLAMA_HOST_START_COMMAND", None)
        get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
