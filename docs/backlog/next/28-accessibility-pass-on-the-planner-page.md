---
title: "ui: accessibility pass on the planner page"
labels: ["wave-3", "ui", "showcase"]
---
## Why
A NO-GO that fails contrast, or a confirm modal that cannot be reached by keyboard, is a safety control that some operators cannot use.

## In scope
- Keyboard path to acknowledge
- Contrast on the NO-GO treatment
- Focus trap on the confirm modal

## Out of scope
- A full audit of every page.

## Acceptance
- [ ] axe or equivalent runs in frontend CI against the planner page
- [ ] The ack path is completable without a mouse

## Test that would have failed before
The acknowledgement could not be completed by keyboard.

## Docs to update
README
