from pathlib import Path
from pydantic import Field,SecretStr
from pydantic_settings import BaseSettings,SettingsConfigDict
from sqlalchemy import URL

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_prefix='FACTORY_',extra='ignore')
    db_host:str='zsk-db'
    db_port:int=5432
    db_name:str='manufacturing'
    db_user:str='manufacturing'
    db_password:SecretStr
    api_token:SecretStr=Field(min_length=24)
    mcp_auth_token:SecretStr=Field(min_length=24)
    ml_api_token:SecretStr=Field(min_length=16)
    task_service_token:SecretStr=Field(min_length=24)
    ml_url:str='http://manufacturing-ml:8000'
    meta_harness_url:str='http://core:8000/api'
    task_template:str='manufacturing-alert'
    machine_id:str='ZSK-SIM-01'
    rag_device_id:str=''
    monitor_interval_minutes:int=Field(default=10,ge=5,le=120,multiple_of=5)
    forecast_alarm_threshold:float=Field(default=.65,ge=0,le=1)
    alarm_cooldown_minutes:int=Field(default=30,ge=10,le=240)
    auto_stop_allowed:bool=False
    auto_restart_allowed:bool=False
    auto_maintenance_allowed:bool=False
    automatic_faults:bool=True
    mcp_allowed_hosts:str='factory:8110,localhost:8110,127.0.0.1:8110'
    migrations:Path=Path('/app/factory-migrations')
    worker_enabled:bool=True
    @property
    def database_url(self):
        return URL.create('postgresql+psycopg',username=self.db_user,password=self.db_password.get_secret_value(),host=self.db_host,port=self.db_port,database=self.db_name)
