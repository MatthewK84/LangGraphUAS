---
title: "ui: unmissable advisory banner"
labels: ["wave-3", "ui", "showcase"]
---
## Why
The single most expensive misreading of this product is treating an advisory plan as a clearance. A banner that scrolls away is a banner that was there for the screenshot.

## In scope
- Mode, weather source and 'not a clearance' visible through scroll
- Present whenever `assessment_mode=advisory`

## Out of scope
- Restyling the rest of the page.

## Acceptance
- [ ] Snapshot test covers the banner
- [ ] The banner is present whenever the mode is advisory, including after a replan

## Test that would have failed before
Nothing asserted the advisory warning survived scrolling.

## Docs to update
README
