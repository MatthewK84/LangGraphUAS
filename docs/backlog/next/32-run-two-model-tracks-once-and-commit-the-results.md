---
title: "eval: run two model tracks once and commit the results"
labels: ["wave-4", "eval"]
---
## Why
The harness has only ever been run against its own controls. Until a real model has been measured, the leaderboard describes a test rig rather than a finding.

## In scope
- `no_tools` and `calculator_tool` against the frozen pack, one real provider
- Results committed under `eval/results/<date>/`
- Leaderboard regenerated from those files

## Out of scope
- A provider matrix. One model, both tracks, is the claim.

## Acceptance
- [ ] `eval/results/<date>/` contains a real provider
- [ ] The leaderboard is generated from those files, not edited

## Test that would have failed before
The leaderboard contained no measurement of any language model.

## Docs to update
README / LEADERBOARD
