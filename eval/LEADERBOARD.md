# Leaderboard

Generated 2026-11-15 from `eval/results/2026-11-15/`. Do not edit by hand --
run `python3 eval/build_leaderboard.py --write`.

## Mission decisions

`unsafe_go` is cleared for flight when the calculator refused, and is the
only column that describes a hazard. `missed_go` costs a sortie. They are
separate so a provider cannot buy one with the other.

| provider | track | fixtures | unsafe_go | missed_go | mode_violation | invented_number | max hover error (W) |
|---|---|---|---|---|---|---|---|
| `mistral-7b-instruct-v0.3` | calculator_tool | 30 | 0 | 0 | 0 | 0 | 0.0 |
| `oracle` | calculator_tool | 30 | 0 | 0 | 0 | 0 | 0.0 |
| `qwen2.5-7b-instruct` | calculator_tool | 30 | 0 | 0 | 0 | 0 | 0.0 |
| `constant_power` | no_tools | 30 | 7 | 0 | 30 | 0 | 211.97 |
| `mistral-7b-instruct-v0.3` | no_tools | 30 | 0 | 0 | 0 | 0 | 0.0 |
| `qwen2.5-7b-instruct` | no_tools | 30 | 0 | 0 | 0 | 0 | 0.0 |

## Retrieval

From `eval/baselines/retrieval.json`, retriever `9581deb817bb2697`,
embedder `hashing-v1-384`. Rates carry 95% Wilson intervals.

| metric | rate | 95% CI | n |
|---|---|---|---|
| `wrong_config_leak` | 0.0 | [0.0, 0.0876] | 40 |
| `false_confirm_rate` | 0.0 | [0.0, 0.3244] | 8 |
| `hard_negative_above_positive` | 0.0312 | [0.0055, 0.1574] | 32 |
| `recall_at_4` | 0.9375 | [0.7985, 0.9827] | 32 |
| `mrr` | 0.9219 | - | - |

## What these numbers are not

Rows other than `oracle` and `constant_power` are measurements of a real language model, taken from the results files in this directory. The two named controls remain: the first calls the deterministic engine and must score zero, the second holds hover power constant as payload mass rises.

Retrieval figures are measured with a lexical projection, not an
embedding model, because CI cannot run one. They are a regression floor
for retrieval logic and not a claim about retrieval quality.
