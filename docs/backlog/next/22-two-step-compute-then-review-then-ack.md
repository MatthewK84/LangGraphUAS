---
title: "ui: two-step compute then review then ack"
labels: ["wave-3", "ui", "showcase"]
---
## Why
The operator signs a sealed assessment. If the brief renders before the signature, the thing signed is not the thing read.

## In scope
- Review card shows sealed numbers only
- Confirm disabled until the displayed hash matches the assessment
- Editing any input invalidates confirm

## Out of scope
- Changing the graph's node order, which is already an ADR-004 invariant.

## Acceptance
- [ ] Playwright: no brief exists before ack
- [ ] An edit invalidates a pending confirm

## Test that would have failed before
The UI could have shown generated prose before the operator signed.

## Docs to update
README / ADR-004
