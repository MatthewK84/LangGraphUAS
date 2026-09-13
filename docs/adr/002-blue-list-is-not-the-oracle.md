# 002. The Blue List is a time-stamped snapshot, not a live authority

- **Status:** Accepted
- **Date:** 2026-09-13

## Context

Blue UAS clearance is three distinct things that are routinely collapsed into
one: the **Cleared List** (specific models and configurations checked for
current law, policy, and cyber), **Blue UAS Select** (a subset carrying an ATO
and further assessment), and the **Framework** (NDAA-compliant components —
flight controller, radio, camera, GCS, storage — not a complete aircraft).
Administration of the list moved to DCMA US-X, with the public portal at
`bluelist.dcma.mil`.

Three facts drive the decision. Clearance attaches to a **configuration**, not a
brand — swapping a critical component requires a new assessment. The list
**churns**: platforms are added and removed. And "NDAA-compliant" on a vendor
page is a statutory floor claim, not evidence of clearance.

A planner that decides operational eligibility by asking a model, or by scraping
a page on the request path, is wrong in a way that reads as authoritative.

## Decision

Blue-list status enters the system only as a **hashed, time-stamped snapshot**
fetched out-of-band:

```
blue_list_snapshots(snapshot_id, fetched_at, source_url, content_hash)

airframe_configs(
  id, manufacturer, model,
  configuration_name,          -- "X10D + Hadron", never "Skydio"
  blue_status,                 -- cleared | select | framework_only
                               -- | ndaa_claimed | unknown | delisted
  blue_list_item_id, listed_as_of, delisted_as_of,
  country_of_manufacture,
  critical_components[],       -- each with a framework_id or "not_on_framework"
  source_url)
```

The operational gate reads the snapshot table and nothing else:

```
operational requires
    blue_status in {cleared, select}
    and listed_as_of <= now
    and delisted_as_of is null
    and snapshot age <= BLUE_LIST_MAX_AGE (default 7 days)
```

A stale snapshot yields the blocker `BLUE_LIST_SNAPSHOT_STALE`. A configuration
that was cleared previously and is absent now is `delisted` and can never be
operational. A cleared airframe carrying a payload not covered by the same
listed configuration drops to advisory with
`PAYLOAD_NOT_ON_SAME_CLEARED_CONFIG`.

We are not a certifying authority, and the UI says so: *"This configuration
appears on the Blue List snapshot taken at T. Verify at bluelist.dcma.mil before
flight."*

## Rejected alternatives

- **Live fetch during planning** — rejected: an upstream outage or a tampered
  page would decide whether an aircraft flies.
- **Manufacturer-level status** — rejected: clearance is configuration-specific,
  so a brand-level flag is wrong by construction.
- **Retrieval over list pages as the gate** — rejected; see ADR-003. Embeddings
  do not know whether a row is current.

## Consequences

A refresh job (`backend/scripts/refresh_blue_list.py`) fetches, normalizes,
hashes, and diffs snapshots, and the operational suite fails if a seeded demo
airframe disappeared and the seed was not updated. We only ingest public
material; no assessor reports, nothing behind authentication.

## Enforcement

- `backend/tests/test_blue_operational_gate.py`: delisted fixture cannot be
  operational; stale snapshot produces the blocker; a retrieved chunk claiming
  clearance does not move the gate.
- Snapshot `content_hash` mismatch fails the gate rather than degrading quietly.
