---
title: "ops: backup and restore of missions and checkpoints"
labels: ["wave-5", "production"]
---
## Why
An acknowledgement is a signature on a specific assessment. A restore that cannot reproduce the hash has lost the signature while appearing to keep it.

## In scope
- Backup and restore script
- ops.md section

## Out of scope
- Continuous replication.

## Acceptance
- [ ] A restored thread's ack still verifies against `inputs_hash`
- [ ] The runbook is the procedure that was actually tested

## Test that would have failed before
No restore had ever been verified against a stored acknowledgement.

## Docs to update
ops.md
