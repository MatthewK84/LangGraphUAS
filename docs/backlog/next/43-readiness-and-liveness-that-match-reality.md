---
title: "ops: readiness and liveness that match reality"
labels: ["wave-5", "production"]
---
## Why
`/ready` currently answers a different question from the one the platform asks it. A container that is up but unmigrated should not receive traffic; a container with no model key should.

## In scope
- `/ready` fails on database unavailable or migrations not applied
- `/ready` stays up when no model key is configured, because advisory is a supported mode

## Out of scope
- Adding new endpoints.

## Acceptance
- [ ] Documented in ops.md
- [ ] Smoke test covers both directions

## Test that would have failed before
An unmigrated container reported ready.

## Docs to update
ops.md
