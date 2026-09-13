---
title: "feat: HITL interrupt + POST /api/plan/{thread_id}/ack"
labels: [phase-1, infra]
blocked_by: [1, 2]
---
## Goal
No brief exists without a human acknowledgement recorded against the exact assessment that was signed.

## Graph change
```
START -> validate -> weather -> calculations -> human_ack -> report -> END
```
`human_ack` interrupts with the sealed assessment, blockers, requested mode, and editable fields (altitude, hover time, payload id).

`POST /api/plan/{thread_id}/ack` with `{"action": "confirm" | "edit" | "abort", "edits": {...}}`, resumed via `Command(resume=...)`.
- `edit` re-enters `calculations`, not validate-from-scratch unless the airframe changed
- `abort` persists `decision: aborted` and never calls the LLM

## Persistence
Store `ack_actor`, `ack_at`, and the signed assessment hash. A changed `inputs_hash` or `calculator_version` invalidates the ack.

## Checkpoint durability
`durability="sync"` at `calculations` and `human_ack` — never `exit`. See `docs/adr/001-checkpointer-strategy.md`.

## Acceptance
- [ ] Confirm without an ack record: report never runs, no model call in logs
- [ ] Editing payload mass changes residual energy, produces a new hash, invalidates the prior ack
- [ ] Kill the process at the interrupt, resume from Postgres, assessment byte-identical
- [ ] Frontend is two-step: compute, review card, confirm, with an explicit advisory checkbox

Node order is a security control — see #17.
