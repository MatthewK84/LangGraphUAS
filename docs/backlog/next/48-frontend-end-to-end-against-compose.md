---
title: "test: frontend end-to-end against Compose"
labels: ["wave-5", "production"]
---
## Why
Every frontend test today runs against mocks. Nothing proves the dashboard and the planner agree once they are in separate containers.

## In scope
- Playwright in CI or nightly: catalog load, plan, ack
- Advisory fixture weather, no live provider

## Out of scope
- Testing against a deployed environment.

## Acceptance
- [ ] The suite uses fixture weather and needs no live METAR
- [ ] A catalog contract break fails the run

## Test that would have failed before
Dashboard and planner were only ever tested apart.

## Docs to update
README / practices
