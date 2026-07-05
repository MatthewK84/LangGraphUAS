# sUAS Intelligent Mission Planner

An async AI orchestration and deterministic physics engine for small unmanned
aircraft system (sUAS) flight planning. A LangGraph state machine coordinates
validation, live weather, deterministic safety math, and a language-model
safety brief. A Next.js dashboard drives it.

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

## API

`GET /health` returns a liveness payload.

`POST /api/plan` accepts a validated mission request and returns the go/no-go
result, weather, deterministic calculations, a report, and the `thread_id`.

```json
{
  "aircraft_id": "DJI_M350",
  "payload_id": "Zenmuse_H30T",
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
    db/             async engine, ORM models, repository, seed
    graph/          state, nodes, checkpointer, workflow
    schemas/        pydantic domain, request, and response models
    services/       async weather and report clients
    config.py       typed settings
    main.py         app factory and lifespan
  tests/            unit, graph, and API tests
frontend/
  src/
    app/            App Router pages and UI components
    lib/            typed API client, geolocation, shared types
docker-compose.yml
```

## License

MIT. See `LICENSE`.
