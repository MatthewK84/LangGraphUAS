# sUAS Intelligent Mission Planner

An async AI orchestration and deterministic physics engine for small unmanned
aircraft system (sUAS) flight planning. A LangGraph state machine coordinates
validation, live weather, deterministic safety math, and a language-model
safety brief. A Next.js dashboard drives it. The reference data covers a set of
DIU/DCMA Blue UAS (NDAA-compliant) multirotor platforms.

## Architecture

- **Frontend**: Next.js 14 (App Router, standalone output), TypeScript strict, TailwindCSS.
- **Backend**: FastAPI on Python 3.11, fully async request path.
- **Orchestration**: LangGraph 1.x `StateGraph` with a conditional edge and durable checkpointing.
- **Language model**: `langchain-openai` `ChatOpenAI`, called with `ainvoke`, timeout, and bounded retries.
- **Database**: PostgreSQL 16 via async SQLAlchemy 2.0 (SQLite for local and tests).
- **Persistence of graph state**: `AsyncPostgresSaver` in production, `InMemorySaver` otherwise.
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
so a follow-up request can resume the same conversation. The API returns the
`thread_id` for the client to reuse.

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
uvicorn suas.main:app --reload      # serves on :8000, defaults to local SQLite
```

Frontend:

```bash
cd frontend
npm install
npm run dev                          # serves on :3000
```

## Configuration

Backend variables use the `SUAS_` prefix. Compose maps friendly names to them.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SUAS_DATABASE_URL` | `sqlite+aiosqlite:///./suas_local.db` | Async SQLAlchemy URL. Postgres enables the durable checkpointer. |
| `SUAS_OPENAI_API_KEY` | empty | Enables the model-generated report. |
| `SUAS_OPENAI_MODEL` | `gpt-4o-mini` | Chat model name. |
| `SUAS_API_KEY` | empty | When set, `/api/plan` requires header `X-API-Key`. |
| `SUAS_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins. |
| `SUAS_LOG_LEVEL` | `INFO` | Root log level. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Browser-reachable backend URL, baked at build time. |

## Platforms and payloads

Reference data is bundled at `backend/suas/data/` and seeds into the database on
startup (idempotent). The frontend dropdowns and defaults resolve against these
same keys.

Aircraft: `Skydio_X10D`, `Skydio_X2D`, `Parrot_ANAFI_USA`, `Teal_Golden_Eagle`,
`Freefly_Astro_Max`, `Freefly_Alta_X`, `Inspired_Flight_IF1200A`.

Payloads: `None`, `FLIR_Hadron_640R`, `Sony_ILX_LR1`, `Nextvision_Raptor`,
`Workswell_WIRIS_Ent`, `Trillium_HD40_LV`.

The default selection is `Skydio_X10D` with `None`. The X10D carries an
integrated sensor suite, so its external payload capacity is 0; pairing it with
any payload other than `None` yields a negative payload margin and a NO-GO,
which is the correct result. For a default that lands on a clean GO, select
`Freefly_Astro_Max` with `Sony_ILX_LR1`.

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

`GET /health` returns a liveness payload.

`POST /api/plan` accepts a validated mission request and returns the go/no-go
result, weather, deterministic calculations, a report, and the `thread_id`.

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

## Testing and quality gates

Backend:

```bash
cd backend
ruff check suas tests     # lint
mypy suas                 # strict type check
pytest -q                 # unit + graph + API tests
```

Frontend:

```bash
cd frontend
npm run typecheck         # tsc strict
npm run lint              # eslint strict
npm run build             # production build
```

CI runs all of the above on every push and pull request. See
`.github/workflows/ci.yml`.

## Coding standards

All Python, JavaScript, and TypeScript follows a strict, safety-critical style
adapted from NASA's Power of Ten: simple control flow, minimal shared state, no
unsafe features, tight scoping, static analysis with no suppressions in domain
code, no deep recursion, small single-purpose functions, explicit data shapes,
standardized error handling, and no builtin or prototype mutation. Configuration
lives in `backend/pyproject.toml` (ruff + mypy strict) and
`frontend/eslint.config.mjs` plus `frontend/tsconfig.json`.

Two thin LangGraph wiring modules relax specific mypy generic-interop codes only.
All domain logic (calculations, schemas, services, database) stays fully strict.

## Project structure

```
backend/
  suas/
    api/            routes, security, request dependencies
    calculations/   pure physics, battery, and assessment functions
    data/           bundled Blue UAS aircraft and payload reference data
    db/             async engine, ORM models, repository, seed
    graph/          state, nodes, checkpointer, workflow
    schemas/        pydantic domain, request, and response models
    config.py       typed settings
    main.py         app factory and lifespan
  tests/            unit, graph, and API tests
frontend/
  src/
    app/            App Router pages and UI components
    lib/            typed API client, geolocation, shared types
docker-compose.yml
```

## Known limitations and roadmap

- **Reference power figures are estimates.** See Data provenance above. Swap in
  measured power draw before relying on the energy budget operationally.
- **Next.js ESLint plugin is disabled.** The `@next/eslint-plugin-next` v14
  rules crash under ESLint 9 flat config, so Next-specific lint is off. Re-add it
  after moving to Next 15, which is flat-config compatible.
- **No database migrations yet.** Schema comes from `create_all`. Add Alembic
  before the database holds data whose schema must evolve.

## License

MIT. See `LICENSE`.
