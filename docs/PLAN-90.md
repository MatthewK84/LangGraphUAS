# LangGraphUAS — 90-day plan

Start date: 2026-09-13. Default branch `main`. Phase branches cut from `main`:
`phase-1-honest-core`, `phase-2-replan`, `phase-3-eval`. A phase merges when its
acceptance table is all checkboxes, not when the calendar runs out.

This file is the calendar and the acceptance gates. The specifications live
beside it:

| Document | Covers |
|---|---|
| `docs/engineering-practices.md` | Branching, CI gates, environments, observability, review bar |
| `docs/retrieval.md` | pgvector hybrid search, schema, RRF fusion, ingest allowlist |
| `docs/rag-eval.md` | Retrieval and citation metrics, fixtures, statistics, CI gates |
| `docs/injection-defense.md` | Injection surfaces, ingest screening, prompt/output controls, test matrix |
| `docs/threat-model.md` | STRIDE across every trust boundary |
| `docs/ops.md` | Retention, single-worker limits, incident handling |
| `docs/adr/` | The four decisions that everything else assumes |
| `docs/backlog/` | The seventeen opening issues, ready to file |

## Status as of 2026-09-19

Calendar day 7 of 90. The calendar is not the progress bar: all seventeen
opening issues are merged, including the Phase 3 eval work, so the backlog is
ahead of the dates. What follows is measured from `main`, not from the plan.

### On main

- **Sealed decision layer.** `decision` and every watt come from
  `backend/suas/calculations/`. The model writes prose and nothing else.
- **Human acknowledgement before the brief.** `human_ack` precedes `report`,
  asserted by a test that fails if the edge is rewired (ADR-004).
- **Replan against live telemetry**, as a child thread of the briefed one.
- **Explicit weather states.** `live | cached_fresh | cached_stale | fallback |
  error`, each one distinguishable on the wire.
- **Injection matrix**, thirteen rows, run against a trap corpus production
  refuses by `kind`.
- **Retrieval gates** in CI: configuration leak and false-confirm at zero.
- **Offline eval harness**: 40 retrieval fixtures, 30 frozen mission fixtures,
  both with committed baselines.

### Blocking operational mode

Two blockers fire on every plan today, even given live weather and a complete
assessment. Both are emitted by `operational_blockers()` in
`backend/suas/calculations/gate.py`; the names below are `Blocker` enum values,
not prose.

| Blocker | Why it fires | What clears it |
|---|---|---|
| `POWER_NOT_OPERATIONAL_GRADE` | Every energy-budget figure in the bundled data is `derived` or `estimate`. None is read from a manufacturer document or a measured flight log. | Issues #75 and #76: one field promoted to `datasheet`, and one flight log that can move a power field. |
| `BLUE_LIST_SNAPSHOT_UNAVAILABLE` | No Blue List snapshot is stored, so configuration clearance cannot be asserted at all. This one is unconditional -- the gate appends it on every call. | Issue #78: a stored snapshot plus a freshness blocker, which turns a standing blocker into a real check. |

`PROVENANCE_INCOMPLETE` does **not** fire: every field that must carry a
provenance record has one. The records exist; what they say is not yet good
enough.

**Operational mode is therefore unreachable today, and that is the honest
state.** The gate fails closed by design: a condition this codebase cannot
verify is a blocker rather than a pass. Issue #77 closes this either by making
one lab configuration pass, or by writing the refusal down.

### Next three PRs

1. **#72** — this status block.
2. **#73** — split `engineering-practices.md` into Enforced in CI and
   Aspirational, and reconcile the README's Known Limitations against it.
3. **#74** — a live issue for the 76 reference fields, replacing the dead link,
   with `CITATIONS.md` regenerated from the seed JSON so the two cannot drift.

Updated in any PR that changes what is on `main`.

## Standing rules (all 90 days)

1. The LLM may write `brief_markdown`, `suggested_contingencies`, and
   `cited_chunk_ids`. Nothing else. `decision` and every watt, mass, derate and
   limit is written by `backend/suas/calculations/` or by a validator wrapping it.
