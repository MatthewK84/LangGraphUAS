---
title: "ci: fail when a calculator bump outruns the fixtures"
labels: ["wave-4", "eval"]
---
## Why
`generate_eval_fixtures.py` already regenerates expected values from the oracle, and the mission tests already refuse a pack built by two calculators. What is missing is the link: a `CALCULATOR_VERSION` bump can still merge while the committed pack carries the old one.

## In scope
- CI check comparing `CALCULATOR_VERSION` against the version stamped in `eval/fixtures/missions.jsonl`
- Failure message that names the regeneration command

## Out of scope
- Regenerating fixtures automatically. Regeneration stays a deliberate commit.

## Acceptance
- [ ] A `CALCULATOR_VERSION` bump fails CI until expected values are regenerated
- [ ] The failure tells the reader exactly what to run

## Test that would have failed before
A calculator change could merge with a stale expected-value pack and every mission test would still pass.

## Docs to update
practices / PLAN-90
