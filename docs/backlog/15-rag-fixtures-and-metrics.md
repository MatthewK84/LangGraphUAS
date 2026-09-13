---
title: "eval: rag_fixtures.jsonl (40 rows) + retrieval metrics + Wilson/McNemar"
labels: [phase-2, eval]
blocked_by: [12]
---
## Goal
Retrieval quality becomes a number with a confidence interval, computed without calling a model.

## Fixtures — `eval/rag_fixtures.jsonl`
Per row: `qid`, `question`, `airframe_config_id`, `field_path`, `relevant_chunk_ids`, `hard_negatives`, `expected_quote_contains`, `answerable`, `class`.

At least 40 questions across 6+ classes, with 20% `answerable: false`. Hard negatives are mandatory on every safety-limit class — for the Astro, the −20 °C airframe minimum against the 10 °C pack procedure (#39).

## Metrics — `backend/suas/eval/`
`recall@4`, `mrr`, `precision@4` (reported, ungated), `hard_negative_above_positive`, `wrong_config_leak`, `field_path_purity`, `false_confirm_rate`, `abstain_rate`, `p95_latency_ms`.

Citation checks: `quote_verbatim` (exact substring of the stored chunk), `citation_resolves`, `url_allowlisted`, `sealed_contamination`, `unsupported_numeric_rate`. These run in the live response assembler too, not only in the eval.

## Statistics — `backend/suas/eval/stats.py`
Wilson intervals on every rate metric. McNemar on paired outcomes when comparing two retriever configurations. `retriever_version` hashes embedding model, chunker, and fusion parameters; the report refuses to compare across versions.

New dependency: `numpy`, for the statistics module only. No evaluation framework, no evaluation SaaS.

## Acceptance
- [ ] 40+ rows, 6+ classes, 20% unanswerable
- [ ] Metrics are pure functions with unit tests over synthetic sets
- [ ] Wilson intervals printed on every reported rate
- [ ] Baseline committed to `eval/baselines/retrieval.json`