2. Every numeric field in aircraft/payload JSON carries `value`, `unit`,
   `source`, `source_url`, `retrieved_at`, `confidence`.
3. A plan is `advisory` or `operational`. Operational requires live weather, a
   cited airframe row, non-estimate power, a current Blue-list snapshot row for
   that exact configuration, and a human acknowledgement.
4. Checkpoints are recovery infrastructure, not the database of record. The
   `missions` table owns the mission; LangGraph owns where the graph paused.
5. Retrieval retrieves. The calculator decides. See ADR-003.
6. No non-public tactics, frequencies, or procedures in this repository.
7. One PR is one mergeable slice with tests. No end-of-week dumps.

## Commit 0 — before anything else

Seal `DeterministicAssessment` from model output and add `assessment_mode`.
Backlog items 01 and 02. Everything after this is product; everything before it
is a better UI over an unverified number.

## Phase 1 — Days 1-21: make the core honest

**Week 1 (Days 1-7) — schema, citations, known-bad numbers**

- Day 1: Commit 0 (backlog 01).
- Days 2-3: `missions` table and `thread_id` policy (ADR-001). Checkpointer
  `setup()` moves out of the FastAPI lifespan into the migration job.
  `docs/threat-model.md` first pass. ADR-004 with its two regression tests.
- Days 4-5: provenance shape and `CITATIONS.md` (backlog 03). Blue-list config
  table and a first checked-in snapshot (ADR-002). Operational gate (backlog 02).
- Days 6-7: patch the four documented datasheet conflicts (backlog 04), unit
  test per constant, advisory/operational banner in the dashboard.

Week 1 is done when every number in the default Blue UAS pack has provenance,
the four conflicts are resolved or explicitly marked `estimate` with a reason,
and Commit 0 is on `main`.

**Week 2 (Days 8-14) — human in the loop**

- Days 8-9: insert `human_ack` between `calculations` and `report`; new
  `POST /api/plan/{thread_id}/ack` (backlog 05). `durability="sync"` at both.
- Day 10: persist `ack_actor`, `ack_at`, signed assessment hash; invalidate on
  `inputs_hash` or `calculator_version` change.
- Days 11-12: two-step frontend — compute, review card, confirm.
- Days 13-14: kill-9 resume test, no-ack-no-report test, edit-invalidates-ack
  test. Output pipeline steps 1-4 from `docs/injection-defense.md` (backlog 13):
  the first brief that exists is the first brief that can be wrong.

Week 2 is done when no brief exists without an ack record on that thread.

**Week 3 (Days 15-21) — one airframe, real power**

- Day 15: flight-log schema and `POST /api/logs` (backlog 06).
- Days 16-17: hover/cruise estimator as pure functions with sample counts and IQR.
- Day 18: wire `source=flight_log` into the operational gate.
- Days 19-20: redacted fixture CSV, README section on recording a log.
  First ingested PDF: `screen_chunk`, quarantine table, link stripping, nonce
  fencing (backlog 11, 12). Ten seeded RAG fixtures including the Astro
  pack-temp / airframe-temp pair. No gates yet — collect numbers first.
- Day 21: tag `v0.2.0-honest-core`. Open the Phase 2 branch only after the tag.

### Phase 1 acceptance

| Check | Pass condition |
|---|---|
| Seal | Injected malicious JSON cannot change `decision` or any watt |
| Citations | CI fails on a bare number |
| Datasheet conflicts | Four rows resolved and matching `CITATIONS.md` |
| HITL | No report without an ack record |
| Flight log | One airframe at `source=flight_log`, n >= 30 hover samples or a documented reason |
| Modes | Operational impossible on fallback weather |
| Node order | `human_ack` precedes `report`, asserted by test |

## Phase 2 — Days 22-50: close the loop

**Week 4 (Days 22-28)** — telemetry schema, `POST /api/replan` on child threads
(`{parent}:{seq}`, parent brief immutable), the compare step, and the alert
schema with conservative thresholds in config (backlog 07).

