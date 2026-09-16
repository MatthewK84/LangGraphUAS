# Deploying on Railway

A from-zero runbook. Follow it in order; each step ends with something you can
check, so a mistake surfaces at the step that caused it rather than three steps
later as a 502.

## The shape of the deployment

One public HTTPS endpoint. Everything else is reachable only from inside the
Railway project.

```
        internet
           |
           | HTTPS  (the only public domain)
           v
    +--------------+
    |  dashboard   |   Next.js. Holds the API key. Talks to nothing else.
    +--------------+
           |
           | private network, IPv6
           v
    +--------------+        +--------------+
    |   planner    |------->|  embeddings  |   private, optional
    |   (FastAPI)  |        +--------------+
    +--------------+
           |
           | private network
           v
    +--------------+
    |   Postgres   |   private
    +--------------+
```

The browser only ever talks to the dashboard's own origin. The dashboard's
server-side route handlers are the only thing that talks to the planner, and
they attach the API key. This is why `BACKEND_API_KEY` is not prefixed
`NEXT_PUBLIC_`: Next.js inlines prefixed variables into the client bundle, and
this key must never reach a browser.

Two consequences worth stating, because they remove work:

- **The planner needs no public domain.** Do not generate one. An API with no
  route at `/` invites exactly the "404 on the homepage" confusion, and a public
  domain puts `/docs`, `/health` and `/metrics` in front of anyone who finds the
  URL.
- **CORS stops mattering.** No browser makes a cross-origin call, so
  `SUAS_CORS_ORIGINS` can keep its default. Set it only if you later expose the
  API directly.

## Two facts that decide whether the wiring works

Both caused real failures in this project. Everything in the runbook follows
from them.

**Railway's private network is IPv6-only.** `<service>.railway.internal`
resolves to an AAAA record. A server bound to `0.0.0.0` listens on IPv4 alone,
so a caller connects to an address with nothing behind it and the connection is
refused. The planner and the embedding service both bind `::` where the kernel
has IPv6 (see their entrypoints); you do not need to configure this, but it is
why a service that "is running" can still be unreachable.

**Railway assigns the port.** Each service binds `$PORT`. Never hardcode a port
in a service reference; use `${{service.PORT}}`. A literal `:8000` was correct
here until Railway picked 8080.

## 1. Postgres

**+ New -> Database -> Add PostgreSQL.** Nothing to configure.

Stock Postgres is enough: this project stores embeddings as JSON text and
computes similarity in the application, so no extension is required. See "Why
not pgvector" below.

Do not generate a public domain for it.

> **Check:** the service shows as deployed and its Variables tab lists
> `DATABASE_URL`.

## 2. The planner (API)

**+ New -> GitHub Repo -> this repository.**

| Setting | Value |
| --- | --- |
| Settings -> Source -> Root Directory | **leave empty** |
| Settings -> Networking | **do not** generate a domain |

The empty root directory is deliberate and load-bearing. Railway resolves
`dockerfilePath` relative to the root directory; with it empty, `railway.json`
at the repository root resolves `backend/Dockerfile` and the build context is
the repository root, which is what that Dockerfile is written for. Setting it to
`backend` breaks the build -- Railway would look for `backend/backend/Dockerfile`.

Rename the service something stable, e.g. `planner`. Other services reference it
by name, and a reference to a name that does not exist resolves to an **empty
string** rather than failing.

Variables:

| Variable | Value |
| --- | --- |
| `SUAS_DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
| `SUAS_API_KEY` | a long random string you generate (see below) |
| `SUAS_OPENAI_API_KEY` | optional; without it briefs are deterministic text |

Reference the database variable directly, with no hand-editing. Railway's value
is `postgresql://`, which SQLAlchemy maps to psycopg2 -- a driver this project
does not install, and a synchronous one that could not serve the async engine
anyway. `suas.config.normalise_database_url` rewrites the scheme on the way in.
A plain `DATABASE_URL` is read too, so a linked Postgres service is sufficient
on its own; where both exist, `SUAS_DATABASE_URL` wins.

Generate the API key with either of these, and keep it -- the dashboard needs
the same value:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
openssl rand -base64 32
```

The key guards `/api/plan`, `/api/logs`, `/api/plan/{id}/ack`, `/api/replan` and
`/api/plan/{id}`. Leave it unset and authentication is a no-op on all of them,
including the acknowledgement endpoint -- the operator sign-off the whole design
treats as its trust boundary. `/health` and `/ready` stay unguarded so the
platform can probe them.

The image sets `SUAS_REQUIRE_POSTGRES=true`, so a missing database URL fails at
startup naming the variable rather than falling back to a SQLite file the
container cannot write.

> **Check** the deploy log, reading the first lines rather than the last:
> - `Running upgrade ... -> 0010` on the first deploy (migrations ran)
> - `Uvicorn running on http://[::]:8080` -- **square brackets** mean it bound
>   IPv6, which is what the private network needs
> - `Database: postgresql+psycopg://...railway.internal:5432/railway`
> - `Using Postgres checkpointer`
> - **no** `API authentication is disabled` warning
> - `Application startup complete`

## 3. The embedding model (optional, but do it before ingest)

**+ New -> GitHub Repo -> this repository**, Root Directory
`services/embeddings`. No public domain.

FastAPI wrapping `sentence-transformers/all-MiniLM-L6-v2`, with the weights
baked into the image so the first request after a deploy does not pay a cold
download. The image is large and the first build is slow.

Then, on the **planner**:

