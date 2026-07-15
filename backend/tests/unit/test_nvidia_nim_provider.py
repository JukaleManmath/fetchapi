"""Unit tests for the NVIDIA NIM provider adapter.

No real API calls are made. The openai client and httpx client are mocked.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest

from fetch.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from fetch.domain.protocols import (
    EmbeddingProvider,
    GenerationConfig,
    LLMMessage,
    LLMProvider,
    RerankCandidate,
    RerankProvider,
)
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def provider() -> NvidiaNimProvider:
    return NvidiaNimProvider(api_key="test-key")


_CONFIG = GenerationConfig(model_id="meta/llama-3.1-70b-instruct")
_MESSAGES = [LLMMessage(role="user", content="Hello")]


# ── Protocol satisfaction ─────────────────────────────────────────────────────


def test_provider_satisfies_llm_protocol(provider: NvidiaNimProvider) -> None:
    assert isinstance(provider, LLMProvider)


def test_provider_satisfies_embedding_protocol(provider: NvidiaNimProvider) -> None:
    assert isinstance(provider, EmbeddingProvider)


def test_provider_satisfies_rerank_protocol(provider: NvidiaNimProvider) -> None:
    assert isinstance(provider, RerankProvider)


# ── generate() ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_returns_content(provider: NvidiaNimProvider) -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello back"

    provider._llm_client.chat.completions.create = AsyncMock(
        return_value=mock_response
    )

    result = await provider.generate(_MESSAGES, _CONFIG)
    assert result == "Hello back"


@pytest.mark.asyncio
async def test_generate_empty_content_returns_empty_string(
    provider: NvidiaNimProvider,
) -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = None

    provider._llm_client.chat.completions.create = AsyncMock(
        return_value=mock_response
    )

    result = await provider.generate(_MESSAGES, _CONFIG)
    assert result == ""


# ── embed() ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_returns_vectors(provider: NvidiaNimProvider) -> None:
    item1 = MagicMock()
    item1.index = 0
    item1.embedding = [0.1, 0.2, 0.3]
    item2 = MagicMock()
    item2.index = 1
    item2.embedding = [0.4, 0.5, 0.6]

    mock_response = MagicMock()
    mock_response.data = [item1, item2]

    provider._embed_client.embeddings.create = AsyncMock(return_value=mock_response)

    results = await provider.embed(["text one", "text two"], "nvidia/nv-embed-v2")

    assert len(results) == 2
    assert results[0].index == 0
    assert results[0].vector == [0.1, 0.2, 0.3]
    assert results[1].index == 1


@pytest.mark.asyncio
async def test_embed_empty_list_returns_empty(provider: NvidiaNimProvider) -> None:
    results = await provider.embed([], "nvidia/nv-embed-v2")
    assert results == []


# ── rerank() ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rerank_returns_sorted_results(provider: NvidiaNimProvider) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "rankings": [
            {"index": 0, "logit": 0.3},
            {"index": 1, "logit": 0.9},
            {"index": 2, "logit": 0.6},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    provider._rerank_http.post = AsyncMock(return_value=mock_response)

    candidates = [
        RerankCandidate(index=0, text="doc a"),
        RerankCandidate(index=1, text="doc b"),
        RerankCandidate(index=2, text="doc c"),
    ]

    results = await provider.rerank(
        query="test query",
        candidates=candidates,
        model_id="nvidia/nv-rerankqa-mistral-4b-v3",
        top_n=2,
    )

    assert len(results) == 2
    assert results[0].score > results[1].score


@pytest.mark.asyncio
async def test_rerank_empty_candidates_returns_empty(
    provider: NvidiaNimProvider,
) -> None:
    results = await provider.rerank(
        query="test", candidates=[], model_id="model", top_n=5
    )
    assert results == []


# ── Error mapping ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_maps_timeout_error(provider: NvidiaNimProvider) -> None:
    provider._llm_client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=MagicMock())
    )
    with pytest.raises(ProviderTimeoutError) as exc_info:
        await provider.generate(_MESSAGES, _CONFIG)
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_generate_maps_rate_limit_error(provider: NvidiaNimProvider) -> None:
    provider._llm_client.chat.completions.create = AsyncMock(
        side_effect=openai.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429),
            body={},
        )
    )
    with pytest.raises(ProviderRateLimitError) as exc_info:
        await provider.generate(_MESSAGES, _CONFIG)
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_generate_maps_auth_error(provider: NvidiaNimProvider) -> None:
    provider._llm_client.chat.completions.create = AsyncMock(
        side_effect=openai.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body={},
        )
    )
    with pytest.raises(ProviderAuthError) as exc_info:
        await provider.generate(_MESSAGES, _CONFIG)
    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_rerank_maps_timeout_error(provider: NvidiaNimProvider) -> None:
    provider._rerank_http.post = AsyncMock(
        side_effect=httpx.TimeoutException("timed out")
    )
    candidates = [RerankCandidate(index=0, text="doc")]
    with pytest.raises(ProviderTimeoutError):
        await provider.rerank("query", candidates, "model", top_n=1)


@pytest.mark.asyncio
async def test_rerank_maps_auth_error(provider: NvidiaNimProvider) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 401
    provider._rerank_http.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_response
        )
    )
    candidates = [RerankCandidate(index=0, text="doc")]
    with pytest.raises(ProviderAuthError):
        await provider.rerank("query", candidates, "model", top_n=1)
