"""Ollama embedding provider.

Implements EmbeddingProvider using Ollama's local /api/embed endpoint.
No API key required — Ollama runs locally.

Default model: mxbai-embed-large (1024-dim, matches NIM nv-embed-v2 dimension).
"""

from __future__ import annotations

import logging

import httpx

from fetch.domain.errors import ProviderError, ProviderTimeoutError
from fetch.domain.protocols import EmbeddingResult

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaEmbeddingProvider:
    """Embedding provider backed by a local Ollama instance.

    Stateless beyond the injected base URL. A single instance can be reused
    across concurrent requests.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def embed(
        self,
        texts: list[str],
        model_id: str,
        input_type: str = "passage",
    ) -> list[EmbeddingResult]:
        """Embed a batch of texts using Ollama's /api/embed endpoint.

        ``input_type`` is accepted for protocol compatibility but ignored —
        Ollama does not distinguish query vs passage embeddings.
        Returns one EmbeddingResult per input, in index order.
        """
        if not texts:
            return []

        payload = {"model": model_id, "input": texts}

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout),
            ) as client:
                response = await client.post("/api/embed", json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"Ollama embed error {exc.response.status_code}: {exc.response.text}",
                retryable=exc.response.status_code >= 500,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                f"Ollama connection error: {exc}. Is Ollama running at {self._base_url}?",
                retryable=True,
            ) from exc

        data = response.json()
        embeddings: list[list[float]] = data.get("embeddings", [])

        if len(embeddings) != len(texts):
            raise ProviderError(
                f"Ollama returned {len(embeddings)} embeddings for {len(texts)} inputs",
                retryable=False,
            )

        logger.debug(
            "ollama_embed_complete",
            extra={
                "model_id": model_id,
                "count": len(texts),
                "dim": len(embeddings[0]) if embeddings else 0,
            },
        )

        return [
            EmbeddingResult(index=i, vector=vec) for i, vec in enumerate(embeddings)
        ]
