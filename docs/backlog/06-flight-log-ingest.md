---
title: "feat: flight-log ingest + hover/cruise power estimator (one airframe)"
labels: [phase-1, data]
blocked_by: [3]
---
## Goal
One airframe gets real power numbers from a real log, so `source=flight_log` means something. Pick the airframe you can actually get a CSV for, self-flown or public. **Do not fake a log.**

## Schema
`timestamp, airframe_id, voltage_v, current_a, power_w, alt_m, tas_mps (or groundspeed + wind), outside_temp_c, payload_id, phase: hover|climb|cruise|descent|unknown`

`POST /api/logs` stores raw and parsed rows.

## Estimator
Pure functions in `backend/suas/calculations/from_log.py`:
- Median hover watts over a hover window, rejecting windows whose climb rate exceeds a threshold
- Median cruise watts in level flight
- Sample count, IQR, and `confidence: low|medium|high`

Written back as `source: flight_log` with `n` and `log_id`.

## Gate interaction
An airframe with flight-log power may run `operational` even when its datasheet power was `estimate`. Live weather is still required.

## Acceptance
- [ ] One airframe at `source=flight_log`, n >= 30 hover samples, or a documented reason for fewer
- [ ] Redacted sample CSV in `backend/tests/fixtures/logs/`
- [ ] README section: how to record a log, units, what a hover window means
- [ ] Estimator functions are pure and unit-tested against the fixture
