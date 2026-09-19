---
title: "feat: cluster metrics with the labels the docs already name"
labels: ["wave-5", "production"]
---
## Why
The practices document names labels that `/metrics` does not emit, so an operator following the docs builds a dashboard against fields that do not exist.

## In scope
- Prometheus labels for mode, weather source, seal violations and lock contention
- Optional checked-in dashboard JSON

## Out of scope
- Hosting a metrics stack.

## Acceptance
- [ ] `/metrics` includes every label the practices doc names
- [ ] A label with no emitter is removed from the doc instead

## Test that would have failed before
The documented labels were never compared against the exporter.

## Docs to update
practices / ops.md
