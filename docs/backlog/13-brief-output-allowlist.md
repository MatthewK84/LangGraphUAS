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
