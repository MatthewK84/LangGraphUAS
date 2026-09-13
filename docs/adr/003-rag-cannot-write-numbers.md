# 003. Retrieval cannot write a number the calculator owns

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

The datasheet corpus exists to answer one question: *what does the manufacturer
or the list actually say about this field?* The temptation is obvious — if
retrieval can find "minimum battery temperature at takeoff: 10 °C", let it
populate `battery.pack_min_takeoff_c` and skip the hand-curated JSON.

That would make a text-similarity score a load-bearing input to a go/no-go
decision, and it would put attacker-controllable document text on the write path
to a physical limit.

## Decision

`cite_limits` runs after `calculations` and **returns citations, never values**:

```
{field_path, quoted_text, url, page, chunk_id, confidence}
```

Below the confidence threshold, the bundled JSON value stands and
`citation_status=unconfirmed` is recorded. Retrieval never mutates
`DeterministicAssessment`, and the calculator never reads `rag.chunks`.

A future v1.1 may write proposals into a `suggested_overrides` queue for human
review. The calculator ignores that queue until a person accepts an entry, at
which point it becomes ordinary curated reference data with provenance.

Availability follows from the same principle: **if retrieval is down, planning
still runs.** The brief says citations are unavailable; the decision is
unchanged. Operational mode does not require the retriever to be up, because the
retriever is not the oracle. Operational mode *does* require a fresh Blue-list
snapshot (ADR-002), because that is a gate, not an explanation.

## Rejected alternatives

- **Retrieval-populated reference data** — rejected: makes cosine similarity a
  safety input.
- **Model-selected chunks (agentic retrieval)** — rejected: lets injected text
  choose its own evidence. Queries are built from `field_path` and
  `airframe_config_id`, both structured.
- **Blocking operational mode when retrieval is down** — rejected: couples
  flight eligibility to a component that by design cannot affect the answer.

## Consequences

Curated JSON stays the source of truth for numbers, so curation effort does not
go away — `CITATIONS.md` and the provenance linter carry it. The payoff is that
the entire retrieval stack, including a poisoned document, sits outside the
trust boundary of the decision.

## Enforcement

- `sealed_contamination` measured at 0 in `docs/rag-eval.md`, gated in CI.
- `quote_verbatim`: every quoted span is an exact substring of the stored chunk
  after whitespace normalization, checked in the live response assembler, not
  only in the eval.
- No import of `suas.rag` from `suas.calculations`, asserted by a test.
