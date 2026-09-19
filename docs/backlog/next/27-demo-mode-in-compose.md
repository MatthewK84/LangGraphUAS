---
title: "feat: demo mode in Compose"
labels: ["wave-3", "ui", "showcase"]
---
## Why
The fastest way to lose a reviewer is a quickstart that needs three secrets. Advisory mode needs none of them.

## In scope
- `docker compose up` with no LLM key and no tracing key
- Advisory only
- No secrets in `docker-compose.yml`

## Out of scope
- A hosted demo.

## Acceptance
- [ ] README quickstart works on a clean machine
- [ ] No secret values appear in the Compose file

## Test that would have failed before
The quickstart was never run against a machine with no keys.

## Docs to update
README
