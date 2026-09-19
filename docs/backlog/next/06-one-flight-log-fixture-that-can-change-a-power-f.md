---
title: "data: one flight-log fixture that can change a power field"
labels: ["wave-1", "credibility"]
---
## Why
`source=flight_log` is the only bucket that beats a datasheet for power, and nothing in the repo exercises it end to end.

## In scope
- One redacted flight log CSV, n >= 30 hover samples
- IQR estimator applied through the existing ingest path
- The `apply=true` path documented

## Out of scope
- Changing the production seed. The seed stays `estimate` until that is a deliberate choice.

## Acceptance
- [ ] One field becomes `source=flight_log` in a test database
- [ ] The production seed is unchanged by the test
- [ ] Fewer than 30 samples is refused, not averaged

## Test that would have failed before
The estimator had no fixture proving a real log changes a stored field.

## Docs to update
README / ops.md
