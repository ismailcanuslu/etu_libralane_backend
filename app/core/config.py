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

    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_secure: bool = False

    jobs_host_dir: str = "/var/lib/librelane/jobs"
    jobs_workdir_in_runner: str = "/work"
    jobs_artifacts_prefix: str = "_jobs"

    runner_image_basic: str = "librelane/runner:basic"
    runner_image_openlane: str = "ghcr.io/efabless/openlane2:latest"
    runner_network: str = "librelane-network"
    runner_timeout_seconds: int = 60 * 30
    # Eşzamanlı en fazla kaç job çalışabilir; aşan job'lar QUEUED kalır.
    max_concurrent_jobs: int = 4

    anthropic_api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
