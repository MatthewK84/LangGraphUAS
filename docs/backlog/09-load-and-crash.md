---
title: "test: 100 concurrent plans + kill -9 checkpoint resume"
labels: [phase-2, infra]
blocked_by: [5]
---
## Goal
Know what breaks first under load, and prove a crash at the interrupt loses nothing.

## Load
`backend/scripts/load_plan.py`
- 100 concurrent `POST /api/plan`, advisory, with `?brief=false` so the run spends nothing on tokens (add the flag as part of this issue)
- Pass bar: p95 under 2s without the model, zero 5xx, every thread checkpointed
- Repeat at 10 concurrent with the model on

## Crash
1. Start a plan, stop at the `human_ack` interrupt
2. `kill -9` the API worker
3. Restart Compose
4. `GET /api/plan/{thread_id}` returns the sealed assessment
5. Ack resumes and the report runs exactly once

Same drill for a replan mid-node if that path is checkpointed.

## Concurrency
Two workers must never resume one `thread_id`. Row lock on `missions.status`.

## Acceptance
- [ ] Load results documented in `docs/ops.md` with the date and the machine
- [ ] Crash drill reproducible from the README
- [ ] Two-worker race test passes
- [ ] In-process rate limiting documented as single-worker-only until Redis exists
