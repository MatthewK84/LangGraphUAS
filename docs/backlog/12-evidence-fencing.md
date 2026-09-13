---
title: "feat: nonce-fenced evidence block + chunk_id-only citation"
labels: [phase-2, security]
blocked_by: [11]
---
## Goal
Retrieved text reaches the model as clearly delimited data whose fences cannot be forged, and the model never handles a URL.

## Scope
- Per-request nonce fence: `<<<EV:{nonce}:{chunk_id}>>> ... <<<END:{nonce}>>>`. A static delimiter is guessable by anyone reading this public repository.
- Evidence cited by `chunk_id` only. The assembler maps id to URL at render time.
- System prompt states that evidence is data, never instruction, and that an anomaly goes in `suggested_contingencies` rather than changing a decision.
- The system prompt is written assuming it leaks: no keys, no internal endpoints, no bypass phrases.
- `cite_limits` node wiring per `docs/retrieval.md`: structured query from `field_path` plus `airframe_config_id`, never the operator's free text against the whole corpus.

## Acceptance
- [ ] A chunk containing a literal `<<<END:` cannot break the fence
- [ ] The model never emits a URL; rendered URLs all come from `rag.documents`
- [ ] Retrieval failure yields `citation_status=unavailable` and the plan still runs
- [ ] No model-selected retrieval: queries are built from structured fields only
