# Backlog — the seventeen opening issues

Each file here is one GitHub issue, ready to file: YAML-ish front matter
(`title`, `labels`, `blocked_by`) followed by the body. They are kept in the
repository rather than only in the issue tracker so the plan and the work items
stay in one reviewable diff.

## Filing them

```bash
gh auth status                                    # needs issue write on the repo
python3 scripts/open_backlog_issues.py --dry-run  # prints titles and blockers
python3 scripts/open_backlog_issues.py            # creates labels, then issues
```

The script creates any missing label, files the issues in filename order, then
makes a second pass appending real `Blocked by #N` references once numbers are
known. It appends the Claude Code attribution footer to each body at creation
time, which is why the files here do not carry one.

**The seventeen below are filed as #36-#52.** The script remains useful for
re-filing them in a fork, or for filing the split-out items named at the bottom
of this file.

## The seventeen

| # | Issue | Title | Phase | Blocked by |
|---|---|---|---|---|
| 01 | #36 | Seal `DeterministicAssessment` from LLM output | 1 | — |
| 02 | #37 | `assessment_mode` advisory / operational | 1 | #36 |
| 03 | #38 | Provenance fields + `CITATIONS.md` | 1 | #37 |
| 04 | #39 | Resolve documented datasheet conflicts | 1 | #38 |
| 05 | #40 | HITL interrupt + ack endpoint | 1 | #36, #37 |
| 06 | #41 | Flight-log ingest + power estimator | 1 | #38 |
| 07 | #42 | `POST /api/replan` + alert schema | 2 | #40 |
| 08 | #43 | Weather timeout and fallback contract | 2 | #37 |
| 09 | #44 | Load test + kill -9 resume | 2 | #40 |
| 10 | #45 | Frozen eval fixture pack + runner + leaderboard | 3 | #39, #42 |
| 11 | #46 | Quarantine on ingest + unicode normalization | 2 | — |
| 12 | #47 | Nonce-fenced evidence + chunk_id citation | 2 | #46 |
| 13 | #48 | `BriefOutput` allowlist + contradiction linter | 1 | #36 |
| 14 | #49 | Injection test matrix + `eval_trap` corpus kind | 2 | #46, #47, #48 |
| 15 | #50 | RAG fixtures + retrieval metrics + statistics | 2 | #47 |
| 16 | #51 | CI retrieval gates | 2 | #50 |
| 17 | #52 | ADR: node order and empty tool binding | 1 | #36 |

Start with #36. Everything else waits on that merge.

The dependency column is the only place the blocker graph is recorded — deliberately, rather than as fifteen one-line comments scattered across the
tracker. Keep it current when issues are split or closed.

## Known gaps in this set

Four work items in `docs/PLAN-90.md` have no issue of their own, because the set
was fixed at seventeen. They are currently carried inside other issues and
should be split out when the phase they belong to opens:

| Work | Currently carried by | Split out at |
|---|---|---|
| `blue_list_snapshots` table and `refresh_blue_list.py` | #02 (the gate consumes it) | Phase 1, Day 4 |
| `rag` schema, pgvector extension, hybrid SQL function | #12 (fencing assumes it) | Phase 1, Day 19 |
| Checkpoint prune job via `delete_thread` | #09 (retention is tested there) | Phase 2, Week 7 |
| Two-worker `thread_id` lock | #09 | Phase 2, Week 6 |

Carrying them is fine for now; losing them is not. Splitting is cheap once the
first seventeen are filed and the numbering is stable.
