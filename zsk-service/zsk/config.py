from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='ZSK_', extra='ignore')
    db_host: str = 'zsk-db'
    db_port: int = 5432
    db_name: str = 'manufacturing'
    db_user: str = 'manufacturing'
    db_password: SecretStr
    api_key: SecretStr = Field(min_length=16)
    admin_api_key: SecretStr = Field(min_length=16)
    artifact_dir: Path = Path('/data/models')
    data_dir: Path = Path('/app/data')
    migration_dir: Path = Path('/app/migrations')
    port: int = 8000
    forecast_bootstrap: bool = True
    forecast_horizon_minutes: int = Field(default=30,ge=5,le=120,multiple_of=5)
    request_timeout: int = Field(default=30, ge=5, le=120)
    job_attempts: int = Field(default=3, ge=1, le=10)
    mcp_allowed_hosts: str = 'zsk-ml:8000,manufacturing-ml:8000,localhost:8000,127.0.0.1:8000,localhost:8100,127.0.0.1:8100'
    @property
    def database_url(self):
        return URL.create('postgresql+psycopg',username=self.db_user,password=self.db_password.get_secret_value(),host=self.db_host,port=self.db_port,database=self.db_name)
