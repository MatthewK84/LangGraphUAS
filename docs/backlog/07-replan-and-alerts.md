---
title: "feat: POST /api/replan + Alert schema"
labels: [phase-2, infra]
blocked_by: [5]
---
## Goal
Compare briefed energy against live telemetry and say something useful about the difference.

## Telemetry snapshot
```
thread_id, ts, lat, lon, alt_m, soc_fraction,
voltage_v?, current_a?, power_w?, wind_mps?, wind_from_deg?,
oat_c, payload_attached, remaining_leg_m,
phase: hover|cruise|climb|descent|unknown
```
`remaining_leg_m` is required. Do not assume the briefed distance still applies.

## Graph
```
ingest_telemetry -> merge_briefed_state -> recalculate -> compare -> alert -> END
```
Runs on a **child thread** `{parent}:{replan_seq}`; the parent brief stays immutable (`docs/adr/001-checkpointer-strategy.md`). Remaining energy is SOC times cited `battery_wh` times the current temperature derate.

## Alert schema
```
severity: info | watch | warning | abort
code: ENERGY_BELOW_RESERVE | WIND_EXCEEDS_LIMIT | SOC_STALE | WEATHER_DEGRADED
briefed: {...}   live: {...}   delta: {...}
recommended_action: continue | land_soon | land_now | advisory_only
```
Starting thresholds, in config, deliberately conservative:
- live residual below briefed reserve -> `abort` / `land_now`
- live residual below 1.5x reserve -> `warning` / `land_soon`
- wind above the airframe limit -> `abort`
- snapshot older than 30s in an operational replan -> `watch`, and operational is refused

Replan alerts never auto-invoke the LLM. An optional post-alert brief follows the same seal rules.

## Acceptance
- [ ] Brief a plan, post a snapshot that burned more energy than expected, receive `ENERGY_BELOW_RESERVE` with both number sets
- [ ] Parent thread JSON unchanged after a replan
- [ ] Seal holds on this path
