---
title: "feat: assessment_mode advisory|operational"
labels: [phase-1, seal]
blocked_by: [1]
---
## Goal
A plan is either `advisory` or `operational`, and the mode is computed by the backend from inputs — never asserted by the client, never by the model.

## Gate (computed in the `validate` node)
```
can_be_operational =
    weather.source == "live"
    and airframe.power.source in {"datasheet", "flight_log"}
    and payload.power.source != "missing"
    and not weather.degraded
    and citations_complete
    and blue_status in {"cleared", "select"}
```
If the client asked for `operational` and the gate fails, the plan runs as `advisory` with populated `blockers: [...]`.

**Open decision to record in an ADR:** return `409`, or return `200` with the mode forced down and `degraded: true`. Pick one and keep it.

## Acceptance
- [ ] `assessment_mode` on the request, on `MissionState`, and on the persisted mission row
- [ ] Fallback or stale weather can never produce `operational`
- [ ] Every downgrade carries a machine-readable blocker code
- [ ] Dashboard shows a red banner for advisory; a green GO badge is impossible in advisory mode
- [ ] Model output claiming `"mode": "operational"` is ignored

## Files
`backend/suas/schemas/requests.py`, `backend/suas/graph/nodes.py`, `backend/suas/graph/state.py`, `frontend/src/app/components/`, `backend/tests/test_modes.py`
