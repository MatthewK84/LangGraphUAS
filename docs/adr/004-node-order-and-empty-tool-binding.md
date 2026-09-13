# 004. Node order and empty tool binding are security controls

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

There is no prompt that makes a model reliably ignore instructions embedded in
text it is given. Every filter in `docs/injection-defense.md` reduces a rate;
none eliminates a class. The system is safe because of two structural facts, and
both look like ordinary architecture choices that a future refactor could
undo for good reasons.

## Decision

**Two invariants, held as security controls rather than as design preferences.**

1. **`human_ack` precedes `report`.** The operator signs a sealed assessment
   that no retrieved text and no model output has touched. Injection therefore
   cannot change what was signed; at worst it corrupts prose rendered after the
   signature. Moving `report` earlier — to hide latency behind the review card,
   for instance — silently converts a structural guarantee into a filtering
   problem.

2. **The `report` node has no tools bound.** Not tools it is instructed not to
   call: an empty binding. The graph gains no general-purpose tool node. A
   retrieval tool the model can aim is a tool an injected document can aim.

Corollaries that follow and are not separately negotiable: the LLM client runs
under a hard `max_tokens` and wall-clock timeout (wallet exhaustion is denial of
service); `/api/replan` calls neither retrieval nor the model by default; and
the system prompt is written on the assumption that it will leak, so it contains
no keys, no internal endpoints, and no bypass phrases.

## Rejected alternatives

- **Brief first, ack after, with a "regenerate" button** — rejected: the
  operator would be signing something a document could have influenced.
- **Tool-enabled report node for on-demand lookups** — rejected: gives injected
  text a way to act rather than only to speak.
- **Prompt-only defense** — rejected as a primary control; retained as depth.

## Consequences

Briefs are generated once, after acknowledgement, which costs a round trip the
UI has to absorb. In exchange, a suppressed or garbled brief is a display
problem rather than a safety problem — a distinction `docs/ops.md` records for
incident response: **a suppressed brief does not invalidate an ack.**

## Enforcement

- `backend/tests/test_injection.py::test_ack_precedes_report` asserts node order
  on the compiled graph.
- `backend/tests/test_injection.py::test_report_node_has_no_tools` asserts the
  bound-tool list is empty.
- Both tests fail if the invariant is removed, which is the point: the refactor
  that would break this is the one that looks reasonable in review.
