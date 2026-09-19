---
title: "ops: migrations as an explicit deploy step"
labels: ["wave-2", "tenancy", "security"]
---
## Why
The container runs `alembic upgrade head` on start. That is convenient locally and wrong in production, where a schema change should be a decision rather than a side effect of a restart.

## In scope
- Documented migration step for Compose, Railway and ops.md
- Optional `migrate` service
- App container upgrades only behind an explicit flag

## Out of scope
- Changing any migration.

## Acceptance
- [ ] The app container does not silently upgrade head unless a flag says so
- [ ] The documented path is the one the runbook uses

## Test that would have failed before
A rollback would have been silently re-upgraded by the next restart.

## Docs to update
ops.md / README / railway.md
