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

### Authentication and the API key

The browser never holds a credential. It calls this app's own origin, and
server-side Next.js route handlers under `frontend/src/app/api/` proxy each
request to the backend, attaching `X-API-Key` from `BACKEND_API_KEY`. That
variable is deliberately not prefixed `NEXT_PUBLIC_`, so Next.js will not inline
it into the client bundle.

This replaces an earlier arrangement where the key was read from
`NEXT_PUBLIC_API_KEY` and shipped inside the JavaScript bundle, which meant
enabling auth published the key to every visitor. Only the Next.js server needs
network reach to the backend now; the backend does not have to be exposed to
browsers at all.

The key still authenticates the *deployment*, not individual users. There is no
per-user identity, so any caller who can reach the proxy can plan a mission and
can fetch any `thread_id` they know. Thread ids are UUIDv4 and so are not
practically enumerable, but put real authentication in front of this before
serving distinct tenants.

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
| `SUAS_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins. Only needed for non-browser clients now that the UI proxies server-side. |
| `SUAS_LOG_LEVEL` | `INFO` | Root log level. |
| `SUAS_JSON_LOGS` | `true` | Emit structured JSON logs. Set false for readable local output. |
| `SUAS_BATTERY_RESERVE_PERCENT` | `20` | Reserve withheld from usable battery capacity. |
| `SUAS_VERTICAL_SPEED_MPS` | `3` | Assumed climb and descent rate. |
| `SUAS_CLIMB_EFFICIENCY` | `0.6` | Propulsive efficiency for the climb energy term. |
| `SUAS_CHECKPOINT_RETENTION_DAYS` | `30` | Age at which graph checkpoints are purged. `0` disables retention. |
| `SUAS_RATE_LIMIT_REQUESTS` | `30` | Requests allowed per window, per client, per worker. |
| `SUAS_RATE_LIMIT_WINDOW_S` | `60` | Rate limit window in seconds. |
| `BACKEND_API_URL` | `http://localhost:8000` | Backend URL as reached by the Next.js **server**, not the browser. |
| `BACKEND_API_KEY` | empty | Sent upstream as `X-API-Key` by the server-side proxy. Never exposed to the client. |

## Platforms and payloads

Reference data is bundled at `backend/suas/data/` and is reconciled into the
database on every startup. The bundled JSON is the source of truth: rows are
matched by id and updated in place, so a corrected performance figure reaches an
existing deployment on the next restart. Rows you add yourself that are not in
the JSON are left untouched. Edit the JSON (or mount your own) to change the
catalog; direct database edits are overwritten on the next boot.

The frontend fetches the catalog from the API at runtime, so the dropdowns
cannot drift from the data the backend actually holds.

Aircraft: `Skydio_X10D`, `Skydio_X2D`, `Parrot_ANAFI_USA`, `Teal_Golden_Eagle`,
`Freefly_Astro_Max`, `Freefly_Alta_X`, `Inspired_Flight_IF1200A`.

Payloads: `None`, `FLIR_Hadron_640R`, `Sony_ILX_LR1`, `Nextvision_Raptor`,
`Workswell_WIRIS_Ent`, `Trillium_HD40_LV`.

The X10D carries an integrated sensor suite, so its external payload capacity is
0; pairing it with any payload other than `None` yields a negative payload margin
and a NO-GO, which is the correct result. For a combination with real payload
headroom, select `Freefly_Astro_Max`.

## The performance model

The deterministic engine is an **energy and performance feasibility calculator**.
It is explicitly not an airspace, NOTAM, or regulatory clearance tool: it knows
nothing about controlled airspace, TFRs, or Part 107 altitude limits. A GO here
means the energy budget and airframe envelope close, nothing more.

What the model accounts for:

| Effect | Treatment |
| --- | --- |
| Payload mass | All-up mass scales induced power by `(m/m_ref)^1.5` (momentum theory). |
| Air density | Power scales by `1/sqrt(rho/rho_0)`, with density from the ISA relation at the mission's density altitude. |
| Density altitude | Computed at the operating altitude, surface temperature extrapolated up at the ISA lapse rate. |
| Wind | Cruise is flown at `cruise_speed - wind_speed`. Heading is unknown, so the full wind is assumed to be a headwind. |
| Climb | Hover power for the climb duration, plus `mgh / efficiency`. |
| Descent | Hover power for the descent duration. No credit for recovered energy. |
| Gusts | Checked against the airframe wind limit independently of sustained wind. |
| Temperature | Two-sided against the airframe envelope, and battery capacity is derated when cold. |

Battery capacity derates linearly from 100% at 20 C to 65% at -10 C, flat
outside that range. This is representative of the chemistry, not a measured
curve for any specific pack.

Every one of these was absent in an earlier revision, and each omission biased
the result toward GO. The choices above are deliberately conservative where the
model is uncertain: worst-case headwind, no descent energy recovery, and the
momentum-theory power law applied to cruise as well as hover.

### Data provenance

Each aircraft field is published, estimated, or derived:

- Published: weight, max payload, max wind, and operating temperature, from
  manufacturer or reputable spec sources.
- Estimated: `battery_wh` where a manufacturer does not state pack energy, and
  nominal cruise speed (roughly 0.6 to 0.7 of published max speed).
- Derived: the two power fields, by
  `hover_power_w = battery_wh / no_payload_endurance_hours` and
  `cruise_power_w = 0.90 * hover_power_w`.

`min_temp_c` is a conservative placeholder of -20 C for every airframe, not a
per-model published figure. Replace it with the manufacturer's stated lower
operating limit before relying on the cold-weather check.

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
npm run format                        # prettier --check
npm test                              # vitest, covers the server-side proxy
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
    app/
      api/          server-side route handlers that proxy to the backend
      components/   UI components
    lib/            typed API client, catalog hook, geolocation, shared types
      server/       backend proxy; the only reader of the API key
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
  measured values before relying on the energy budget operationally. Edit
  `backend/suas/data/*.json`; the change is applied on the next restart.
- **Checkpoint retention runs at startup.** Threads older than
  `SUAS_CHECKPOINT_RETENTION_DAYS` are purged through the checkpointer's own
  API, capped at 1000 threads per pass. A long-running process that never
  restarts will not purge; schedule a periodic restart or call the purge from
  your own scheduler. Retention failures are logged and never block startup.

## Known limitations

- **Next.js ESLint plugin is disabled.** The `@next/eslint-plugin-next` v14 rules
  crash under ESLint 9 flat config, so Next-specific lint is off. Re-add it after
  moving to Next 15, which is flat-config compatible.
- **`pip-audit --strict` can fail on transitive advisories** outside this
  project's control. Pin a specific `--ignore-vuln` with a written rationale
  rather than disabling the job.

## License

MIT. See `LICENSE`.
