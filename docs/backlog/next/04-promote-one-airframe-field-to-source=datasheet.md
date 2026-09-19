---
title: "data: promote one airframe field to source=datasheet"
labels: ["wave-1", "credibility"]
---
## Why
Every reference number is currently `secondary` or weaker, which is why the operational gate is shut. One field with a real manufacturer URL proves the promotion path works end to end.

## In scope
- Pick one limit with a public manufacturer URL
- Set `source`, `source_url`, `retrieved_at`, `confidence`
- Keep the provenance CI check that rejects bare numbers

## Out of scope
- Bulk promotion. One field, proven, beats 76 asserted.

## Acceptance
- [ ] CI still fails a bare number
- [ ] That one field is no longer `secondary` or `estimate`
- [ ] The URL resolves and the retrieved_at is the date it was read

## Test that would have failed before
No test distinguished 'we have a URL' from 'we have a citation'.

## Docs to update
CITATIONS.md / README
