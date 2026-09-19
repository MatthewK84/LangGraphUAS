---
title: "docs: split engineering practices into Enforced vs Aspirational"
labels: ["wave-1", "credibility"]
---
## Why
`engineering-practices.md` describes gates as though they all run. Some do, some are intentions. A practices doc that overstates CI is worse than no practices doc, because a reviewer stops checking.

## In scope
- Split `docs/engineering-practices.md` into **Enforced in CI** and **Aspirational**
- Every Enforced entry names the job in `.github/workflows/ci.yml`
- README Known Limitations reconciled against the same list

## Out of scope
- Adding new gates. This issue only tells the truth about the ones that exist.

## Acceptance
- [ ] Every gate named as blocking appears in `.github/workflows/ci.yml`
- [ ] Nothing in Enforced is unverifiable from the workflow file

## Test that would have failed before
A reader could believe dependency auditing blocked merges. It does not; the job was removed.

## Docs to update
README / practices
