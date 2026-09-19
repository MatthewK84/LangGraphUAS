---
title: "gate: blue-list snapshot freshness blocker"
labels: ["wave-1", "credibility"]
---
## Why
A pinned Blue UAS snapshot silently ages. An operational claim resting on a year-old snapshot is a claim about the past.

## In scope
- Refresh script for the snapshot
- New blocker `BLUE_LIST_SNAPSHOT_STALE` when the pinned snapshot is older than a configured age
- Advisory mode continues to work with a stale snapshot

## Out of scope
- Fetching the list automatically at request time. Ingest stays deliberate.

## Acceptance
- [ ] A stale snapshot cannot yield operational
- [ ] Advisory still produces a plan with a stale snapshot
- [ ] The age threshold is configuration, not a literal

## Test that would have failed before
A snapshot of any age was treated as current.

## Docs to update
ops.md / threat-model
