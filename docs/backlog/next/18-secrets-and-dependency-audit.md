---
title: "ci: secrets and dependency audit"
labels: ["wave-2", "tenancy", "security"]
---
## Why
Auditing is manual, which means it happens when someone remembers. A leaked key is the failure with the shortest path to real harm.

## In scope
- `gitleaks` on pull requests
- Scheduled `pip-audit` and `npm audit`, non-blocking first, then gate what can actually be fixed

## Out of scope
- Re-adding the dependency-audit job that was removed for flakiness. Scheduled, not per-PR.

## Acceptance
- [ ] A committed test credential fails the PR
- [ ] The Known Limitation about manual-only auditing is no longer true for the scheduled part

## Test that would have failed before
A committed key would have been caught only by a human reading the diff.

## Docs to update
README / practices
