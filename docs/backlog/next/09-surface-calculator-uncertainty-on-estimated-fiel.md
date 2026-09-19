---
title: "api: surface calculator uncertainty on estimated fields"
labels: ["wave-1", "credibility"]
---
## Why
The UI receives a watt figure with no indication that it came from an estimate. A number shown identically whether measured or guessed invites the reader to treat them alike.

## In scope
- Carry `confidence` and the `source` bucket into the assessment payload the UI renders
- One field per number, not one flag per response

## Out of scope
- Changing how the numbers are computed.

## Acceptance
- [ ] The UI cannot display an estimate as a measured watt
- [ ] A response whose every input is `estimate` is visibly distinguishable in the payload

## Test that would have failed before
The wire payload could not tell a datasheet watt from a derived one.

## Docs to update
README / PLAN-90
