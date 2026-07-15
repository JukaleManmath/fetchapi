"""Application configuration.

All settings are loaded from environment variables via pydantic-settings.
Required production fields (API keys, secret_key) have no default and will
cause a fast startup failure when absent.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    env: str = "development"
    debug: bool = False
    secret_key: SecretStr
    workspace_id: UUID = UUID("00000000-0000-0000-0000-000000000001")


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    db: str = "fetchapi"
    user: str = "fetchapi"
    password: SecretStr = SecretStr("fetchapi")
    pool_size: int = 20

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )

    @property
    def sync_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT_", extra="ignore")

    host: str = "localhost"
    port: int = 6333
    collection_name: str = "fetch_chunks_v1"
    pool_size: int = 10


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    url: str = "redis://localhost:6379/0"
    pool_size: int = 10
    cache_ttl_seconds: int = 3600


class ObjectStorageSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OBJECT_STORAGE_", extra="ignore")

    endpoint: str = "http://localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "fetchapi-snapshots"
    region: str = "us-east-1"


class WorkerSettings(BaseSettings):
    """Ingestion tuning parameters. No broker — ingestion runs as asyncio background tasks."""

    model_config = SettingsConfigDict(env_prefix="WORKER_", extra="ignore")

    ingestion_max_retries: int = 3
    ingestion_max_aliases: int = 100


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")

    provider: str = "nvidia_nim"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    api_key: SecretStr
    model_id: str = "meta/llama-3.1-70b-instruct"
    timeout_seconds: float = 60.0
    max_tokens: int = 4096


class EmbeddingsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBEDDINGS_", extra="ignore")

    provider: str = "nvidia_nim"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    api_key: SecretStr
    model_id: str = "nvidia/nv-embed-v2"
    dimension: int = 4096
    batch_size: int = 32


class RerankerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RERANKER_", extra="ignore")

    provider: str = "nvidia_nim"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    api_key: SecretStr
    model_id: str = "nvidia/nv-rerankqa-mistral-4b-v3"


class RetrievalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    dense_candidate_limit: int = 25
    sparse_candidate_limit: int = 25
    fused_candidate_limit: int = 30
    rerank_limit: int = 10
    final_evidence_limit: int = 6
    max_evidence_tokens: int = 6000


class UploadSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UPLOAD_", extra="ignore")

    max_file_bytes: int = 10_485_760
    max_operations: int = 500


class ExternalRefSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXT_REF_", extra="ignore")

    max_hops: int = 3
    max_bytes: int = 1_048_576
    timeout_seconds: float = 10.0


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SECURITY_", extra="ignore")

    allowed_hosts: str = "*"
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OTEL_", extra="ignore")

    service_name: str = "fetchapi"
    otlp_endpoint: str = ""
    log_level: str = "INFO"


class Settings(BaseSettings):
    app: AppSettings = Field(default_factory=AppSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    object_storage: ObjectStorageSettings = Field(default_factory=ObjectStorageSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    embeddings: EmbeddingsSettings = Field(default_factory=EmbeddingsSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    upload: UploadSettings = Field(default_factory=UploadSettings)
    external_ref: ExternalRefSettings = Field(default_factory=ExternalRefSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
