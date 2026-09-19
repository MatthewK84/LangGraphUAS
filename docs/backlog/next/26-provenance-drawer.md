---
title: "ui: provenance drawer"
labels: ["wave-3", "ui", "showcase"]
---
## Why
Issue 9 puts provenance on the wire. This makes it reachable, which is the point: a number a reviewer cannot trace is a number they have to take on faith.

## In scope
- Click a number, see `source`, `source_url`, `confidence`, `retrieved_at`
- Estimated fields labelled as estimates

## Out of scope
- Editing provenance from the UI.

## Acceptance
- [ ] Estimated fields are labelled
- [ ] Datasheet fields link out to the cited URL

## Test that would have failed before
A displayed watt had no path back to its source.

## Docs to update
README
