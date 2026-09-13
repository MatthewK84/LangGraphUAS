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

In-process rate limiting does not cluster. Until a Redis counter exists, run
**one API worker**. This is a documented constraint, not an oversight; the
alternative is a limit that silently multiplies by replica count.

Two workers must never resume the same `thread_id`. Enforced by a row lock on
`missions.status`, not by convention.

## Weather degradation

| State | Operational allowed |
|---|---|
| `live` | yes |
| `cached_fresh` (< 10 min) | yes |
| `cached_stale` | no — `degraded: true` |
| `fallback` | no — `degraded: true` |
| `error` | no — `degraded: true` |

Timeout is 2-3 seconds and must never hang `/api/plan` or `/api/replan`.

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
