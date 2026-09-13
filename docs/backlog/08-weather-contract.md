---
title: "test: weather timeout and fallback contract"
labels: [phase-2, infra]
blocked_by: [2]
---
## Goal
The degraded weather path must never be mistakable for live data.

## States
| State | Operational allowed |
|---|---|
| `live` | yes |
| `cached_fresh` (< 10 min) | yes |
| `cached_stale` | no, `degraded: true` |
| `fallback` | no, `degraded: true` |
| `error` | no, `degraded: true` |

`source` is tagged by our client from the transport outcome. It is never read from a field in the provider's response body.

## Scope
- 2-3s timeout that cannot hang `/api/plan` or `/api/replan`
- Fake weather client covering: hang, 500, empty body, malformed body, valid body
- `WEATHER_DEGRADED` blocker surfaced to the operator, not buried in logs
- Weather alert strings treated as untrusted text (`docs/injection-defense.md`)

## Acceptance
- [ ] Each failure mode has a test and none produces `source=live`
- [ ] Timeout path returns advisory within the budget
- [ ] An imperative inside `alerts[].description` cannot move the decision
