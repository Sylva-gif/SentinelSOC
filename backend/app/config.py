from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Sentinel SOC"
    service_role: Literal["all", "core", "ingestion", "assistant"] = "all"
    database_url: str = "sqlite:///./sentinel.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "local-demo-key-change-before-deployment"
    jwt_expire_minutes: int = 45
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    data_dir: str = "./data"
    ai_provider: str = "mock"
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""
    rate_limit_per_minute: int = 120
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4318/v1/traces"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()