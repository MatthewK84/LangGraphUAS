---
title: "feat: quarantine-on-ingest + invisible-unicode normalization"
labels: [phase-2, security]
blocked_by: []
---
## Goal
Corpus text is untrusted input. Screen it at ingest, and make a suspicious document block flight rather than quietly disappear.

## Scope
- `screen_chunk()` in `backend/suas/rag/ingest.py`: NFKC normalize, strip zero-width and bidi-override characters, then match an imperative tripwire regex. See `docs/injection-defense.md`.
- Stripping runs **before** both the manifest hash comparison and the regex.
- Matches go to `rag.quarantine` with the matched pattern. **Never silently dropped** — a dropped datasheet paragraph is a missing limit.
- A quarantined chunk sets `citations_complete = false` for that configuration, which blocks `operational` until a human clears it.
- Strip HTML and markdown link syntax at ingest; URLs come from `rag.documents.source_url`. Cap chunk length.
- Manifest allowlist: reject any file not in `corpus/manifest.json` or from a host outside `ALLOWED_HOSTS`.

## Acceptance
- [ ] Zero-width-padded and bidi-reversed imperatives are caught
- [ ] Quarantine blocks operational for the affected configuration
- [ ] `injection_quarantine_total{pattern}` exported
- [ ] False-positive rate logged and reviewed — a tripwire silenced for noise is worse than none
- [ ] Unlisted file rejected; no PDF parser imported anywhere under `suas.api`
