---
title: "test: injection matrix (13 rows) + eval_trap corpus kind"
labels: [phase-2, security]
blocked_by: [11, 12, 13]
---
## Goal
Every injection technique we know about is a test that fails loudly, not a paragraph in a design document.

## Scope
`backend/tests/test_injection.py`, against `corpus/eval_trap/` which production ingest refuses by `kind`.

Rows (full table in `docs/injection-defense.md`): classic override, numeric override, invisible unicode, bidi override, fake citation, exfiltration markdown, delimiter spoof, mode escalation, Blue-list spoof, weather alert injection, telemetry string injection, tool-binding regression, node-order regression.

## Acceptance
- [ ] All thirteen rows present and green
- [ ] `kind='eval_trap'` cannot be ingested by the production path
- [ ] The file grows monotonically — rows are added as techniques appear, never pruned
- [ ] Contamination rate measured at 0, gated in CI (#51)

## Shipped

All thirteen rows are green in `backend/tests/test_injection.py`, plus six tests
covering the trap corpus itself. Three things differ from the scope above and are
worth reading before the next change here.

**Row 5 (fake citation) guards a shape we do not ship.** `resolve_citations()` in
`backend/suas/graph/seal.py` drops a `chunk_id` that was not retrieved, and is
tested — but nothing in production calls it, because `ReportService.generate`
returns a `str`. The model has no citation channel to abuse at all; `citations`
are built by `cite_limits` from retrieval hits. That is the stronger position, so
the test asserts it directly (`test_the_model_has_no_citation_channel_at_all`)
alongside the pure-function check. Adopting structured output means wiring
`resolve_citations` in the same commit, and the doc says so.

**The trap corpus gained a third document.** Row 3 claims "quarantined at
ingest", which the original test did not exercise — it called `screen_chunk`
directly. `corpus/eval_trap/invisible.txt` now runs the full ingest path. Its
only tripwire trigger is a zero-width-split imperative, deliberately: two earlier
drafts contained a second, plainly-visible imperative, and the ingest test passed
with normalisation switched off. The mutation check caught both. If this file
ever gains another imperative, the test stops testing the ordering.

**Matrix drift is now enforced.** `test_every_matrix_row_is_present` parses the
table in `docs/injection-defense.md` and compares it to the section markers in
the test file. Adding a row to either without the other fails CI. It found one
real drift on its first run (`Exfil markdown` vs `Exfiltration markdown`).

Not done here: the contamination rate is asserted per-test but not yet a measured
CI gate — that is #51.
