---
title: "feat: shared weather cache"
labels: ["wave-2", "tenancy", "security"]
---
## Why
Same defect as the limiter: each worker fetches its own weather, so the cache TTL means less than it claims and the provider sees more traffic than intended.

## In scope
- Shared cache behind the existing weather service interface
- TTL semantics unchanged

## Out of scope
- Changing the weather contract or its provenance states.

## Acceptance
- [ ] Worker B serves `cached_fresh` from worker A's fetch within TTL
- [ ] A cache miss still records the correct source state

## Test that would have failed before
Cache hit rate was per process and never measured across workers.

## Docs to update
README / ops.md
