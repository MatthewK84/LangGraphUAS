"""Choosing an embedding provider from configuration.

Which model runs, and where, is a deployment decision. This is the one place the
choice is made, so nothing downstream has to know whether the vectors came from a
service on Railway or from a hash function in the same process.
"""

import logging
from typing import Final

import httpx

from suas.config import Settings
from suas.rag.embedding import EmbeddingProvider, HashingEmbedder, HttpEmbedder

logger: Final[logging.Logger] = logging.getLogger(__name__)


def build_embedder(settings: Settings, client: httpx.AsyncClient) -> EmbeddingProvider:
    """Return the configured provider, falling back loudly rather than quietly.

    An ``http`` provider with no URL is a misconfiguration, not a reason to
    silently serve lexical-only retrieval: the fallback is taken, and it is
    logged at error level so the deployment that meant to have a model knows it
    does not.
    """
    if settings.embedding_provider == "http":
        if not settings.embedding_url:
            logger.error(
                "embedding_provider is 'http' but embedding_url is empty; "
                "falling back to the hashing projection, which is lexical only"
            )
            return HashingEmbedder(settings.embedding_dimension)
        return HttpEmbedder(
            client,
            settings.embedding_url,
            settings.embedding_model_id,
            settings.embedding_dimension,
            settings.embedding_timeout_s,
        )
    return HashingEmbedder(settings.embedding_dimension)