**Week 5 (Days 29-35)** — explicit weather states `live | cached_fresh |
cached_stale | fallback | error`, a 2-3s timeout that cannot hang either
endpoint, and a fake-client test matrix of hang/500/empty/valid (backlog 08).
Live panel on the thread. Fixtures to 40 rows, baseline committed, three
zero-tolerance retrieval gates on in CI (backlog 15, 16).

**Week 6 (Days 36-42)** — load test at 100 concurrent advisory plans with
`?brief=false` so the run costs nothing; kill-9 resume at the interrupt; the
two-worker lock; Prometheus labels for mode, degraded, and violations. Citation
checks move into the live response assembler, not only the eval (backlog 09, 14).

**Week 7 (Days 43-50)** — per-operator API keys with non-enumerable threads,
checkpoint purge job via `delete_thread`, Blue-list refresh script and the
`BLUE_LIST_SNAPSHOT_STALE` blocker. Tag `v0.3.0-closed-loop`.

### Phase 2 acceptance

| Check | Pass condition |
|---|---|
| Replan | Briefed vs live residual in one response |
| Alerts | Energy, wind, and stale-SOC codes, each tested |
| Weather | The timeout path can never look like `live` |
| Load | 100 concurrent advisory plans, p95 < 2s, zero 5xx, all threads checkpointed |
| Resume | kill -9 at the interrupt, ack still works, report runs once |
| Seal | Still holds on the replan path |
| Retrieval | Wrong-config leak, hard-negative inversion, and false-confirm all at zero |

## Phase 3 — Days 51-90: publish the eval

Not a bigger product. A frozen test that models fail in a way an engineer
recognizes.

**Week 8 (Days 51-57)** — `eval/fixtures/`, no live weather, minimum 25 mission
fixtures. Required traps: payload mass scaling where hover power must rise as
`(m/m_ref)^1.5`; high density altitude crossing reserve; `weather.source =
fallback` with an operational claim; a delisted configuration claimed as
cleared; the pack-procedure vs airframe-limit confusion; a trap copy of an old
datasheet conflict (eval-only, never in the production seed). The deterministic
engine is the oracle; expected values are regenerated by script on a
`calculator_version` bump, never hand-edited.

**Week 9 (Days 58-64)** — `eval/run.py` across providers with one prompt
wrapper. Two tracks: no tools, and a calculator tool. Scores per fixture:
`unsafe_go`, `missed_go`, `energy_error`, `mode_violation`, `invented_number`.

**Week 10 (Days 65-71)** — generated `eval/LEADERBOARD.md`, plus two columns
this repo is unusually positioned to report: RAG contamination rate and
injection resistance (the fraction of trap fixtures where a model's proposed
decision moved because a document told it to). 800-1500 word writeup. The title
claim is not pre-committed — if models pass the mass-scaling trap, say so.

**Week 11 (Days 72-78)** — pin only this repo; move the feeder repos to
`attic/README.md`; three-line profile README; Docker Compose public demo,
advisory only, no keys in the compose file.

**Week 12 (Days 79-90)** — tag `v0.4.0-eval`, `good first fixture` issues,
fifteen cold emails carrying the leaderboard and one failure trace, then
applications. No new features for two weeks unless a reviewer finds an oracle bug.

### Phase 3 acceptance

| Check | Pass condition |
|---|---|
| Frozen pack | 25+ mission fixtures, no network in `eval/run.py` by default |
| Tracks | Both no-tool and calculator-tool reported |
| Leaderboard | Regenerable from the results JSON, never hand-edited |
| Writeup | Every number traceable to a committed results file |
| Profile | LangGraphUAS is the only pinned engineering work |

## Weekly cadence

- **Monday** — pick the week's PRs from this file. No extra scope.
- **Wednesday** — if a PR is not reviewable, cut scope. Never cut the seal,
  HITL, or oracle tests.
- **Friday** — full backend suite plus one Compose up/down. Five lines in
  `CHANGELOG.md`.
- **Any day** — an idea not in this plan becomes an issue titled `attic:` and
  the laptop closes.
