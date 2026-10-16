from pathlib import Path
import re

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")
    db_host: str = "127.0.0.1"
    db_port: int = Field(5432, ge=1, le=65535)
    db_name: str = "rag"
    db_user: str = "rag"
    db_password: SecretStr
    storage_dir: Path = Path("./storage")
    model_cache_dir: Path = Path("./model-cache")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"
    embedding_dimension: int = Field(384, ge=1, le=2000)
    embedding_device: str = "cpu"
    model_offline: bool = False
    embedding_batch_size: int = Field(16, ge=1, le=128)
    torch_threads: int = Field(2, ge=1, le=64)
    semantic_min_chars: int = Field(700, ge=100, le=20000)
    semantic_buffer_size: int = Field(1, ge=1, le=5)
    semantic_breakpoint_percentile: int = Field(90, ge=1, le=99)
    max_chunk_tokens: int = Field(220, ge=32, le=1024)
    max_extract_chars: int = Field(5_000_000, ge=1000)
    max_pdf_pages: int = Field(1000, ge=1)
    max_chunks: int = Field(20000, ge=1)
    max_upload_mb: int = Field(25, ge=1, le=100)
    retrieval_top_k: int = Field(10, ge=1, le=50)
    candidate_count: int = Field(50, ge=10, le=500)
    similarity_threshold: float = Field(0.2, ge=-1, le=1)
    issue_similarity_threshold: float = Field(0.3, ge=-1, le=1)
    rrf_k: int = Field(60, ge=1, le=200)
    reranker_enabled: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_revision: str = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
    auth_required: bool = True
    api_key: SecretStr = SecretStr("")
    port: int = Field(8090, ge=1, le=65535)
    logging_level: str = "INFO"
    worker_poll_seconds: float = Field(2, ge=0.1, le=60)
    worker_max_attempts: int = Field(3, ge=1, le=10)
    worker_retry_seconds: float = Field(10, ge=0, le=3600)
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,rag:*,rag-api:*"

    @model_validator(mode="after")
    def validate_secrets(self):
        if not self.db_password.get_secret_value().strip():
            raise ValueError("RAG_DB_PASSWORD is required")
        if self.auth_required and len(self.api_key.get_secret_value()) < 32:
            raise ValueError("Set RAG_API_KEY to at least 32 characters or explicitly disable authentication")
        if not re.fullmatch(r"[a-fA-F0-9]{40}", self.embedding_revision):
            raise ValueError("A 40-character immutable embedding-model revision is required")
        return self

    @property
    def database_url(self):
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def embedding_contract(self):
        return {
            "model": self.embedding_model,
            "revision": self.embedding_revision,
            "dimension": self.embedding_dimension,
            "normalized": True,
        }