| Variable | Value |
| --- | --- |
| `SUAS_EMBEDDING_PROVIDER` | `http` |
| `SUAS_EMBEDDING_URL` | `http://${{embeddings.RAILWAY_PRIVATE_DOMAIN}}:${{embeddings.PORT}}/embed` |
| `SUAS_EMBEDDING_MODEL_ID` | `sentence-transformers/all-MiniLM-L6-v2` |
| `SUAS_EMBEDDING_DIMENSION` | `384` |

**Without this service the planner still runs.** It falls back to a hashing
projection that matches shared vocabulary rather than shared meaning -- a real
reduction in recall. `SUAS_EMBEDDING_PROVIDER=http` with an empty URL logs an
error rather than degrading silently.

**Changing the model means re-ingesting.** Every chunk records the model that
embedded it, and rows from another model are skipped rather than scored, because
a similarity between two models' vectors is a number with no meaning.

Decide on the embedder **before** step 5. Ingesting first and adding the model
afterwards means ingesting twice.

## 4. The dashboard -- the only public service

**+ New -> GitHub Repo -> this repository.**

| Setting | Value |
| --- | --- |
| Settings -> Source -> Root Directory | `frontend` |
| Settings -> Networking | **Generate Domain** -- this one, and only this one |

Variables:

| Variable | Value |
| --- | --- |
| `BACKEND_API_URL` | `http://${{planner.RAILWAY_PRIVATE_DOMAIN}}:${{planner.PORT}}` |
| `BACKEND_API_KEY` | the **same value** as the planner's `SUAS_API_KEY` |

Substitute your planner service's actual name for `planner` in that reference.
`http`, not `https`: the private network is unencrypted by design and there is no
certificate for `.railway.internal`.

> **Check:** open the generated domain. The form renders and the aircraft and
> payload dropdowns populate with 7 airframes and 6 payloads. If the dropdowns
> are empty with "Backend returned status 502", see Troubleshooting.

## 5. Ingest the corpus

Until this runs, retrieval returns nothing and citations read `unconfirmed`.
Plans still work -- the corpus is not the oracle, the calculator is -- but no
brief will cite a document.

Ingest is offline by design: the planner never parses a document. Run it from a
checkout against a connection string that reaches Railway from your machine. The
private URL will not work from a laptop; use the public connection string from
the Postgres service's **Connect** tab (Railway exposes one through a TCP
proxy).

```bash
SUAS_DATABASE_URL='<public connection string from the Connect tab>' \
  python3 backend/scripts/ingest_corpus.py --corpus corpus
```

Anything quarantined is reported, and blocks operational mode for the
configuration it belongs to until a person clears it.

If you enabled the TCP proxy only for this, turn it off afterwards.

## 6. Verify end to end

1. Open the dashboard's public URL.
2. Pick an airframe and payload, leave the defaults, **Analyze flight
   feasibility**.
3. You should get a decision, an energy budget, and an acknowledgement prompt.

Decisions and numbers come from `backend/suas/calculations/`, never from a
model, so step 3 works with no `SUAS_OPENAI_API_KEY` set. Without that key the
prose is deterministic template text; the numbers are identical either way.

## Troubleshooting

Read these by signature, not by guesswork.

**Dashboard shows "Backend returned status 502".** The dashboard reached you; its
server-side call to the planner did not. That 502 is generated by the dashboard
when its `fetch` **throws**, so it means unreachable, not an error response -- a
wrong API key surfaces as **401**, not this. Check in order:

1. `BACKEND_API_URL` names the planner service **exactly** as Railway spells it.
   A wrong name resolves to an empty string and the dashboard calls its own origin.
2. The port is `${{planner.PORT}}`, not a literal.
3. The planner's log says `http://[::]:PORT`, not `0.0.0.0`.

**Dashboard shows 401.** `BACKEND_API_KEY` does not match `SUAS_API_KEY` exactly.
Check for a trailing space or newline from copy-paste; the comparison is exact.

**Build fails with `"/alembic.ini": not found`,** or any `COPY` failing on a
file that is plainly committed. The build context is not what the Dockerfile
expects. Check the planner's Root Directory is empty and `railway.json` is at
the repository root. The leading slash in `"/alembic.ini"` means "the context
root has no alembic.ini", which is true of the repository root and false of
`backend/`. Two things disguise this: BuildKit runs `COPY` steps in parallel and
aborts siblings on the first failure, so only one of several wrong paths reports
an error; and unrelated steps report `cached` from an older build, which makes a
path fault look like a cache fault.

**Startup fails naming `SUAS_DATABASE_URL`.** The variable did not reach the
service. If this is a service you meant to be the dashboard, its Root Directory
is empty, so Railway built the planner from the root `railway.json` instead --
set it to `frontend`.

**`{"detail":"Not Found"}` in a browser.** You are on the planner, which has no
route at `/`. It is a JSON API. Use `/ready`, or `/docs` for the browsable UI.
If you can reach it from a browser at all, it has a public domain it does not
need.

**502 with no traceback and the log shows a hardcoded port.** Something is
overriding the image's entrypoint -- check for a Start Command in the service
settings. The image owns startup; `railway.json` carries no `startCommand`.

**Briefs are deterministic fallback text.** `SUAS_OPENAI_API_KEY` is unset. A
supported state, not an error: no model writes a number.

**Retrieval is poor and `SUAS_EMBEDDING_PROVIDER` is unset.** The planner is
using the hashing fallback. See step 3.

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
