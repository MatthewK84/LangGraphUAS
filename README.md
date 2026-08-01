# sUAS Intelligent Mission Planner

An async AI orchestration and deterministic physics engine for small unmanned
aircraft system (sUAS) flight planning. A LangGraph state machine coordinates
validation, live weather, deterministic safety math, and a language-model
safety brief. A Next.js dashboard drives it. The reference data covers a set of
DIU/DCMA Blue UAS (NDAA-compliant) multirotor platforms.

Supported on Python 3.10, 3.11, and 3.12. CI verifies all three.

## Architecture

- **Frontend**: Next.js 14 (App Router, standalone output), TypeScript strict, TailwindCSS.
- **Backend**: FastAPI on Python 3.10 to 3.12, fully async request path.
- **Orchestration**: LangGraph 1.x `StateGraph` with a conditional edge and durable checkpointing.
- **Language model**: `langchain-openai` `ChatOpenAI`, called with `ainvoke`, timeout, and bounded retries.
- **Database**: PostgreSQL 16 via async SQLAlchemy 2.0 (SQLite for local and tests).
- **Migrations**: Alembic, async-aware, verified against the ORM models in CI.
- **Persistence of graph state**: `AsyncPostgresSaver` in production, `InMemorySaver` otherwise.
- **Observability**: request correlation, JSON logs, Prometheus metrics, split liveness and readiness.
- **Deployment**: Docker Compose with health checks and non-root images.

### Graph design

The graph is defined in `backend/suas/graph/`. Nodes are built by factories that
receive dependencies explicitly, so no node relies on global state and each is
unit testable. The flow is:

```
START -> validate -> (conditional) -> weather -> calculations -> report -> END
                          \-> report (when validation fails)
```

State holds only JSON-native values. Pydantic models are dumped to dictionaries
before entering state, which keeps checkpoint serialization simple and safe.
The container sets `LANGGRAPH_STRICT_MSGPACK=true` to restrict checkpoint
deserialization to known-safe types.

Every request supplies a `thread_id`. The checkpointer persists state per thread,
so `GET /api/plan/{thread_id}` can retrieve a prior assessment and a follow-up
request can resume the same conversation.

## Quickstart (Docker)

1. Copy `.env.example` to `.env` and set at least `POSTGRES_PASSWORD`. Add
   `OPENAI_API_KEY` to enable the model narrative (optional).
2. Run `docker compose up --build`.
3. Open `http://localhost:3000`.

Without an `OPENAI_API_KEY`, the app still runs. The report node returns a
deterministic go/no-go summary instead of a model narrative.

## Local development

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head                 # optional locally; the app can self-create schema
uvicorn suas.main:app --reload        # serves on :8000, defaults to local SQLite
```

Frontend:

```bash
cd frontend
npm install
npm run dev                           # serves on :3000
```

Optional git hooks:

```bash
pre-commit install
```

## Configuration

Backend variables use the `SUAS_` prefix. Compose maps friendly names to them.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUAS_DATABASE_URL` | `sqlite+aiosqlite:///./suas_local.db` | Async SQLAlchemy URL. Postgres enables the durable checkpointer. |
| `SUAS_OPENAI_API_KEY` | empty | Enables the model-generated report. |
| `SUAS_OPENAI_MODEL` | `gpt-4o-mini` | Chat model name. |
| `SUAS_API_KEY` | empty | When set, planning endpoints require header `X-API-Key`. |
| `SUAS_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins. |
| `SUAS_LOG_LEVEL` | `INFO` | Root log level. |
| `SUAS_JSON_LOGS` | `true` | Emit structured JSON logs. Set false for readable local output. |
| `SUAS_BATTERY_RESERVE_PERCENT` | `20` | Reserve withheld from usable battery capacity. |
| `SUAS_RATE_LIMIT_REQUESTS` | `30` | Requests allowed per window, per client, per worker. |
| `SUAS_RATE_LIMIT_WINDOW_S` | `60` | Rate limit window in seconds. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Browser-reachable backend URL, baked at build time. |

## Platforms and payloads

Reference data is bundled at `backend/suas/data/` and seeds into the database on
startup (idempotent). The frontend fetches the catalog from the API at runtime,
so the dropdowns cannot drift from the data the backend actually holds.

Aircraft: `Skydio_X10D`, `Skydio_X2D`, `Parrot_ANAFI_USA`, `Teal_Golden_Eagle`,
`Freefly_Astro_Max`, `Freefly_Alta_X`, `Inspired_Flight_IF1200A`.

Payloads: `None`, `FLIR_Hadron_640R`, `Sony_ILX_LR1`, `Nextvision_Raptor`,
`Workswell_WIRIS_Ent`, `Trillium_HD40_LV`.

The X10D carries an integrated sensor suite, so its external payload capacity is
0; pairing it with any payload other than `None` yields a negative payload margin
and a NO-GO, which is the correct result. For a combination with real payload
headroom, select `Freefly_Astro_Max`.

### Data provenance

Each aircraft field is published, estimated, or derived:

- Published: weight, max payload, max wind, and operating temperature, from
  manufacturer or reputable spec sources.
- Estimated: `battery_wh` where a manufacturer does not state pack energy, and
  nominal cruise speed (roughly 0.6 to 0.7 of published max speed).
- Derived: the two power fields, by
  `hover_power_w = battery_wh / no_payload_endurance_hours` and
  `cruise_power_w = 0.90 * hover_power_w`.

The power fields are engineering estimates, not measurements. Replace them with
real power logs before operational use. Treat the `Freefly_Alta_X` power values
and the `Inspired_Flight_IF1200A` `battery_wh` (which assumes a 12S pack) as the
softest numbers. All payload `power_draw_w` values are estimates. For the
authoritative live roster, cross-check `bluelist.dcma.mil`.

## API

### Operations

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness. Touches no dependencies. |
| `GET` | `/ready` | Readiness. Executes a real database query; returns 503 when unavailable. |
| `GET` | `/metrics` | Prometheus text exposition: request counts, latency, plan outcomes, weather provenance. |

### Catalog

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/aircraft` | Selectable airframes. Drives the client dropdown. |
| `GET` | `/api/payloads` | Selectable payloads. Drives the client dropdown. |

