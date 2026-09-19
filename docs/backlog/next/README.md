# The next fifty

Filed in the order they should be worked. Each is one PR.

These start after the seventeen in `docs/backlog/` — seal, HITL, replan, the
weather contract, the injection matrix, the retrieval gates and the offline eval
harness are on main and are not reopened here.

| Wave | Issues | Gate before moving on |
| --- | --- | --- |
| 1. Make the numbers defensible | 1–10 | Before any more graph nodes |
| 2. Tenancy and the trust boundary | 11–20 | Before inviting anyone onto a shared deploy |
| 3. Showcase UI (advisory, unmistakable) | 21–30 | Part of the showcase artifact |
| 4. Eval a reviewer can reproduce | 31–40 | Part of the showcase artifact |
| 5. Production quality | 41–50 | Only if this runs longer than a demo weekend |

The product this supports is an **advisory energy planner with a sealed
calculator**, not an operational mission AI. Wave 1 exists to keep that sentence
true.

## Three of the fifty were already green and are not filed

Skipped after checking main, rather than filed and immediately closed:

- **5, resolve or mark the four datasheet conflicts.**
  `backend/tests/test_datasheet_conflicts.py` names all four with a kept value, a
  rejected value and a reason, plus the pack-procedure limit from #39.
- **34, leaderboard columns that are not vapor.** `eval/LEADERBOARD.md` already
  names `hashing-v1-384` as the CI embedder and carries a "What these numbers
  are not" section.
- **37, offline eval in CI on a slice.** The mission pack already runs in CI on
  every PR across three interpreters, over all 30 fixtures and both controls
  rather than a five-fixture slice, with no network.

**31 was narrowed.** The regeneration script and the single-calculator assertion
already exist; what is missing is the link between them, so the issue is now
just that: a `CALCULATOR_VERSION` bump must fail CI while the committed pack
carries the old one.

Numbering follows the original list, so gaps at 5, 34 and 37 are deliberate.
