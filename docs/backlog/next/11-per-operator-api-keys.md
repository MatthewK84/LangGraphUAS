---
title: "feat: per-operator API keys"
labels: ["wave-2", "tenancy", "security"]
---
## Why
One shared key means every caller can read every mission. A thread id is currently the only thing standing between two operators, and thread ids are guessable enough to matter.

## In scope
- `operator_key_id` recorded on missions
- A mismatch returns **404, not 403**, so the API does not confirm a thread exists to someone who cannot read it

## Out of scope
- User accounts, roles, or a login UI.

## Acceptance
- [ ] Key A cannot read key B's `thread_id`
- [ ] The refusal is indistinguishable from a thread that does not exist

## Test that would have failed before
Any valid key could read any thread.

## Docs to update
README / ops.md / threat-model
