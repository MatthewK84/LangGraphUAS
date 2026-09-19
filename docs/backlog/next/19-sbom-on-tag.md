---
title: "ci: SBOM on tag"
labels: ["wave-2", "tenancy", "security"]
---
## Why
The practices doc claims a software bill of materials. There is none.

## In scope
- CycloneDX or SPDX generated on `v*` tags
- Attached as a release asset

## Out of scope
- SBOM on every PR.

## Acceptance
- [ ] A release asset exists for the next tag
- [ ] The practices doc matches what the workflow produces

## Test that would have failed before
The practices doc described an artifact that was never generated.

## Docs to update
practices
