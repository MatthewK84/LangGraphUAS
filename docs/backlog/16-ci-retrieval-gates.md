---
title: "ci: retrieval gates (leak / hard-negative / false-confirm at zero)"
labels: [phase-2, ci]
blocked_by: [15]
---
## Goal
Three retrieval failures are treated as build breaks, because each one hands a human a plausible wrong limit.

## Gates
| Metric | Rule |
|---|---|
| `wrong_config_leak` | 0 — a `WHERE` clause went missing from one fusion leg |
| `hard_negative_above_positive` | 0 — a plausible wrong limit outranked the right one |
| `false_confirm_rate` | 0 — confident answer on an unanswerable question |
| `sealed_contamination` | 0 |
| `recall@4` | >= 0.90 overall, >= 0.95 on `class=safety_limit` |
| `mrr` | >= 0.80 |

## Regression rule
Compare against `eval/baselines/retrieval.json`. **Fail only when the point estimate drops below the gate or below the baseline's lower bound.** Anything tighter makes CI a coin flip, and a gate people learn to ignore is worse than no gate.

## Scope
- `backend/tests/test_rag_gates.py` runs against the ephemeral Postgres already used for graph tests
- CI corpus of roughly 200 chunks, committed. If the corpus cannot be committed the gate does not run, and a gate that does not run is not a gate.

## Acceptance
- [ ] Gates enforced on PRs, not nightly-only
- [ ] Baseline refresh is a deliberate commit with a reason in the message
- [ ] A deliberately broken filter fails CI — verify by breaking it once
