from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    db_path: str = "/data/jobs.db"

    workspace_root: str = "/workspace"

    jobs_host_dir: str = "/var/lib/librelane/jobs"
    jobs_workdir_in_runner: str = "/work"
    jobs_artifacts_prefix: str = "_jobs"

    runner_image_basic: str = "efabless/openlane:ci2504-dev-amd64"
    runner_image_openlane: str = "efabless/openlane:ci2504-dev-amd64"
    runner_network: str = "librelane-network"
    runner_timeout_seconds: int = 0
    # Eşzamanlı en fazla kaç job çalışabilir; aşan job'lar QUEUED kalır.
    max_concurrent_jobs: int = 4

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:26b"
    ollama_timeout_seconds: int = 300
    ollama_auto_start: bool = True
    ollama_container_name: str = ""
    ollama_host_start_command: str = ""
    ollama_ready_timeout_seconds: int = 60
    enable_openlane_tools: bool = True
    openlane_pdk_host_path: str = ""
    openlane_pdk_mount_path: str = "/openlane/pdk"

    enable_host_terminal: bool = True
    host_terminal_use_nsenter: bool = True
    host_terminal_shell: str = "/bin/bash"
    max_host_terminal_sessions: int = 4


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
