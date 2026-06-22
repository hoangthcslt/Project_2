"""
src/config/settings.py
Cấu hình trung tâm - load từ .env qua pydantic-settings.
RULE 00: Tuyệt đối không hardcode bất kỳ credential nào ở đây.
"""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Neo4j ---
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str = "neo4j"
    neo4j_query_limit: int = 20

    # --- Qdrant ---
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "product_reviews"

    # --- Google AI (Primary LLM) ---
    google_api_key: str
    google_api_key_backups: Optional[str] = None
    smart_model: str = "gemini-2.5-flash-lite"
    llm_temperature: float = 0.1

    # --- OpenRouter (Legacy/Fallback - Optional) ---
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # --- Embedding ---
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_device: str = "cpu"

    # --- RAG Settings ---
    top_k_retrieval: int = 10

    @property
    def resolved_embedding_model(self) -> str:
        from pathlib import Path
        # Lấy thư mục gốc dự án (Project_2)
        project_root = Path(__file__).resolve().parent.parent.parent
        local_model_path = project_root / self.embedding_model
        if local_model_path.exists() and local_model_path.is_dir():
            return str(local_model_path)
        return self.embedding_model

    @property
    def all_google_api_keys(self) -> list[str]:
        keys = [self.google_api_key]
        if self.google_api_key_backups:
            for k in self.google_api_key_backups.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in keys:
                    keys.append(k_clean)
        return keys


@lru_cache
def get_settings() -> Settings:
    return Settings()

