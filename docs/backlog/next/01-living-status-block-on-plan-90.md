---
title: "docs: living status block on PLAN-90"
labels: ["wave-1", "credibility"]
---
## Why
PLAN-90.md still reads as a future calendar. Anyone landing on the repo cannot tell what is done, what is blocked, or what comes next without reading the whole file and the commit log.

## In scope
- A `Status as of YYYY-MM-DD` block at the top of `docs/PLAN-90.md`
- Three sub-headings: **On main**, **Blocking operational mode**, **Next three PRs**
- Updated as part of any PR that changes what is on main

## Out of scope
- Rewriting the 90-day calendar itself. The calendar is the plan; this is the odometer.

## Acceptance
- [ ] A stranger can name the current week and the blockers in 30 seconds
- [ ] The blockers listed match the `Blocker` enum values the gate can actually emit

## Test that would have failed before
A reader asked 'is operational mode reachable today?' would have had to read `calculations/gate.py` to answer. Now the file answers it.

## Docs to update
PLAN-90
