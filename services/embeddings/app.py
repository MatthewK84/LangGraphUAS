"""An embedding service.

One endpoint, one job. Deployed as its own Railway service so the model lives
where model-sized things belong: with its own image, its own memory limit, and
its own scaling, reached by the planner over HTTP.

The contract is the one `suas.rag.embedding.HttpEmbedder` expects:

    POST /embed  {"texts": ["...", "..."]}
    -> {"model_id": "...", "dimension": 384, "embeddings": [[...], [...]]}

`dimension` is returned on every response on purpose. The planner refuses
vectors whose width disagrees with what its corpus was embedded at, because
vectors from two different models are not comparable and quietly mixing them
produces a retriever that is subtly and unfixably wrong.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Final

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_ID: Final[str] = os.environ.get("EMBEDDING_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2")
DIMENSION: Final[int] = int(os.environ.get("EMBEDDING_DIMENSION", "384"))
MAX_TEXTS: Final[int] = int(os.environ.get("EMBEDDING_MAX_TEXTS", "256"))
MAX_CHARS: Final[int] = int(os.environ.get("EMBEDDING_MAX_CHARS", "8000"))

app = FastAPI(title="suas-embeddings", version="1.0.0")


class EmbedRequest(BaseModel):
    """A batch of texts to embed."""

    texts: list[str] = Field(min_length=1, max_length=MAX_TEXTS)


class EmbedResponse(BaseModel):
    """Vectors, with the identity and width that produced them."""

    model_id: str
    dimension: int
    embeddings: list[list[float]]


@lru_cache(maxsize=1)
def _model() -> Any:
    """Load the model once per process.

    Imported lazily so the module can be introspected, and the image built,
    without pulling a few hundred megabytes of weights into every context that
    merely imports it.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_ID)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness. Deliberately does not load the model."""
    return {"status": "ok", "model_id": MODEL_ID}


@app.get("/ready")
def ready() -> dict[str, Any]:
    """Readiness. Loads the model, so a cold service reports not-ready until it can serve."""
    try:
        width = int(_model().get_sentence_embedding_dimension())
    except Exception as exc:  # noqa: BLE001 - readiness reports, it does not raise
        return {"ready": False, "detail": str(exc)}
    return {"ready": True, "model_id": MODEL_ID, "dimension": width}


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest) -> EmbedResponse:
    """Return one vector per input text, in order."""
    texts = [text[:MAX_CHARS] for text in request.texts]
    try:
        vectors = _model().encode(texts, normalize_embeddings=True).tolist()
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a 503
        raise HTTPException(status_code=503, detail=f"Embedding failed: {exc}") from exc

    width = len(vectors[0]) if vectors else DIMENSION
    if width != DIMENSION:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Model produced {width}-dimensional vectors but this service is "
                f"configured for {DIMENSION}. Set EMBEDDING_DIMENSION to match the model."
            ),
        )
    return EmbedResponse(model_id=MODEL_ID, dimension=width, embeddings=vectors)
