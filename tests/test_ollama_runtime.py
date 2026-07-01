import unittest
from unittest.mock import MagicMock, patch

from app.services.ollama_config import OllamaPrefs
from app.services.ollama_runtime import (
    _candidate_ollama_base_urls,
    build_ollama_host_start_command,
    reset_ollama_base_url_cache,
)


class OllamaRuntimeTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_ollama_base_url_cache()

    DEFAULT_MODEL = "hf.co/bartowski/Qwen_Qwen3.6-27B-GGUF:IQ3_XS"

    def test_default_model_value(self) -> None:
        self.assertEqual(OllamaPrefs().model, self.DEFAULT_MODEL)

    @patch("app.services.ollama_runtime.load_ollama_prefs")
    def test_default_host_start_uses_ollama_run_model(self, mock_load: MagicMock) -> None:
        mock_load.return_value = OllamaPrefs(host_start_command="")
        command = build_ollama_host_start_command()
        self.assertIn("nsenter", command)
        self.assertIn("ollama run", command)
        self.assertIn(self.DEFAULT_MODEL, command)
        self.assertIn("nohup", command)

    @patch("app.services.ollama_runtime.load_ollama_prefs")
    def test_custom_host_start_command_is_preserved(self, mock_load: MagicMock) -> None:
        mock_load.return_value = OllamaPrefs(host_start_command="systemctl start ollama")
        self.assertEqual(build_ollama_host_start_command(), "systemctl start ollama")

    def test_candidate_urls_include_localhost(self) -> None:
        urls = _candidate_ollama_base_urls(OllamaPrefs(base_url="http://custom:11434"))
        self.assertEqual(urls[0], "http://custom:11434")
        self.assertIn("http://127.0.0.1:11434", urls)


if __name__ == "__main__":
    unittest.main()
