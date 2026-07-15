"""Shared provider error mapping.

Every infrastructure adapter imports this module to convert provider-specific
exceptions into stable domain errors before they cross the layer boundary.
"""

import logging
from typing import TypeVar

import openai

from fetch.domain.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def map_openai_error(exc: openai.OpenAIError) -> ProviderError:
    """Convert an openai SDK exception into a stable domain ProviderError."""
    message = str(exc)

    if isinstance(exc, openai.APITimeoutError):
        return ProviderTimeoutError(message)

    if isinstance(exc, openai.RateLimitError):
        return ProviderRateLimitError(message)

    if isinstance(exc, openai.AuthenticationError):
        return ProviderAuthError(message)

    if isinstance(exc, openai.APIConnectionError):
        return ProviderUnavailableError(message)

    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        if status >= 500:
            return ProviderUnavailableError(message)
        if status == 429:
            return ProviderRateLimitError(message)
        if status in (401, 403):
            return ProviderAuthError(message)
        return ProviderError(message, retryable=False)

    return ProviderError(message, retryable=False)
