# Flight log fixtures

**`synthetic_hover_cruise.csv` is synthetic. It measures nothing.**

It was generated to exercise the parser and the selection rules — a climb whose
power must never reach the hover figure, a hover leg, a cruise leg, a descent,
and two unusable rows (a blank power reading and a non-numeric altitude) — and
for no other purpose. No airframe in `backend/suas/data/` is seeded from it, and
nothing in it should be cited as evidence of what any aircraft draws.

A real log replaces it by being uploaded, not by being copied in here:

```bash
curl -X POST "http://localhost:8000/api/logs?airframe_id=Freefly_Astro_Max&apply=true" \
  -H "Content-Type: text/csv" -H "X-API-Key: $SUAS_API_KEY" \
  --data-binary @your-flight.csv
```

## Columns the parser reads

`timestamp` and `alt_m` are required. Everything else is optional, and any
column not listed is ignored.

| Column | Unit | Notes |
| --- | --- | --- |
| `timestamp` | ISO 8601 | Required. Rows are sorted by it. |
| `alt_m` | m | Required. Climb rate is derived from it. |
| `power_w` | W | Used directly when present. |
| `voltage_v`, `current_a` | V, A | Multiplied when `power_w` is absent. A row with neither is rejected. |
| `tas_mps` | m/s | Preferred over ground speed. |
| `groundspeed_mps` | m/s | Used when airspeed is not logged. |
| `wind_mps` | m/s | Recorded, not currently used by the estimator. |
| `outside_temp_c` | C | Recorded, not currently used by the estimator. |
| `payload_id` | — | Truncated to 100 characters. |
| `phase` | enum | `hover`, `climb`, `cruise`, `descent`, `unknown`. Unrecognised values become `unknown`. |

## What a hover window means

A row counts toward hover power only if it is not labeled `climb`, `descent`,
or `cruise`, **and** its measured vertical rate is within ±0.5 m/s, **and** its
speed is at or below 1.5 m/s. The label alone is not enough: a row marked
`hover` while the aircraft was climbing is excluded on its measured rate, because
averaging climb power into a hover figure biases the energy budget toward GO.

Cruise is the mirror image: not labeled `climb`, `descent`, or `hover`, within
±1.0 m/s vertically, and at or above 3.0 m/s.

## `astro_max_hover_excerpt.csv` is real flight data, used only in tests

This file is a redacted, contiguous excerpt of a public PX4 Flight Review log
of a Freefly Astro Max. It is checked in so the ingest path can be tested
against real samples. **It is test-only.** It does not seed
`backend/suas/data/aircraft.json`, and applying it in tests must leave that
file unchanged. The payload on this flight is unknown: the public log does not
name one, and every `payload_id` cell in the excerpt is empty.

The source log is licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
(“CC-BY PX4” in the PX4 documentation). The excerpt is provided under the same
license, with attribution below.

Timestamps in the excerpt are boot-relative microseconds rendered as UTC
datetimes starting at `1970-01-01`. They preserve the original intervals so
climb rate stays valid; they are not a claim about the wall-clock flight time.

### Attribution

| Field | Value |
| --- | --- |
| Flight Review | https://review.px4.io/plot_app?log=054112f4-683e-49c2-8777-097f5fe35df2 |
| Source ULog | https://cdn.logs.px4.io/054112f4-683e-49c2-8777-097f5fe35df2.ulg |
| Uploader description | Astro Max flight |
| License | CC BY 4.0 (CC-BY PX4) |
| Retrieved | 2026-11-14 14:53:58 EST (America/New_York) |
| Source SHA-256 | `5bcef1faf0bcd0a72e5ac38a4b36150951635f80edd5d888c4ae942f50b50618` |
| Source size | 21,731,794 bytes |
| Excerpt SHA-256 | `4c6f179debc48ea0e5580ab5fe97ad2db4253946478f57a2e72df5177c6fd531` |
| Excerpt window | boot-relative 00:02:15.331489–00:03:01.332054 (93 rows, 64 hover samples) |

The excerpt was produced by `backend/scripts/ulog_to_csv.py`, which sums both
battery packs, uses barometric altitude plus EKF velocity (this log has no
`vehicle_local_position` because stealth logging was on), drops landed
samples, and does not copy pack serials or vehicle identifiers.
