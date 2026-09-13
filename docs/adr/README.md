# Architecture decision records

One ADR per decision that later code is allowed to assume. An ADR is not
documentation of what the code does — it is the record of what was decided, what
was rejected, and what would have to change for the decision to be revisited.

| # | Title | Status |
|---|---|---|
| [001](001-checkpointer-strategy.md) | Checkpointer strategy and thread identity | Accepted |
| [002](002-blue-list-is-not-the-oracle.md) | The Blue List is a time-stamped snapshot, not a live authority | Accepted |
| [003](003-rag-cannot-write-numbers.md) | Retrieval cannot write a number the calculator owns | Accepted |
| [004](004-node-order-and-empty-tool-binding.md) | Node order and empty tool binding are security controls | Accepted |
| [005](005-mode-downgrade-is-not-an-error.md) | A refused mode is a downgrade, not an error, and the gate fails closed | Accepted |

Rules:

- A PR that changes `calculations/`, the Blue-list gate, or `graph/seal.py`
  either matches an accepted ADR or ships a new one.
- Superseding is explicit: the old ADR gains a `Superseded by` line and keeps
  its file. Deleting an ADR deletes the reasoning.
- Copy `000-template.md` to start.
