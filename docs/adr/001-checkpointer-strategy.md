# 001. Checkpointer strategy and thread identity

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

The graph already uses `InMemorySaver` locally and `AsyncPostgresSaver` in
production. Adding a human-in-the-loop interrupt changes what a checkpoint is
for: it stops being a convenience and becomes the thing that survives a crash
between a sealed assessment and an operator's signature. Two questions had to be
settled before that node lands — what durability each environment runs at, and
whether LangGraph's `thread_id` is allowed to be the business identifier.

## Decision

**Durability by environment.**

| Environment | Saver | Durability | Why |
|---|---|---|---|
| Unit tests | `InMemorySaver` | `exit` | Fast, no database |
| Integration/CI graph tests | `AsyncPostgresSaver` on ephemeral Postgres | `sync` | Proves resume |
| Local Compose | Postgres saver | `sync` | Matches production |
| Production | `AsyncPostgresSaver` on a pooled connection | `sync` at `calculations` and `human_ack` | A crash mid-graph must not lose a sealed assessment |

`exit` durability is never used in production. Cheap advisory previews may use a
looser setting only if they never reach `human_ack`.

**Thread identity is ours, not the framework's.** The `missions` table is the
record of the mission:

```
mission_id          uuid primary key
thread_id           varchar(64) unique      -- uuid, passed into graph config
operator_key_id
airframe_config_id
assessment_mode
status              drafting | awaiting_ack | briefed | replanning | aborted | expired
calculator_version
inputs_hash
assessment_json     jsonb                   -- sealed copy, application-owned
ack_at, ack_actor
blue_list_snapshot_id
```

One mission is one thread. A replan opens a **child thread**
(`{parent}:{replan_seq}`) so the original brief stays immutable — it is evidence.

**State contents are allowlisted.** JSON-native only: the mission request
snapshot, the weather record with its source and fetch time, the
`DeterministicAssessment` dict, `degraded`/`blockers`, the interrupt payload, and
the brief once acknowledged. Never API keys, never operator PII beyond an opaque
id, never raw flight-log rows, never embeddings. `LANGGRAPH_STRICT_MSGPACK`
stays on. Wrapping the serializer with `EncryptedSerializer` is open if
coordinates end up in state — location in a UAS planner is sensitive even
unclassified.

**Lifecycle.** `setup()` runs once in the migration job, not in the FastAPI
lifespan on every boot. Retention is ours, because the library has no TTL:
`awaiting_ack` 14 days, `briefed`/`replanning` 90 days, `aborted` 30 days,
pinned rows kept. Deletion goes through `delete_thread(thread_id)` — never
hand-written SQL across `checkpoints`, `checkpoint_blobs`, and `checkpoint_writes`.

## Rejected alternatives

- **`thread_id` as the only identifier** — rejected because a corrupt or purged
  checkpoint would take the decision record with it.
- **Same thread for replans** — rejected because it overwrites the briefed
  assessment an operator signed.
- **`durability="exit"` in production for latency** — rejected because the
  window it optimizes is exactly the window the interrupt sits in.

## Consequences

Every mission survives a checkpoint loss: the graph can be rebuilt from the
`missions` row. Cost is a second write path and a reconciliation rule — when the
table and the checkpoint disagree, the calculator and the table win.

## Enforcement

- `backend/tests/test_checkpoint_resume.py`: interrupt, `kill -9`, restart,
  sealed assessment byte-identical, ack still resumes, report runs once.
- Two workers racing one `thread_id`: only one resumes, enforced by a row lock
  on `missions.status`.
- A `thread_id` over 255 characters is rejected at the API boundary.
- A checkpoint that deserializes to an unknown type fails closed and does not
  call the LLM.
