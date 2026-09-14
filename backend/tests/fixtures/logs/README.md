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

A row counts toward hover power only if it is not labelled `climb`, `descent`,
or `cruise`, **and** its measured vertical rate is within ±0.5 m/s, **and** its
speed is at or below 1.5 m/s. The label alone is not enough: a row marked
`hover` while the aircraft was climbing is excluded on its measured rate, because
averaging climb power into a hover figure biases the energy budget toward GO.

Cruise is the mirror image: not labelled `climb`, `descent`, or `hover`, within
±1.0 m/s vertically, and at or above 3.0 m/s.
