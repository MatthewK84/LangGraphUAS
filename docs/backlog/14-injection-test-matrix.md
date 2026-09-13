---
title: "test: injection matrix (13 rows) + eval_trap corpus kind"
labels: [phase-2, security]
blocked_by: [11, 12, 13]
---
## Goal
Every injection technique we know about is a test that fails loudly, not a paragraph in a design document.

## Scope
`backend/tests/test_injection.py`, against `corpus/eval_trap/` which production ingest refuses by `kind`.

Rows (full table in `docs/injection-defense.md`): classic override, numeric override, invisible unicode, bidi override, fake citation, exfiltration markdown, delimiter spoof, mode escalation, Blue-list spoof, weather alert injection, telemetry string injection, tool-binding regression, node-order regression.

## Acceptance
- [ ] All thirteen rows present and green
- [ ] `kind='eval_trap'` cannot be ingested by the production path
- [ ] The file grows monotonically — rows are added as techniques appear, never pruned
- [ ] Contamination rate measured at 0, gated in CI (#51)
