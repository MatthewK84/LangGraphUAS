# sUAS Intelligent Mission Planner

An async AI orchestration and deterministic physics engine for small unmanned
aircraft system (sUAS) flight planning. A LangGraph state machine coordinates
validation, live weather, deterministic safety math, and a language-model
safety brief. A Next.js dashboard drives it. The reference data covers a set of
DIU/DCMA Blue UAS (NDAA-compliant) multirotor platforms.

Supported on Python 3.11, 3.12, and 3.13. CI verifies all three.

## Architecture

- **Frontend**: Next.js 14 (App Router, standalone output), TypeScript strict, TailwindCSS.
- **Backend**: FastAPI on Python 3.11 to 3.13, fully async request path.
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
START -> validate -> (conditional) -> weather -> calculations -> human_ack -> report -> END
                          \-> report (when validation fails)          |
                                        edit <---------------------- /
                                        abort -> END
```

`human_ack` interrupts the run and waits for a person. The order is a security
control rather than a workflow preference: the operator signs an assessment that
neither retrieved text nor generated prose has touched, so nothing a model
produces can change what was signed. See
[ADR-004](docs/adr/004-node-order-and-empty-tool-binding.md). The report node has
no tools bound, for the same reason. Both are pinned by tests that fail if the
invariant is removed.

State holds only JSON-native values. Pydantic models are dumped to dictionaries
before entering state, which keeps checkpoint serialization simple and safe.
The container sets `LANGGRAPH_STRICT_MSGPACK=true` to restrict checkpoint
deserialization to known-safe types.

Every request supplies a `thread_id`. The checkpointer persists state per thread,
so `GET /api/plan/{thread_id}` can retrieve a prior assessment and a follow-up
request can resume the same conversation. Checkpoints are written with
`durability="sync"`, so a crash between the assessment and the signature loses
neither.

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

Every numeric field in `backend/suas/data/*.json` carries its value, unit,
source, confidence, and notes. The full inventory is generated into
[`backend/suas/data/CITATIONS.md`](backend/suas/data/CITATIONS.md) and a test
fails if it drifts from the data.

| Source | Meaning | Good enough to fly on |
| --- | --- | --- |
| `datasheet` | Read from the manufacturer's own published document | yes |
| `flight_log` | Measured from recorded flight telemetry | yes |
| `secondary` | Published figure from a specification summary, not the primary document | no |
| `derived` | Computed from other fields by a formula in the notes | no |
| `estimate` | An engineering estimate | no |
| `unknown` | Provenance not recorded. Nobody vouched for this number | no |

As of this writing: **76 fields, none of them operational-grade.** 36 are
`secondary`, 15 `derived` (the two power fields, by
`hover_power_w = battery_wh / no_payload_endurance_hours` and
`cruise_power_w = 0.90 * hover_power_w`), 14 `estimate` (nominal cruise speed at
roughly 0.6 to 0.7 of published maximum, and every payload power figure), and 11
`unknown` (pack energy, payload mass). That is why the operational gate refuses
every plan today, and it will keep refusing until a figure is read out of a
manufacturer document or measured from a flight log.

`secondary` is not a hedge. The figures below were gathered from published
specification summaries rather than retrieved from the manufacturers' own
documents, and recording them as `datasheet` would overstate what this project
knows. Resolving them is [#39](https://github.com/MatthewK84/LangGraphUAS/issues/39).

Operating temperature limits are published manufacturer figures:

| Aircraft | `min_temp_c` | Published range | Source |
| --- | --- | --- | --- |
| Skydio X10D | -20 | -20 to 45 C | Skydio X10 specifications |
| Skydio X2D | -10 | -10 to 43 C | Skydio X2 support documentation |
| Parrot ANAFI USA | -35 | -32 F (-35 C) to 120 F (49 C) | ANAFI USA user guide |
| Teal Golden Eagle (Teal 2) | -36.7 | -34 F to 110 F (-36.7 to 43.3 C) | Teal 2 specifications |
| Freefly Astro Max | -20 | -20 to 50 C | Freefly Astro pilot's operating handbook |
| Freefly Alta X | -20 | -20 to 50 C | Freefly Alta X specifications |
| Inspired Flight IF1200A | -20 | -20 to 45 C | IF1200A specifications |

`Freefly_Astro_Max` additionally carries `pack_min_takeoff_c` at 10 C.

#### Where the four documented conflicts stand

| Conflict | Resolution |
| --- | --- |
| IF1200A `max_temp_c` stored 50 against a published 45 | **Corrected to 45.** A stored limit more permissive than the published one is the dangerous direction. |
| ANAFI USA `max_temp_c` stored 43, published figures of 43, 49 and 50 in circulation | **Unresolved; 43 kept.** For an upper limit the most restrictive candidate is the safe one. The disagreement is recorded in the field's notes. |
| IF1200A `battery_wh` assuming a 12S pack | **Kept, arithmetic recorded.** 1420 Wh is consistent with two 16 Ah packs at 12S (2 x 16 x 44.4 = 1420.8). Pack count and cell count remain unverified, so it stays an `estimate`. |
| Alta X power figures soft | **Kept, discrepancy recorded.** The stored hover figure implies ~20 minutes of endurance, which matches the published figure at a 20 lb load rather than the no-payload figure its own formula names. It is conservative, so it stays until a flight log settles it. |

None of these became `datasheet`. Every figure above was obtained from a web
search summary of the manufacturer's page, not by opening the page, so they are
recorded as `secondary` with the URL and the caveat attached. The operational
gate is unmoved, which is correct: a citation nobody has read is not evidence.

Freefly documents a separate battery procedure of 10 C minimum at takeoff for
the Astro, well above the airframe's -20 C limit. That is modelled as
`pack_min_takeoff_c` and checked as its own safety flag rather than folded into
`min_temp_c`: they are different limits with different owners, and an airframe
rated to -20 C can still have a pack that must not launch below +10 C. Ambient
temperature stands in for pack temperature, which is conservative for the
cold-soaked aircraft the procedure is written for.

The power fields are engineering estimates, not measurements. Replace them with
real power logs before operational use, which `POST /api/logs` now makes
possible. All payload `power_draw_w` values are estimates. For the authoritative
live roster, cross-check `bluelist.dcma.mil`.

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
  "thread_id": null,
  "assessment_mode": "advisory"
}
```

`elevation_m` is the launch point's elevation above sea level and
`target_altitude_m` is the planned operating height above that launch point
(AGL). Density altitude is reported for the operating altitude, not the field:
the surface temperature is extrapolated upward with the ISA lapse rate before
the deviation from standard is applied. Under a standard lapse rate that means
planning `h` meters higher raises reported density altitude by exactly `h`.

`POST /api/plan` now returns with `awaiting_ack: true` and no brief. The run is
paused at the review step until a person acts:

```
POST /api/plan/{thread_id}/ack
{ "action": "confirm", "actor": "dispatcher-1", "inputs_hash": "<from the plan response>" }
```

`action` is `confirm`, `edit`, or `abort`. `inputs_hash` is the assessment the
operator was actually shown; if it no longer matches, the acknowledgement is
refused with `409` rather than applied to numbers that changed underneath it. An
`edit` (altitude, hover time, or payload) re-runs the calculator and pauses
again, because a revision is a new thing to sign. An `abort` ends the run without
calling the model at all. Confirmations are recorded against the thread with the
actor, timestamp, assessment hash, and calculator version.

The response carries an `assessment` object, which is the authoritative
decision: `decision` (`go`, `no_go`, or `insufficient_data`), the `reasons`
behind it, the `mode` granted, any `blockers`, plus `inputs_hash` and
`calculator_version` identifying exactly which numbers produced it. It is
written by `suas/calculations/` and never by the language model. `is_viable`
remains as a derived alias for `decision == "go"`.

#### Advisory and operational

`assessment_mode` is what you ask for. The backend decides what you get, and it
fails closed: a gate condition it cannot verify counts against the plan. Today
that means **operational mode is unreachable** — every plan returns `200` with
`mode: "advisory"` and blockers naming what is missing, because the bundled
power figures carry no provenance and no Blue List snapshot is stored. An
ungrantable mode is a downgrade with reasons attached, not a `409`; see
[ADR-005](docs/adr/005-mode-downgrade-is-not-an-error.md). A mode that is not a
valid value is still a `422`.

`GET /api/plan/{thread_id}` returns the persisted state for a prior mission
thread, or `found: false` when the thread is unknown.

Every response carries an `X-Request-ID` header. Supply your own to correlate a
client trace with server logs; one is generated when absent.

### Replanning in flight

`POST /api/replan` takes a telemetry snapshot from an aircraft already flying and
compares it against the plan that was briefed.

```json
{
  "thread_id": "<the briefed thread>",
  "ts": "2026-09-14T14:03:11Z",
  "latitude": 34.0, "longitude": -80.0, "alt_m": 100.0,
  "soc_fraction": 0.42,
  "remaining_leg_m": 1800.0,
  "remaining_hover_s": 60.0,
  "oat_c": 4.0,
  "wind_mps": 6.0,
  "payload_attached": true
}
```

`remaining_leg_m` is required rather than inferred from the briefed distance. An
aircraft that has deviated, held, or been retasked is no longer flying the route
it was briefed on, and assuming otherwise computes a residual for a mission
nobody is flying.

The response carries the live energy picture, the briefed margin, and a list of
alerts, each with `briefed`, `live`, and `delta` blocks so the recommendation can
be checked rather than taken on faith:

| Code | Severity | Action |
| --- | --- | --- |
| `ENERGY_BELOW_RESERVE` | abort | land now |
| `ENERGY_NEAR_RESERVE` | warning | land soon |
| `WIND_EXCEEDS_LIMIT` | abort | land now |
| `SOC_STALE` | watch | advisory only |
| `WEATHER_DEGRADED` | watch | advisory only |
| `PAYLOAD_MISMATCH` | watch | advisory only |

Three properties worth knowing. **The briefed plan does not move**: a replan runs
on a child thread (`{parent}:{seq}`), so the assessment an operator signed stays
addressable and unchanged. **No language model is involved** — this runs while an
aircraft is airborne, which is the worst moment to wait on one or to let one
influence what the operator is told. And **any alert at all, including a watch,
makes the replan advisory**: an alert means something could not be confirmed, and
an unconfirmed replan is advice rather than clearance.

Remaining capacity is derated for the temperature the aircraft reports, not the
one it was briefed for, and the reserve is measured against that same derated
capacity — a reserve computed on nameplate watt-hours is not a reserve on a cold
day.

### Flight logs

`POST /api/logs?airframe_id=<id>` takes a CSV flight log as the request body and
derives measured hover and cruise power from it. This is the only way a figure in
the reference data can become `source: flight_log`, which is one of the two
sources the operational gate accepts.

```bash
curl -X POST "http://localhost:8000/api/logs?airframe_id=Freefly_Astro_Max&apply=true" \
  -H "Content-Type: text/csv" -H "X-API-Key: $SUAS_API_KEY" \
  --data-binary @your-flight.csv
```

`timestamp` and `alt_m` are required; `power_w`, or `voltage_v` and `current_a`
together, supply the power figure. The full column list, units, and what gets
rejected are in
[`backend/tests/fixtures/logs/README.md`](backend/tests/fixtures/logs/README.md).

**Ingesting is not applying.** An upload always stores the log and reports the
estimates. `apply=true` additionally writes them into the airframe's reference
row, and only for fields with at least 30 selected samples. Changing a number
that plans are built on should be a deliberate act, not a side effect of
uploading a file.

**What a hover window means.** A sample counts toward hover power only if it is
not labelled `climb`, `descent`, or `cruise`, **and** its measured vertical rate
is within ±0.5 m/s, **and** its speed is at or below 1.5 m/s. The label alone is
not enough: a row marked `hover` while the aircraft was climbing is excluded on
its measured rate, because averaging climb power into a hover figure understates
hover draw, which understates the energy budget, which biases the decision toward
GO. Cruise is the mirror image — level within ±1.0 m/s and at or above 3.0 m/s.

The estimator reports the median rather than the mean, with the interquartile
range and a sample count beside it, because a log routinely contains brief spikes
that a mean would let move the figure.

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

CI runs the backend gates across Python 3.11, 3.12, and 3.13, plus a Postgres
integration job (real migrations and startup smoke check), the frontend gates,
and Docker image builds for both services. See `.github/workflows/ci.yml`.

Dependency auditing is **not** a CI gate. `pip-audit` stays in the dev extras
and is run on demand:

```bash
pip install -e ".[dev]"
pip-audit                             # runtime + dev, advisory
```

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

## Planning and design documents

The 90-day plan for taking this from a working demo to a system whose numbers
can be defended lives in [`docs/PLAN-90.md`](docs/PLAN-90.md). Supporting
specifications:

| Document | Covers |
|---|---|
| [`docs/engineering-practices.md`](docs/engineering-practices.md) | Branching, CI gates, environments, review bar |
| [`docs/retrieval.md`](docs/retrieval.md) | pgvector hybrid search for datasheet citations |
| [`docs/rag-eval.md`](docs/rag-eval.md) | Retrieval and citation metrics that gate CI |
| [`docs/injection-defense.md`](docs/injection-defense.md) | Prompt injection surfaces and controls |
| [`docs/threat-model.md`](docs/threat-model.md) | STRIDE across every trust boundary |
| [`docs/ops.md`](docs/ops.md) | Retention, concurrency, incident handling |
| [`docs/adr/`](docs/adr/README.md) | The decisions later code is allowed to assume |
| [`docs/backlog/`](docs/backlog/README.md) | The seventeen opening issues, ready to file |

The organizing rule across all of it: the language model writes prose, and
`backend/suas/calculations/` writes every number that can keep an aircraft in
the air.

## Known limitations

- **Python 3.10 is not supported.** The floor is 3.11, which is what makes
  `enum.StrEnum` and `datetime.UTC` available to this codebase. The production
  image still pins `python:3.11-slim`, the floor of the supported range, so CI
  exercises a wider range than the container runs.
- **Next.js ESLint plugin is disabled.** The `@next/eslint-plugin-next` v14 rules
  crash under ESLint 9 flat config, so Next-specific lint is off. Re-add it after
  moving to Next 15, which is flat-config compatible.
- **No dependency-audit gate.** `pip-audit --strict` failed regularly on
  transitive advisories outside this project's control, so the job was removed
  rather than left red. Nothing watches for a vulnerable dependency
  automatically: run `pip-audit` before a release, and reinstate a scheduled
  (non-blocking) job if that proves too easy to forget.

## License

MIT. See `LICENSE`.
