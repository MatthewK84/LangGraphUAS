---
title: "feat: LangSmith opt-in with redaction"
labels: ["wave-5", "production"]
---
## Why
Tracing is the single easiest way to send mission coordinates and raw briefs to a third party by accident. It is issue 41 and not issue 1 because it does not make a single watt more true.

## In scope
- Off by default
- `SUAS_LANGSMITH_*` mapped to `LANGSMITH_*`
- Coordinates and raw brief hidden outside a local environment
- Tracers flushed on shutdown

## Out of scope
- Tracing as a default. Default off, always.

## Acceptance
- [ ] CI never calls the service
- [ ] Unit test proves coordinates are hidden in a non-local environment
- [ ] Threat-model row from issue 20 ships in the same PR

## Test that would have failed before
No test proved coordinates stayed out of a trace payload.

## Docs to update
threat-model / ops.md / README
