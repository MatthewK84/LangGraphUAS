---
title: "feat: shared rate limiter"
labels: ["wave-2", "tenancy", "security"]
---
## Why
The limiter is per process. With two workers the effective ceiling is double what the configuration says, and the README admits it.

## In scope
- Redis or equivalent as the production path
- Per-process limiter remains the local default

## Out of scope
- Per-operator quotas. One shared ceiling first.

## Acceptance
- [ ] Two workers share one ceiling
- [ ] The README operational note is deleted or corrected

## Test that would have failed before
The documented limit was wrong by a factor of the worker count.

## Docs to update
README / ops.md
