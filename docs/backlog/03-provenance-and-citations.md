---
title: "data: provenance fields on every number + CITATIONS.md"
labels: [phase-1, data]
blocked_by: [2]
---
## Goal
No bare numbers in `backend/suas/data/`. Every performance field records where it came from, so the operational gate has something real to check.

## Shape
```json
"hover_power_w": {
  "value": 420.0,
  "unit": "W",
  "source": "datasheet | estimate | flight_log",
  "source_url": "https://...",
  "retrieved_at": "2026-09-13",
  "confidence": "low | medium | high",
  "notes": "..."
}
```

## Scope
- Migrate bundled aircraft and payload JSON to the provenance shape
- `backend/suas/data/CITATIONS.md` listing every field, its value, and the URL used
- CI linter `backend/tests/test_reference_data.py`: fails when a required performance field lacks `source`, or `source=datasheet` lacks `source_url`
- Boot-time seed reconciliation keeps working against the new shape

## Acceptance
- [ ] Every field in the default pack has provenance
- [ ] CI fails on a bare number
- [ ] `CITATIONS.md` URL count matches the JSON
- [ ] `source=estimate` is permitted, records why, and blocks `operational`
