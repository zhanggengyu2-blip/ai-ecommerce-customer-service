import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

# Avoid writing TLS session keys to a machine-wide debug path during local DB/API calls.
os.environ.pop("SSLKEYLOGFILE", None)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///../agentserve.db"
    jwt_secret: str = "change-me-before-production"
    jwt_minutes: int = 10080
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = ""
    cors_origins: str = "http://localhost:6173,http://127.0.0.1:6173"
    redis_url: str = "redis://localhost:6379/0"
    async_ingestion: bool = False
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "knowledge"
    opensearch_url: str = ""
    opensearch_user: str = ""
    opensearch_password: str = ""
    llm_mode: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    ai_base_url: str = ""
    ai_api_key: str = ""
    llm_model: str = ""
    semantic_routing_enabled: bool = True
    routing_timeout_seconds: int = 10
    routing_history_messages: int = 6
    routing_context_characters: int = 1600
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    rerank_url: str = ""
    rerank_api_key: str = ""
    rerank_model: str = ""
    embedding_dim: int = 1024
    business_api_url: str = ""
    business_api_token: str = ""
    business_mode: str = "mock"
    demo_enabled: bool = False
    foundation_enabled: bool = False
    model_encryption_key: str = ''
    dashscope_base_url: str = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    model_worker_enabled: bool = True
    customer_token_secret: str = ""


@lru_cache
def settings() -> Settings:
    return Settings()
