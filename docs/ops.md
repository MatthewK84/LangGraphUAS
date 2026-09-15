# Operations

## Retention

LangGraph's Postgres saver has no TTL, so retention is ours.

**Today** it runs at application startup through the checkpointer's own API,
capped at 1000 threads per pass (`SUAS_CHECKPOINT_RETENTION_DAYS`). A process
that never restarts never purges.

**Planned (Phase 2, Week 7)** it moves to `backend/scripts/prune_threads.py` on a
schedule, with the status-aware policy below. Until then the single retention
window applies to every status.

| Status | Keep |
|---|---|
| `awaiting_ack` | 14 days |
| `briefed`, `replanning` | 90 days |
| `aborted` | 30 days |
| pinned (demo, eval fixtures) | indefinitely |

Deletion goes through `delete_thread(thread_id)`. Never hand-written SQL across
`checkpoints`, `checkpoint_blobs`, and `checkpoint_writes` — partial deletes
leave threads that resume into a corrupt state.

## Concurrency

Three things in this service are per process, and each is a deliberate
constraint rather than an oversight:

- **Rate limiting.** The budget is per worker, so the cluster ceiling is
  `SUAS_RATE_LIMIT_REQUESTS * worker_count`. It is a spend guard against runaway
  model calls, not an exact quota. A shared limiter belongs in Redis or the
  ingress.
- **The weather cache.** A reading fresh in one worker is not fresh in another.
- **Metrics.** Scrape every replica and aggregate in Prometheus.

Resuming an interrupt is **not** in that list. Two workers must never resume the
same `thread_id`, and that is enforced rather than assumed — see "Two workers,
one interrupt" below. Running more than one worker is therefore safe for
correctness; what it costs you is the precision of the three counters above.

## Weather degradation

| State | Operational allowed |
|---|---|
| `live` | yes |
| `cached_fresh` (< 10 min) | yes |
| `cached_stale` | no — `degraded: true` |
| `fallback` | no — `degraded: true` |
| `error` | no — `degraded: true` |

Timeout is 2-3 seconds and must never hang `/api/plan` or `/api/replan`.

## Load

Measured 2026-09-15 on the development container: 4 vCPU, PostgreSQL 16 on the
same host, one `uvicorn` process per worker, weather deliberately failing fast so
the provider is not in the measurement. **These are not benchmark numbers for
your hardware** — they are the shape of the curve and the point at which this
service stops keeping up.

`python3 backend/scripts/load_plan.py --requests 100 --concurrency 100`

| Concurrency | Workers | p50 | p95 |
| --- | --- | --- | --- |
| 1 | 1 | 0.189s | 0.189s |
| 5 | 1 | 0.396s | 0.455s |
| 10 | 1 | 0.451s | 0.522s |
| 25 | 1 | 0.726s | 0.872s |
| 50 | 1 | 1.847s | 1.919s |
| 100 | 1 | 3.347s | 3.415s |
| 100 | 4 | 2.114s | 2.238s |

Read it this way. Correctness held everywhere: 100 of 100 plans succeeded, zero
5xx, 100 distinct threads all checkpointed. What gives way is throughput. Above
about 25 concurrent the latency is flat across p50, p95 and max, which is the
signature of queueing rather than of slow work — one worker sustains roughly 30
plans per second and everything else waits its turn.

**The plan's own pass bar, p95 under 2s at 100 concurrent, is not met here.** One
worker misses it by 70%; four workers still miss it by 12%, and four workers on
four vCPUs is already past the point of useful return. Either the bar belongs at
50 concurrent per worker, or the service needs more hosts. It is recorded as a
miss rather than adjusted after the fact.

The `?brief=false` flag the plan called for was not added. A plan now stops at
the human acknowledgement before any brief exists, so the plan path never reaches
the model and the flag would have been a no-op. Pass `--ack` to exercise the path
that does call one, and keep that run small: 10 concurrent acknowledgements ran
at p95 0.539s.

## Crash recovery

Drill run 2026-09-15 against PostgreSQL 16, single worker, verbatim:

1. `POST /api/plan` → `awaiting_ack: true`, empty report, `inputs_hash c0eb19e1…`
2. `kill -9` the worker. Health returns nothing.
3. Restart.
4. `GET /api/plan/{thread_id}` → `found: true`, `awaiting_ack: true`, decision
   `go`, **`inputs_hash` byte-identical to step 1**
5. `POST /api/plan/{thread_id}/ack` → brief generated, `awaiting_ack: false`
6. `mission_threads` carries `drill-operator | confirm | c0eb19e1… | 1.6.0`
7. A second acknowledgement returns 409. The report ran once.

Nothing was lost between the assessment and the signature, which is what
`durability="sync"` at those two nodes buys.

## Two workers, one interrupt

An acknowledgement is serialised by two locks: an in-process `asyncio.Lock` per
thread id, and `SELECT … FOR UPDATE` on the mission row. Both are needed. The row
lock is what separates worker processes sharing Postgres; it does nothing on
SQLite, where the clause is silently ignored, and nothing between two coroutines
inside one process.

This is not theoretical. Measured against four workers on real Postgres:

| Configuration | Trials | Result |
| --- | --- | --- |
| No lock | 8 | **6 double-resumed** — two briefs for one signature |
| Both locks, 2 simultaneous acks | 8 | 8 produced exactly one brief |
| Both locks, 3 simultaneous acks | 10 | 10 produced exactly one brief |

The losing requests get 409. Holding the locks across the resume is deliberate:
they cover a single mission's row, so they serialise only the duplicate that must
be serialised, and the model client's own timeout bounds how long either is held.

## Incident response

These counters sit at zero in production. Any non-zero value on a real mission
is an incident, not a curiosity:

`injection_quarantine_total{pattern}`, `llm_field_violations_total{field}`,
`hallucinated_citation_total`, `brief_suppressed_total{reason}`,
`unverified_span_total`.

**A suppressed brief does not invalidate an acknowledgement.** The decision was
computed and signed before the model ran (ADR-004). Preserve the sealed
assessment, preserve the ack, investigate the brief separately.

On a quarantine hit: the affected configuration loses `citations_complete` and
therefore cannot run operational until a human clears the quarantined chunk.
This is the intended default — an aircraft whose paperwork contains something
that looks like an attack does not fly on that paperwork.
