# RAG evaluation — metrics that can fail a build

The Phase 3 leaderboard evaluates models. This evaluates our retriever, runs on
every PR, and calls a model only where it cannot be avoided.

## The design advantage

`field_path` is a label applied at ingest. That makes retrieval evaluation a
supervised classification problem with free ground truth rather than a judgment
call. No evaluation framework dependency, no LLM judge on the critical path:
deterministic set arithmetic in `backend/suas/eval/retrieval_metrics.py`, pure
functions, no I/O.

**Anything checkable with a substring compare or a set intersection is never
checked by a model.**

## Fixture format

`eval/rag_fixtures.jsonl`, hand-written, reviewed like code.

```json
{
  "qid": "astro-pack-min-takeoff",
  "question": "What is the minimum battery pack temperature for takeoff?",
  "airframe_config_id": "freefly-astro-max-2026-01",
  "field_path": "battery.pack_min_takeoff_c",
  "relevant_chunk_ids": ["c8f1...", "c8f2..."],
  "hard_negatives": ["c3aa..."],
  "expected_quote_contains": "10",
  "expected_unit": "C",
  "answerable": true,
  "class": "procedure_vs_airframe_limit"
}
```

- `relevant_chunk_ids` — graded once against the PDF. Regenerated only when the
  corpus `sha256` changes.
- `hard_negatives` — the chunk that looks right and is wrong. For the Astro,
  the -20 °C airframe minimum. A retriever that ranks the negative above the
  positive is worse than one that returns nothing, because a plausible wrong
  limit is handed to a human as evidence.
- `answerable: false` on at least 20% of rows. The correct behavior is
  `citation_status=unconfirmed`, not a confident near-miss.
- `class` — the aggregate hides the failure. Overall recall of 0.93 can conceal
  0.4 on the one class that matters.

Minimum 40 questions across at least 6 classes before quoting a number.

## Retrieval metrics

Offline, no network, no model.

| Metric | Definition | Gate |
|---|---|---|
| `recall@4` | relevant set intersects returned, over answerable rows | >= 0.90 overall, >= 0.95 on `class=safety_limit` |
| `mrr` | 1 / rank of the first relevant chunk | >= 0.80 |
| `precision@4` | fraction of returned that are relevant | report only |
| `hard_negative_above_positive` | a negative outranks every positive | **0 — hard fail** |
| `wrong_config_leak` | returned chunk from another `airframe_config_id` | **0 — hard fail** |
| `field_path_purity` | returned chunks matching the requested `field_path` | >= 0.95 |
| `false_confirm_rate` | `answerable=false` rows returning `confirmed` | **0 — hard fail** |
| `abstain_rate` | `unconfirmed` on answerable rows | <= 0.15, trend tracked |
| `p95_latency_ms` | hybrid SQL only, warm cache | <= 50 on the seed corpus |

The three zero-tolerance rows are why this file exists. A non-zero
`wrong_config_leak` means a `WHERE` clause went missing from one leg of the
hybrid query — the exact bug that survives code review and that the fused SQL in
`docs/retrieval.md` is shaped to prevent. Test it; do not read for it.

`precision@4` is deliberately ungated. With `k=4` and often two relevant chunks,
precision caps near 0.5 and optimizing it costs recall. Rank position is what
matters; the model sees four spans and quotes the right one.

## Citation metrics

Applied to generated briefs — and enforced live in the response assembler, not
only in the eval.

| Metric | Check | Gate |
|---|---|---|
| `quote_verbatim` | every quoted span is an exact substring of the stored chunk after whitespace normalization | 1.0 — hard fail |
| `citation_resolves` | every `chunk_id` exists and belongs to this configuration | 1.0 — hard fail |
| `url_allowlisted` | every rendered URL came from `rag.documents.source_url`, never from model text | 1.0 — hard fail |
| `sealed_contamination` | a watt/mass/limit token in prose absent from the sealed assessment and from cited spans | **0 — hard fail** |
| `unsupported_numeric_rate` | numerics traceable to neither | <= 0.02, every instance logged |

`quote_verbatim` as a substring compare is the highest-leverage check in the
stack. A model that paraphrases "do not launch below 10 °C" into "avoid cold
starts" has destroyed the evidence chain, and a substring test catches it for
free. At generation time, a span failing the check is dropped and marked
`citation_status=unverified`.

Numeric extraction for contamination: regex every
`\d+(\.\d+)?\s*(W|Wh|kg|g|m|ft|°?C|mps|kt)` token out of the brief, normalize
units, set-difference against sealed values and span text. Crude, fast, and it
has not yet needed to be clever.

## Where an LLM judge is allowed

One place: narrative quality of the advisory brief, offline, never gating.

- Pinned judge model id and prompt hash recorded in the results JSON. A floating
  judge makes the time series meaningless.
- Four binary rubric items — names the binding constraint, states the mode, adds
  no invented mitigations, readable to a non-engineer — not a 1-10 scale.
- 10% of judged rows hand-checked each run. Below 0.8 judge-human agreement, the
  score is withdrawn from the report until recalibrated.
- Nothing affecting `decision` is ever judged by a model.

## Statistics

At n = 40, a recall of 0.90 carries a Wilson 95% interval of roughly 0.77-0.96 —
wider than most improvements worth celebrating.

- `eval/report.py` prints Wilson intervals on every rate metric. Not optional.
- Comparing two retriever configurations uses McNemar on paired per-question
  outcomes, not two independent proportions.
- CI compares against `eval/baselines/retrieval.json`. **Fail only when the point
  estimate drops below the gate or below the baseline's lower bound.** A tighter
  rule makes CI a coin flip, and a gate people learn to ignore is worse than no
  gate.
- `retriever_version` hashes the embedding model, chunker, and fusion parameters.
  Baselines are comparable only within a version; the report refuses to compare
  across one.

## Files and dependencies

```
backend/suas/eval/retrieval_metrics.py   # pure: sets in, floats out
backend/suas/eval/citation_checks.py     # verbatim, resolve, contamination
backend/suas/eval/stats.py               # wilson, mcnemar
eval/rag_fixtures.jsonl
eval/baselines/retrieval.json
eval/run_rag.py                          # no network by default
backend/tests/test_retrieval_metrics.py  # metrics over synthetic sets
backend/tests/test_rag_gates.py          # fixtures against seeded Postgres
```

New dependencies: `numpy`, for the statistics module only. No evaluation
framework, no evaluation SaaS, no `scipy` — Wilson and McNemar are a dozen lines
each, and a dependency not added is a supply-chain row not threat-modeled.

CI seeds the ephemeral Postgres from a committed corpus of roughly 200 chunks.
If the corpus is too large to commit, the gate does not run in CI, and a gate
that does not run is not a gate.
