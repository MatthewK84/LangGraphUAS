# 005. A refused mode is a downgrade, not an error, and the gate fails closed

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

`assessment_mode` lets a caller ask for a plan that carries operational weight.
Two questions had to be settled before the gate could ship.

First: what happens when the request cannot be granted? Either the API refuses
the request (`409`), or it runs the assessment and returns it marked advisory
with the reasons attached.

Second, and more consequential: what happens to a gate condition this codebase
cannot yet evaluate? Reference power figures carry no provenance, no citation
resolves against a datasheet, and no Blue List snapshot is stored. Three of the
six conditions in the gate are currently unverifiable.

## Decision

**A refused mode is a downgrade.** `POST /api/plan` returns `200` with
`assessment.mode = "advisory"` and a populated `assessment.blockers`. The
assessment ran; the caller is better served by the result plus the reasons than
by an error carrying neither. `409` would discard work the caller asked for and
would push clients toward retrying with a weaker request rather than reading why
the stronger one failed.

A malformed mode is still a `422`. "I asked for something you would not give me"
and "I sent a value that is not a mode" are different, and only the second is a
client error.

**The gate fails closed.** A condition that cannot be verified is a blocker.
Unverifiable and satisfied are different states, and only one of them is safe to
treat as met. Concretely this means **operational mode is currently
unreachable**: every plan returns advisory with at least
`POWER_PROVENANCE_UNAVAILABLE`, `CITATIONS_UNAVAILABLE`, and
`BLUE_LIST_SNAPSHOT_UNAVAILABLE`.

That is the correct state of affairs while the README still says the bundled
power figures are estimates. The blockers are the roadmap: each is retired by
the issue named beside it in `suas/calculations/gate.py`, and the day the last
one clears is the day this system can honestly claim a plan is good enough to
fly on.

## Rejected alternatives

- **`409` on an ungrantable mode** — rejected: throws away a completed
  assessment and teaches clients to downgrade their request instead of reading
  the blockers.
- **Enforcing only the conditions that are implemented** — rejected, and this is
  the one that mattered. It would produce operational plans today, and an
  operational claim resting on three unchecked conditions is exactly the
  dishonesty this project exists to remove.
- **Omitting unimplemented conditions until their data lands** — rejected: the
  gate would silently widen as each feature merged, with no single commit where
  anyone decided the standard had been met.

## Consequences

Operational mode has no passing path until [#38](https://github.com/MatthewK84/LangGraphUAS/issues/38) and the Blue-list snapshot work land, so
its acceptance test asserts the downgrade and its blockers rather than a grant.
Anyone reading the code will find a gate that always says no; the docstring in
`gate.py` and this record exist so that reads as deliberate rather than broken.

## Enforcement

- `backend/tests/test_modes.py::test_gate_fails_closed_on_unverifiable_conditions`
  pins the three standing blockers; it is expected to change when they become
  real checks.
- `test_operational_request_is_downgraded_not_refused` pins `200`-with-blockers
  over `409`.
- `mode`, `blockers`, `assessment_mode` and `requested_mode` are in
  `SEALED_FIELDS`, so nothing downstream of the calculator can write a mode.
