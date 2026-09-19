---
title: "test: contract test for the public API"
labels: ["wave-5", "production"]
---
## Why
`test_api.py` covers behaviour, not shape. Removing a field from the assessment payload would break the dashboard and pass CI.

## In scope
- OpenAPI frozen, or schemathesis/pytest over `/api/plan`, `/api/plan/{id}/ack` and `/api/replan`

## Out of scope
- Versioning the API.

## Acceptance
- [ ] Removing a field from the assessment fails CI
- [ ] Adding an optional field does not

## Test that would have failed before
A removed response field broke no test.

## Docs to update
README / practices
