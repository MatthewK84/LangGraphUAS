# Engineering practices

This is flight-adjacent software that happens to contain a chat node. The bar is
set accordingly.

The document has three parts, and only the first is a promise:

- **[Enforced in CI](#enforced-in-ci)**: a job in `.github/workflows/ci.yml`
  fails the run when the rule breaks. Every row names that job and its steps.
- **[Reported, not enforced](#reported-not-enforced)**: a workflow runs the
  check and shows its findings, but stays green.
- **[Aspirational](#aspirational)**: practices this repository follows at
  review, or intends to, with nothing in CI holding them.

`backend/tests/test_engineering_practices.py` reads `ci.yml` and fails if a row
of the Enforced table names a job or step that does not exist, is report-only,
or if a blocking job is missing from the table. A gate moves up only when a
workflow can prove it.

## Enforced in CI

Changes merge only on a fully green run of `.github/workflows/ci.yml`. That is
project practice: the branch ruleset does not list required status checks (see
[Aspirational](#aspirational)). Every job below runs on each push to `main` and
each pull request; `calculator-version` runs on pull requests only.

| Gate | Job | Steps | Rule |
|---|---|---|---|
| Python SAST | `backend` ("Backend (py3.11, py3.12, py3.13)") | "Ruff lint" | ruff's flake8-bandit `S` rules over `suas`, `tests`, `alembic`, `scripts`, `eval`; only asserts and fixed subprocess calls are ignored, and only in tests and scripts |
| Formatting | `backend` | "Ruff format check" | `ruff format --check` over `suas`, `tests`, `scripts`, `eval` |
| Types | `backend` | "Mypy strict" | `mypy --strict` over `suas` finds no error |
| Tests and coverage | `backend` | "Pytest with coverage" | every test passes on Python 3.11, 3.12 and 3.13, and line coverage of `suas` is 80% or more |
| Trojan Source | `backend` | "Pytest with coverage" | `tests/test_source_hygiene.py` fails on any zero-width, bidi or BOM character in backend, eval, or frontend source; patterns spell them as `\u` escapes |
| Safety properties | `backend` | "Pytest with coverage" | `tests/test_safety_properties.py`: Hypothesis (100 examples per property, fixed seed in CI) shows worse wind, gust, payload or battery never turns NO_GO into GO, any failed flag is NO_GO, limits are inclusive, and the gate never grants more than was requested |
| Reference data | `backend` | "Pytest with coverage" | `tests/test_reference_data.py`: every performance field carries a `source`, `source=datasheet` carries a `source_url`, units match the field name, and no bare number is accepted |
| Retrieval gates | `backend` | "Pytest with coverage" | `tests/test_rag_gates.py`: configuration leak and false confirm at exactly 0 (`docs/rag-eval.md`); hard-negative inversion and safety-limit recall no worse than the committed baseline. Their targets (0 and 0.95) are not yet met by the CI embedder, so those two are regression gates, not target gates |
| Injection matrix | `backend` | "Pytest with coverage" | `tests/test_injection.py`: one test per row of `docs/injection-defense.md`, and a test that fails if a row has no test |
| Changelog format | `backend` | "Pytest with coverage" | `tests/test_changelog.py`: weekly sections headed by their Monday, newest first, five lines at most, each naming its PRs or issues |
| Docs match the workflows | `backend` | "Pytest with coverage" | `tests/test_engineering_practices.py` (this document), `tests/test_readme.py` (the README's gates, badges and diagram) and `tests/test_supply_chain_workflows.py` (SBOM and image scan claims) |
| Migrations, SQLite | `backend` | "Verify migrations apply and match models" | `alembic upgrade head`, `alembic check` and `alembic downgrade base` succeed |
| Migrations, Postgres | `postgres-integration` ("Postgres integration (py3.12)") | "Apply migrations against Postgres" | `alembic upgrade head` and `alembic check` on Postgres 16 |
| Honest readiness | `postgres-integration` | "Smoke test app against Postgres", "Smoke test /ready refuses an unmigrated database" | `/ready` is 200 on a migrated Postgres with database, migrations and checkpointer all `ok`, and 503 with migrations `pending` on a database alembic never touched; `EXPECTED_REVISION` is pinned to the alembic head by `tests/test_api.py` |
| Multi-worker startup | `postgres-integration` | "Concurrent startup on a fresh database" | `tests/test_startup_concurrency.py`: four workers at once on an empty Postgres database, five rounds each, for `create_schema`, the reference-data seed, the checkpointer's `setup()`, and the three in lifespan order; all succeed (the image starts two uvicorn workers, and each runs the whole lifespan). All three are serialised by advisory locks in `suas/db/startup_lock.py`. The startup retention purge runs in every worker unlocked on purpose: its deletes are idempotent, so a second pass only repeats work. `alembic upgrade head` runs once per container, before uvicorn forks; several replicas starting at once are not covered (backlog 17) |
| Shared rate limit | `postgres-integration` | "Shared rate limit on Postgres" | `tests/test_shared_rate_limit.py`: two limiters over two connection pools race fifteen requests at a limit of five and admit exactly five; without the `FOR UPDATE` row lock the race overshoots. The same test runs on SQLite in the backend job (#84) |
| Calculator version | `calculator-version` ("Calculator version bump") | "Require a version bump when the oracle changes" | `backend/scripts/check_calculator_version.py` fails a pull request that changes `calculations/` without bumping `CALCULATOR_VERSION`. Documentation-only edits need a patch bump too: the gate cannot tell prose from physics, and a version bumped for nothing beats one silently stale |
| CRAP and duplication | `ub-mode` ("ub-mode (crapper, dryer)") | "Gate on CRAP < 10 and unlisted duplication < 0.8" | see [ub-mode](#ub-mode-crapper-and-dryer) below |
| Frontend types | `frontend` ("Frontend (tsc, eslint, build)") | "Typecheck" | `tsc` finds no error |
| Frontend complexity | `frontend` | "Lint" | ESLint `complexity: ["error", 10]` on `src/`, the half of CRAP the frontend can hold until it measures coverage; `src/lib/lint-rules.test.ts` proves 11 fails and 10 passes |
| Frontend format | `frontend` | "Format check" | Prettier finds nothing to change |
| Frontend tests | `frontend` | "Test" | Vitest passes, including the server-side proxy |
| Frontend build | `frontend` | "Build" | `next build` succeeds |
| Images build | `docker` ("Docker images build") | "Build backend image", "Build frontend image" | both production images build. The trivy scan in the same job is report-only; see below |
| Workflow lint | `workflow-lint` ("Workflow lint (actionlint, zizmor)") | "actionlint", "zizmor" | actionlint finds no error, and zizmor finds no issue in `.github/`: every action pinned to a commit SHA, no `${{ }}` expansion inside `run:`, no persisted checkout credentials, a read-only default token, and a Dependabot cooldown |
| Secret scan | `secrets-scan` ("Secret scan (gitleaks)") | "gitleaks over the full history" | gitleaks, a checksum-verified pinned release, finds no secret in any commit of the full history |

### ub-mode (crapper and dryer)

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

## Reported, not enforced

These run, and their findings are visible, but none of them can turn a run red
for a finding.

### Mutation report (report-only)

The `mutation` job ("Mutation (mutator, report-only)") in
`.github/workflows/ci.yml` runs mutator, pinned to a commit, and lists every
surviving mutant in the job summary. Survivors never fail it; a tool that
cannot run (mutator exits other than 0 or 3) does, so an empty run cannot pass
as a clean one. On a pull request
it mutates the `backend/suas` modules the PR changed, as chosen by
`backend/scripts/mutation_targets.py`. On a push to `main`, and on a pull
request that edits that selector, it mutates the safety core: `calculations/`,
`graph/seal.py` and `rag/screening.py`. A survivor in a file you touched is
yours to kill or to explain as equivalent in the PR. It is not a gate because
equivalent mutants cannot be told apart from real gaps without a reader.

To run it locally, from `backend/`, after producing `coverage/lcov.info` as above:
`mutator --use-existing-coverage --test-command "python -m pytest -q -x -p no:cacheprovider" <files>`.

### Dependency audit (report-only)

Dependency auditing is deliberately not a merge gate: `pip-audit --strict`
failed on transitive advisories this project cannot fix, and a gate that is red
for reasons nobody can act on teaches people to ignore red. Instead
`.github/workflows/audit.yml` ("Dependency audit") runs every Monday and on
demand: `pip-audit` over the backend's runtime dependency set and `npm audit`
over the frontend. It is report-only for now: findings go to the job summary
and as warnings, and the run stays green. Issue #88 turns the fixable part into
a gate once today's findings are cleared.

### Image scan (report-only)

Image scanning is report-only for the same reason as the dependency audit. The `docker` job ("Docker
images build") in `.github/workflows/ci.yml`, step "Image scan (trivy,
report-only)", scans both built images with trivy (a checksum-verified pinned
release, `scripts/install-trivy.sh`) for HIGH and CRITICAL vulnerabilities that
have a fix, and writes them to the job summary with `--exit-code 0`. On day one
the frontend image has CRITICAL findings in `next` that need a major bump
(#100), so a blocking scan would be red for reasons a PR cannot act on. The scan
step still fails if trivy itself cannot run.

### SBOM

`sbom.yml` ("SBOM"), job `sbom`, writes a CycloneDX SBOM of each image on every
`v*` tag, and the tag-only `attach` job adds them to that release.
`workflow_dispatch`, or a pull request touching the workflow, is the dry run
(artifact only). It records what shipped; it does not judge it.

## Aspirational

Practices this repository intends to follow, or follows at review, with nothing
in CI holding them. Nothing here blocks a merge. Each is written so a reviewer
knows to check it by hand, and moves to [Enforced in CI](#enforced-in-ci) only
with the job that proves it.

### Gates not yet built

| Gate | Rule | Today |
|---|---|---|
| Required status checks | The branch ruleset lists every blocking job as required | The `Updates` ruleset has none; "merge only on green" is held by people |
| Oracle coverage | `backend/suas/calculations/` at 95%, not the repo default | Only the repo-wide 80% is checked |
| Graph tests on Postgres | Graph tests run against real Postgres | They run on SQLite; only migrations, the smoke tests and concurrent startup use Postgres |
| Frontend CRAP | The frontend's CRAP is measured like the backend's | Complexity is held at 10; there is no frontend coverage report, so CRAP is not measured |
| Retrieval targets | Hard-negative inversion at 0, safety-limit recall at 0.95 | Held at "no worse than baseline" until a real embedding model serves CI |

### Review bar

A PR touching `calculations/`, the Blue-list gate, or `graph/seal.py` requires a
second reviewer and a test that would have failed before the change. "I read it
carefully" is not a control. Today nothing enforces the second reviewer: there
is no CODEOWNERS file and the ruleset requires no review.

### ub-mode discipline, beyond CRAP and duplication

The discipline is the vendored skill in
[`docs/skills/ub-mode/SKILL.md`](skills/ub-mode/SKILL.md) (source and credit in
the README beside it). Only its CRAP and duplication limits are a gate; the rest
is held at review. Each change goes First Make it Work, then Make it Right,
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
- **Mutation testing** on the files a PR touches: cover the uncovered, kill
  survivors, delete dead code. See [Mutation report](#mutation-report-report-only).
- **Commits.** Small and ordered. Each message says why, what changed, and how
  it was proven. The PR body carries the log of what was done and why.

### Branching and release

- Trunk-based. `main` is always deployable. Short-lived `feat/` branches.
- Phase tags: `v0.2.0-honest-core`, `v0.3.0-closed-loop`, `v0.4.0-eval`.
- Conventional commits.
- Every PR appends its line to the current week's section of `CHANGELOG.md`,
  starting the section (headed by that week's Monday) if the week has none.
  Five lines a week at most, so fold related PRs into one line, and name the
  PRs or issues each line records. The format is enforced (see Changelog
  format above); that a PR adds its line is held at review.
- One PR is one mergeable slice with tests.

### Design targets

The environment, observability and security targets below describe what the
service is built toward. Parts are implemented, but no CI job checks any of
them, so treat each as a claim to verify, not a guarantee.

#### Environments

| Env | LLM | Weather | Blue-list snapshot | Checkpointer |
|---|---|---|---|---|
| test | stub | fixture | frozen JSON | memory or ephemeral PG |
| staging | cheap model | live + recorded | weekly | Postgres |
| prod | configured model | live | pinned + freshness alarm | Postgres, optional encryption |

Promotion is by image digest. Never by `latest`.

#### Observability

- **Logs** — JSON, carrying `request_id`, `mission_id`, `thread_id`, `node`,
  `calculator_version`, `operator_key_id`. Coordinates redacted at `info`.
- **Metrics** — plan latency, interrupt age, `llm_field_violations_total`,
  weather source counts, checkpoint put/get latency, retrieval hit/miss, and the
  five injection counters from `docs/injection-defense.md`.
- **Traces** — one span per graph node. Full prompts are never logged at `info`
  in production.

#### Security baseline

- Per-operator API keys; threads not enumerable across keys.
- Separate database roles: the ingest role writes `rag.*` only; the application
  role reads `rag.*` and cannot write it; neither can drop checkpoint tables.
- Non-root production image, hash-pinned dependencies, Dependabot on.
- No PDF upload path in the API. Ingest is offline, allowlisted, and hashed.

### Documentation obligations

- A new graph node, ingest source, or external dependency adds a STRIDE row to
  `docs/threat-model.md` before merge.
- A decision later code will assume gets an ADR. See `docs/adr/README.md`.

### Compose quickstart and golden path, local only

The `compose` CI job was removed: it failed too often on backend startup to be
a meaningful gate. The stack and its smoke remain and can be run locally:
`cp .env.example .env`, `DEMO_MODE=true docker compose up --build --detach --wait`,
then `python3 scripts/compose_smoke.py`. It checks `/ready`, the dashboard page,
the aircraft and payload catalog through the frontend proxy against
`frontend/src/lib/types.ts`, and the golden path (plan, pending read-back,
acknowledgement, signed read-back, still advisory on fixture weather). Nothing
in CI runs it.
