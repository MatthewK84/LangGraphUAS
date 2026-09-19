---
title: "feat: request-scoped trace metadata without a tracing vendor"
labels: ["wave-5", "production"]
---
## Why
Most of what tracing is wanted for is answerable from the logs already emitted, if they carried four more fields.

## In scope
- `calculator_version`, `weather_source`, `assessment_mode` and the request id on every plan log line

## Out of scope
- A log shipping pipeline.

## Acceptance
- [ ] One grep of a fixture log shows all four fields on a single line
- [ ] The fields are present on the failure path too

## Test that would have failed before
A plan log line could not be tied to the calculator that produced it.

## Docs to update
ops.md / practices
