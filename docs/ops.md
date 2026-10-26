# Operations

## Readiness

`GET /ready` answers 200 only when the instance can serve a plan, and 503 otherwise. Each field reports one dependency:

| Field | `ok` means | Not ready when |
|---|---|---|
| `database` | `SELECT 1` succeeds | `unavailable`: no connection |
| `migrations` | `alembic_version` holds `EXPECTED_REVISION` (`suas/db/migrations.py`) | `pending`: an older revision, or no version table on Postgres (tables from `create_all` alone); `unknown` when the database is down |
| `checkpointer` | the plan checkpoint store answers a read | `unavailable`: the read raised |

`not_tracked` is ready. It is local SQLite with no version table, the default development path, where `create_all` builds the schema. Deployed containers do not migrate on start (see [Migrations](#migrations)), so `pending` there means the deploy's migration step has not run, failed, or ran against another database.

A missing model key does not affect readiness. Advisory briefs are a supported mode.

A new migration must also bump `EXPECTED_REVISION`; a test fails until it does. CI proves both directions against Postgres. A migrated database must be ready, and a database alembic never touched must answer 503 with `pending` (`scripts/smoke_check.py --expect-unmigrated`).

## Migrations

Upgrading the schema is a deploy step, never a side effect of a restart (#87).
The image's entrypoint serves without touching the schema unless told to:

| Path | Migration step |
|---|---|
| Compose | the one-shot `migrate` service runs `docker-entrypoint.sh migrate` (`alembic upgrade head`) after `db` is healthy; `backend` starts only once it exits 0 |
| Railway | `railway.json` sets `"preDeployCommand": ["alembic upgrade head"]`; a failure stops the deploy before the new image serves |
| Anything else | run `docker-entrypoint.sh migrate` (or `alembic upgrade head` with `SUAS_DATABASE_URL` set) once per release, before the new image serves |
| One local container | `MIGRATE_ON_START=true` upgrades before uvicorn starts, and a failed upgrade stops the start. Exactly `true`; anything else is off |

Every upgrade holds the Postgres startup advisory lock for its transaction, so
replicas or a stray second upgrade run one after another; the later ones find
the database at head. The app's own startup writes take the same lock.

**Rolling back** a release that added a migration: deploy the previous image,
then `alembic downgrade <its EXPECTED_REVISION>` once (from either image; the
newer one knows the downgrade). Because no container upgrades on start, the
restarted old image keeps the downgraded schema, and `/ready` answers 200 again
once the revision matches. Do not set `MIGRATE_ON_START=true` on an image you
might roll back, since its next restart would re-upgrade.

Start the new image only after its migration step: the app's `create_all`
creates missing tables on any database, and a table it created first makes the
migration that creates it fail. `/ready` answers 503 `pending` in that window.

## Backup and restore

An acknowledgement is a signature on one assessment: `mission_threads` keeps
the `inputs_hash` the operator signed, and the LangGraph checkpoint keeps the
sealed assessment it was signed against. Both live in the planner's one
Postgres database, along with the catalog, flight logs and corpus, so one
`pg_dump` snapshot keeps them consistent (#113). Continuous replication or
point-in-time recovery is the platform's job, not this one.

Run these from a checkout with the backend installed (`pip install -e
backend`) and PostgreSQL client tools at least as new as the server. The
image has no `pg_dump`. From `backend/`:

1. **Back up** the live database:
   `SUAS_DATABASE_URL=<live> scripts/backup.sh suas.dump`
   (`pg_dump --format=custom`, one snapshot; no owner or grants).
2. **Restore into an empty database**, never over the live one:
   `CREATE DATABASE suas_restored;`, then
   `SUAS_DATABASE_URL=<restored> scripts/restore.sh suas.dump`.
   It is one transaction that stops at the first error, so it lands whole or
   not at all.
3. **Migrate** only if the backup predates the release you will serve:
   `SUAS_DATABASE_URL=<restored> alembic upgrade head` (see
   [Migrations](#migrations)).
4. **Verify** every signature:
   `SUAS_DATABASE_URL=<restored> python scripts/verify_restore.py`.
   It compares each stored ack's `inputs_hash` with its checkpoint's sealed
   assessment and prints `N acknowledgement(s) verified, 0 broken`. Exit 1
   lists each `thread: signed <hash>, checkpoint has <hash|nothing>`; do not
   serve that database.
5. **Switch**: point `SUAS_DATABASE_URL` at the restored database and restart
   the planner. `/ready` answers 200, signed plans read back with the hash they
   were signed on, and a plan that was waiting for a signature still waits.
   It accepts its original `inputs_hash` and refuses any other with 409.

`tests/test_backup_restore.py` runs exactly these steps on Postgres in CI
(postgres-integration): it backs up a database holding one signed and one
pending plan, restores it into an empty one, verifies, serves it, and signs the
pending plan. Restored threads keep their `created_at`, so retention purges
old ones on its next pass as it would have.

## Retention

LangGraph's Postgres saver has no TTL, so retention is ours.

Every worker runs a retention pass at startup and then every
`SUAS_RETENTION_INTERVAL_S` (default 3600s), in-process, so a long-lived
process purges without a restart (#86). No cron or scheduler is needed. A pass:

- **Purges threads older than `SUAS_CHECKPOINT_RETENTION_DAYS`** through the
  checkpointer's own API, with each thread's replan children (`<id>:1` to
  `<id>:<replan_count>`), capped at 1000 threads per pass. A thread is claimed
  by deleting its tracking row, and that delete commits only after every
  checkpoint delete succeeds, so two workers purge a thread once and a failed
  delete is retried next pass. Another thread's replan child is untouched.
- **Prunes idle `rate_limit_buckets` rows**: those with no hit left in
  `SUAS_RATE_LIMIT_WINDOW_S`. An idle row admits exactly as a missing one, so
  this changes no decision. Buckets are paged in key order, 1000 per
  transaction, so idle rows behind many live ones are reached. Rows are read
  `FOR UPDATE SKIP LOCKED`, so a bucket mid-admission is skipped rather than
  waited on, and the delete matches the hits it judged, so a request admitted
  meanwhile keeps its bucket, on SQLite too.
- **Prunes `weather_cache` rows past `SUAS_WEATHER_STALE_MAX_AGE_S`**
  (default 10800s), judged from each reading's own `fetched_at`; a row with
  none counts as infinitely old. Such a reading is never served: when the
  provider fails, a reading within the max age is the `cached_stale` answer and
  an older one is treated as missing, so the plan gets the same `fallback` or
  `error` reading an empty cache gives. Pruning therefore changes no answer.
  Rows are paged in key order (1000 per transaction) and read `FOR UPDATE SKIP
  LOCKED`, and the delete matches the `fetched_at` it judged, so a reading
  another worker stored meanwhile is kept, on SQLite too. A worker's own
  in-memory cache (sharing off) drops readings past the max age on each store.

Failures in a pass are logged and never stop the app. The single retention
window applies to every status; a status-aware policy like the one below is
not built:

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

One thing in this service is per process, as a deliberate constraint rather
than an oversight:

- **Metrics.** Scrape every replica and aggregate in Prometheus.

Resuming an interrupt is **not** in that list. Two workers must never resume the
same `thread_id`, and that is enforced rather than assumed — see "Two workers,
one interrupt" below. Running more than one worker is therefore safe for
correctness; what it costs you is the precision of the counters above.

Rate limiting is shared when `SUAS_RATE_LIMIT_SHARED=true`, as Compose sets it
(#84). Each client's recent request times sit in one `rate_limit_buckets` row,
keyed by a SHA-256 of the client key so no API key is stored. Every admission
locks that row (`FOR UPDATE`), prunes, decides and writes in one transaction,
so concurrent workers on one client queue on the lock and the ceiling is
exact. The cost is one short write transaction per rate-limited request, on
the database those requests already use; if it is unreachable the request
fails as the plan would have. Idle clients' rows stay until the table is
truncated, which is always safe: it only resets budgets. Unshared, each worker
keeps its own budget and the ceiling is the limit times the worker count.
Measured with two uvicorn workers at a limit of 4 and 12 concurrent plans: 5
admitted unshared, exactly 4 shared.

The weather cache is shared when `SUAS_WEATHER_CACHE_SHARED=true`, as Compose
sets it (#85). Each ~1 km cell's last live reading sits in one `weather_cache`
row (migration 0014), so a reading any worker fetched is `cached_fresh` in every
worker until `SUAS_WEATHER_CACHE_TTL_S` passes, judged from its own
`fetched_at`; the TTL and the provenance states are unchanged. The cost is one
read per weather lookup and one write per live fetch. Two workers that miss the
same cell at the same moment may both fetch; the later write wins, which is
harmless. If the database is unreachable the cache is a miss and the fetch goes
to the provider, so weather still never raises. Rows are one per cell ever
planned; deleting them only costs a refetch. Unshared, each worker keeps its
own cache and the provider sees one request per worker per cell.

## Weather degradation

| State | Operational allowed |
|---|---|
| `live` | yes |
| `cached_fresh` (< 10 min) | yes |
| `cached_stale` (≤ `SUAS_WEATHER_STALE_MAX_AGE_S`, default 3 h) | no — `degraded: true` |
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

## Operator keys

`SUAS_API_KEYS=alpha:key-a,bravo:key-b` names each key by operator, and
`SUAS_API_KEY`, if set, joins the list as operator `default`. Startup refuses a
list with a blank id or key, a repeated id, or one key under two ids.

Each mission row records `operator_key_id`, the key that planned it. `GET
/api/plan/{id}`, the ack and `/api/replan` answer another operator's thread
exactly as they answer one that does not exist, and a plan onto another
operator's thread id is refused as unknown. A replan child belongs to its
parent's operator.

Migration 0011 sets every existing mission to `default`, so a deployment that
keeps its one `SUAS_API_KEY` keeps reading its threads, open interrupts
included. Moving those missions to a named operator is an `UPDATE
mission_threads SET operator_key_id = ...`; nothing else stores the owner.
Missions planned with auth off record no operator, and once auth is on no key
can read them. Revoking a key hides that operator's missions until a key with
the same id is configured again; to replace a key, keep its id (see Key
rotation).

## Browser sessions

With `SUAS_SESSION_KEY_SECRET` on the backend and the same value as
`BACKEND_SESSION_SECRET` on the frontend, each browser is its own operator
(#82). The frontend sets an `HttpOnly`, `SameSite=Strict`, 30-day
`suas_session` cookie holding a random 256-bit id (`Secure` when the request
arrived over HTTPS, so terminate TLS in front of it and pass
`X-Forwarded-Proto`), and signs it into the `X-API-Key` it sends upstream.
`operator_key_id` stores `session:` plus a hash of the id, never the cookie.
Sessions share one rate-limit bucket, so fresh cookies buy no extra allowance;
per-instance limits are #84.

- **Clearing cookies loses that browser's threads.** A new cookie is a new
  operator, and nothing can recover the old one. The same happens when the
  cookie expires or another browser is used.
- **The Compose default is demo-only.** `docker-compose.yml` falls back to
  `demo-only-session-secret-from-docker-compose-never-deploy`, which is public:
  anyone who can reach the backend can forge any session with it. The backend
  logs `DEMO session secret in use` at startup while it is. Set
  `SESSION_KEY_SECRET` (`openssl rand -hex 32`) in `.env` for any shared
  stack. Changing the secret later keeps every browser's threads (see Key
  rotation).
- **Cross-site requests.** The proxy refuses any `POST` whose `Origin` is not
  its own host (`X-Forwarded-Host`, then `Host`) with 403. A reverse proxy
  must pass the public host through.
- A secret shorter than 32 characters refuses to start. The backend still
  accepts `SUAS_API_KEYS` keys alongside sessions, for scripts and the CSV
  importer.

## Key rotation

A mission belongs to an operator id, not to a key, and an acknowledgement is
bound to the assessment's `inputs_hash`, not to the key that sends it (#83). So
rotating a key strands nothing:

1. Replace the key under the same id: `alpha:old` becomes `alpha:new` in
   `SUAS_API_KEYS`, or set a new `SUAS_API_KEY` for `default`. A key under a
   different id is a different operator, and that operator cannot see the old
   id's missions.
2. Restart every backend worker. Settings are read once per process, so a
   worker keeps the old key until it restarts. Once it has restarted the old
   key gets 401 immediately, unless you open an overlap window (below): a
   script still holding the old key fails rather than acting under a stale
   identity.
3. Open interrupts carry on. The operator reads the pending plan with the new
   key and signs it. The signature must still match the `inputs_hash` it was
   shown; a stale hash is 409 as before.

**Overlap window (opt-in).** To give a script time to pick up its new key,
list the old one in `SUAS_RETIRED_API_KEYS` as `id:old-key@expiry`, e.g.
`alpha:key-a@2026-10-26T18:00:00Z`, alongside `alpha:new-key` in
`SUAS_API_KEYS`. Until the expiry, the old key is accepted only from the
same client IP that last authenticated with it successfully before rotation.
From any other address, after the expiry, or if it was never used, it gets the
same 401 as an unknown key. The new key works from anywhere.

- The expiry is an ISO 8601 time with a zone. Startup refuses one more than
  `SUAS_RETIRED_KEY_MAX_GRACE_S` ahead (default 3600, one hour; at most a
  week). It also refuses an id that is not a configured operator, a retired key
  that is still a current key, and a key listed twice. Remove the entry once it
  has expired; leaving it does nothing.
- The backend records each direct API key's last client IP in
  `api_key_last_seen`, by SHA-256 of the key and never the key (migration
  0013). Only uses after this release are recorded, so a key last used before
  it has no IP and cannot overlap.
- The client IP is the TCP peer. `X-Forwarded-For` counts only when the peer is
  listed in `SUAS_TRUSTED_PROXIES` (comma-separated IPs, default empty, trust
  none), and then the rightmost hop that is not a trusted proxy is the client.
  The image runs uvicorn with `--no-proxy-headers`, so nothing else rewrites
  the peer. Behind a load balancer, either list it or accept that every client
  shares its address.
- Clients behind one NAT share an IP, so the window is short on purpose.

The IP rule is for direct API keys only. Browser session keys arrive through
the Next server, whose IP says nothing about the browser, so they record no IP
and the session secret has no overlap window. It rotates as before.

The session secret rotates the same way. Set a new `SESSION_KEY_SECRET` (both
`SUAS_SESSION_KEY_SECRET` and `BACKEND_SESSION_SECRET`) and restart the backend
and the frontend. A browser's operator is a digest of its session id, which
the secret only signs, so every browser keeps its cookie and its threads, and
keys signed with the old secret stop working. Requests between the two
restarts get 401 and succeed on retry. Leaving the public demo secret is the
case that needs rotating: moving to a private one keeps every browser's
missions.

`tests/test_key_rotation.py` covers a named key, the `default` key and the
session secret, each with a plan left waiting for a signature.
`tests/test_retired_keys.py` covers the overlap window: same IP, another IP,
expiry, a spoofed `X-Forwarded-For`, a trusted proxy and the new key.

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
