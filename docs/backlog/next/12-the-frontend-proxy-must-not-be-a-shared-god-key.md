---
title: "fix: the frontend proxy must not be a shared god key"
labels: ["wave-2", "tenancy", "security"]
---
## Why
The dashboard holds one backend key for every browser. Two people on the same deployment currently share one identity, which makes issue 11 decorative.

## In scope
- Map a browser session or demo token to an operator key server-side
- Default Compose file demonstrates the mapping

## Out of scope
- Real authentication. A demo token is enough to prove the boundary exists.

## Acceptance
- [ ] Two browsers cannot resume each other's threads in the default Compose file
- [ ] The browser still never sees a backend key

## Test that would have failed before
Two browsers against one dashboard were the same operator.

## Docs to update
README / threat-model
