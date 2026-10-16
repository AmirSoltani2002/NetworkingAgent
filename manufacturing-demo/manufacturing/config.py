from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MANUFACTURING_", extra="ignore")
    db_host: str = "manufacturing-db"
    db_port: int = 5432
    db_name: str = "manufacturing"
    db_user: str = "manufacturing"
    db_password: SecretStr
    api_key: SecretStr = Field(min_length=16)
    artifact_dir: Path = Path("/data/models")
    port: int = Field(default=8000, ge=1024, le=65535)
    seed: int = 42
    sample_count: int = Field(default=1000, ge=100, le=50000)
    max_dataset_size: int = Field(default=50000, ge=100, le=100000)
    request_timeout: int = Field(default=30, ge=5, le=120)
    log_level: str = "INFO"
    mcp_allowed_hosts: str = "manufacturing-ml:8000,localhost:8000,127.0.0.1:8000,localhost:8100,127.0.0.1:8100"

    @property
    def database_url(self):
        return URL.create("postgresql+psycopg", username=self.db_user, password=self.db_password.get_secret_value(),
                          host=self.db_host, port=self.db_port, database=self.db_name)
