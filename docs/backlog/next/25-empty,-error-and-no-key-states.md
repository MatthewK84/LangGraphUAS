---
title: "ui: empty, error and no-key states"
labels: ["wave-3", "ui", "showcase"]
---
## Why
Without an OpenAI key the system is fully functional and produces deterministic prose. A UI that fakes a thinking state is lying about a supported configuration.

## In scope
- No key: deterministic brief, no fabricated 'thinking'
- Backend down: readable failure
- Empty result: explicit

## Out of scope
- Adding a retry UI.

## Acceptance
- [ ] Three UI states covered by component tests
- [ ] The no-key path is visually honest about what produced the text

## Test that would have failed before
The absence of a model key had no defined presentation.

## Docs to update
README
