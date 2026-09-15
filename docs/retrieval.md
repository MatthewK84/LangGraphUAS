# Retrieval — hybrid search

> **Implemented without pgvector.** This document specified pgvector with an
> HNSW index. The shipped implementation stores embeddings as JSON text and
> computes cosine over the filtered candidate set in the application. At this
> corpus size the filter reduces candidates to tens of rows, so an index buys
> nothing measurable while costing a required extension, a vector width baked
> into the schema, and a migration that fails on stock Postgres. The same schema
> now runs on Railway's stock Postgres, on a pgvector image, and on SQLite with
> no branch in the code. Revisit at roughly ten thousand chunks per
> configuration, or when retrieval shows up in the plan's p95. Everything below
> about filtering, fusion, and ingest still holds; the SQL is illustrative.

Retrieval answers "what does the manufacturer or the list say about this field?"
It never decides anything. See ADR-003.

## Why hybrid

Datasheets are full of tokens embeddings smear: `X10D`, `IF1200A`, `12S`,
`Hadron 640R`, `-10 °C`, `NDAA 848`. Pure vector search misses them. Pure
full-text misses "pack minimum at takeoff" when the PDF says "do not launch
below 10 C battery temperature". Run both, fuse by rank, and filter structurally
first.

## Query plan for `cite_limits`

```
1. Require airframe_config_id or payload_id. No global semantic search in v1.
2. If field_path is known -> filter to those chunks, then hybrid among them.
3. If not -> hybrid within that configuration only.
4. k_retr = 20 per leg, return top 4 after fusion.
5. Both legs empty -> citation_status = unconfirmed, calculator untouched.
```

The operator's free-text mission is never embedded and searched across the
corpus. That is the path by which an injected PDF becomes the brief.

## Schema

Same Postgres instance as `missions` and the checkpoint tables, separate `rag`
schema so a compromised ingest job cannot reach LangGraph's tables.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE rag.documents (
  document_id     uuid PRIMARY KEY,
  sha256          char(64) NOT NULL UNIQUE,
  source_url      text NOT NULL,
  retrieved_at    timestamptz NOT NULL,
  license         text,
  kind            text NOT NULL CHECK (kind IN
                    ('datasheet','blue_list','procedure','eval_trap')),
  embedding_model text NOT NULL,
  embedding_dim   int NOT NULL
);

CREATE TABLE rag.chunks (
  chunk_id            uuid PRIMARY KEY,
  document_id         uuid NOT NULL REFERENCES rag.documents,
  airframe_config_id  text,
  payload_id          text,
  field_path          text,          -- e.g. battery.pack_min_takeoff_c
  page                int,
  text                text NOT NULL,
  embedding           vector(1024) NOT NULL,
  fts                 tsvector GENERATED ALWAYS AS
                        (to_tsvector('english', text)) STORED,
  ingested_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX chunks_hnsw ON rag.chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX chunks_fts_gin ON rag.chunks USING gin (fts);
CREATE INDEX chunks_trgm   ON rag.chunks USING gin (text gin_trgm_ops);
CREATE INDEX chunks_filter ON rag.chunks (airframe_config_id, payload_id, field_path);
```

The generated `tsvector` stays in sync with no triggers. `chunks_filter` is
mandatory: both hybrid legs must apply the same `WHERE`, or fusion mixes
airframes. `kind = 'eval_trap'` exists only in the eval database; production
ingest refuses it.

## Chunking

Chunk by **field**, not by token count. One chunk should support one numeric
field or one procedure sentence, carrying `field_path`, `page`, `url`,
`retrieved_at`, and the document `sha256`. A manual field map beats clever
segmentation at this corpus size.

## Fusion

Do not add cosine distance to `ts_rank`; the scales are unrelated. Use
reciprocal rank fusion with `k = 60` and equal weights, and do not tune `k`
until `docs/rag-eval.md` produces recall numbers to tune against.

```sql
WITH q AS (
  SELECT websearch_to_tsquery('english', $query) AS tsq, $emb::vector AS emb
),
vec AS (
  SELECT c.chunk_id,
         row_number() OVER (ORDER BY c.embedding <=> (SELECT emb FROM q)) AS rnk
  FROM rag.chunks c
  WHERE c.airframe_config_id = $config
    AND ($field_path IS NULL OR c.field_path = $field_path)
  ORDER BY c.embedding <=> (SELECT emb FROM q)
  LIMIT 20
),
fts AS (
  SELECT c.chunk_id,
         row_number() OVER (
           ORDER BY ts_rank_cd(c.fts, (SELECT tsq FROM q)) DESC) AS rnk
  FROM rag.chunks c
  WHERE c.airframe_config_id = $config
    AND ($field_path IS NULL OR c.field_path = $field_path)
    AND c.fts @@ (SELECT tsq FROM q)
  LIMIT 20
)
SELECT c.chunk_id, c.field_path, c.page, c.text, c.document_id,
       COALESCE(1.0/(60 + vec.rnk), 0) + COALESCE(1.0/(60 + fts.rnk), 0) AS rrf
FROM rag.chunks c
LEFT JOIN vec USING (chunk_id)
LEFT JOIN fts USING (chunk_id)
WHERE vec.chunk_id IS NOT NULL OR fts.chunk_id IS NOT NULL
ORDER BY rrf DESC
LIMIT 4;
```

`websearch_to_tsquery` so quoted phrases and exclusions cannot become syntax
errors. `<=>` matches the cosine HNSW index.

## Ingest

```
corpus/manifest.json
  -> verify sha256
  -> reject if the URL host is not in ALLOWED_HOSTS
  -> reject if the file is not in the manifest
  -> screen_chunk() per docs/injection-defense.md
  -> extract text by page, split to field_path chunks
  -> embed with the pinned model and dimension
  -> INSERT documents then chunks in one transaction
```

`ALLOWED_HOSTS` is the manufacturer domains actually retrieved from, plus
`bluelist.dcma.mil` and `diu.mil`. No cloud drives. No operator upload in v1.

Embedding happens offline in `backend/scripts/ingest_corpus.py`; the API process
never parses a PDF. `embedding_model` and `embedding_dim` are pinned in
`config.py` — mixing dimensions in one column is a production outage.

## When hybrid is skipped

| Case | Behavior |
|---|---|
| `field_path` set and <= 8 chunks match | Return those by `ts_rank` alone |
| Query is a model string (`IF1200A`) | Trigram/exact filter, no embedding |
| Retrieval error | `citation_status=unavailable`, plan still runs |
| Both legs empty | `unconfirmed`, calculator uses bundled JSON |

## Code layout

`backend/suas/rag/ingest.py`, `backend/suas/rag/retrieve.py`,
`backend/suas/graph/nodes.py::make_cite_limits_node`. The `cite_limits` node is
the only graph entry point into retrieval.

New dependencies: `pgvector` Python bindings. Nothing else.
