import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    db_path: str = os.environ.get(
        "DB_PATH",
        str(_BACKEND_ROOT / "data" / "jobs.db"),
    )

    workspace_root: str = os.environ.get(
        "WORKSPACE_ROOT",
        str(_BACKEND_ROOT / "workspace"),
    )

    jobs_host_dir: str = "/var/lib/librelane/jobs"
    jobs_workdir_in_runner: str = "/work"
    jobs_artifacts_prefix: str = "_jobs"
    autonom_jobs_artifacts_prefix: str = "_autonom_jobs"
    max_concurrent_autonom_campaigns: int = 1

    runner_image_basic: str = "efabless/openlane:ci2504-dev-amd64"
    runner_image_openlane: str = "efabless/openlane:ci2504-dev-amd64"
    runner_network: str = "librelane-network"
    runner_timeout_seconds: int = 0
    # Eşzamanlı en fazla kaç job çalışabilir; aşan job'lar QUEUED kalır.
    max_concurrent_jobs: int = 4

    enable_openlane_tools: bool = True
    openlane_pdk_host_path: str = ""
    openlane_pdk_mount_path: str = "/openlane/pdk"

    enable_host_terminal: bool = True
    host_terminal_use_nsenter: bool = True
    host_terminal_shell: str = "/bin/bash"
    # Container icinde serbest terminal baslangic dizini (varsayilan: /)
    host_terminal_container_cwd: str = "/"
    max_host_terminal_sessions: int = 4

    # RAG (Qdrant) — sunucudaki hazir "librelane_verilog" koleksiyonundan retrieval.
    # indexer.py ile birebir ayni embedding modeli kullanilmali (nomic-embed-text).
    rag_enabled: bool = True
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "librelane_verilog"
    rag_embedding_model: str = "nomic-embed-text"
    rag_top_k: int = 5
    # Modele enjekte edilen referans baglaminin ust siniri (karakter).
    rag_max_context_chars: int = 6000
    # Qdrant istekleri icin kisa timeout (saniye); RAG opsiyonel oldugu icin sohbeti bekletmez.
    rag_timeout_seconds: float = 5.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
