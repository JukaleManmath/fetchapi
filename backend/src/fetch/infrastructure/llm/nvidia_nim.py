"""NVIDIA NIM provider adapter.

Implements LLMProvider, EmbeddingProvider, and RerankProvider using the
OpenAI-compatible NVIDIA NIM API. This is the only file in the codebase
that imports the openai SDK directly.

Reranking uses httpx directly because NIM's /ranking endpoint is not
OpenAI-compatible.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import openai

from fetch.domain.errors import ProviderError
from fetch.domain.protocols import (
    EmbeddingResult,
    GenerationConfig,
    LLMMessage,
    LLMUsage,
    RerankCandidate,
    RerankResult,
    StreamChunk,
)
from fetch.infrastructure.llm.base import map_openai_error

logger = logging.getLogger(__name__)

_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaNimProvider:
    """Single adapter implementing LLMProvider, EmbeddingProvider, RerankProvider.

    Uses one API key and base URL for all three capabilities.
    Instantiate once at startup and inject via dependency injection.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _NIM_BASE_URL,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._llm_client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout=timeout_seconds),
        )
        self._embed_client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout=timeout_seconds),
        )
        self._rerank_http = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout=timeout_seconds),
        )

    # ── LLMProvider ───────────────────────────────────────────────────────────

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        config: GenerationConfig,
    ) -> AsyncIterator[StreamChunk]:
        """Stream text chunks from the LLM. Yields a final chunk with usage."""
        try:
            stream = await self._llm_client.chat.completions.create(
                model=config.model_id,
                messages=[
                    {"role": m.role, "content": m.content} for m in messages
                ],
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                stream=True,
                stream_options={"include_usage": config.stream_include_usage},
            )
        except openai.OpenAIError as exc:
            raise map_openai_error(exc) from exc

        return self._iter_stream(stream)

    async def _iter_stream(
        self,
        stream: Any,
    ) -> AsyncIterator[StreamChunk]:
        try:
            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                text = ""
                if choice and choice.delta and choice.delta.content:
                    text = choice.delta.content

                usage: LLMUsage | None = None
                if chunk.usage:
                    usage = LLMUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens,
                    )

                if text or usage:
                    yield StreamChunk(text=text, usage=usage)
        except openai.OpenAIError as exc:
            raise map_openai_error(exc) from exc

    async def generate(
        self,
        messages: list[LLMMessage],
        config: GenerationConfig,
    ) -> str:
        """Non-streaming generation. Used for structured tasks."""
        try:
            response = await self._llm_client.chat.completions.create(
                model=config.model_id,
                messages=[
                    {"role": m.role, "content": m.content} for m in messages
                ],
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                stream=False,
            )
            return response.choices[0].message.content or ""
        except openai.OpenAIError as exc:
            raise map_openai_error(exc) from exc

    # ── EmbeddingProvider ─────────────────────────────────────────────────────

    async def embed(
        self,
        texts: list[str],
        model_id: str,
    ) -> list[EmbeddingResult]:
        """Embed a batch of texts using NIM's embeddings endpoint."""
        if not texts:
            return []
        try:
            response = await self._embed_client.embeddings.create(
                model=model_id,
                input=texts,
                encoding_format="float",
            )
            return [
                EmbeddingResult(index=item.index, vector=item.embedding)
                for item in response.data
            ]
        except openai.OpenAIError as exc:
            raise map_openai_error(exc) from exc

    # ── RerankProvider ────────────────────────────────────────────────────────

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        model_id: str,
        top_n: int,
    ) -> list[RerankResult]:
        """Rerank candidates using NIM's /ranking endpoint.

        NIM reranking is not OpenAI-compatible so httpx is used directly.
        Returns up to top_n results sorted by descending score.
        """
        if not candidates:
            return []

        payload: dict[str, Any] = {
            "model": model_id,
            "query": {"text": query},
            "passages": [{"text": c.text} for c in candidates],
            "truncate": "END",
        }

        try:
            response = await self._rerank_http.post("/ranking", json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            from fetch.domain.errors import ProviderTimeoutError
            raise ProviderTimeoutError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                from fetch.domain.errors import ProviderAuthError
                raise ProviderAuthError(str(exc)) from exc
            if status == 429:
                from fetch.domain.errors import ProviderRateLimitError
                raise ProviderRateLimitError(str(exc)) from exc
            if status >= 500:
                from fetch.domain.errors import ProviderUnavailableError
                raise ProviderUnavailableError(str(exc)) from exc
            raise ProviderError(str(exc), retryable=False) from exc
        except httpx.RequestError as exc:
            from fetch.domain.errors import ProviderUnavailableError
            raise ProviderUnavailableError(str(exc)) from exc

        data = response.json()
        rankings = data.get("rankings", [])

        results = [
            RerankResult(
                index=candidates[r["index"]].index,
                score=r["logit"],
            )
            for r in rankings
        ]

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_n]

    async def aclose(self) -> None:
        """Close underlying HTTP clients. Call on application shutdown."""
        await self._llm_client.close()
        await self._embed_client.close()
        await self._rerank_http.aclose()
