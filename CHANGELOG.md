# Changelog

What reached `main` each week: one section per week, headed by its Monday
(dates in UTC), newest first, five lines at most. Every PR adds its line to the
current week's section, creating that section if the week has none. Each line
names the PRs or issues it records. `backend/tests/test_changelog.py` checks
the format.

## Week of 2026-10-19

- ub-mode is now a blocking CI gate: crapper and dryer at pinned commits, CRAP < 10 for every function in `backend/suas`, and no duplicate pair at 0.8 or above unless allowlisted with a reason (#131, #136, #137). The frontend lint now fails any function above cyclomatic complexity 10 (#152). A report-only `mutation` job lists mutator survivors for the backend modules a PR changes (#155).
- The seven functions at CRAP 10 or above got characterization tests first, then small refactors where needed: `acknowledge_plan`, `replan_mission`, `make_cite_limits_node`, `retrieve`, `ingest_document`, `lifespan`, `apply_flight_log`. Coverage now counts code run under greenlets (#132, #133, #134, #135). Hypothesis property tests pin the safety calculators' direction: worse conditions never turn NO_GO into GO (#153). Tests now kill every non-equivalent mutant left in the safety calculators and route helpers (#154).
- Dependabot bumps. Backend: sqlalchemy 2.0.54, psycopg 3.3.5, uvicorn 0.53.0, langchain-core 1.6.3, mypy 2.3.1. Frontend: @types/node 26.6.1, typescript-eslint 8.70.0, autoprefixer 10.6.1, postcss 8.5.28 (#121, #122, #123, #124, #125, #126, #127, #129, #130).
- PLAN-90 gained a living status block measured from `main` (#120), and `CHANGELOG.md` started, with a test for its format (#80). Demo mode: `DEMO_MODE=true docker compose up` runs with no keys on fixture weather, every plan advisory, and a CI `compose` job runs the README quickstart (#157), then walks plan, ack and read-back through the frontend and fails on a catalog contract break (#158). Two workers seeding a fresh database no longer race to INSERT and kill the container: seeding takes a Postgres advisory lock (#160).
- Security gates: every action pinned to a commit with a read-only token and a blocking `workflow-lint` job (actionlint, zizmor) (#139); ruff's bandit (`S`) rules on, and a test that forbids hidden bidi characters in source (#149); a blocking gitleaks scan of the full history, and a weekly report-only `pip-audit` and `npm audit` (#88). `/ready` now answers 503 when migrations are pending or the checkpoint store fails a read; CI proves both directions against Postgres (#156). The `docker` job scans both images with trivy (report-only), and every `v*` tag gets CycloneDX SBOMs from `sbom.yml` (#89).
