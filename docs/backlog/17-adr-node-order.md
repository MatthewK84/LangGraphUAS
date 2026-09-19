---
title: "adr: node order and empty tool binding are security controls"
labels: [phase-1, security]
blocked_by: [1]
---
## Goal
Two invariants that look like ordinary architecture choices are recorded as security controls, so the reasonable-looking refactor that breaks them fails CI instead of review.

## The invariants
1. **`human_ack` precedes `report`.** The operator signs a sealed assessment no retrieved text and no model output has touched. Injection cannot change what was signed. Moving `report` earlier to hide latency converts a structural guarantee into a filtering problem.
2. **The `report` node has no tools bound.** Not tools it is told not to call — an empty binding. A retrieval tool the model can aim is a tool an injected document can aim.

Corollaries: hard `max_tokens` and wall-clock timeout on the LLM client; `/api/replan` calls neither retrieval nor the model by default; the system prompt is written assuming it leaks.

## Scope
- `docs/adr/004-node-order-and-empty-tool-binding.md` (drafted, needs review and acceptance)
- `test_ack_precedes_report` — asserts node order on the compiled graph
- `test_report_node_has_no_tools` — asserts the bound-tool list is empty

## Acceptance
- [ ] Both tests fail when the invariant is removed — verify by removing each once
- [ ] `docs/ops.md` records that a suppressed brief does not invalidate an ack
- [ ] ADR reviewed and marked Accepted

## Shipped

ADR-004 is Accepted. `docs/ops.md` records that a suppressed brief does not
invalidate an acknowledgement. Both invariants are asserted by tests that live
in `backend/tests/test_injection.py` as matrix rows 12 and 13, rather than in a
file of their own -- they are injection controls, and keeping them in the matrix
means the drift test counts them.

Both were verified by removing the invariant once, which is the acceptance
criterion that matters:

- Rewiring `cite_limits -> report` (the "move report earlier to hide latency"
  refactor the ADR names) fails `test_human_ack_precedes_report`.
- Binding a `search_corpus` tool to the report model fails
  `test_the_report_node_has_no_tools_bound`, which reads the bound-tool list
  rather than trusting the model type.

Both pass again once restored.
