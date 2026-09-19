# Leaderboard

Generated 2026-09-19 from `eval/results/2026-09-19/`. Do not edit by hand --
run `python3 eval/build_leaderboard.py --write`.

## Mission decisions

`unsafe_go` is cleared for flight when the calculator refused, and is the
only column that describes a hazard. `missed_go` costs a sortie. They are
separate so a provider cannot buy one with the other.

| provider | track | fixtures | unsafe_go | missed_go | mode_violation | invented_number | max hover error (W) |
|---|---|---|---|---|---|---|---|
| `oracle` | calculator_tool | 30 | 0 | 0 | 0 | 0 | 0.0 |
| `constant_power` | no_tools | 30 | 8 | 0 | 30 | 13 | 531.98 |

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

No real language model has been measured here. `oracle` and
`constant_power` are controls: the first calls the deterministic engine
and must score zero, the second holds hover power constant as payload
mass rises. They demonstrate that the harness separates a correct answer
from the specific mistake the pack is built to catch. A row for a real
model appears only when someone runs the pack against one.

Retrieval figures are measured with a lexical projection, not an
embedding model, because CI cannot run one. They are a regression floor
for retrieval logic and not a claim about retrieval quality.
