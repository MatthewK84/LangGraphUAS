---
title: "ui: weather source chip"
labels: ["wave-3", "ui", "showcase"]
---
## Why
Weather provenance decides whether operational is even possible, and it currently lives in JSON where nobody looks.

## In scope
- `live | cached_fresh | cached_stale | fallback | error` rendered in the thread panel
- Distinct treatment per state

## Out of scope
- Changing the weather contract.

## Acceptance
- [ ] `fallback` cannot be styled as `live`
- [ ] Every state in the enum has a rendering

## Test that would have failed before
A fallback reading was visually identical to a live one.

## Docs to update
README
