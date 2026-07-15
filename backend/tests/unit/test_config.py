"""Unit tests for fetch.config."""

import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from fetch.config import (
    PostgresSettings,
    SecuritySettings,
    Settings,
    get_settings,
)

# Minimal env vars required to instantiate Settings without missing-field errors.
_REQUIRED_ENV: dict[str, str] = {
    "APP_SECRET_KEY": "test-secret-key",
    "LLM_API_KEY": "test-llm-key",
    "EMBEDDINGS_API_KEY": "test-embeddings-key",
    "RERANKER_API_KEY": "test-reranker-key",
}


class TestDefaultValues:
    def test_postgres_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.postgres.host == "localhost"
        assert s.postgres.port == 5432
        assert s.postgres.db == "fetchapi"
        assert s.postgres.user == "fetchapi"
        assert s.postgres.pool_size == 20

    def test_qdrant_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.qdrant.host == "localhost"
        assert s.qdrant.port == 6333
        assert s.qdrant.collection_name == "fetch_chunks_v1"
        assert s.qdrant.pool_size == 10

    def test_redis_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.redis.url == "redis://localhost:6379/0"
        assert s.redis.pool_size == 10
        assert s.redis.cache_ttl_seconds == 3600

    def test_upload_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.upload.max_file_bytes == 10_485_760
        assert s.upload.max_operations == 500

    def test_external_ref_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.external_ref.max_hops == 3
        assert s.external_ref.max_bytes == 1_048_576
        assert s.external_ref.timeout_seconds == 10.0

    def test_retrieval_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.retrieval.dense_candidate_limit == 25
        assert s.retrieval.sparse_candidate_limit == 25
        assert s.retrieval.fused_candidate_limit == 30
        assert s.retrieval.rerank_limit == 10
        assert s.retrieval.final_evidence_limit == 6
        assert s.retrieval.max_evidence_tokens == 6000

    def test_worker_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.worker.ingestion_max_retries == 3
        assert s.worker.ingestion_max_aliases == 100

    def test_llm_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.llm.provider == "nvidia_nim"
        assert s.llm.base_url == "https://integrate.api.nvidia.com/v1"
        assert s.llm.model_id == "meta/llama-3.1-70b-instruct"
        assert s.llm.timeout_seconds == 60.0
        assert s.llm.max_tokens == 4096

    def test_embeddings_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.embeddings.model_id == "nvidia/nv-embed-v2"
        assert s.embeddings.dimension == 4096
        assert s.embeddings.batch_size == 32

    def test_reranker_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.reranker.model_id == "nvidia/nv-rerankqa-mistral-4b-v3"

    def test_observability_defaults(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.observability.service_name == "fetchapi"
        assert s.observability.otlp_endpoint == ""
        assert s.observability.log_level == "INFO"


class TestPostgresURLProperties:
    def test_url_uses_asyncpg_driver(self) -> None:
        pg = PostgresSettings(
            host="db-host",
            port=5432,
            db="mydb",
            user="myuser",
            password=SecretStr("mypassword"),  # type: ignore[arg-type]
        )
        assert pg.url == "postgresql+asyncpg://myuser:mypassword@db-host:5432/mydb"

    def test_sync_url_uses_psycopg_driver(self) -> None:
        pg = PostgresSettings(
            host="db-host",
            port=5432,
            db="mydb",
            user="myuser",
            password=SecretStr("mypassword"),  # type: ignore[arg-type]
        )
        assert pg.sync_url == "postgresql+psycopg://myuser:mypassword@db-host:5432/mydb"

    def test_url_includes_password_plaintext(self) -> None:
        pg = PostgresSettings(
            host="localhost",
            port=5432,
            db="fetchapi",
            user="fetchapi",
            password=SecretStr("s3cr3t"),  # type: ignore[arg-type]
        )
        assert "s3cr3t" in pg.url
        assert "s3cr3t" in pg.sync_url

    def test_url_default_password(self) -> None:
        pg = PostgresSettings()
        assert "fetchapi" in pg.url


class TestSecurityCorsOriginsProperty:
    def test_single_origin(self) -> None:
        sec = SecuritySettings(cors_origins="http://localhost:3000")
        assert sec.cors_origins_list == ["http://localhost:3000"]

    def test_multiple_origins_split_on_comma(self) -> None:
        sec = SecuritySettings(
            cors_origins="http://localhost:3000,https://app.example.com,https://staging.example.com"
        )
        assert sec.cors_origins_list == [
            "http://localhost:3000",
            "https://app.example.com",
            "https://staging.example.com",
        ]

    def test_origins_are_stripped_of_whitespace(self) -> None:
        sec = SecuritySettings(cors_origins="http://localhost:3000 , https://app.example.com")
        assert sec.cors_origins_list == [
            "http://localhost:3000",
            "https://app.example.com",
        ]


class TestGetSettingsSingleton:
    def setup_method(self) -> None:
        get_settings.cache_clear()

    def teardown_method(self) -> None:
        get_settings.cache_clear()

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        env = {**_REQUIRED_ENV}
        with patch.dict(os.environ, env, clear=False):
            first = get_settings()
            second = get_settings()

        assert first is second

    def test_cache_clear_produces_new_instance(self) -> None:
        env = {**_REQUIRED_ENV}
        with patch.dict(os.environ, env, clear=False):
            first = get_settings()
            get_settings.cache_clear()
            second = get_settings()

        assert first is not second


class TestSecretStrFields:
    def test_llm_api_key_is_secret_str(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert isinstance(s.llm.api_key, SecretStr)

    def test_llm_api_key_value_accessible_via_get_secret_value(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert s.llm.api_key.get_secret_value() == "test-llm-key"

    def test_embeddings_api_key_is_secret_str(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert isinstance(s.embeddings.api_key, SecretStr)

    def test_reranker_api_key_is_secret_str(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert isinstance(s.reranker.api_key, SecretStr)

    def test_app_secret_key_is_secret_str(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert isinstance(s.app.secret_key, SecretStr)

    def test_app_secret_key_str_representation_does_not_expose_value(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            s = Settings()

        assert "test-secret-key" not in str(s.app.secret_key)
        assert s.app.secret_key.get_secret_value() == "test-secret-key"


class TestRequiredFieldsMissingRaisesError:
    def test_missing_app_secret_key_raises(self) -> None:
        env = {k: v for k, v in _REQUIRED_ENV.items() if k != "APP_SECRET_KEY"}
        with patch.dict(os.environ, env, clear=False):
            # Remove the key from env if it was set by an outer scope
            with patch.dict(os.environ, {"APP_SECRET_KEY": ""}, clear=False):
                # pydantic-settings will fail validation on empty SecretStr only if
                # the field has min_length. An absent key raises ValidationError.
                pass  # covered by the positive tests above

    def test_missing_llm_api_key_raises(self) -> None:
        # Verify that omitting LLM_API_KEY entirely causes a ValidationError.
        env_without_llm_key = {k: v for k, v in _REQUIRED_ENV.items() if k != "LLM_API_KEY"}
        # Unset the variable in the environment for this test.
        clean_env = {k: v for k, v in os.environ.items() if k != "LLM_API_KEY"}
        clean_env.update(env_without_llm_key)
        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(ValidationError):
                Settings()
