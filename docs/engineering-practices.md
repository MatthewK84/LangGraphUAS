# Engineering practices

This is flight-adjacent software that happens to contain a chat node. The bar is
set accordingly.

## Branching and release

- Trunk-based. `main` is always deployable. Short-lived `feat/` branches.
- Phase tags: `v0.2.0-honest-core`, `v0.3.0-closed-loop`, `v0.4.0-eval`.
- Conventional commits.
- Every PR appends its line to the current week's section of `CHANGELOG.md`,
  starting the section (headed by that week's Monday) if the week has none.
  Five lines a week at most, so fold related PRs into one line, and name the
  PRs or issues each line records. `backend/tests/test_changelog.py` enforces
  the format.
- One PR is one mergeable slice with tests.

## CI gates that block merge

Already in place: `ruff`, `mypy --strict`, `pytest` with coverage, frontend
typecheck and Vitest, Prettier, the calculator-version gate below, and the
ub-mode gate (CRAP and duplication) described under
[ub-mode](#ub-mode-crapper-and-dryer).

Added by this plan:

| Gate | Rule |
|---|---|
| Oracle coverage | `backend/suas/calculations/` at 95%, not the repo default |
| Reference data | Fails on any performance field lacking `source`, or `source=datasheet` lacking `source_url` |
| ~~Calculator version~~ | **Shipped.** `backend/scripts/check_calculator_version.py` fails a pull request that changes `calculations/` without bumping `CALCULATOR_VERSION`. Documentation-only edits need a patch bump too: the gate cannot tell prose from physics, and a version bumped for nothing beats one silently stale. |
| Graph tests | Run against real Postgres, not SQLite |
| Retrieval gates | Wrong-config leak, hard-negative inversion, false-confirm all at 0 (`docs/rag-eval.md`) |
| Injection matrix | Every row in `docs/injection-defense.md` green |
| Secret scan | `gitleaks` |
| SBOM | Generated on tag |

Dependency auditing is deliberately not a merge gate: `pip-audit --strict`
failed on transitive advisories this project cannot fix, and a gate that is red
for reasons nobody can act on teaches people to ignore red. It runs on demand
instead. The tradeoff is real and unmitigated — nothing currently notices a
vulnerable dependency on its own. If that bites, the fix is a scheduled
non-blocking job that opens an issue, not a restored merge gate.

### ub-mode (crapper and dryer)

The discipline is the vendored skill in
[`docs/skills/ub-mode/SKILL.md`](skills/ub-mode/SKILL.md) (source and credit in
the README beside it). Each change goes First Make it Work, then Make it Right,
then Practice. The parts that matter most here:

- **TDD.** Write the failing test first and see it fail for the expected
  reason, then make the smallest change that passes. If an honest test is
  impractical, say so in the PR instead of writing a bad one.
- **Small, single-purpose edits.** One decision lives in one place. Take
  complexity out before adding any.
- **Boundaries and types.** Parse outside data once where it enters, keep
  business logic in pure functions, and do not silence the compiler: no new
  `# type: ignore`, `noqa`, or widened mypy overrides.
- **Root causes.** Reproduce, then fix the cause. A guard that hides a crash is
  not a fix.
- **Behavior tests.** A test calls the code the way its user does. A test that
  would still pass if every function returned nothing is deleted.
- **CRAP under 10** for every function
  ([crapper](https://github.com/unclebob/crapper)), and **no duplication at
  0.8 or above** ([dryer](https://github.com/unclebob/dryer)). Enforced in CI;
  see below.
- **Mutation testing** ([mutator](https://github.com/unclebob/mutator)) on the
  files a PR touches: cover the uncovered, kill survivors, delete dead code.
  Not yet in CI; see [Aspirational](#aspirational).
- **Commits.** Small and ordered. Each message says why, what changed, and how
  it was proven. The PR body carries the log of what was done and why.

What blocks a merge: the `ub-mode` job ("ub-mode (crapper, dryer)") in
`.github/workflows/ci.yml` runs crapper and dryer, at pinned commits, on
`backend/suas`. Then `backend/scripts/ub_gate.py` fails the job when:

- any function has a CRAP score of 10 or more, or
- any duplicate pair scores 0.8 or more and is not listed in
  `backend/ub-mode-allowlist.txt`.

Each allowlist entry names its functions as `path::qualname` and must give a
reason. An entry that no longer matches a reported pair also fails the job, so
delete it once the duplication is gone. Add an entry only when removing the
duplication would make the code worse, and say why in the entry. The job
summary shows both tools' full output.

To run it locally, from `backend/`: produce `coverage/lcov.info` with
`pytest --cov=suas --cov-report=lcov:coverage/lcov.info`. Then run
`crapper --use-existing-coverage suas > crap.txt` and
`dryer --threshold 0.8 suas > dry.txt`, and finally
`python scripts/ub_gate.py --crap crap.txt --dry dry.txt --allowlist ub-mode-allowlist.txt`.

The gate was made blocking at 0 of 278 functions at CRAP 10 or above, with 8
duplicate pairs at 0.8 or above, all allowlisted. The baseline at `01949cd`
was 7 functions and 10 pairs.

## Environments

| Env | LLM | Weather | Blue-list snapshot | Checkpointer |
|---|---|---|---|---|
| test | stub | fixture | frozen JSON | memory or ephemeral PG |
| staging | cheap model | live + recorded | weekly | Postgres |
| prod | configured model | live | pinned + freshness alarm | Postgres, optional encryption |

Promotion is by image digest. Never by `latest`.

## Observability

- **Logs** — JSON, carrying `request_id`, `mission_id`, `thread_id`, `node`,
  `calculator_version`, `operator_key_id`. Coordinates redacted at `info`.
- **Metrics** — plan latency, interrupt age, `llm_field_violations_total`,
  weather source counts, checkpoint put/get latency, retrieval hit/miss, and the
  five injection counters from `docs/injection-defense.md`.
- **Traces** — one span per graph node. Full prompts are never logged at `info`
  in production.

## Security baseline

- Per-operator API keys; threads not enumerable across keys.
- Separate database roles: the ingest role writes `rag.*` only; the application
  role reads `rag.*` and cannot write it; neither can drop checkpoint tables.
- Non-root production image, hash-pinned dependencies, Dependabot on.
- No PDF upload path in the API. Ingest is offline, allowlisted, and hashed.

## Review bar

A PR touching `calculations/`, the Blue-list gate, or `graph/seal.py` requires a
second reviewer and a test that would have failed before the change. "I read it
carefully" is not a control.

## Documentation obligations

- A new graph node, ingest source, or external dependency adds a STRIDE row to
  `docs/threat-model.md` before merge.
- A decision later code will assume gets an ADR. See `docs/adr/README.md`.

## Aspirational

Practices this repository intends to follow but does not yet enforce in CI.
Nothing here blocks a merge. Issue #73 will finish splitting this document into
Enforced and Aspirational; this section only covers ub-mode.

### ub-mode, beyond CRAP and duplication

The rest of the [ub-mode](#ub-mode-crapper-and-dryer) discipline (TDD,
small edits, behavior tests, commit messages) is held at review, not by a tool.
Mutator and the frontend are not measured in CI.
