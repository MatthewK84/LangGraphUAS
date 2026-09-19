---
title: "docs: threat-model row for any new processor"
labels: ["wave-2", "tenancy", "security"]
---
## Why
Adding a processor — LangSmith, object storage, an embedder API — moves data across a trust boundary. That analysis is worth nothing if it arrives after the client is already calling out.

## In scope
- A STRIDE row in `docs/threat-model.md` ships in the same PR as any new processor
- Recorded as a review rule, not a hope

## Out of scope
- Retrospective rows for existing processors, which are already documented.

## Acceptance
- [ ] `docs/threat-model.md` gains the row before the client is called
- [ ] The rule is written where a reviewer will see it

## Test that would have failed before
A new egress destination could be added with no threat-model change.

## Docs to update
threat-model / practices
