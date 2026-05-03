from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = "http://localhost:11434"
    reasoning_model: str = "qwen3.5:4b"
    reasoning_model_think: bool = False
    embedding_model: str = "nomic-embed-text:v1.5"

    qdrant_url: str = "http://localhost:6333"
    dense_collection: str = "ce_dense"
    sparse_collection: str = "ce_sparse"
    retrieval_top_k: int = 10
    reranker_enabled: bool = False
    generation_top_k: int = 3
    history_turns: int = 6

    sqlite_db_path: str = "data/qc.db"

    hardware_check_url: str = "http://127.0.0.1:8000/hardware/anomaly-check"
    django_mcp_url: str = "http://localhost:8001/mcp"


settings = Settings()
