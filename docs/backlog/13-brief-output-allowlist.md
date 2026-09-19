---
title: "feat: BriefOutput allowlist + contradiction linter + markdown sanitizer"
labels: [phase-1, security]
blocked_by: [1]
---
## Goal
Model output is parsed into a closed model, checked against the sealed assessment, and rendered without any way to reach outward.

**Ships with #40, not in Phase 3.** The first brief that exists is the first brief that can be wrong.

## Pipeline (small pure functions in `backend/suas/graph/seal.py`)
1. **Parse** into `BriefOutput` with `extra="forbid"` and length caps. Failure yields `brief_status=unavailable` — never a retry loop that lets the model negotiate to a valid-looking object.
2. **Drop sealed keys**, incrementing `llm_field_violations_total{field}`.
3. **Resolve citations.** A `chunk_id` not among this request's spans is dropped and counted as `hallucinated_citation`.
4. **Contradiction lint.** With a sealed `no_go`, scan prose for go-language outside a negated context. On a hit, **replace** the brief with a template rendered from the sealed object and set `brief_status=suppressed_contradiction`. Do not truncate silently — silent truncation hides an attack in progress.
5. **Numeric trace.** Regex unit-bearing numerics, set-difference against sealed values and cited spans. Over threshold: suppress and template.
6. **Render.** BFF sanitizer: no raw HTML, no images, no auto-linking, allowlisted hosts only, `rel="noopener noreferrer"`.

The UI renders `decision` from the sealed object as its own component, above the prose, from a different data path.

## Acceptance
- [ ] Unknown keys rejected, not merged
- [ ] A sealed `no_go` with go-language in prose produces a templated brief and a loud log
- [ ] An `<img src>` in chunk text cannot reach the rendered page
- [ ] `brief_suppressed_total{reason}` and `hallucinated_citation_total` exported

## Shipped

Steps 1, 2, 4 and 6 were already in place from #40. This completes 5 and the
metrics, and records honestly what step 3 and step 6 actually are.

**Step 5, the numeric trace,** is `unsupported_numerics()` in
`backend/suas/graph/seal.py`, wired into `_vet_prose`. Not a rate check: a brief
is short, and one wattage the calculator never produced is the whole failure
mode. The 0.02 in `docs/rag-eval.md` is the corpus-level measurement, not a
per-brief tolerance. Rounding is accepted -- a calculator value of 119.94 W
written as "120 W" is readable prose, not invention -- by matching at whatever
precision the prose chose.

It is **unit-blind**, and that is asserted in a test rather than left in a
docstring: a wind speed of 6.9 m/s will vouch for "7 W". Unit-awareness would
mean inferring units from JSON key suffixes, which cannot work for numbers
quoted out of citation text, since free prose carries no key. Closing it later
should be a visible change.

**Step 3 guards a shape we do not ship.** `resolve_citations()` exists and is
tested, but production never calls it, because `ReportService.generate` returns
a `str` -- the model has no citation channel to abuse. See #49.

**Step 6 is not a sanitizer, and is stronger for it.** `ResultsPanel.tsx`
interpolates the brief as a JSX text child, so React escapes it. A sanitizer can
have a bypass; escaping by construction cannot. `src/lib/render-safety.test.ts`
asserts the three things that would undo it: no `dangerouslySetInnerHTML`
anywhere, the report still rendered as a text child, and no markdown-to-HTML
dependency -- so the failure lands on whoever adds a renderer.

`brief_suppressed_total{reason}` and `hallucinated_citation_total` are exported,
both at zero, because a counter that only appears once it fires cannot be
alerted on. The reason label splits a contradiction from an invented number:
one suggests an injected document, the other a model writing from memory.

Verified by mutation. Removing the trace from the report node fails
`test_the_node_suppresses_a_brief_stating_an_invented_wattage` -- which the
pure-function tests alone did not catch, and which is why that test exists.
