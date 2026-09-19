---
title: "ui: replan residual panel"
labels: ["wave-3", "ui", "showcase"]
---
## Why
A replan exists to answer 'is this still true?', and the answer is a comparison. Showing only the new number hides the delta that matters.

## In scope
- Briefed vs live energy, wind and state of charge
- Alert codes read from configuration

## Out of scope
- Adding new telemetry fields.

## Acceptance
- [ ] One watch alert forces advisory in the UI
- [ ] The briefed figure is still visible next to the live one

## Test that would have failed before
A replan could change the verdict without showing what moved.

## Docs to update
README
