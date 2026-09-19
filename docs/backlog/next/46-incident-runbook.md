---
title: "docs: incident runbook"
labels: ["wave-5", "production"]
---
## Why
Four failures are foreseeable and each currently requires improvisation at exactly the wrong moment.

## In scope
- Four playbooks in `docs/ops.md`: weather provider down, seal-violation spike, quarantined corpus, leaked key

## Out of scope
- A general on-call policy.

## Acceptance
- [ ] Four short playbooks exist
- [ ] Each names the metric or log line that signals it

## Test that would have failed before
There was no written response to a seal-violation spike.

## Docs to update
ops.md
