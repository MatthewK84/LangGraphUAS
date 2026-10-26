# Threat model (STRIDE)

Reviewed at the end of each phase, and whenever a graph node, tool, or ingest
path is added. A new node without a STRIDE row does not merge.

## Trust boundaries

```
[operator browser]                     untrusted
        | HTTPS
[Next.js BFF]                          semi-trusted (no keys in the client)
        |
[FastAPI]                              trusted compute
        +-- calculations/              trusted oracle
        +-- missions table             trusted record
        +-- LangGraph + checkpointer   trusted cursor, untrusted state contents
        +-- weather HTTP               untrusted
        +-- LLM HTTP                   untrusted output
        +-- rag.chunks                 untrusted text, trusted filters
[corpus ingest (CI or workstation)]    trusted only via manifest + sha256
[Blue List HTTP]                       untrusted until snapshotted and hashed
```

Assets: the sealed assessment, coordinates, flight logs, API keys, the session
secret, checkpoint
blobs, Blue-list snapshot integrity, operator identity.

The AI-specific point that governs the rest: retrieved documents and model
output share a context window with the system prompt. Stored text is not trusted
text.

## Spoofing

| Threat | Mitigation | Test |
|---|---|---|
| Stolen key resumes another operator's thread | Keys scoped to `mission_threads.operator_key_id` (#81); a mismatch answers exactly as an unknown thread (404, or `found: false` on `GET`) | `tests/test_operator_keys.py`: cross-key read, ack, replan and plan-onto are refused as unknown |
| One browser resumes another browser's thread through the shared proxy | Each browser gets a random 256-bit session id in an `HttpOnly`, `SameSite=Strict` cookie; the proxy signs it as `session.<id>.<HMAC-SHA256(SUAS_SESSION_KEY_SECRET, id)>` and the backend scopes the mission to it (#82). Default Compose uses a public, demo-only `SESSION_KEY_SECRET` that anyone can forge sessions with; the backend warns at startup while it is set | `tests/test_session_keys.py`: two sessions cannot read, ack or replan each other's threads and get the unknown-thread answer; forged, unsigned and wrong-secret keys get 401. `scripts/compose_smoke.py`: a second cookie jar cannot read or sign the first one's thread |
| A rotated-out key, or an old session secret, still acts; or rotation strands a plan waiting for a signature | The owner is the operator id, not the key, and the ack is bound to `inputs_hash`; a restart with the new key refuses the old one with 401 (#83). The opt-in `SUAS_RETIRED_API_KEYS` overlap accepts an old direct key only until its expiry (capped by `SUAS_RETIRED_KEY_MAX_GRACE_S`, default one hour) and only from the client IP that last used it, stored by key hash; `X-Forwarded-For` counts only from `SUAS_TRUSTED_PROXIES`. A thief behind the same NAT inside the window is not stopped; session keys have no overlap | `tests/test_key_rotation.py`: for a named key, the `default` key and the session secret, the old key gets 401, the open interrupt is signed with the new key, and a stale hash is still 409. `tests/test_retired_keys.py`: another IP, an expired window and a spoofed `X-Forwarded-For` get the unknown-key 401 |
| A client-chosen thread id poses as another operator's replan child: plan `x:1` before someone plans `x`, then read the replan the server runs on `x:1` | New ids must match `[A-Za-z0-9_-]{1,128}` (422 otherwise, checked before any lookup, so the answer does not depend on what exists); `:` ids are only handed out by replan. A `:` id stored before the rule stays its planner's, and replan allocation and purge skip any child id that has a row of its own | `tests/test_thread_ids.py`: the squat is 422 and identical whether or not the parent exists; a replan skips a stored child id and purge leaves it; legacy ids still resolve on `GET`, ack and replan |
| Cross-site request forges a plan or an ack from an operator's browser | `SameSite=Strict` cookie, and the proxy refuses any `POST` whose `Origin` is missing or not its own host with 403 before calling the backend | `frontend/src/lib/server/session.test.ts`: cross-origin and Origin-less POSTs return 403 without a backend call |
| Forged "live" weather | `source` is tagged by our client from transport outcome, never read from the response body | A fake body cannot set `source=live` when the request failed |
| Demo mode left on in a deployment (#97) | `SUAS_DEMO_MODE` defaults off in Settings, Compose and `.env.example`. Demo weather is tagged `fixture`, never operational grade, so the gate blocks operational (`WEATHER_NOT_LIVE`) and every plan says advisory. The backend logs a `DEMO MODE` warning at startup | `tests/test_demo_mode.py`: an operational request on fixture weather comes back advisory; `scripts/compose_smoke.py` checks the same end to end when run locally |
| Forged Blue List page | Snapshot plus `content_hash`; the gate reads the snapshot, never a request-path scrape | Tampered hash fails the gate |
| Model claiming to be the calculator | Seal drop-list | `test_seal.py` |

## Tampering

| Threat | Mitigation | Test |
|---|---|---|
| Poisoned datasheet PDF | Manifest allowlist, sha256, no user upload in v1 | Unlisted file rejected |
| Prompt injection in a chunk | Seal; nonce-fenced evidence; quarantine at ingest | Trap corpus, contamination rate 0 |
| Checkpoint blob rewritten | Ingest role cannot write application tables; strict msgpack; optional encrypted serializer | Unknown type fails closed |
| Forged reading planted in the shared weather cache (#85) | The cache is a table in the application database, so writing it needs the same access as rewriting missions; a row is re-validated as a `WeatherReading` on load (a bad row is a miss, not an exception), only `live` readings are stored, and freshness is judged from the reading's own `fetched_at` against the TTL | `tests/test_shared_weather_cache.py`: degraded answers are never cached; an aged reading refetches as `live` or, on failure, comes back `cached_stale` |
| Mass edited after ack without recalculation | Ack bound to `inputs_hash` and `calculator_version` | Edit invalidates the ack |
| Hybrid search without a configuration filter | Same `WHERE` on both fusion legs | A query for the Astro cannot return ANAFI chunks |
| Compromised CI-only analysis tool (crapper, dryer) | Installed from commit-pinned refs into a separate venv; the `ub-mode` job reads no secrets, has a read-only token, and is not part of any image | `ci.yml`: the job has `permissions: contents: read` and no `secrets.` reference |
| Compromised test library (Hypothesis) | An exact `==` pin in the dev extra, which Dependabot bumps after a 7-day cooldown; it runs only in test jobs, which have the read-only token and no secrets, and the runtime images install no dev extra | `pyproject.toml` pins `hypothesis==`; `ci.yml` sets `permissions: contents: read` at the top |
| Compromised mutation tool (mutator) | Installed with crapper from commit-pinned refs into its own venv, with tree-sitter pinned; the `mutation` job reads no secrets, has a read-only token, rewrites only its own checkout, and is not part of any image | `ci.yml`: the job has `permissions: contents: read`, `persist-credentials: false`, and no `secrets.` reference |
| Compromised or retagged GitHub Action, or a workflow lint tool (actionlint, zizmor) | Every `uses:` pinned to a full commit SHA, with Dependabot proposing new SHAs after a 7-day cooldown; the lint tools are pinned PyPI releases in their own venv, run `--offline`, and get the workflow-wide read-only token and no secrets | `workflow-lint` job: zizmor fails on any unpinned `uses:`; `ci.yml` sets `permissions: contents: read` at the top |
| Compromised secret or audit tool (gitleaks, pip-audit) | gitleaks is a pinned release whose SHA-256 is checked before it runs; pip-audit is a pinned PyPI release in its own venv; both jobs get the read-only token and no secrets, and neither is part of any image | `ci.yml` `secrets-scan` runs `sha256sum --check`; `audit.yml` sets `permissions: contents: read` |
| Compromised image scanner or SBOM tool (trivy) | trivy is one pinned release (`scripts/install-trivy.sh`) whose SHA-256 is checked before it runs, not a third-party action; the CI scan gets the read-only token; in `sbom.yml` only the tag-gated `attach` job can write, and it only uploads the SBOM files | `install-trivy.sh` runs `sha256sum --check --strict`; `tests/test_supply_chain_workflows.py` fails if any other job gets write access |

## Repudiation

| Threat | Mitigation | Test |
|---|---|---|
| "I never confirmed that go" | `ack_at`, `ack_actor`, assessment hash, calculator version on the mission row | Row exists before report runs |
| Model blamed for a watt figure | Watts exist only in calculator-written `assessment_json` | Audit query |
| Silent replan | Child `thread_id`; parent brief immutable | Parent JSON unchanged after replan |

Logs carry `request_id`, `mission_id`, `thread_id`, `node`, `operator_key_id`.
There are no debug endpoints that skip the ack.

## Information disclosure

| Threat | Mitigation | Test |
|---|---|---|
| Thread enumeration | UUIDs; no unauthenticated list endpoint; another operator's thread reads as unknown (#81) | `tests/test_operator_keys.py`: another key's thread and a never-planned id get the same answer |
| Credential committed to the repository | gitleaks over the full history on every pull request | A planted AWS key pair fails `secrets-scan` (gitleaks exit 1) |
| Coordinates in logs or checkpoints | Redacted at `info`; minimal state; encryption option | Log fixture carries no raw coordinates |
| Corpus exfiltration via the brief | Top-4 spans, `field_path` filtered | A brief cannot quote another airframe |
| Open metrics endpoint | Bound to the internal network | Compose test |
| Provider keys in the browser bundle | Server-only proxy; `BACKEND_*` read only under `lib/server/`, imported only by API route handlers. The session secret and derived keys stay on the Next server; the browser holds only its own session id | `session.test.ts`: source checks, and no response carries the secret or MAC; `test_session_keys.py`: no backend response echoes the secret or MAC |

## Denial of service

| Threat | Mitigation | Test |
|---|---|---|
| Mass plan requests with model and embedding calls | `?brief=false` for load runs, per-key rate limit, one ceiling across workers when `SUAS_RATE_LIMIT_SHARED` (#84), retrieval only inside `cite_limits` | 100 concurrent advisory plans |
| Weather hang | 2-3s timeout, advisory fallback | Fake-hang test |
| Unbounded tool loops | No tools bound on `report` (ADR-004) | Bound-tool assertion |
| Checkpoint table growth | `delete_thread` prune job | Retention job test |
| Large PDF parsed on the request path | Ingest is offline; the API has no PDF parser | No parser import in `suas.api` |

Token spend is denial of service. The report node runs under a hard token cap
and wall-clock timeout.

## Elevation of privilege

| Threat | Mitigation | Test |
|---|---|---|
| Advisory flipped to operational by the model | Mode computed in `validate` from weather, snapshot, and power source | Model JSON ignored |
| Retrieval node used as a file reader | Retrieval reads `rag.chunks` via SQL only; no filesystem parameter | No path parameter exists |
| HITL skipped by an internal header | No internal bypass in production | Grep and test |
| Ingest role writing `missions` | Separate database roles | Role test |
| Delisted airframe flown as cleared on the strength of a retrieved blog post | Gate reads `blue_list_snapshots`, not embeddings | Delisted fixture |

## AI-specific extensions

- **Indirect prompt injection via retrieval** is Tampering plus Elevation. The
  mitigation is the seal and the node ordering, not a cleverer system prompt.
- **Non-deterministic agent paths**: two runs produce two briefs and one
  decision. Tests assert assessment equality, never brief equality.
- **Supply chain**: pinned embedding model, hash-pinned dependencies, pinned
  image digests. A poisoned embedding model is spoofing of the retriever.

## Review cadence

| When | Walk through |
|---|---|
| Day 2 | This document plus the data-flow diagram |
| End of Phase 1 | HITL and the seal |
| End of Phase 2 | Replan, checkpoints, the two-worker lock |
| End of Phase 3 | Eval corpus isolation — `eval_trap` never reaches production |
| Any new node or ingest source | One STRIDE row before merge |
