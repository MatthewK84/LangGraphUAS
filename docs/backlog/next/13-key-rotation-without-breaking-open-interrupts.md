---
title: "ops: key rotation without breaking open interrupts"
labels: ["wave-2", "tenancy", "security"]
---
## Why
A key rotated while an operator has an unacknowledged plan open would either strand the plan or accept a stale identity. Neither is acceptable for a sign-off.

## In scope
- Rotate a key, old key rejected immediately
- An in-flight acknowledgement stays bound to the mission hash, not to the key

## Out of scope
- Automatic rotation schedules.

## Acceptance
- [ ] Rotation test covering an open interrupt
- [ ] The ack still verifies against `inputs_hash` after rotation

## Test that would have failed before
Rotation was untested against the HITL interrupt.

## Docs to update
ops.md
