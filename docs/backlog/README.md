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

**These were not filed from the Claude Code session that wrote them.** That
session's GitHub app had repository read and pull-request access but not
`issues: write`, so every create returned
`403 Resource not accessible by integration`. Run the script from a shell with
your own `gh` credentials, or grant the app issue write access and ask for them
to be filed again.

## The seventeen

| # | Title | Phase |
|---|---|---|
| 01 | Seal `DeterministicAssessment` from LLM output | 1 |
| 02 | `assessment_mode` advisory / operational | 1 |
| 03 | Provenance fields + `CITATIONS.md` | 1 |
| 04 | Resolve documented datasheet conflicts | 1 |
| 05 | HITL interrupt + ack endpoint | 1 |
| 06 | Flight-log ingest + power estimator | 1 |
| 07 | `POST /api/replan` + alert schema | 2 |
| 08 | Weather timeout and fallback contract | 2 |
| 09 | Load test + kill -9 resume | 2 |
| 10 | Frozen eval fixture pack + runner + leaderboard | 3 |
| 11 | Quarantine on ingest + unicode normalization | 2 |
| 12 | Nonce-fenced evidence + chunk_id citation | 2 |
| 13 | `BriefOutput` allowlist + contradiction linter | 1 |
| 14 | Injection test matrix + `eval_trap` corpus kind | 2 |
| 15 | RAG fixtures + retrieval metrics + statistics | 2 |
| 16 | CI retrieval gates | 2 |
| 17 | ADR: node order and empty tool binding | 1 |

Start with 01. Everything else waits on that merge.

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
