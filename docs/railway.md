# Deploying on Railway

Three services: the planner, Postgres, and — optionally — the embedding model.

## 1. Postgres

Add Railway's **Postgres** service. Stock Postgres is enough: this project stores
embeddings as JSON text and computes similarity in the application, so no
extension is required. See "Why not pgvector" below.

Railway sets `DATABASE_URL` on the service that references it. This project reads
`SUAS_DATABASE_URL` and expects the `postgresql+psycopg://` driver prefix, so set
it explicitly on the planner service:

```
SUAS_DATABASE_URL=${{Postgres.DATABASE_URL}}
```

then change the scheme to `postgresql+psycopg://`. Railway's variable is
`postgresql://`, which SQLAlchemy reads as psycopg2.

## 2. The planner

Deploy this repository and **leave the service's Root Directory empty**
(Settings -> Source). Railway resolves `dockerfilePath` relative to the root
directory, so with it empty, `railway.json` at the repository root resolves
`backend/Dockerfile` and the build context is the repository root.

That context is what `backend/Dockerfile` is written for: every `COPY` source in
it is prefixed `backend/`, and `.dockerignore` at the root bounds the upload.
Setting the Root Directory to `backend` breaks the build -- Railway would then
look for `backend/backend/Dockerfile`.

`railway.json` runs migrations before serving:

```
alembic upgrade head && uvicorn suas.main:app --host 0.0.0.0 --port ${PORT}
```

CI and `docker-compose.yml` build the same image the same way, from the same
context, so a green CI build is evidence about the image Railway builds.

The embedding service is different and deliberately so: it *does* set a root
directory (`services/embeddings`) and its `railway.json` lives inside it, because
it is a self-contained service whose Dockerfile needs nothing from the rest of
the repository.

Minimum variables:

| Variable | Value |
| --- | --- |
| `SUAS_DATABASE_URL` | `postgresql+psycopg://...` from the Postgres service |
| `SUAS_API_KEY` | A key of your choosing. Empty disables auth entirely. |
| `SUAS_OPENAI_API_KEY` | Optional. Without it, briefs fall back to deterministic text. |

Health check is `/health`; it touches nothing. `/ready` executes a real query and
returns 503 when the database or checkpointer is unavailable, which is what you
want Railway's healthcheck to *not* use during a migration.

## 3. The embedding model (optional)

`services/embeddings/` is a deployable service: FastAPI wrapping
`sentence-transformers/all-MiniLM-L6-v2`, with the weights baked into the image
so the first request after a deploy does not pay a cold download.

Deploy it as a **second service from this same repository** with root directory
`services/embeddings`. Then point the planner at it:

| Variable | Value |
| --- | --- |
| `SUAS_EMBEDDING_PROVIDER` | `http` |
| `SUAS_EMBEDDING_URL` | `http://${{embeddings.RAILWAY_PRIVATE_DOMAIN}}:8080/embed` |
| `SUAS_EMBEDDING_MODEL_ID` | `sentence-transformers/all-MiniLM-L6-v2` |
| `SUAS_EMBEDDING_DIMENSION` | `384` |

Use the private domain: the planner is the only thing that should reach it, and
a private URL keeps it off the public internet without any auth of its own.

**Without this service the planner still runs.** It falls back to a hashing
projection that matches shared vocabulary rather than shared meaning — see
`backend/suas/rag/embedding.py`. That is a real reduction in recall, and
`SUAS_EMBEDDING_PROVIDER=http` with an empty URL logs an error rather than
degrading silently.

**Changing the model means re-ingesting.** Every chunk records the model that
embedded it, and rows from another model are skipped rather than scored, because
a similarity between two models' vectors is a number with no meaning. After a
model change, re-run the ingest.

## 4. Ingest the corpus

Ingest is offline by design — the planner never parses a document. Run it from a
checkout with `SUAS_DATABASE_URL` pointed at the Railway database:

```bash
SUAS_DATABASE_URL='postgresql+psycopg://...' \
  python3 backend/scripts/ingest_corpus.py --corpus corpus
```

Anything quarantined is reported, and blocks operational mode for the
configuration it belongs to until a person clears it.

## Why not pgvector

Railway offers pgvector templates, and `docs/retrieval.md` originally specified
pgvector with an HNSW index. This implementation does not use it.

At this corpus size the filtered candidate set is tens of rows, not millions: a
structured `WHERE` on airframe and field already does the selecting, and cosine
over what survives costs microseconds. An HNSW index would add a required
extension, a fixed vector width baked into the schema, and a migration that fails
on stock Postgres — for no measurable gain at the scale this runs at.

The trade is recorded rather than assumed. Move to pgvector when the corpus
passes roughly ten thousand chunks per configuration, or when retrieval latency
shows up in the plan's p95. Until then, portable storage means the same schema
runs on Railway's stock Postgres, on a pgvector image, and on SQLite in
development, with no branch in the code.

## Troubleshooting

**`"/alembic.ini": not found`, or any `COPY` failing on a file that is plainly
committed.** The build context is not what the Dockerfile expects. Check the
Root Directory is empty and that `railway.json` is at the repository root.

Read the leading slash in that error: `"/alembic.ini"` is a path at the *context
root*, so the message is "the context root has no alembic.ini" -- which is true
of the repository root and false of `backend/`. It is not a missing file, and it
is not a stale cache. Two details make this failure read as something it is not:

- Only one `COPY` reports an error even when several are wrong. BuildKit runs
  them in parallel and aborts the siblings on the first failure, so the others
  show `0ms` and no error.
- Unrelated steps report `cached` from an older build, which makes the one
  failing step look like a cache fault rather than a path fault.

The way to confirm it is the context and not the file: `git ls-files` the path,
then compare against what the context root actually contains.

**Briefs come back as deterministic fallback text.** `SUAS_OPENAI_API_KEY` is
unset. That is a supported state, not an error -- the numbers are unaffected,
since no model writes them.

**Retrieval quality is poor and `SUAS_EMBEDDING_PROVIDER` is unset.** The
planner is using the hashing fallback. See section 3.