### Planning

`POST /api/plan` accepts a validated mission request and returns the go/no-go
result, weather, deterministic calculations, a report, the `thread_id`, and any
degraded-input warnings.

```json
{
  "aircraft_id": "Skydio_X10D",
  "payload_id": "None",
  "mission_params": {
    "distance_m": 5000,
    "hover_time_s": 600,
    "target_altitude_m": 120,
    "elevation_m": 0,
    "latitude": 34.0,
    "longitude": -80.0
  },
  "thread_id": null
}
```

`elevation_m` is the launch point's elevation above sea level and
`target_altitude_m` is the planned operating height above that launch point
(AGL). Density altitude is reported for the operating altitude, not the field:
the surface temperature is extrapolated upward with the ISA lapse rate before
the deviation from standard is applied. Under a standard lapse rate that means
planning `h` meters higher raises reported density altitude by exactly `h`.

`GET /api/plan/{thread_id}` returns the persisted state for a prior mission
thread, or `found: false` when the thread is unknown.

Every response carries an `X-Request-ID` header. Supply your own to correlate a
client trace with server logs; one is generated when absent.

### Degraded inputs

When the weather provider cannot be reached after retries, the engine proceeds
with fallback values rather than failing the request, but it never presents them
as live data. The reading is tagged `source: "fallback"`, the response sets
`degraded: true` with an explicit warning, and the dashboard renders an amber
banner. Treat any degraded plan as advisory and confirm conditions independently.

## Testing and quality gates

Backend:

```bash
cd backend
ruff check suas tests alembic scripts   # lint
ruff format --check suas tests          # formatting
mypy suas                               # strict type check
pytest -q --cov=suas --cov-fail-under=80
alembic upgrade head && alembic check   # migrations apply and match models
python scripts/smoke_check.py           # boots the real lifespan end to end
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run lint
npm run build
```

CI runs the backend gates across Python 3.10, 3.11, and 3.12, plus a Postgres
integration job (real migrations and startup smoke check), a `pip-audit`
dependency audit, the frontend gates, and Docker image builds for both services.
See `.github/workflows/ci.yml`.

## Coding standards

All Python, JavaScript, and TypeScript follows a strict, safety-critical style
adapted from NASA's Power of Ten: simple control flow, minimal shared state, no
unsafe features, tight scoping, static analysis with no suppressions in domain
code, no deep recursion, small single-purpose functions, explicit data shapes,
standardized error handling, and no builtin or prototype mutation. Configuration
lives in `backend/pyproject.toml` (ruff + mypy strict) and
`frontend/eslint.config.mjs` plus `frontend/tsconfig.json`.

Narrow, documented exceptions: two thin LangGraph wiring modules relax specific
mypy generic-interop codes, Alembic's generated migration environment is excluded
from strict typing, and CI scripts may write to stdout. All domain logic
(calculations, schemas, services, database, API) stays fully strict.

## Project structure

```
backend/
  alembic/          async migration environment and versioned migrations
  scripts/          smoke_check.py, run in CI against Postgres
  suas/
    api/            routes, security, rate limiting, observability, error handlers
    calculations/   pure physics, battery, and assessment functions
    data/           bundled Blue UAS aircraft and payload reference data
    db/             async engine, ORM models, repository, seed
    graph/          state, nodes, checkpointer, workflow
    schemas/        pydantic domain, request, and response models
    services/       async weather and report clients
    config.py       typed settings
    logging_config.py  JSON formatter and request-id correlation
    main.py         app factory and lifespan
  tests/            unit, service, graph, observability, and API tests
frontend/
  src/
    app/            App Router pages and UI components
    lib/            typed API client, catalog hook, geolocation, shared types
docker-compose.yml
```

## Operational notes

- **Rate limiting is per process.** Each worker enforces its own budget, so the
  effective cluster ceiling is `SUAS_RATE_LIMIT_REQUESTS * worker_count`. It is a
  spend guard against runaway model calls, not an exact global quota. Put a
  shared limiter (Redis or the ingress) in front when you need a hard ceiling.
- **Metrics are per process too.** Scrape every replica and aggregate in
  Prometheus rather than assuming one endpoint reports the whole fleet.
- **Migrations are not run automatically on boot.** The app can create its own
  schema for convenience, but in production run `alembic upgrade head` as a
  deploy step so schema changes are explicit and auditable.
- **Reference power figures are estimates.** See Data provenance. Swap in
  measured values before relying on the energy budget operationally.

## Known limitations

- **Next.js ESLint plugin is disabled.** The `@next/eslint-plugin-next` v14 rules
  crash under ESLint 9 flat config, so Next-specific lint is off. Re-add it after
  moving to Next 15, which is flat-config compatible.
- **`pip-audit --strict` can fail on transitive advisories** outside this
  project's control. Pin a specific `--ignore-vuln` with a written rationale
  rather than disabling the job.

## License

MIT. See `LICENSE`.
