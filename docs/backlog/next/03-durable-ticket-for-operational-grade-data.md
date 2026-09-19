---
title: "docs: durable ticket for operational-grade data"
labels: ["wave-1", "credibility"]
---
## Why
The README points at a dead reference for provenance work. The 76 reference fields are the reason operational mode is unreachable, and that fact currently has no live home.

## In scope
- One issue listing all 76 fields bucketed by `source` (datasheet / flight_log / secondary / derived / estimate / unknown)
- README links it
- `backend/suas/data/CITATIONS.md` table regenerated from the JSON so the two cannot drift

## Out of scope
- Actually promoting fields. That is issues 4 and 6.

## Acceptance
- [ ] README links a live issue, not a dead one
- [ ] The CITATIONS.md table matches `aircraft.json` and `payloads.json` field for field

## Test that would have failed before
CITATIONS.md could disagree with the seed JSON and nothing would notice.

## Docs to update
README / CITATIONS.md
