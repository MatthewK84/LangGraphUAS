---
title: "feat: checkpoint purge job"
labels: ["wave-2", "tenancy", "security"]
---
## Why
Retention runs at process start. A long-lived process therefore never purges, and `SUAS_CHECKPOINT_RETENTION_DAYS` quietly means nothing in production.

## In scope
- Scheduled purge of threads past retention
- Runs without a restart

## Out of scope
- Changing what a checkpoint stores.

## Acceptance
- [ ] A thread older than the retention window is gone without a restart
- [ ] Purging a thread does not break an unrelated replan child

## Test that would have failed before
Retention was only enforced by restarting.

## Docs to update
ops.md
