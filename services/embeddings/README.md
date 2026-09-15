# Embedding service

FastAPI wrapping `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions).
Deployed as its own service so the model lives where model-sized things belong:
its own image, its own memory limit, its own scaling.

```
POST /embed  {"texts": ["...", "..."]}
-> {"model_id": "...", "dimension": 384, "embeddings": [[...], [...]]}
```

`dimension` is returned on every response on purpose. The planner refuses vectors
whose width disagrees with what its corpus was embedded at, because vectors from
two different models are not comparable and quietly mixing them produces a
retriever that is subtly and unfixably wrong.

`GET /health` does not load the model, so it answers immediately for a platform
health check. `GET /ready` does load it, so a cold service reports not-ready
until it can actually serve.

Weights are baked into the image at build time. Without that, the first request
after every deploy pays a cold download, and a service that is slow exactly when
it is first used is one people route around.

Deployment, and how to point the planner at it, are in
[`../../docs/railway.md`](../../docs/railway.md).

## Not verified here

This service was written but never executed: the environment it was built in
could not download model weights. The HTTP contract is tested from the client
side against a scripted transport in `backend/tests/test_retrieval.py`; the model
loading and encoding path has not been run. Deploy it to a staging service and
hit `/ready` before pointing a planner at it.
