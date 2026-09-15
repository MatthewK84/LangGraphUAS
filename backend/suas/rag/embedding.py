"""Turning text into vectors.

The provider is pluggable because the model has to live somewhere, and where it
lives is a deployment decision rather than a code one. Two implementations ship:

``HashingEmbedder`` needs nothing. It is a deterministic lexical projection --
hashed token counts, L2 normalised -- so it runs in tests, in CI, and in a
deployment that has no model service at all. It is **not semantic**: it matches
shared vocabulary, not shared meaning, and the code says so rather than letting
a reader assume otherwise.

``HttpEmbedder`` calls a service over HTTP. That is the shape a real model takes
on Railway: a separate service with its own image and its own scaling, reached by
URL. ``services/embeddings/`` in this repository is one such service, ready to
deploy.

Whichever is configured, the model identity and dimension are recorded on every
chunk. Vectors from two different models are not comparable, and silently mixing
them produces a retriever that is subtly and unfixably wrong.
"""

import hashlib
import logging
import math
import re
from typing import Final, Protocol

import httpx

from suas.errors import SuasError

logger: Final[logging.Logger] = logging.getLogger(__name__)

_TOKEN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")


class EmbeddingError(SuasError):
    """Raised when embeddings cannot be produced."""


class EmbeddingProvider(Protocol):
    """What the corpus needs from whatever turns text into vectors."""

    @property
    def model_id(self) -> str:
        """Return the identity recorded alongside every vector this produces."""

    @property
    def dimension(self) -> int:
        """Return the fixed length of the vectors this produces."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in order."""


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity, or 0.0 when either vector has no magnitude."""
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class HashingEmbedder:
    """A deterministic lexical projection. Runs anywhere, understands nothing.

    Tokens are hashed into a fixed number of buckets and the counts are L2
    normalised. Two chunks sharing vocabulary land near each other; two chunks
    meaning the same thing in different words do not. That is a real limitation,
    not a temporary one, and it is why this is the fallback rather than the
    default for a deployment that cares about recall.
    """

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    @property
    def model_id(self) -> str:
        """Return the identity of this projection, including its width."""
        return f"hashing-v1-{self._dimension}"

    @property
    def dimension(self) -> int:
        """Return the vector width."""
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one hashed, normalised vector per text."""
        return [self._project(text) for text in texts]

    def _project(self, text: str) -> list[float]:
        """Return the normalised bucket counts for one text."""
        vector = [0.0] * self._dimension
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dimension
            vector[bucket] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0.0:
            return vector
        return [value / magnitude for value in vector]


class HttpEmbedder:
    """Calls an embedding service over HTTP.

    The contract is deliberately small, so any service can satisfy it:

        POST {url}
        {"texts": ["...", "..."]}
        -> {"model_id": "...", "dimension": 384, "embeddings": [[...], [...]]}

    A dimension that disagrees with what was configured is an error rather than
    something to coerce: it means the service is running a different model than
    the corpus was embedded with, and the vectors are not comparable.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        model_id: str,
        dimension: int,
        timeout_s: float = 30.0,
    ) -> None:
        self._client = client
        self._url = url
        self._model_id = model_id
        self._dimension = dimension
        self._timeout_s = timeout_s

    @property
    def model_id(self) -> str:
        """Return the configured model identity."""
        return self._model_id

    @property
    def dimension(self) -> int:
        """Return the configured vector width."""
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return vectors from the service, or raise EmbeddingError."""
        if not texts:
            return []
        try:
            response = await self._client.post(
                self._url, json={"texts": texts}, timeout=self._timeout_s
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingError(f"Embedding service call failed: {exc}") from exc

        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError("Embedding service returned the wrong number of vectors")
        reported = int(body.get("dimension", self._dimension))
        if reported != self._dimension:
            raise EmbeddingError(
                f"Embedding service reports dimension {reported}, corpus expects "
                f"{self._dimension}. Vectors from different models are not comparable."
            )
        return [[float(value) for value in vector] for vector in vectors]
