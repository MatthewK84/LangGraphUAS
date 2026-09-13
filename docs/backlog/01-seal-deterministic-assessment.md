---
title: "feat: seal DeterministicAssessment from LLM output"
labels: [phase-1, seal]
blocked_by: []
---
**Commit 0. Nothing else in this plan merges before this does.**

## Goal
The LLM must be physically unable to write any field that can keep an aircraft in the air. Today `make_report_node` receives model output and the graph has no barrier between parsed JSON and persisted results.

## Scope
- `DeterministicAssessment`: `decision` (`go | no_go | insufficient_data`), `reasons`, `energy{}`, `limits{}`, `inputs_hash`, `calculator_version`.
- `backend/suas/calculations/assessment.py` returns it; nothing else constructs one.
- `backend/suas/graph/seal.py` with `seal_assessment()` — a positive allowlist over parsed model output. Unknown keys are dropped, not merged.
- On intersection with the sealed field set: drop, log `llm_field_violation`, increment a counter. Never raise, never retry the model.

## Acceptance
- [ ] Model output containing `"decision": "go"` and fabricated watts leaves the stored assessment at the calculator's `no_go`
- [ ] Parse failure yields `brief_status=unavailable`, never a retry loop
- [ ] `calculator_version` changes when any formula in `calculations/` changes
- [ ] The report node contains no assignment to energy or limit fields from model JSON
- [ ] `llm_field_violations_total{field}` exported

## Files
`backend/suas/schemas/assessment.py`, `backend/suas/graph/seal.py`, `backend/suas/graph/nodes.py`, `backend/suas/calculations/assessment.py`, `backend/tests/test_seal.py`

Spec: `docs/PLAN-90.md` (Commit 0). Invariant: `docs/adr/004-node-order-and-empty-tool-binding.md`.
