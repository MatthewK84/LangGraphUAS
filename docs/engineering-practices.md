# Engineering practices

This is flight-adjacent software that happens to contain a chat node. The bar is
set accordingly.

## Branching and release

- Trunk-based. `main` is always deployable. Short-lived `feat/` branches.
- Phase tags: `v0.2.0-honest-core`, `v0.3.0-closed-loop`, `v0.4.0-eval`.
- Conventional commits. `CHANGELOG.md` gets five lines every Friday.
- One PR is one mergeable slice with tests.

## CI gates that block merge

Already in place: `ruff`, `mypy --strict`, `pytest` with coverage, frontend
typecheck and Vitest, Prettier, and the calculator-version gate below.

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
